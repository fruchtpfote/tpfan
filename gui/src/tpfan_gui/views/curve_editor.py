from __future__ import annotations
from dataclasses import dataclass, field

EPS = 0.5


@dataclass
class CurveModel:
    points: list[tuple[float, int]] = field(default_factory=list)
    t_min: float = 20.0
    t_max: float = 110.0

    def add(self, t: float, level: int) -> None:
        t = float(t)
        lvl = max(0, min(7, int(level)))
        self.points.append((t, lvl))
        self.points.sort(key=lambda p: p[0])
        idx = next(i for i, p in enumerate(self.points) if p[0] == t and p[1] == lvl)
        left = self.points[idx - 1][0] if idx > 0 else self.t_min - EPS
        right = self.points[idx + 1][0] if idx < len(self.points) - 1 else self.t_max + EPS
        if t - left < EPS or right - t < EPS:
            del self.points[idx]
            raise ValueError("point too close to neighbour")

    def remove(self, index: int) -> None:
        if len(self.points) <= 2:
            raise ValueError("curve must keep at least 2 points")
        del self.points[index]

    def move(self, index: int, t: float, level: float) -> tuple[float, int]:
        if not (0 <= index < len(self.points)):
            raise IndexError(f"index {index} out of range")
        t = max(self.t_min, min(self.t_max, float(t)))
        lvl = max(0, min(7, int(round(level))))
        left = self.points[index - 1][0] + EPS if index > 0 else self.t_min
        right = self.points[index + 1][0] - EPS if index < len(self.points) - 1 else self.t_max
        t = max(left, min(right, t))
        self.points[index] = (t, lvl)
        return self.points[index]


def make_widget(model: CurveModel, on_change, parent=None):
    """on_change(points) wird gerufen, wenn der User Apply klickt."""
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
    from PyQt6.QtCore import Qt

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

            self.hint = QLabel("Linksklick = Punkt hinzufügen, Rechtsklick = nächsten Punkt entfernen")
            lay.addWidget(self.hint)

            row = QHBoxLayout()
            self.apply_btn = QPushButton("Anwenden")
            self.apply_btn.clicked.connect(self.commit)
            row.addWidget(self.apply_btn)
            lay.addLayout(row)

            try:
                self.plot.scene().sigMouseClicked.connect(self._on_click)
            except Exception:
                pass

            self.refresh()

        def refresh(self):
            ts = [p[0] for p in model.points]
            ls = [p[1] for p in model.points]
            self.scatter.setData(x=ts, y=ls)
            self.line.setData(x=ts, y=ls)

        def _on_click(self, ev):
            try:
                vb = self.plot.plotItem.vb
                pos = ev.scenePos()
                pt = vb.mapSceneToView(pos)
                t = float(pt.x())
                lvl = float(pt.y())
            except Exception:
                return
            if ev.button() == Qt.MouseButton.RightButton:
                if not model.points:
                    return
                idx = min(range(len(model.points)),
                          key=lambda i: abs(model.points[i][0] - t))
                try:
                    model.remove(idx)
                except ValueError:
                    return
                self.refresh()
            elif ev.button() == Qt.MouseButton.LeftButton:
                try:
                    model.add(t, int(round(lvl)))
                except ValueError:
                    return
                self.refresh()

        def commit(self):
            on_change(list(model.points))

    return CurveEditor(parent)
