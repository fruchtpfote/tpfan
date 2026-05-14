from __future__ import annotations
from typing import Optional

from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QAction, QActionGroup, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QMenu, QSystemTrayIcon

from .ipc.dbus_client import TickPayload
from .views.curve_editor import format_mode_label


LEVEL_COLOR_GRAY = QColor(140, 140, 140)
LEVEL_COLOR_GREEN = QColor(58, 175, 58)
LEVEL_COLOR_YELLOW = QColor(220, 162, 30)
LEVEL_COLOR_RED = QColor(211, 65, 65)


def color_for_level(level: str) -> QColor:
    if level in ("0", "1", "2"):
        return LEVEL_COLOR_GREEN
    if level in ("3", "4", "5"):
        return LEVEL_COLOR_YELLOW
    if level in ("6", "7", "disengaged", "full-speed"):
        return LEVEL_COLOR_RED
    return LEVEL_COLOR_GRAY


def make_level_icon(level: str, size: int = 32) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(color_for_level(level))
    painter.setPen(QColor(255, 255, 255))
    margin = max(2, size // 16)
    painter.drawEllipse(margin, margin, size - 2 * margin, size - 2 * margin)
    painter.end()
    return QIcon(pm)


class TrayController(QObject):
    """System-tray UI with status display and quick actions.

    Signals:
        modeRequested(str)    - Auto/Kurve/Manuell aus dem Submenü
        levelRequested(str)   - 0..7 oder 'disengaged' aus dem Submenü
        openRequested()       - 'Öffnen' oder Doppelklick aufs Tray-Icon
        quitRequested()       - 'Beenden'
    """

    modeRequested = pyqtSignal(str)
    levelRequested = pyqtSignal(str)
    openRequested = pyqtSignal()
    quitRequested = pyqtSignal()

    MODES = [("auto", "Auto"), ("curve", "Kurve"), ("manual", "Manuell")]
    LEVELS = ["0", "1", "2", "3", "4", "5", "6", "7", "disengaged"]

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._mode: str = "auto"
        self._curve_points: list = []
        self._last_payload: Optional[TickPayload] = None

        self.tray = QSystemTrayIcon(make_level_icon("auto"), parent)

        self.menu = QMenu()
        self._status_action = self.menu.addAction("tpfan — keine Daten")
        self._status_action.setEnabled(False)
        self._max_action = self.menu.addAction("Max: —")
        self._max_action.setEnabled(False)
        self._level_action = self.menu.addAction("Level: —")
        self._level_action.setEnabled(False)
        self.menu.addSeparator()

        mode_menu = self.menu.addMenu("Modus")
        self._mode_group = QActionGroup(self.menu)
        self._mode_group.setExclusive(True)
        self._mode_actions: dict[str, QAction] = {}
        for key, label in self.MODES:
            a = QAction(label, mode_menu, checkable=True)
            a.triggered.connect(lambda _=False, k=key: self.modeRequested.emit(k))
            self._mode_group.addAction(a)
            mode_menu.addAction(a)
            self._mode_actions[key] = a

        self._level_menu = self.menu.addMenu("Manuelles Level")
        for lvl in self.LEVELS:
            a = QAction(lvl, self._level_menu)
            a.triggered.connect(lambda _=False, v=lvl: self.levelRequested.emit(v))
            self._level_menu.addAction(a)
        self._level_menu.setEnabled(False)

        self.menu.addSeparator()
        open_act = self.menu.addAction("Öffnen")
        open_act.triggered.connect(self.openRequested)
        quit_act = self.menu.addAction("Beenden")
        quit_act.triggered.connect(self.quitRequested)

        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._on_activated)
        self.tray.setToolTip("tpfan — Daemon nicht verbunden")
        self.apply_mode(self._mode)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.openRequested.emit()

    def show(self) -> None:
        self.tray.show()

    def apply_mode(self, mode: str) -> None:
        self._mode = mode
        for key, a in self._mode_actions.items():
            a.setChecked(key == mode)
        self._level_menu.setEnabled(mode == "manual")
        self._refresh_status_header()
        self._refresh_tooltip()

    def apply_curve(self, curve_points) -> None:
        self._curve_points = list(curve_points or [])
        self._refresh_status_header()
        self._refresh_tooltip()

    def _refresh_status_header(self) -> None:
        self._status_action.setText(
            f"Modus: {format_mode_label(self._mode, self._curve_points)}"
        )

    def apply_tick(self, p: TickPayload) -> None:
        self._last_payload = p
        self.tray.setIcon(make_level_icon(p.level))
        if p.temps:
            name, val = max(p.temps.items(), key=lambda kv: kv[1])
            self._max_action.setText(f"Max: {name} {val:.1f} °C")
        else:
            self._max_action.setText("Max: —")
        rpm = p.fans[0][0] if p.fans else None
        if rpm is not None:
            self._level_action.setText(f"Level: {p.level}  ·  {rpm} RPM")
        else:
            self._level_action.setText(f"Level: {p.level}")
        self._refresh_tooltip()

    def set_connected(self, ok: bool) -> None:
        if not ok:
            self.tray.setToolTip("tpfan — Daemon nicht verbunden")
            self._status_action.setText("tpfan — Daemon nicht verbunden")
            self.tray.setIcon(make_level_icon("auto"))
        else:
            self._refresh_status_header()
            self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        mode_label = format_mode_label(self._mode, self._curve_points)
        p = self._last_payload
        if p is None:
            self.tray.setToolTip(f"tpfan — Modus: {mode_label}")
            return
        lines = [f"tpfan — Modus: {mode_label}"]
        if p.temps:
            name, val = max(p.temps.items(), key=lambda kv: kv[1])
            lines.append(f"Max: {name} {val:.1f} °C")
        rpm = p.fans[0][0] if p.fans else None
        if rpm is not None:
            lines.append(f"Level: {p.level} · {rpm} RPM")
        else:
            lines.append(f"Level: {p.level}")
        self.tray.setToolTip("\n".join(lines))
