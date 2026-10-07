from __future__ import annotations
import logging
from pathlib import Path
import pytest
from tpfan_daemon.hw.sensors import CALIBRATION_SAMPLES, Sensors
from .conftest import make_hwmon


def test_discovery_maps_known_drivers(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "k10temp",   temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    make_hwmon(hwmon_tree, 1, "amdgpu",    temps={"temp1": 50.0}, labels={"temp1": "edge"})
    make_hwmon(hwmon_tree, 2, "nvme",      temps={"temp1": 38.0, "temp2": 40.0}, labels={"temp1": "Composite"})
    make_hwmon(hwmon_tree, 3, "thinkpad",  temps={"temp1": 47.0, "temp2": 48.0}, labels={"temp1": "CPU", "temp2": "GPU"})

    s = Sensors(root=hwmon_tree)
    s.discover()
    readings = s.read_all()

    assert readings["CPU"] == pytest.approx(45.0)
    assert readings["GPU"] == pytest.approx(50.0)
    assert readings["NVMe"] == pytest.approx(38.0)
    assert readings["MB-CPU"] == pytest.approx(47.0)
    assert readings["MB-GPU"] == pytest.approx(48.0)


def test_unreadable_sensor_skipped(hwmon_tree: Path):
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    (d / "temp2_input").write_text("garbage\n")
    (d / "temp2_label").write_text("Tctl\n")
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r == {"CPU": pytest.approx(45.0)}


def test_unknown_driver_exposed_generically(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "exotic_driver",
               temps={"temp1": 30.0, "temp2": 31.0},
               labels={"temp1": "zone_a"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["exotic_driver-zone_a"] == pytest.approx(30.0)
    assert r["exotic_driver-temp2"] == pytest.approx(31.0)


def test_generic_name_collision_disambiguated(hwmon_tree: Path):
    # zwei hwmon-Instanzen mit identischem Treibernamen und ohne Label →
    # zweiter bekommt Suffix '#2', damit der Schlüssel eindeutig bleibt.
    make_hwmon(hwmon_tree, 0, "iwlwifi_1", temps={"temp1": 40.0})
    make_hwmon(hwmon_tree, 1, "iwlwifi_1", temps={"temp1": 41.0})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["iwlwifi_1-temp1"] == pytest.approx(40.0)
    assert r["iwlwifi_1-temp1#2"] == pytest.approx(41.0)


def test_coretemp_maps_to_cpu(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "coretemp",
               temps={"temp1": 52.0, "temp2": 51.0, "temp3": 50.0},
               labels={"temp1": "Package id 0", "temp2": "Core 0", "temp3": "Core 1"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["CPU"] == pytest.approx(52.0)
    # Cores fallen auf generischen Namen zurück, damit sie nicht verloren gehen.
    assert r["coretemp-Core 0"] == pytest.approx(51.0)
    assert r["coretemp-Core 1"] == pytest.approx(50.0)


def test_unreadable_sensor_warns_only_once(hwmon_tree: Path, caplog):
    # Ein Sensor, der bei jedem Tick unlesbar ist (z. B. thinkpad-Slot mit
    # ENXIO), darf das Journal nicht fluten: nur eine Warnung, nicht pro Aufruf.
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    (d / "temp2_input").write_text("40000\n")  # bei discover lesbar
    s = Sensors(root=hwmon_tree); s.discover()
    (d / "temp2_input").unlink()  # danach unlesbar -> OSError bei read

    with caplog.at_level(logging.WARNING, logger="tpfan_daemon.hw.sensors"):
        for _ in range(5):
            s.read_all()

    warnings = [r for r in caplog.records if "unreadable" in r.getMessage()]
    assert len(warnings) == 1


def test_unreadable_sensor_warns_again_after_recovery(hwmon_tree: Path, caplog):
    # Erholt sich ein Sensor und fällt später erneut aus, soll wieder gewarnt
    # werden (die Idempotenz gilt nur pro ununterbrochener Ausfallphase).
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    input_path = d / "temp2_input"
    input_path.write_text("40000\n")
    s = Sensors(root=hwmon_tree); s.discover()

    with caplog.at_level(logging.WARNING, logger="tpfan_daemon.hw.sensors"):
        input_path.unlink()
        s.read_all(); s.read_all()          # 1. Warnung
        input_path.write_text("41000\n")
        s.read_all()                        # Erholung -> Reset
        input_path.unlink()
        s.read_all()                        # 2. Warnung

    warnings = [r for r in caplog.records if "unreadable" in r.getMessage()]
    assert len(warnings) == 2


def test_thinkpad_generic_zone_indexed(hwmon_tree: Path):
    make_hwmon(hwmon_tree, 0, "thinkpad",
               temps={"temp3": 40.0, "temp4": 41.0},
               labels={"temp3": "other", "temp4": "other2"})
    s = Sensors(root=hwmon_tree); s.discover()
    r = s.read_all()
    assert r["MB-temp3"] == pytest.approx(40.0)
    assert r["MB-temp4"] == pytest.approx(41.0)


# --- Zwei-Tier-Polling -------------------------------------------------

def _scripted_timer(costs: list[float], samples: int):
    """Timer-Stub: liefert Zeitstempel, bei denen Sensor k `costs[k]` kostet.

    Reihenfolge wie die Kalibrierung: `samples` Sweeps über alle Sensoren,
    pro Read zwei Timer-Aufrufe (vorher/nachher).
    """
    vals: list[float] = []
    t = 0.0
    for _ in range(samples):
        for cost in costs:
            vals.append(t)
            t += cost
            vals.append(t)
            t += 0.001
    it = iter(vals)
    return lambda: next(it)


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _two_sensors(root: Path) -> None:
    make_hwmon(root, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    make_hwmon(root, 1, "nvme", temps={"temp1": 38.0}, labels={"temp1": "Composite"})


def test_calibration_marks_slow_drivers(hwmon_tree: Path):
    _two_sensors(hwmon_tree)
    s = Sensors(root=hwmon_tree,
                timer=_scripted_timer([0.0, 0.002], CALIBRATION_SAMPLES))
    s.discover()

    assert s.slow == {"NVMe"}


def test_calibration_does_not_swallow_the_first_unreadable_warning(hwmon_tree: Path, caplog):
    d = make_hwmon(hwmon_tree, 0, "k10temp", temps={"temp1": 45.0}, labels={"temp1": "Tctl"})
    (d / "temp2_input").write_text("garbage\n")
    s = Sensors(root=hwmon_tree)

    with caplog.at_level(logging.WARNING, logger="tpfan_daemon.hw.sensors"):
        s.discover()
        s.read_all()

    assert [r for r in caplog.records if "unreadable" in r.getMessage()]


def test_slow_sensors_are_served_from_cache_between_polls(hwmon_tree: Path):
    _two_sensors(hwmon_tree)
    clock = _FakeClock()
    s = Sensors(root=hwmon_tree, clock=clock, slow_poll_interval_s=5.0)
    s.discover()
    s.slow = {"NVMe"}

    first = s.read_for_control()
    assert first["NVMe"] == pytest.approx(38.0)

    (hwmon_tree / "hwmon0" / "temp1_input").write_text("60000\n")
    (hwmon_tree / "hwmon1" / "temp1_input").write_text("70000\n")

    clock.now = 1.0
    r = s.read_for_control()
    assert r["CPU"] == pytest.approx(60.0)    # schnell -> frisch
    assert r["NVMe"] == pytest.approx(38.0)   # langsam -> gecacht

    clock.now = 6.0
    r = s.read_for_control()
    assert r["NVMe"] == pytest.approx(70.0)   # Intervall abgelaufen -> frisch


def test_required_sensors_are_read_fresh_even_when_slow(hwmon_tree: Path):
    _two_sensors(hwmon_tree)
    clock = _FakeClock()
    s = Sensors(root=hwmon_tree, clock=clock, slow_poll_interval_s=5.0)
    s.discover()
    s.slow = {"NVMe"}
    s.read_for_control()

    (hwmon_tree / "hwmon1" / "temp1_input").write_text("70000\n")
    clock.now = 1.0

    assert s.read_for_control(("NVMe",))["NVMe"] == pytest.approx(70.0)


def test_read_for_control_drops_sensor_that_became_unreadable(hwmon_tree: Path):
    _two_sensors(hwmon_tree)
    clock = _FakeClock()
    s = Sensors(root=hwmon_tree, clock=clock, slow_poll_interval_s=5.0)
    s.discover()
    s.slow = {"NVMe"}
    s.read_for_control()

    (hwmon_tree / "hwmon1" / "temp1_input").unlink()
    clock.now = 6.0

    assert "NVMe" not in s.read_for_control()


def test_read_all_bypasses_the_cache(hwmon_tree: Path):
    _two_sensors(hwmon_tree)
    clock = _FakeClock()
    s = Sensors(root=hwmon_tree, clock=clock, slow_poll_interval_s=5.0)
    s.discover()
    s.slow = {"NVMe"}
    s.read_for_control()

    (hwmon_tree / "hwmon1" / "temp1_input").write_text("70000\n")
    clock.now = 1.0

    assert s.read_all()["NVMe"] == pytest.approx(70.0)
