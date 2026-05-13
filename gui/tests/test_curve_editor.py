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
