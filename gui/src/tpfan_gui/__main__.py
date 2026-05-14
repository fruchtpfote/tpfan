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

    icon = QIcon.fromTheme("fan")
    if icon.isNull():
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        from PyQt6.QtCore import Qt
        pm = QPixmap(32, 32)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(70, 130, 180))
        painter.setPen(QColor(255, 255, 255))
        painter.drawEllipse(2, 2, 28, 28)
        painter.end()
        icon = QIcon(pm)
    tray = QSystemTrayIcon(icon)
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
