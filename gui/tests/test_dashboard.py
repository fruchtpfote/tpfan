from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")


def test_dashboard_updates_with_tick(qtbot):
    from tpfan_gui.ipc.dbus_client import TickPayload
    from tpfan_gui.views.dashboard import Dashboard
    d = Dashboard()
    qtbot.addWidget(d)
    payload = TickPayload(
        temps={"CPU": 45.5, "GPU": 50.0},
        fans=[(2200, "auto"), (2100, "auto")],
        level="auto",
    )
    d.apply_tick(payload)
    assert "45.5" in d.cpu_label.text()
    assert "50.0" in d.gpu_label.text()
    assert "2200" in d.fan1_label.text()
    assert "auto" in d.level_label.text().lower()


def test_dashboard_shows_session_max(qtbot):
    from tpfan_gui.ipc.dbus_client import TickPayload
    from tpfan_gui.views.dashboard import Dashboard
    d = Dashboard()
    qtbot.addWidget(d)
    d.apply_tick(TickPayload(temps={"CPU": 50.0}, fans=[], level="auto"))
    d.apply_tick(TickPayload(temps={"CPU": 60.0}, fans=[], level="auto"))
    d.apply_tick(TickPayload(temps={"CPU": 55.0}, fans=[], level="auto"))
    assert "55.0" in d.cpu_label.text()
    assert "max 60.0" in d.cpu_label.text()


def test_dashboard_no_max_before_any_tick(qtbot):
    from tpfan_gui.views.dashboard import Dashboard
    d = Dashboard()
    qtbot.addWidget(d)
    assert d.cpu_label.text() == "--"


def test_dashboard_resets_fan_labels_when_fewer_fans(qtbot):
    from tpfan_gui.ipc.dbus_client import TickPayload
    from tpfan_gui.views.dashboard import Dashboard
    d = Dashboard()
    qtbot.addWidget(d)
    d.apply_tick(TickPayload(temps={}, fans=[(2200, "auto"), (2100, "auto")], level="auto"))
    assert d.fan1_label.text() != "--"
    assert d.fan2_label.text() != "--"
    d.apply_tick(TickPayload(temps={}, fans=[], level="auto"))
    assert d.fan1_label.text() == "--"
    assert d.fan2_label.text() == "--"
