# daemon/tests/test_integration.py
from __future__ import annotations
from pathlib import Path
from tpfan_daemon.daemon import Daemon


class DriveSensors:
    def __init__(self, schedule):
        self.schedule = schedule
        self.i = 0
    def read_all(self):
        r = self.schedule[min(self.i, len(self.schedule) - 1)]
        self.i += 1
        return dict(r)
    def read_for_control(self, required=()):
        return self.read_all()
    def describe(self):
        return {}


class RememberFan:
    def __init__(self): self.level = "auto"; self.history = []
    def writable(self): return True
    def read(self):
        class S: pass
        s = S(); s.level = self.level; s.speed_rpm = 2000; s.enabled = True
        return s
    def set_level(self, lvl):
        self.level = lvl
        self.history.append(lvl)


def test_curve_drives_fan_over_temp_sweep(tmp_path: Path):
    cfg_path = tmp_path / "c.toml"
    fan = RememberFan()
    schedule = [
        {"CPU": 40.0},   # index 0 wird von set_curve-Validation konsumiert
        {"CPU": 40.0},   # -> 0
        {"CPU": 55.0},   # -> 2
        {"CPU": 70.0},   # -> 4
        {"CPU": 80.0},   # -> 7
        {"CPU": 78.0},   # Hysterese: bleibt 7
        {"CPU": 60.0},   # deutlich unter Schwelle: drop
    ]
    d = Daemon(cfg_path, DriveSensors(schedule), fan)
    d.loop.boot_grace_seconds = 0.0
    d.handle("set_mode", "curve")
    d.handle("set_curve", [(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)], ["CPU"])

    for _ in range(6):
        d.loop.tick()

    assert fan.history[:4] == ["0", "2", "4", "7"]
    assert fan.history[-1] in ("2", "3")
