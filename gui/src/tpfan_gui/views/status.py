from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QFormLayout, QGroupBox,
                              QLabel, QTableWidget, QTableWidgetItem,
                              QPushButton, QHBoxLayout, QHeaderView)


LEVEL_ORDER = ["0", "1", "2", "3", "4", "5", "6", "7", "auto", "disengaged"]


@dataclass
class LevelRpmTracker:
    """Sammelt RPM-Beobachtungen pro Lüfter-Level aus dem Tick-Stream."""
    last: dict[str, int] = field(default_factory=dict)
    minv: dict[str, int] = field(default_factory=dict)
    maxv: dict[str, int] = field(default_factory=dict)
    count: dict[str, int] = field(default_factory=dict)

    def record(self, level: str, rpm: int) -> None:
        if not level or rpm < 0:
            return
        self.last[level] = rpm
        self.count[level] = self.count.get(level, 0) + 1
        if level not in self.minv or rpm < self.minv[level]:
            self.minv[level] = rpm
        if level not in self.maxv or rpm > self.maxv[level]:
            self.maxv[level] = rpm

    def rows(self) -> list[tuple[str, str, str, str]]:
        out: list[tuple[str, str, str, str]] = []
        for lvl in LEVEL_ORDER:
            if lvl in self.last:
                out.append((
                    lvl,
                    str(self.last[lvl]),
                    f"{self.minv[lvl]} / {self.maxv[lvl]}",
                    str(self.count[lvl]),
                ))
            else:
                out.append((lvl, "—", "—", "0"))
        return out


def _fmt_curve(points: list) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for p in points:
        try:
            t = float(p[0])
            lvl = int(p[1])
            rows.append((f"{t:.1f} °C", str(lvl)))
        except (TypeError, ValueError, IndexError):
            continue
    return rows


class StatusView(QWidget):
    """Read-only Übersicht der aktuell gesetzten Daemon-Einstellungen."""

    def __init__(self, client, parent=None):
        super().__init__(parent)
        self._client = client
        self.rpm_tracker = LevelRpmTracker()

        root = QVBoxLayout(self)

        gb_general = QGroupBox("Aktuelle Einstellungen")
        form = QFormLayout(gb_general)
        self.mode_lbl = QLabel("—")
        self.level_lbl = QLabel("—")
        self.failsafe_lbl = QLabel("—")
        self.version_lbl = QLabel("—")
        form.addRow("Modus:", self.mode_lbl)
        form.addRow("Aktueller Level:", self.level_lbl)
        form.addRow("Failsafe-Schwelle:", self.failsafe_lbl)
        form.addRow("Daemon-Version:", self.version_lbl)
        root.addWidget(gb_general)

        gb_curve = QGroupBox("Aktive Kurve")
        cl = QVBoxLayout(gb_curve)
        self.sensors_lbl = QLabel("Sensoren: —")
        self.sensors_lbl.setWordWrap(True)
        cl.addWidget(self.sensors_lbl)
        self.curve_table = QTableWidget(0, 2)
        self.curve_table.setHorizontalHeaderLabels(["Temperatur", "Level"])
        self.curve_table.verticalHeader().setVisible(False)
        self.curve_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.curve_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.curve_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.curve_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.curve_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cl.addWidget(self.curve_table)
        root.addWidget(gb_curve)

        gb_rpm = QGroupBox("Beobachtete Drehzahlen pro Level")
        rl = QVBoxLayout(gb_rpm)
        hint = QLabel("Werte aus dem laufenden Tick-Stream — RPM-zu-Level-Zuordnung ist nicht "
                      "fest in der Firmware definiert und kann variieren.")
        hint.setWordWrap(True)
        rl.addWidget(hint)
        self.rpm_table = QTableWidget(0, 4)
        self.rpm_table.setHorizontalHeaderLabels(["Level", "RPM (zuletzt)", "min / max", "n"])
        self.rpm_table.verticalHeader().setVisible(False)
        self.rpm_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.rpm_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.rpm_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.rpm_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rpm_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        rl.addWidget(self.rpm_table)
        root.addWidget(gb_rpm)

        row = QHBoxLayout()
        self.reset_rpm_btn = QPushButton("RPM-Statistik zurücksetzen")
        self.reset_rpm_btn.clicked.connect(self._reset_rpm_stats)
        self.refresh_btn = QPushButton("Aktualisieren")
        self.refresh_btn.clicked.connect(self.refresh)
        row.addWidget(self.reset_rpm_btn)
        row.addStretch(1)
        row.addWidget(self.refresh_btn)
        root.addLayout(row)

    @staticmethod
    def _autosize_table(t: QTableWidget) -> None:
        h = t.horizontalHeader().height()
        for i in range(t.rowCount()):
            h += t.rowHeight(i)
        h += 2 * t.frameWidth()
        t.setFixedHeight(h)

    def record_tick(self, payload) -> None:
        try:
            rpm = int(payload.fans[0][0])
        except (AttributeError, IndexError, TypeError, ValueError):
            return
        level = getattr(payload, "level", "")
        self.rpm_tracker.record(str(level), rpm)

    def _reset_rpm_stats(self) -> None:
        self.rpm_tracker = LevelRpmTracker()
        self._refresh_rpm_table()

    def refresh(self) -> None:
        self._set_label(self.mode_lbl, self._get("Mode"))
        self._set_label(self.level_lbl, self._get("CurrentLevel"))
        fs = self._get("FailsafeTemp")
        self.failsafe_lbl.setText(f"{float(fs):.1f} °C" if fs is not None else "—")
        self._set_label(self.version_lbl, self._get("DaemonVersion"))

        sensors = self._get("CurveSensors") or []
        self.sensors_lbl.setText("Sensoren: " + (", ".join(sensors) if sensors else "—"))

        rows = _fmt_curve(self._get("Curve") or [])
        self.curve_table.setRowCount(len(rows))
        for i, (t, l) in enumerate(rows):
            it_t = QTableWidgetItem(t)
            it_l = QTableWidgetItem(l)
            it_t.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            it_l.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.curve_table.setItem(i, 0, it_t)
            self.curve_table.setItem(i, 1, it_l)
        self._autosize_table(self.curve_table)

        self._refresh_rpm_table()

    def _refresh_rpm_table(self) -> None:
        rows = self.rpm_tracker.rows()
        self.rpm_table.setRowCount(len(rows))
        for i, cells in enumerate(rows):
            for j, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.rpm_table.setItem(i, j, item)
        self._autosize_table(self.rpm_table)

    def _get(self, name: str) -> Any:
        try:
            return self._client.get(name)
        except Exception:
            return None

    @staticmethod
    def _set_label(lbl: QLabel, value: Any) -> None:
        lbl.setText(str(value) if value not in (None, "") else "—")
