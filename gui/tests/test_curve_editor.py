from __future__ import annotations
import pytest
from tpfan_gui.views.curve_editor import CurveModel


def test_add_point_sorts_and_validates():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    assert m.points == [(40.0, 0), (60.0, 4), (80.0, 7)]


def test_remove_keeps_minimum_two_points():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    with pytest.raises(ValueError):
        m.remove(0)
    m.add(60.0, 4)
    m.remove(1)
    assert m.points == [(40.0, 0), (80.0, 7)]


def test_move_clamps_to_range_and_keeps_monotonic():
    m = CurveModel(points=[(40.0, 0), (60.0, 4), (80.0, 7)])
    new = m.move(1, 35.0, 4)
    assert new[0] >= 40.0
    ts = [p[0] for p in m.points]
    assert ts == sorted(ts)


def test_move_clamps_level_to_0_7():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    new = m.move(1, 60.0, 9)
    assert new[1] == 7
    new = m.move(1, 60.0, -2)
    assert new[1] == 0


def test_move_rejects_out_of_range_index():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    with pytest.raises(IndexError):
        m.move(5, 60.0, 4)
    with pytest.raises(IndexError):
        m.move(-1, 60.0, 4)


def test_add_rejects_duplicate_t():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    with pytest.raises(ValueError):
        m.add(60.0, 5)


def test_add_rejects_too_close():
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    m.add(60.0, 4)
    with pytest.raises(ValueError):
        m.add(60.3, 5)


def test_presets_are_valid_curves():
    from tpfan_gui.views.curve_editor import PRESETS
    assert len(PRESETS) == 5
    names = [n for n, _ in PRESETS]
    assert names[0] == "Sehr ruhig" and names[-1] == "Sehr kühl"
    for name, pts in PRESETS:
        assert len(pts) >= 7, f"{name}: zu wenig Stützpunkte ({len(pts)})"
        ts = [t for t, _ in pts]
        lvls = [l for _, l in pts]
        assert ts == sorted(ts)
        for i in range(1, len(ts)):
            assert ts[i] - ts[i - 1] >= 0.5
        for lvl in lvls:
            assert 0 <= lvl <= 7
        # Endpunkt soll Volllast erreichen
        assert lvls[-1] == 7


def test_apply_preset_replaces_curve_without_emitting(qtbot):
    pytest.importorskip("pyqtgraph")
    from tpfan_gui.views.curve_editor import make_widget, PRESETS
    received: list = []
    m = CurveModel(points=[(40.0, 0), (80.0, 7)])
    w = make_widget(m, lambda pts: received.append(list(pts)))
    qtbot.addWidget(w)
    w.preset_buttons[0].click()  # "Sehr ruhig"
    expected = [(float(t), int(l)) for t, l in PRESETS[0][1]]
    assert m.points == expected
    assert received == []  # preset alleine sendet nichts
    w.apply_btn.click()
    assert received == [expected]


def test_match_preset_name_recognises_known_curve():
    from tpfan_gui.views.curve_editor import PRESETS, match_preset_name
    name, pts = PRESETS[2]  # Ausgewogen
    assert match_preset_name(pts) == name


def test_match_preset_name_returns_none_for_custom_curve():
    from tpfan_gui.views.curve_editor import match_preset_name
    assert match_preset_name([(40.0, 0), (80.0, 7)]) is None


def test_format_mode_label_for_curve_with_preset():
    from tpfan_gui.views.curve_editor import PRESETS, format_mode_label
    name, pts = PRESETS[0]  # Sehr ruhig
    assert format_mode_label("curve", pts) == f"curve · {name}"


def test_format_mode_label_for_manual_curve_and_other_modes():
    from tpfan_gui.views.curve_editor import format_mode_label
    assert format_mode_label("curve", [(40.0, 0), (80.0, 7)]) == "curve · manuelle Kurve"
    assert format_mode_label("auto") == "auto"
    assert format_mode_label("profile:quiet") == "profile:quiet"


def test_apply_button_triggers_on_change(qtbot):
    pytest.importorskip("pyqtgraph")
    from tpfan_gui.views.curve_editor import make_widget
    received: list = []
    m = CurveModel(points=[(40.0, 0), (60.0, 4), (80.0, 7)])
    w = make_widget(m, lambda pts: received.append(list(pts)))
    qtbot.addWidget(w)
    w.apply_btn.click()
    assert received == [[(40.0, 0), (60.0, 4), (80.0, 7)]]
