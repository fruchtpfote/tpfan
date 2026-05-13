from __future__ import annotations
from typing import Sequence

HYSTERESIS_C = 3.0
Point = tuple[float, int]


def _raw_level(points: Sequence[Point], t: float) -> float:
    if t <= points[0][0]:
        return float(points[0][1])
    if t >= points[-1][0]:
        return float(points[-1][1])
    for (t0, l0), (t1, l1) in zip(points, points[1:]):
        if t0 <= t <= t1:
            f = (t - t0) / (t1 - t0)
            return l0 + f * (l1 - l0)
    return float(points[-1][1])


def threshold_for_level(points: Sequence[Point], level: int) -> float:
    if level <= points[0][1]:
        return points[0][0]
    if level >= points[-1][1]:
        return points[-1][0]
    for (t0, l0), (t1, l1) in zip(points, points[1:]):
        if l0 <= level <= l1 and l1 > l0:
            f = (level - l0) / (l1 - l0)
            return t0 + f * (t1 - t0)
    return points[-1][0]


def interpolate(points: Sequence[Point], t: float, prev_level: int) -> int:
    raw = round(_raw_level(points, t))
    raw = max(0, min(7, raw))
    if raw >= prev_level:
        return raw
    thr = threshold_for_level(points, prev_level)
    if t >= thr - HYSTERESIS_C:
        return prev_level
    return raw
