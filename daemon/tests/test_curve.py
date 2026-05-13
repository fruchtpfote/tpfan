# daemon/tests/test_curve.py
from __future__ import annotations
import pytest
from tpfan_daemon.control.curve import interpolate, threshold_for_level

POINTS = [(40.0, 0), (55.0, 2), (70.0, 4), (80.0, 7)]


@pytest.mark.parametrize("t,prev,expected", [
    (30.0, 0, 0),
    (40.0, 0, 0),
    (47.5, 0, 1),
    (55.0, 0, 2),
    (62.5, 0, 3),
    (70.0, 0, 4),
    (75.0, 0, 6),
    (80.0, 0, 7),
    (95.0, 0, 7),
])
def test_steigend_keine_hysterese(t, prev, expected):
    assert interpolate(POINTS, t, prev) == expected


def test_hysterese_haelt_level_bei_kleinem_drop():
    assert interpolate(POINTS, 68.0, 4) == 4


def test_hysterese_release_unter_drei_grad():
    assert interpolate(POINTS, 60.0, 4) == 3


def test_threshold_for_level():
    assert threshold_for_level(POINTS, 4) == 70.0
    assert threshold_for_level(POINTS, 2) == 55.0
    assert threshold_for_level(POINTS, 1) == pytest.approx(47.5)


def test_unter_erstem_punkt_clampt():
    assert interpolate(POINTS, 10.0, 0) == 0


def test_zwei_punkte_minimal():
    assert interpolate([(40.0, 0), (80.0, 7)], 60.0, 0) == 4
