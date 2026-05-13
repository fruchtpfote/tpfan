from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol
import logging

from .curve import interpolate
from ..config import Config, CurveCfg

log = logging.getLogger(__name__)


class SensorsLike(Protocol):
    def read_all(self) -> dict[str, float]: ...


class FanLike(Protocol):
    def read(self): ...
    def set_level(self, level: str) -> None: ...


@dataclass
class TickResult:
    temps: dict[str, float]
    fan_speed: int
    current_level: str
    target_level: str
    emergency: tuple[float, str] | None = None
    fallback_to_auto: bool = False


@dataclass
class ControlLoop:
    sensors: SensorsLike
    fan: FanLike
    config: Config
    _last_level: str = "auto"
    _last_curve_level: int = 0

    def set_config(self, cfg: Config) -> None:
        self.config = cfg

    def _active_curve(self) -> CurveCfg | None:
        m = self.config.mode
        if m == "curve":
            return self.config.curve
        if m.startswith("profile:"):
            name = m.split(":", 1)[1]
            return self.config.profiles.get(name)
        return None

    def tick(self) -> TickResult:
        temps = self.sensors.read_all()
        st = self.fan.read()
        current = st.level

        target: str
        emergency: tuple[float, str] | None = None
        fallback = False

        if temps:
            hot = max(temps.items(), key=lambda kv: kv[1])
            if hot[1] >= self.config.failsafe_temp:
                target = "disengaged"
                emergency = (hot[1], hot[0])
                try:
                    self.fan.set_level(target)
                except OSError as e:
                    log.error("emergency fan write failed: %s", e)
                self._last_level = target
                return TickResult(temps, st.speed_rpm, current, target, emergency)
        else:
            target = "auto"
            try:
                if current != target:
                    self.fan.set_level(target)
                self._last_level = target
            except OSError:
                fallback = True
            return TickResult(temps, st.speed_rpm, current, target,
                              fallback_to_auto=fallback)

        m = self.config.mode
        if m == "auto":
            target = "auto"
        elif m == "manual":
            target = self.config.manual_level
        else:
            curve = self._active_curve()
            if curve is None:
                target = "auto"
            else:
                values = [temps[s] for s in curve.sensors if s in temps]
                if not values:
                    target = "auto"
                else:
                    t = max(values)
                    prev = self._last_curve_level
                    lvl = interpolate(curve.points, t, prev)
                    self._last_curve_level = lvl
                    target = str(lvl)

        try:
            if target != current:
                self.fan.set_level(target)
            self._last_level = target
        except OSError as e:
            log.error("fan write failed permanently: %s — falling back to auto", e)
            try:
                self.fan.set_level("auto")
                self._last_level = "auto"
            except OSError:
                pass
            fallback = True

        return TickResult(temps, st.speed_rpm, current, target,
                          emergency=emergency, fallback_to_auto=fallback)
