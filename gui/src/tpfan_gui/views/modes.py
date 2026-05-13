from __future__ import annotations
from PyQt6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton,
                              QDoubleSpinBox, QComboBox, QLabel, QGroupBox)
from PyQt6.QtCore import pyqtSignal


class ModesPanel(QWidget):
    modeRequested = pyqtSignal(str)
    manualLevelRequested = pyqtSignal(str)
    failsafeRequested = pyqtSignal(float)

    def __init__(self, profiles: list[str], parent=None):
        super().__init__(parent)
        root = QVBoxLayout(self)

        gb_modes = QGroupBox("Modus")
        ml = QHBoxLayout(gb_modes)
        self.auto_btn   = QPushButton("Auto")
        self.curve_btn  = QPushButton("Kurve")
        self.manual_btn = QPushButton("Manuell")
        for b, name in [(self.auto_btn, "auto"), (self.curve_btn, "curve"), (self.manual_btn, "manual")]:
            b.clicked.connect(lambda _=False, n=name: self.modeRequested.emit(n))
            ml.addWidget(b)
        root.addWidget(gb_modes)

        gb_man = QGroupBox("Manuelles Level")
        manl = QHBoxLayout(gb_man)
        for lvl in ["0", "1", "2", "3", "4", "5", "6", "7", "disengaged"]:
            b = QPushButton(lvl)
            b.clicked.connect(lambda _=False, v=lvl: self.manualLevelRequested.emit(v))
            manl.addWidget(b)
        root.addWidget(gb_man)

        gb_prof = QGroupBox("Profil")
        pl = QHBoxLayout(gb_prof)
        self.profile_combo = QComboBox()
        self.profile_combo.addItems(profiles)
        self.apply_profile_btn = QPushButton("Anwenden")
        self.apply_profile_btn.clicked.connect(self._on_apply_profile)
        pl.addWidget(self.profile_combo); pl.addWidget(self.apply_profile_btn)
        root.addWidget(gb_prof)

        gb_fs = QGroupBox("Failsafe (°C)")
        fl = QHBoxLayout(gb_fs)
        self.failsafe_spin = QDoubleSpinBox()
        self.failsafe_spin.setRange(40.0, 110.0)
        self.failsafe_spin.setDecimals(1)
        self.failsafe_spin.setValue(95.0)
        self.failsafe_spin.editingFinished.connect(
            lambda: self.failsafeRequested.emit(self.failsafe_spin.value()))
        fl.addWidget(QLabel("Schwelle:")); fl.addWidget(self.failsafe_spin)
        root.addWidget(gb_fs)

    def _on_apply_profile(self):
        name = self.profile_combo.currentText()
        if name:
            self.modeRequested.emit(f"profile:{name}")
