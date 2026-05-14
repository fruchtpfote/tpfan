from __future__ import annotations
import sys
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .ipc.dbus_client import make_client
from .main_window import MainWindow
from .tray import TrayController


def _activate_window(win):
    win.show()
    win.raise_()
    win.activateWindow()


def main() -> int:
    app = QApplication(sys.argv)
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
    tray.openRequested.connect(lambda: _activate_window(win))
    tray.quitRequested.connect(app.quit)

    def _sync_mode_and_curve():
        mode = client.get("Mode")
        if mode:
            tray.apply_mode(str(mode))
        try:
            tray.apply_curve(client.get("Curve") or [])
        except Exception:
            tray.apply_curve([])

    def on_tick(payload):
        tray.apply_tick(payload)
        _sync_mode_and_curve()

    def on_connected(ok: bool):
        tray.set_connected(ok)
        if ok:
            _sync_mode_and_curve()

    def on_props(changed: dict):
        if "Mode" in changed or "Curve" in changed:
            _sync_mode_and_curve()

    client.tickReceived.connect(on_tick)
    client.connected.connect(on_connected)
    client.propertiesChanged.connect(on_props)

    tray.show()
    win.show()

    run_qt_loop = getattr(app, "exec")
    return run_qt_loop()


if __name__ == "__main__":
    sys.exit(main())
