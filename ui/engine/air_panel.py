"""Widget fallback for the air-brake Auto Tune dock. QML paints the same fields."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...lib.engine_tuner.airtune import AirTune

_ROWS = (
    ("BP release (bar)", "bp_rel", 0.0, 20.0, 0.1),
    ("BP initial (bar)", "bp_ini", 0.0, 20.0, 0.1),
    ("BP full (bar)", "bp_full", 0.0, 20.0, 0.1),
    ("BC full (bar)", "bc_full", 0.0, 20.0, 0.1),
    ("MR (bar)", "mr", 0.0, 20.0, 0.1),
    ("MR start (bar)", "mr_start", 0.0, 20.0, 0.1),
    ("BC start (bar)", "bc_start", 0.0, 20.0, 0.1),
    ("MR volume", "vol_mr", 0.0, 500.0, 1.0),
    ("Aux volume", "vol_aux", 0.0, 500.0, 0.5),
    ("BC volume", "vol_bc", 0.0, 500.0, 0.5),
    ("Pipe volume", "vol_pipe", 0.0, 500.0, 0.5),
    ("Ind BC volume", "vol_ind", 0.0, 500.0, 0.5),
    ("Brake ratio", "brake_ratio", 0.0, 1_000_000.0, 100.0),
    ("Max decel (mm/s²)", "max_decel", 0.0, 20000.0, 100.0),
    ("Speed (km/h)", "speed_kmh", 0.0, 300.0, 5.0),
    ("Mass (t)", "mass_t", 1.0, 5000.0, 1.0),
    ("Grade %", "grade", -10.0, 10.0, 0.1),
)


class AirPanel(QWidget):
    changed = Signal()
    preview_clicked = Signal()
    apply_clicked = Signal()
    preset_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(500)
        self._air: AirTune | None = None
        self._spins: dict[str, QDoubleSpinBox] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        title = QLabel("Air brake")
        title.setObjectName("welcomeTitle")
        root.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        form = QFormLayout(body)
        for label, key, lo, hi, step in _ROWS:
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            spin.setDecimals(2 if step < 1 else 1)
            spin.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
            spin.editingFinished.connect(self._push)
            self._spins[key] = spin
            form.addRow(label, spin)
        self._advanced = QCheckBox("Write train-pipe flow rates")
        self._advanced.toggled.connect(self._push)
        self._emergency = QCheckBox("Emergency")
        self._emergency.toggled.connect(self._push)
        form.addRow(self._advanced)
        form.addRow(self._emergency)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)
        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setObjectName("mutedTip")
        root.addWidget(self.summary)
        row = QVBoxLayout()
        preset = QPushButton("JNR 5 bar preset")
        preset.clicked.connect(self.preset_clicked.emit)
        preview = QPushButton("Preview")
        preview.clicked.connect(self.preview_clicked.emit)
        apply = QPushButton("Apply")
        apply.clicked.connect(self.apply_clicked.emit)
        row.addWidget(preset)
        row.addWidget(preview)
        row.addWidget(apply)
        root.addLayout(row)

    def load(self, air: AirTune) -> None:
        self._air = air
        for key, spin in self._spins.items():
            spin.blockSignals(True)
            spin.setValue(float(getattr(air, key)))
            spin.blockSignals(False)
        self._advanced.blockSignals(True)
        self._emergency.blockSignals(True)
        self._advanced.setChecked(air.advanced)
        self._emergency.setChecked(air.emergency)
        self._advanced.blockSignals(False)
        self._emergency.blockSignals(False)

    def _push(self) -> None:
        air = self._air
        if air is None:
            return
        for key, spin in self._spins.items():
            setattr(air, key, float(spin.value()))
        air.advanced = self._advanced.isChecked()
        air.emergency = self._emergency.isChecked()
        air.sim_line = ""
        self.changed.emit()
