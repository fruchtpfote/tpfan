from __future__ import annotations
from dataclasses import replace
from pathlib import Path
from typing import Any
import logging

from .config import CurveCfg, DEFAULT, load, save, _validate_points, VALID_LEVELS, validate_preset_name
from .control.loop import ControlLoop

log = logging.getLogger(__name__)


class Daemon:
    def __init__(self, config_path: Path, sensors, fan):
        self.config_path = config_path
        self.sensors = sensors
        self.fan = fan
        cfg = load(config_path) if config_path.exists() else DEFAULT
        if not config_path.exists():
            save(config_path, cfg)
        self.loop = ControlLoop(sensors=sensors, fan=fan, config=cfg)

    def _save(self) -> None:
        save(self.config_path, self.loop.config)

    def handle(self, cmd: str, *args: Any) -> None:
        if cmd == "set_mode":
            mode = args[0]
            if not (mode in ("auto", "curve", "manual") or mode.startswith("profile:")):
                raise ValueError(f"unknown mode: {mode}")
            if mode.startswith("profile:") and mode.split(":", 1)[1] not in self.loop.config.profiles:
                raise ValueError(f"unknown profile: {mode}")
            self.loop.set_config(replace(self.loop.config, mode=mode))
            self._save()
        elif cmd == "set_curve":
            points, sensors_ = args
            if not sensors_:
                raise ValueError("set_curve requires at least one sensor")
            pts = _validate_points([list(p) for p in points])
            known = set(self.sensors.read_all().keys())
            for s in sensors_:
                if s not in known:
                    raise ValueError(f"unknown sensor: {s}")
            curve = CurveCfg(sensors=tuple(sensors_), points=pts)
            self.loop.set_config(replace(self.loop.config, curve=curve))
            self._save()
        elif cmd == "set_manual_level":
            lvl = args[0]
            if self.loop.config.mode != "manual":
                raise ValueError("SetManualLevel requires mode=manual")
            if lvl not in VALID_LEVELS:
                raise ValueError(f"invalid level: {lvl}")
            self.loop.set_config(replace(self.loop.config, manual_level=lvl))
            self._save()
        elif cmd == "set_failsafe_temp":
            t = float(args[0])
            if not (40.0 <= t <= 110.0):
                raise ValueError("failsafe out of range")
            self.loop.set_config(replace(self.loop.config, failsafe_temp=t))
            self._save()
        elif cmd == "reload_config":
            self.loop.set_config(load(self.config_path))
        elif cmd == "save_user_preset":
            name, points, sensors_ = args
            validate_preset_name(name)
            if not sensors_:
                raise ValueError("save_user_preset requires at least one sensor")
            pts = _validate_points([list(p) for p in points])
            known = set(self.sensors.read_all().keys())
            for s in sensors_:
                if s not in known:
                    raise ValueError(f"unknown sensor: {s}")
            new_presets = {**self.loop.config.user_presets,
                           name: CurveCfg(sensors=tuple(sensors_), points=pts)}
            self.loop.set_config(replace(self.loop.config, user_presets=new_presets))
            self._save()
        elif cmd == "delete_user_preset":
            name = args[0]
            if name not in self.loop.config.user_presets:
                raise ValueError(f"unknown preset: {name}")
            new_presets = {k: v for k, v in self.loop.config.user_presets.items() if k != name}
            self.loop.set_config(replace(self.loop.config, user_presets=new_presets))
            self._save()
        else:
            raise ValueError(f"unknown command: {cmd}")
