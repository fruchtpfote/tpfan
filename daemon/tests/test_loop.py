from __future__ import annotations
from dataclasses import dataclass
from tpfan_daemon.control.loop import ControlLoop
from tpfan_daemon.config import Config, CurveCfg, DEFAULT


class FakeSensors:
    def __init__(self, temps):
        self.temps = temps
        self.fail_read: bool = False
        self.required: tuple[str, ...] = ()
    def read_all(self):
        if self.fail_read:
            raise OSError("sensors unavailable")
        return dict(self.temps)
    def read_for_control(self, required=()):
        self.required = tuple(required)
        return self.read_all()


class FakeFan:
    def __init__(self):
        self.level = "auto"
        self.history: list[str] = []
        self.fail_set: bool = False
        self.fail_read: bool = False
        self.fail_only_non_auto: bool = False

    def read(self):
        if self.fail_read:
            raise OSError("fan read failed")
        @dataclass
        class S:
            speed_rpm: int = 2000
            level: str = "auto"
            enabled: bool = True
        s = S()
        s.level = self.level
        return s

    def set_level(self, lvl):
        if self.fail_set and not (self.fail_only_non_auto and lvl == "auto"):
            raise OSError("nope")
        self.level = lvl
        self.history.append(lvl)


def _loop(temps, cfg=DEFAULT, fan=None):
    fan = fan or FakeFan()
    return ControlLoop(sensors=FakeSensors(temps), fan=fan, config=cfg,
                       boot_grace_seconds=0.0), fan


def test_auto_mode_sets_auto():
    loop, fan = _loop({"CPU": 50.0}, cfg=Config(mode="auto"))
    loop.tick()
    assert fan.level == "auto"


def test_manual_mode_sets_level():
    cfg = Config(mode="manual", manual_level="5")
    loop, fan = _loop({"CPU": 50.0}, cfg=cfg)
    loop.tick()
    assert fan.level == "5"


def _clock(value: list[float]):
    return lambda: value[0]


def test_boot_grace_forces_auto_during_grace():
    cfg = Config(mode="curve",
                 curve=CurveCfg(("CPU",), ((45.0, 0), (60.0, 1), (70.0, 2), (80.0, 7))))
    fan = FakeFan()
    t = [0.0]
    loop = ControlLoop(sensors=FakeSensors({"CPU": 70.0}), fan=fan, config=cfg,
                       clock=_clock(t))
    tr = loop.tick()
    assert tr.target_level == "auto"
    assert fan.level == "auto"


def test_boot_grace_releases_after_window():
    cfg = Config(mode="curve",
                 curve=CurveCfg(("CPU",), ((45.0, 0), (60.0, 1), (70.0, 2), (80.0, 7))))
    fan = FakeFan()
    t = [0.0]
    loop = ControlLoop(sensors=FakeSensors({"CPU": 70.0}), fan=fan, config=cfg,
                       clock=_clock(t))
    t[0] = 31.0
    tr = loop.tick()
    assert tr.target_level == "2"
    assert fan.level == "2"


def test_boot_grace_remaining_counts_down():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU",), ((40.0, 0), (80.0, 7))))
    t = [0.0]
    loop = ControlLoop(sensors=FakeSensors({}), fan=FakeFan(), config=cfg,
                       clock=_clock(t), boot_grace_seconds=30.0)
    assert loop.boot_grace_remaining() == 30.0
    t[0] = 20.0
    assert loop.boot_grace_remaining() == 10.0
    t[0] = 45.0
    assert loop.boot_grace_remaining() == 0.0


def test_boot_grace_does_not_block_failsafe():
    cfg = Config(mode="curve", failsafe_temp=70.0,
                 curve=CurveCfg(("CPU",), ((40.0, 0), (80.0, 7))))
    fan = FakeFan()
    t = [0.0]
    loop = ControlLoop(sensors=FakeSensors({"CPU": 75.0}), fan=fan, config=cfg,
                       clock=_clock(t))
    tr = loop.tick()
    assert tr.target_level == "disengaged"
    assert tr.emergency is not None


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


def test_failsafe_write_failure_falls_back_to_auto():
    cfg = Config(mode="curve", failsafe_temp=70.0,
                 curve=CurveCfg(("CPU",), ((40.0, 0), (80.0, 7))))
    fan = FakeFan()
    fan.fail_set = True
    fan.fail_only_non_auto = True
    loop, _ = _loop({"CPU": 95.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.emergency is not None
    assert tr.fallback_to_auto is True


def test_set_config_resets_curve_state_on_mode_change():
    curve = CurveCfg(("CPU",), ((40.0, 0), (80.0, 7)))
    cfg_curve = Config(mode="curve", curve=curve)
    loop, fan = _loop({"CPU": 80.0}, cfg=cfg_curve)
    loop.tick()
    assert loop._last_curve_level == 7
    loop.set_config(Config(mode="manual", manual_level="3"))
    assert loop._last_curve_level == 0
    loop.set_config(cfg_curve)
    assert loop._last_curve_level == 0
    loop.sensors.temps = {"CPU": 42.0}
    loop.tick()
    assert loop._last_curve_level < 7


def test_sensors_read_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    sensors = FakeSensors({"CPU": 50.0})
    sensors.fail_read = True
    loop = ControlLoop(sensors=sensors, fan=fan, config=cfg, boot_grace_seconds=0.0)
    tr = loop.tick()
    assert tr.fallback_to_auto is True
    assert tr.temps == {}
    assert tr.target_level == "auto"


def test_last_level_property():
    cfg = Config(mode="manual", manual_level="5")
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg)
    loop.tick()
    assert loop.last_level == "5"


def test_fan_read_failure_falls_back_to_auto():
    cfg = Config(mode="manual", manual_level="5")
    fan = FakeFan()
    fan.fail_read = True
    loop, _ = _loop({"CPU": 50.0}, cfg=cfg, fan=fan)
    tr = loop.tick()
    assert tr.fallback_to_auto is True
    assert tr.target_level == "auto"


def test_curve_sensors_are_requested_as_required():
    cfg = Config(mode="curve", curve=CurveCfg(("CPU", "NVMe"), ((40.0, 0), (80.0, 7))))
    loop, _ = _loop({"CPU": 50.0, "NVMe": 45.0}, cfg=cfg)
    loop.tick()
    assert loop.sensors.required == ("CPU", "NVMe")


def test_non_curve_modes_require_no_sensor():
    loop, _ = _loop({"CPU": 50.0}, cfg=Config(mode="auto"))
    loop.tick()
    assert tuple(loop.sensors.required) == ()
