from __future__ import annotations
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tpfan_daemon.__main__ import _state_dict
from tpfan_daemon.daemon import Daemon
from tpfan_daemon.rpm_stats import RpmStatsTracker


class CountingSensors:
    def __init__(self):
        self.describe_calls = 0
        self.read_all_calls = 0

    def read_all(self):
        self.read_all_calls += 1
        return {"CPU": 50.0}

    def read_for_control(self, required=()):
        return self.read_all()

    def describe(self):
        self.describe_calls += 1
        return {"CPU": (50.0, "CPU", "k10temp/Tctl")}


class StubFan:
    def __init__(self): self.level = "auto"
    def writable(self): return True
    def read(self):
        class S: speed_rpm, level, enabled = 2000, "auto", True
        return S()
    def set_level(self, lvl): self.level = lvl


def _state(tmp_path: Path):
    sensors = CountingSensors()
    d = Daemon(tmp_path / "c.toml", sensors, StubFan())
    sensors.read_all_calls = 0          # Daemon-Init zählt nicht mit
    return _state_dict(d, sensors, RpmStatsTracker()), sensors


def test_cheap_properties_touch_no_sensor(tmp_path: Path):
    # Mode/Curve-Reads der GUI dürfen keinen Sensor-Sweep über I2C/ACPI auslösen.
    st, sensors = _state(tmp_path)

    assert st["mode"] == "curve"
    assert st["failsafe_temp"] == 95.0
    assert st["curve_sensors"] == ["CPU", "GPU", "NVMe"]
    assert st["boot_grace_remaining"] >= 0.0

    assert sensors.describe_calls == 0
    assert sensors.read_all_calls == 0


def test_sensor_data_is_read_once_on_demand(tmp_path: Path):
    st, sensors = _state(tmp_path)

    assert st["temps"] == {"CPU": 50.0}
    assert sensors.describe_calls == 1

    assert st["sensor_describe"] == {"CPU": (50.0, "CPU", "k10temp/Tctl")}
    assert st["temps"] == {"CPU": 50.0}
    assert sensors.describe_calls == 1          # memoisiert
    assert sensors.read_all_calls == 0          # describe() reicht


def test_state_behaves_like_a_mapping(tmp_path: Path):
    st, _ = _state(tmp_path)

    assert st.get("mode") == "curve"
    assert st.get("gibt-es-nicht") is None
    assert st.get("gibt-es-nicht", "fallback") == "fallback"
    assert "temps" in st
    assert "sensor_describe" in st
    assert set(st) >= {"mode", "level", "temps", "sensor_describe", "curve"}
