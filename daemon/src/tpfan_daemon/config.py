from __future__ import annotations
from dataclasses import dataclass, field, replace
from pathlib import Path
import os
import re
import tomllib
import logging

log = logging.getLogger(__name__)

VALID_LEVELS = {"0", "1", "2", "3", "4", "5", "6", "7", "auto", "disengaged"}

_PRESET_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,64}$")


def validate_preset_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("preset name must be a string")
    if not _PRESET_NAME_RE.match(name):
        raise ValueError(f"invalid preset name: {name!r}")
    return name


@dataclass(frozen=True)
class CurveCfg:
    sensors: tuple[str, ...]
    points: tuple[tuple[float, int], ...]

    @staticmethod
    def from_default() -> "CurveCfg":
        return CurveCfg(
            sensors=("CPU", "GPU", "NVMe"),
            points=((40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)),
        )

    def _wrap_in_config(self, **overrides) -> "Config":
        return replace(DEFAULT, curve=self, **overrides)


@dataclass(frozen=True)
class Config:
    mode: str = "curve"
    manual_level: str = "3"
    failsafe_temp: float = 95.0
    curve: CurveCfg = field(default_factory=CurveCfg.from_default)
    profiles: dict[str, CurveCfg] = field(default_factory=dict)
    user_presets: dict[str, CurveCfg] = field(default_factory=dict)


DEFAULT = Config(
    profiles={
        "quiet":       CurveCfg(("CPU", "GPU", "NVMe"), ((50.0, 0), (65.0, 1), (75.0, 3), (85.0, 7))),
        "balanced":    CurveCfg(("CPU", "GPU", "NVMe"), ((40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7))),
        "performance": CurveCfg(("CPU", "GPU", "NVMe"), ((35.0, 1), (50.0, 3), (65.0, 5), (75.0, 7))),
    }
)


def _validate_points(points: list[list[float]]) -> tuple[tuple[float, int], ...]:
    if len(points) < 2:
        raise ValueError("curve must have at least 2 points")
    out: list[tuple[float, int]] = []
    prev_t: float | None = None
    for pt in points:
        if len(pt) != 2:
            raise ValueError(f"bad point: {pt}")
        t, lvl = float(pt[0]), int(pt[1])
        if not (20.0 <= t <= 110.0):
            raise ValueError(f"temperature out of range: {t}")
        if not (0 <= lvl <= 7):
            raise ValueError(f"level out of range: {lvl}")
        if prev_t is not None and t <= prev_t:
            raise ValueError("temperatures must be strictly monotonic")
        prev_t = t
        out.append((t, lvl))
    return tuple(out)


def _validate_curve(d: dict) -> CurveCfg:
    sensors = tuple(d.get("sensors", ("CPU",)))
    points = _validate_points(d.get("points", []))
    return CurveCfg(sensors=sensors, points=points)


def load(path: Path) -> Config:
    if not path.exists():
        return DEFAULT
    with path.open("rb") as f:
        raw = tomllib.load(f)
    mode = raw.get("mode", DEFAULT.mode)
    manual_level = str(raw.get("manual_level", DEFAULT.manual_level))
    if manual_level not in VALID_LEVELS:
        raise ValueError(f"invalid manual_level: {manual_level}")
    failsafe_temp = float(raw.get("failsafe_temp", DEFAULT.failsafe_temp))
    curve = _validate_curve(raw["curve"]) if "curve" in raw else DEFAULT.curve
    profiles = {k: _validate_curve(v) for k, v in raw.get("profiles", {}).items()}
    user_presets = {
        validate_preset_name(k): _validate_curve(v)
        for k, v in raw.get("user_presets", {}).items()
    }
    return Config(mode=mode, manual_level=manual_level,
                  failsafe_temp=failsafe_temp, curve=curve,
                  profiles=profiles, user_presets=user_presets)


def _serialize(cfg: Config) -> str:
    def _curve(c: CurveCfg) -> str:
        s = "sensors = [" + ", ".join(f'"{x}"' for x in c.sensors) + "]\n"
        pts = ", ".join(f"[{t}, {l}]" for t, l in c.points)
        s += f"points = [{pts}]\n"
        return s

    out = []
    out.append(f'mode = "{cfg.mode}"')
    out.append(f'manual_level = "{cfg.manual_level}"')
    out.append(f"failsafe_temp = {cfg.failsafe_temp}")
    out.append("")
    out.append("[curve]")
    out.append(_curve(cfg.curve))
    for name, c in cfg.profiles.items():
        out.append(f"[profiles.{name}]")
        out.append(_curve(c))
    for name, c in cfg.user_presets.items():
        # TOML-Quoted-Keys, damit Leerzeichen erlaubt sind
        out.append(f'[user_presets."{name}"]')
        out.append(_curve(c))
    return "\n".join(out)


def save(path: Path, cfg: Config) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(_serialize(cfg))
    os.replace(tmp, path)
