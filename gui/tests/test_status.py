from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")

from tpfan_gui.views.status import StatusView, _fmt_curve, rpm_rows


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
    assert v.mode_lbl.text().startswith("curve")
    # Erwartung: bei beliebiger Kurve ohne Preset-Match → 'manuelle Kurve'
    assert "manuelle Kurve" in v.mode_lbl.text() or "·" in v.mode_lbl.text()
    assert v.level_lbl.text() == "3"
    assert "92.0" in v.failsafe_lbl.text()
    assert "1.2.3" in v.version_lbl.text()
    assert "CPU" in v.sensors_lbl.text() and "GPU" in v.sensors_lbl.text()
    assert v.curve_table.rowCount() == 3
    assert v.curve_table.item(1, 0).text() == "60.0 °C"
    assert v.curve_table.item(1, 1).text() == "4"


def test_rpm_rows_renders_stats_dict():
    rows = {r[0]: r for r in rpm_rows({"3": (2600, 2400, 2800, 7), "7": (4800, 4800, 4800, 1)})}
    assert rows["3"] == ("3", "2600", "2400 / 2800", "7")
    assert rows["7"][1] == "4800"
    assert rows["0"][1] == "—"


def test_rpm_rows_ignores_malformed_entries():
    rows = {r[0]: r for r in rpm_rows({"3": "bad"})}
    assert rows["3"][1] == "—"


def test_status_pulls_rpm_stats_from_daemon(qtbot):
    v = StatusView(_FakeClient({"LevelRpmStats": {"3": (2750, 2700, 2800, 4)}}))
    qtbot.addWidget(v)
    v.refresh()
    # row for level "3" is index 3 (0..7, then auto, disengaged)
    assert v.rpm_table.item(3, 0).text() == "3"
    assert v.rpm_table.item(3, 1).text() == "2750"
    assert v.rpm_table.item(3, 2).text() == "2700 / 2800"


def test_refresh_handles_missing_values(qtbot):
    v = StatusView(_FakeClient({}))
    qtbot.addWidget(v)
    v.refresh()
    assert v.mode_lbl.text() == "—"
    assert v.failsafe_lbl.text() == "—"
    assert v.curve_table.rowCount() == 0
