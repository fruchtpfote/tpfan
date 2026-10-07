from __future__ import annotations
import argparse
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .ipc.dbus_client import make_client
from .main_window import MainWindow
from .tray import TrayController

# Netz für verpasste PropertiesChanged-Signale (z. B. nach einem
# Daemon-Neustart). Bewusst träge: jeder Property-Read kostet den Daemon
# einen Sensor-Sweep über I2C/ACPI.
RESYNC_INTERVAL_MS = 30_000


class TraySync:
    """Hält Mode und Curve im Tray mit dem Daemon synchron.

    Liest die Properties NICHT im Tick-Takt: Mode und Curve ändern sich nur
    durch Kommandos, und die meldet der Daemon per PropertiesChanged. Ein
    sekündlicher Read kostete ihn dagegen zwei komplette Sensor-Sweeps und
    damit die Hälfte seiner Idle-CPU-Last.
    """

    def __init__(self, client, tray):
        self._client = client
        self._tray = tray

    def resync(self) -> None:
        mode = self._client.get("Mode")
        if mode:
            self._tray.apply_mode(str(mode))
        try:
            self._tray.apply_curve(self._client.get("Curve") or [])
        except Exception:
            self._tray.apply_curve([])

    def on_tick(self, payload) -> None:
        self._tray.apply_tick(payload)

    def on_connected(self, ok: bool) -> None:
        self._tray.set_connected(ok)
        if ok:
            self.resync()

    def on_props(self, changed: dict) -> None:
        if "Mode" in changed or "Curve" in changed:
            self.resync()


def _toggle_window(win):
    if win.isVisible() and not win.isMinimized() and win.isActiveWindow():
        win.hide()
        return
    win.show()
    win.setWindowState(win.windowState() & ~Qt.WindowState.WindowMinimized)
    win.raise_()
    win.activateWindow()


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="tpfan-gui",
                                description="tpfan ThinkPad-Lüfter-Steuerung GUI")
    p.add_argument("--tray", action="store_true",
                   help="nur im System-Tray starten, Hauptfenster zunächst nicht öffnen")
    # Qt schluckt eigene Argumente weiter unten; unbekannte werden an Qt
    # weitergereicht, damit z. B. -style/-platform funktionieren.
    return p.parse_known_args(argv[1:])


def main() -> int:
    args, qt_argv = _parse_args(sys.argv)
    app = QApplication([sys.argv[0], *qt_argv])
    app.setOrganizationName("tpfan")
    app.setApplicationName("tpfan")
    app.setDesktopFileName("tpfan-gui")
    app.setWindowIcon(QIcon.fromTheme("tpfan"))
    app.setQuitOnLastWindowClosed(False)

    client = make_client()
    win = MainWindow(client)
    win.resize(700, 500)

    tray = TrayController(app)

    def safe_call(fn, *args):
        try:
            fn(*args)
        except Exception as e:
            QMessageBox.warning(win, "tpfan", MainWindow._friendly_error(e))

    def on_mode(mode: str):
        safe_call(client.set_mode, mode)
        win.modes.set_mode_state(mode)
        tray.apply_mode(mode)

    def on_level(lvl: str):
        safe_call(client.set_manual_level, lvl)

    tray.modeRequested.connect(on_mode)
    tray.levelRequested.connect(on_level)
    tray.openRequested.connect(lambda: _toggle_window(win))
    tray.quitRequested.connect(app.quit)

    sync = TraySync(client, tray)
    client.tickReceived.connect(sync.on_tick)
    client.connected.connect(sync.on_connected)
    client.propertiesChanged.connect(sync.on_props)

    resync_timer = QTimer(app)
    resync_timer.setInterval(RESYNC_INTERVAL_MS)
    resync_timer.timeout.connect(sync.resync)
    resync_timer.start()

    tray.show()
    if not args.tray:
        win.show()

    run_qt_loop = getattr(app, "exec")
    return run_qt_loop()


if __name__ == "__main__":
    sys.exit(main())
