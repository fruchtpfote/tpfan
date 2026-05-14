from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel
from ..ipc.dbus_client import TickPayload


class Dashboard(QWidget):
    SENSOR_ORDER = ["CPU", "GPU", "NVMe", "RAM", "WLAN", "MB-CPU", "MB-GPU", "ACPI"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._labels: dict[str, QLabel] = {}
        self._max: dict[str, float] = {}
        grid = QGridLayout(self)
        for row, name in enumerate(self.SENSOR_ORDER):
            grid.addWidget(QLabel(name + ":"), row, 0)
            v = QLabel("--")
            grid.addWidget(v, row, 1)
            self._labels[name] = v
        self.cpu_label = self._labels["CPU"]
        self.gpu_label = self._labels["GPU"]
        self.fan1_label = QLabel("--")
        self.fan2_label = QLabel("--")
        self.level_label = QLabel("--")
        row = len(self.SENSOR_ORDER)
        grid.addWidget(QLabel("Fan 1 RPM:"), row, 0); grid.addWidget(self.fan1_label, row, 1); row += 1
        grid.addWidget(QLabel("Fan 2 RPM:"), row, 0); grid.addWidget(self.fan2_label, row, 1); row += 1
        grid.addWidget(QLabel("Level:"),     row, 0); grid.addWidget(self.level_label, row, 1)

    def apply_tick(self, p: TickPayload) -> None:
        for name, lbl in self._labels.items():
            v = p.temps.get(name)
            if v is None:
                lbl.setText("--")
                continue
            self._max[name] = max(self._max.get(name, v), v)
            lbl.setText(f"{v:.1f} °C  (max {self._max[name]:.1f} °C)")
        self.fan1_label.setText(f"{p.fans[0][0]} ({p.fans[0][1]})" if len(p.fans) >= 1 else "--")
        self.fan2_label.setText(f"{p.fans[1][0]} ({p.fans[1][1]})" if len(p.fans) >= 2 else "--")
        self.level_label.setText(p.level)
