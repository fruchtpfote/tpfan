from __future__ import annotations
import pytest

pytest.importorskip("pytestqt")

from tpfan_gui.ipc.dbus_client import TickPayload
from tpfan_gui.tray import TrayController, color_for_level, LEVEL_COLOR_GREEN, LEVEL_COLOR_YELLOW, LEVEL_COLOR_RED, LEVEL_COLOR_GRAY


def test_color_for_level_mapping():
    assert color_for_level("0") == LEVEL_COLOR_GREEN
    assert color_for_level("2") == LEVEL_COLOR_GREEN
    assert color_for_level("3") == LEVEL_COLOR_YELLOW
    assert color_for_level("5") == LEVEL_COLOR_YELLOW
    assert color_for_level("7") == LEVEL_COLOR_RED
    assert color_for_level("disengaged") == LEVEL_COLOR_RED
    assert color_for_level("auto") == LEVEL_COLOR_GRAY
    assert color_for_level("unknown") == LEVEL_COLOR_GRAY


def test_apply_mode_marks_radio_and_enables_level(qtbot):
    t = TrayController()
    t.apply_mode("manual")
    assert t._mode_actions["manual"].isChecked()
    assert not t._mode_actions["auto"].isChecked()
    assert t._level_menu.isEnabled() is True

    t.apply_mode("curve")
    assert t._mode_actions["curve"].isChecked()
    assert t._level_menu.isEnabled() is False


def test_tray_status_header_shows_preset_or_manual(qtbot):
    from tpfan_gui.views.curve_editor import PRESETS
    t = TrayController()
    name, pts = PRESETS[1]  # Ruhig
    t.apply_curve(pts)
    t.apply_mode("curve")
    assert name in t._status_action.text()
    t.apply_curve([(40.0, 0), (80.0, 7)])
    assert "manuelle Kurve" in t._status_action.text()
    t.apply_mode("auto")
    assert t._status_action.text().endswith("auto")


def test_apply_tick_updates_status(qtbot):
    t = TrayController()
    payload = TickPayload(
        temps={"CPU": 52.4, "GPU": 47.0},
        fans=[(2750, "3")],
        level="3",
    )
    t.apply_tick(payload)
    assert "CPU" in t._max_action.text()
    assert "52.4" in t._max_action.text()
    assert "2750" in t._level_action.text()
    assert "Level: 3" in t._level_action.text()
    tip = t.tray.toolTip()
    assert "Modus" in tip and "CPU" in tip and "2750" in tip


def test_mode_signal_fires(qtbot):
    t = TrayController()
    received: list[str] = []
    t.modeRequested.connect(received.append)
    t._mode_actions["manual"].trigger()
    assert received == ["manual"]


def test_level_signal_fires(qtbot):
    t = TrayController()
    received: list[str] = []
    t.levelRequested.connect(received.append)
    # level menu has actions in insertion order
    actions = t._level_menu.actions()
    actions[3].trigger()  # "3"
    assert received == ["3"]


def test_set_connected_false_resets_tooltip(qtbot):
    t = TrayController()
    t.apply_tick(TickPayload(temps={"CPU": 60.0}, fans=[(2000, "4")], level="4"))
    t.set_connected(False)
    assert "nicht verbunden" in t.tray.toolTip()
