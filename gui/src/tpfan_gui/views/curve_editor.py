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


HIT_THRESHOLD_PX = 12


def make_widget(model: CurveModel, on_change, parent=None):
    """on_change(points) wird gerufen, wenn der User Apply klickt."""
    import pyqtgraph as pg
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
    from PyQt6.QtCore import Qt, QPointF, QObject, QEvent

    LEGEND_TEXT = (
        "<b>Bedienung:</b><br>"
        "• Punkt mit linker Maustaste <i>ziehen</i> → Position verschieben<br>"
        "• Linksklick auf leere Fläche → neuen Punkt hinzufügen<br>"
        "• Rechtsklick auf Punkt → Punkt entfernen<br>"
        "• <b>Anwenden</b> überträgt die Kurve an den Daemon"
    )

    class _DragFilter(QObject):
        def __init__(self, editor):
            super().__init__()
            self.editor = editor
            self.drag_idx: int | None = None

        def eventFilter(self, obj, ev):
            et = ev.type()
            if et == QEvent.Type.GraphicsSceneMousePress and ev.button() == Qt.MouseButton.LeftButton:
                idx = self.editor._hit_test(ev.scenePos())
                if idx is not None:
                    self.drag_idx = idx
                    self.editor._dragging = True
                    ev.accept()
                    return True
            elif et == QEvent.Type.GraphicsSceneMouseMove and self.drag_idx is not None:
                self.editor._drag_to(self.drag_idx, ev.scenePos())
                ev.accept()
                return True
            elif et == QEvent.Type.GraphicsSceneMouseRelease and self.drag_idx is not None:
                self.drag_idx = None
                # Drag-Flag erst nach dem nachfolgenden sigMouseClicked zurücksetzen,
                # damit der Klick nicht als "Punkt hinzufügen" interpretiert wird.
                ev.accept()
                return True
            return False

    class CurveEditor(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            lay = QVBoxLayout(self)
            self.plot = pg.PlotWidget()
            self.plot.setXRange(30, 95)
            self.plot.setYRange(0, 7)
            self.plot.setLabel("bottom", "°C")
            self.plot.setLabel("left", "Level")
            self.plot.setMouseEnabled(x=False, y=False)
            lay.addWidget(self.plot)
            self.scatter = pg.ScatterPlotItem(size=12)
            self.line = pg.PlotCurveItem()
            self.plot.addItem(self.line)
            self.plot.addItem(self.scatter)

            self.hint = QLabel(LEGEND_TEXT)
            self.hint.setTextFormat(Qt.TextFormat.RichText)
            self.hint.setWordWrap(True)
            lay.addWidget(self.hint)

            row = QHBoxLayout()
            self.apply_btn = QPushButton("Anwenden")
            self.apply_btn.clicked.connect(self.commit)
            row.addWidget(self.apply_btn)
            lay.addLayout(row)

            self._dragging = False
            self._drag_filter = _DragFilter(self)
            try:
                self.plot.scene().installEventFilter(self._drag_filter)
                self.plot.scene().sigMouseClicked.connect(self._on_click)
            except Exception:
                pass

            self.refresh()

        def refresh(self):
            ts = [p[0] for p in model.points]
            ls = [p[1] for p in model.points]
            self.scatter.setData(x=ts, y=ls)
            self.line.setData(x=ts, y=ls)

        def _hit_test(self, scene_pos) -> int | None:
            vb = self.plot.plotItem.vb
            best: int | None = None
            best_d = float(HIT_THRESHOLD_PX)
            for i, (t, lvl) in enumerate(model.points):
                p_scene = vb.mapViewToScene(QPointF(float(t), float(lvl)))
                dx = p_scene.x() - scene_pos.x()
                dy = p_scene.y() - scene_pos.y()
                d = (dx * dx + dy * dy) ** 0.5
                if d < best_d:
                    best_d = d
                    best = i
            return best

        def _drag_to(self, idx: int, scene_pos):
            vb = self.plot.plotItem.vb
            pt = vb.mapSceneToView(scene_pos)
            try:
                model.move(idx, float(pt.x()), float(pt.y()))
            except (IndexError, ValueError):
                return
            self.refresh()

        def _on_click(self, ev):
            if self._dragging:
                # Click direkt nach Drag-Release ignorieren
                self._dragging = False
                return
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
                idx = self._hit_test(pos)
                if idx is None:
                    return
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
