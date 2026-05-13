from __future__ import annotations
import sys
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon

from .ipc.dbus_client import make_client
from .main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    client = make_client()
    win = MainWindow(client)
    win.resize(700, 500)

    tray = QSystemTrayIcon(QIcon.fromTheme("fan"))
    menu = QMenu()
    menu.addAction("Öffnen").triggered.connect(win.show)
    menu.addAction("Beenden").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.show()
    win.show()

    run_qt_loop = getattr(app, "exec")
    return run_qt_loop()


if __name__ == "__main__":
    sys.exit(main())
