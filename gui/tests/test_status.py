from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")

from tpfan_gui.views.status import StatusView, _fmt_curve, LevelRpmTracker


class _FakeClient:
    def __init__(self, values):
        self._v = values

    def get(self, name):
        return self._v.get(name)


def test_fmt_curve_filters_invalid():
    rows = _fmt_curve([(40.0, 0), (60.5, 4), ("bad", 2), (80.0, 7)])
    assert rows == [("40.0 °C", "0"), ("60.5 °C", "4"), ("80.0 °C", "7")]


def test_refresh_populates_labels_and_table(qtbot):
    client = _FakeClient({
        "Mode": "curve",
        "CurrentLevel": "3",
        "FailsafeTemp": 92.0,
        "DaemonVersion": "1.2.3",
        "CurveSensors": ["CPU", "GPU"],
        "Curve": [(40.0, 0), (60.0, 4), (80.0, 7)],
    })
    v = StatusView(client)
    qtbot.addWidget(v)
    v.refresh()
    assert v.mode_lbl.text() == "curve"
    assert v.level_lbl.text() == "3"
    assert "92.0" in v.failsafe_lbl.text()
    assert v.version_lbl.text() == "1.2.3"
    assert "CPU" in v.sensors_lbl.text() and "GPU" in v.sensors_lbl.text()
    assert v.curve_table.rowCount() == 3
    assert v.curve_table.item(1, 0).text() == "60.0 °C"
    assert v.curve_table.item(1, 1).text() == "4"


def test_level_rpm_tracker_records_min_max_and_last():
    t = LevelRpmTracker()
    t.record("3", 2400)
    t.record("3", 2800)
    t.record("3", 2600)
    t.record("7", 4800)
    rows = {r[0]: r for r in t.rows()}
    assert rows["3"][1] == "2600"           # last
    assert rows["3"][2] == "2400 / 2800"    # min / max
    assert rows["3"][3] == "3"              # count
    assert rows["7"][1] == "4800"
    assert rows["0"][1] == "—"


def test_level_rpm_tracker_ignores_invalid():
    t = LevelRpmTracker()
    t.record("", 1000)
    t.record("3", -1)
    assert t.rows()[0][1] == "—"  # nothing recorded


def test_status_record_tick_updates_rpm_table(qtbot):
    from tpfan_gui.ipc.dbus_client import TickPayload
    v = StatusView(_FakeClient({}))
    qtbot.addWidget(v)
    v.record_tick(TickPayload(temps={}, fans=[(2750, "3")], level="3"))
    v.record_tick(TickPayload(temps={}, fans=[(2900, "3")], level="3"))
    v.refresh()
    # row for level "3" is index 3 (0..7, then auto, disengaged)
    assert v.rpm_table.item(3, 0).text() == "3"
    assert v.rpm_table.item(3, 1).text() == "2900"


def test_refresh_handles_missing_values(qtbot):
    v = StatusView(_FakeClient({}))
    qtbot.addWidget(v)
    v.refresh()
    assert v.mode_lbl.text() == "—"
    assert v.failsafe_lbl.text() == "—"
    assert v.curve_table.rowCount() == 0
