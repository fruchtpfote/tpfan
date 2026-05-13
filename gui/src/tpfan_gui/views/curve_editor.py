from __future__ import annotations
from dataclasses import dataclass, field

EPS = 0.5


@dataclass
class CurveModel:
    points: list[tuple[float, int]] = field(default_factory=list)
    t_min: float = 20.0
    t_max: float = 110.0

    def add(self, t: float, level: int) -> None:
        self.points.append((float(t), max(0, min(7, int(level)))))
        self.points.sort(key=lambda p: p[0])

    def remove(self, index: int) -> None:
        if len(self.points) <= 2:
            raise ValueError("curve must keep at least 2 points")
        del self.points[index]

    def move(self, index: int, t: float, level: float) -> tuple[float, int]:
        t = max(self.t_min, min(self.t_max, float(t)))
        lvl = max(0, min(7, int(round(level))))
        left = self.points[index - 1][0] + EPS if index > 0 else self.t_min
        right = self.points[index + 1][0] - EPS if index < len(self.points) - 1 else self.t_max
        t = max(left, min(right, t))
        self.points[index] = (t, lvl)
        return self.points[index]


def make_widget(model: CurveModel, on_change, parent=None):
    """on_change(points) wird gerufen, wenn der User loslässt."""
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout

    class CurveEditor(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setXRange(30, 95)
            self.plot.setYRange(0, 7)
            self.plot.setLabel("bottom", "°C")
            self.plot.setLabel("left", "Level")
            lay.addWidget(self.plot)
            self.scatter = pg.ScatterPlotItem(size=12)
            self.line = pg.PlotCurveItem()
            self.plot.addItem(self.line)
            self.plot.addItem(self.scatter)
            self.refresh()

        def refresh(self):
            ts = [p[0] for p in model.points]
            ls = [p[1] for p in model.points]
            self.scatter.setData(x=ts, y=ls)
            self.line.setData(x=ts, y=ls)

        def commit(self):
            on_change(list(model.points))

    return CurveEditor(parent)
