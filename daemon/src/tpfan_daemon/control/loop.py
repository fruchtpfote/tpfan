from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol
import logging
import time

from .curve import interpolate
from ..config import Config, CurveCfg

log = logging.getLogger(__name__)

BOOT_GRACE_SECONDS = 30.0


class SensorsLike(Protocol):
    def read_for_control(self, required: Iterable[str] = ()) -> dict[str, float]: ...


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
    boot_grace_seconds: float = BOOT_GRACE_SECONDS
    clock: Callable[[], float] = time.monotonic
    _last_level: str = "auto"
    _last_curve_level: int = 0
    _started_at: float = field(init=False)

    def __post_init__(self) -> None:
        self._started_at = self.clock()

    @property
    def last_level(self) -> str:
        return self._last_level

    def boot_grace_remaining(self) -> float:
        return max(0.0, self.boot_grace_seconds - (self.clock() - self._started_at))

    def set_config(self, cfg: Config) -> None:
        old = self.config
        if old.mode != cfg.mode or old.curve != cfg.curve:
            self._last_curve_level = 0
        self.config = cfg

    def _active_curve(self) -> CurveCfg | None:
        m = self.config.mode
        if m == "curve":
            return self.config.curve
        if m.startswith("profile:"):
            name = m.split(":", 1)[1]
            return self.config.profiles.get(name)
        return None

    def _try_set_auto(self) -> None:
        try:
            self.fan.set_level("auto")
            self._last_level = "auto"
        except OSError:
            pass

    def tick(self) -> TickResult:
        curve = self._active_curve()
        try:
            # Die Sensoren der aktiven Kurve müssen frisch sein, der Rest darf
            # aus dem Cache kommen — siehe Sensors.read_for_control().
            temps = self.sensors.read_for_control(curve.sensors if curve else ())
        except OSError as e:
            log.error("sensor read failed: %s — falling back to auto", e)
            self._try_set_auto()
            return TickResult({}, 0, "auto", "auto", fallback_to_auto=True)

        try:
            st = self.fan.read()
        except OSError as e:
            log.error("fan read failed: %s — falling back to auto", e)
            self._try_set_auto()
            return TickResult(temps, 0, "auto", "auto", fallback_to_auto=True)

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
                    self._last_level = target
                except OSError as e:
                    log.error("emergency fan write failed: %s — falling back to auto", e)
                    fallback = True
                    try:
                        self.fan.set_level("auto")
                        self._last_level = "auto"
                        target = "auto"
                    except OSError:
                        pass
                return TickResult(temps, st.speed_rpm, current, target,
                                  emergency=emergency, fallback_to_auto=fallback)
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

        if self.clock() - self._started_at < self.boot_grace_seconds:
            target = "auto"
            try:
                if target != current:
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
