from __future__ import annotations
from dataclasses import dataclass
from tpfan_daemon.control.loop import ControlLoop
from tpfan_daemon.config import Config, CurveCfg, DEFAULT


class FakeSensors:
    def __init__(self, temps): self.temps = temps
    def read_all(self): return dict(self.temps)


class FakeFan:
    def __init__(self):
        self.level = "auto"
        self.history: list[str] = []
        self.fail_set: bool = False

    def read(self):
        @dataclass
        class S:
            speed_rpm: int = 2000
            level: str = "auto"
            enabled: bool = True
        s = S()
        s.level = self.level
        return s

    def set_level(self, lvl):
        if self.fail_set:
            raise OSError("nope")
        self.level = lvl
        self.history.append(lvl)


def _loop(temps, cfg=DEFAULT, fan=None):
    fan = fan or FakeFan()
    return ControlLoop(sensors=FakeSensors(temps), fan=fan, config=cfg), fan


def test_auto_mode_sets_auto():
    loop, fan = _loop({"CPU": 50.0}, cfg=Config(mode="auto"))
    loop.tick()
    assert fan.level == "auto"


def test_manual_mode_sets_level():
    cfg = Config(mode="manual", manual_level="5")
    loop, fan = _loop({"CPU": 50.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "5"


def test_curve_mode_uses_max_of_sensors():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU","GPU"), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 40.0, "GPU": 80.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "7"


def test_failsafe_disengages_above_threshold():
    cfg = Config(mode="curve", failsafe_temp=70.0,
                 curve=CurveCfg(("CPU",), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 75.0}, cfg=cfg)
    tr = loop.tick()
    assert fan.level == "disengaged"
    assert tr.emergency is not None
    assert tr.emergency[1] == "CPU"


def test_curve_unchanged_level_does_not_rewrite():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU",), ((40.0,0),(80.0,7))))
    loop, fan = _loop({"CPU": 80.0}, cfg=cfg)
    loop.tick()
    n = len(fan.history)
    loop.tick()
    assert len(fan.history) == n


def test_fan_write_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    fan.fail_set = True
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.fallback_to_auto is True


def test_profile_mode_uses_profile_curve():
    cfg = Config(mode="profile:quiet", profiles=DEFAULT.profiles)
    loop, fan = _loop({"CPU": 85.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "7"
