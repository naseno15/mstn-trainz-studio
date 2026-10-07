"""Auto Tune right dock — Mesh Editor-style editorDock chrome."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ...lib.engine_tuner.autotune import (
    SHAPE_PRESETS,
    AccelResult,
    AutogenParams,
    ResistParams,
    VehicleResist,
    acceleration_time,
    balancing_speeds,
    estimate_max_te_kn,
    generate_throttle_power,
)
from ...lib.engine_tuner.config_io import EngineConfig

from ..frost import FROST_CONTENT_MARGINS, FrostGlassFrame
from ..smooth_scroll import enable_smooth_scroll_area

# Auto Tune body scroll — heavier coast = longer glide (“หน่วง”)
_SCROLL_COAST = 0.972


class _NoWheelFilter(QObject):
    """Block wheel on spins so scrolling the dock doesn't nudge values (Mesh Editor)."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and isinstance(
            obj, (QSpinBox, QDoubleSpinBox)
        ):
            event.ignore()
            return True
        return False


_NO_WHEEL = _NoWheelFilter()


def _spin(lo: float, hi: float, step: float, val: float, *, decimals: int = 2) -> QDoubleSpinBox:
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(decimals)
    s.setValue(val)
    s.setMinimumWidth(72)
    s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    s.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    s.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    s.installEventFilter(_NO_WHEEL)
    return s


def _ispin(lo: int, hi: int, val: int) -> QSpinBox:
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(val)
    s.setMinimumWidth(72)
    s.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    s.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
    s.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    s.installEventFilter(_NO_WHEEL)
    return s


def _field_cell(label: str, widget: QWidget) -> QWidget:
    cell = QWidget()
    h = QHBoxLayout(cell)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(6)
    lab = QLabel(label)
    lab.setMinimumWidth(64)
    h.addWidget(lab)
    h.addWidget(widget, 1)
    return cell


def _pair_row(
    lay: QVBoxLayout,
    a_label: str,
    a_w: QWidget,
    b_label: str,
    b_w: QWidget,
) -> None:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.addWidget(_field_cell(a_label, a_w), 1)
    row.addWidget(_field_cell(b_label, b_w), 1)
    lay.addLayout(row)


def _solo_row(lay: QVBoxLayout, label: str, widget: QWidget) -> None:
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(12)
    row.addWidget(_field_cell(label, widget), 1)
    row.addStretch(1)
    lay.addLayout(row)


def _full_row(lay: QVBoxLayout, widget: QWidget) -> None:
    lay.addWidget(widget)


def _card(outer: QVBoxLayout, title: str) -> QVBoxLayout:
    """Left-sidebar statsCard well — text sits on frosted plate, not raw black."""
    card = QFrame()
    card.setObjectName("statsCard")
    body = QVBoxLayout(card)
    body.setContentsMargins(10, 8, 10, 10)
    body.setSpacing(8)
    lab = QLabel(title)
    lab.setStyleSheet("font-weight: 650;")
    body.addWidget(lab)
    outer.addWidget(card)
    return body


class AutotunePanel(FrostGlassFrame):
    """Right Auto Tune dock — Mesh left-sidebar frost (`sidePanel` + statsCard)."""

    applied = Signal(object, object, bool, bool)
    closed = Signal()

    PANEL_W = 500

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, radius=14.0)
        self.setObjectName("sidePanel")
        self.setMinimumWidth(0)
        self.setMaximumWidth(520)
        self.setFixedWidth(self.PANEL_W)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.cfg: EngineConfig | None = None
        self._theme = "dark"
        self._build_shell()
        self.set_frost(None, dark=True)

    def _build_shell(self) -> None:
        from ..app import SideTabStrip

        title = QLabel("Auto Tune")
        title.setObjectName("brandTitle")
        title.setStyleSheet("font-weight: 650; font-size: 15px;")
        tip = QLabel("TE generate · Davis resistance · Preview then Apply")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        tip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self._tab_strip = SideTabStrip(("Generate", "Friction"))
        self._stack = QStackedWidget()
        self._stack.setObjectName("sideTabStack")
        self._tab_strip.index_changed.connect(self._on_tab)

        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body = QWidget()
        body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_lay.addWidget(self._stack)
        scroll.setWidget(body)
        enable_smooth_scroll_area(scroll, coast=_SCROLL_COAST)
        self._scroll = scroll
        self._tab_strip.index_changed.connect(self._sync_scroll_body)

        self.summary = QLabel("")
        self.summary.setObjectName("mutedTip")
        self.summary.setWordWrap(True)
        self.summary.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        preview_btn = QPushButton("Preview")
        preview_btn.setMinimumHeight(36)
        preview_btn.clicked.connect(self._preview)
        apply_btn = QPushButton("Apply")
        apply_btn.setObjectName("accentBtn")
        apply_btn.setMinimumHeight(40)
        apply_btn.setDefault(True)
        apply_btn.clicked.connect(self._apply)
        foot = QHBoxLayout()
        foot.setSpacing(6)
        foot.addWidget(preview_btn, 1)
        foot.addWidget(apply_btn, 1)

        lay = QVBoxLayout(self)
        # same inset as Engine left sidebar (frost soft shadow room)
        lay.setContentsMargins(*FROST_CONTENT_MARGINS)
        lay.setSpacing(10)
        lay.addWidget(title)
        lay.addWidget(tip)
        lay.addWidget(self._tab_strip)
        lay.addWidget(scroll, 1)
        lay.addWidget(self.summary)
        sep = QFrame()
        sep.setObjectName("separatorLine")
        lay.addWidget(sep)
        lay.addLayout(foot)
        QTimer.singleShot(0, self._sync_scroll_body)

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        self.set_frost(None, dark=self._theme != "light")

    def _on_tab(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._sync_scroll_body()

    def _sync_scroll_body(self, *_args) -> None:
        """Size scroll body to the active page (same idea as Mesh Editor dock)."""
        page = self._stack.currentWidget()
        body = self._scroll.widget()
        if page is None or body is None:
            return
        page.adjustSize()
        hint = page.sizeHint()
        body.setMinimumHeight(max(hint.height(), page.minimumSizeHint().height(), 1))
        body.adjustSize()

    def bind(
        self,
        cfg: EngineConfig,
        *,
        graph_max_kmh: float,
        graph_max_kn: float,
        current_resist: ResistParams | None,
    ) -> None:
        self.cfg = cfg
        keep = self._tab_strip.current_index()
        while self._stack.count():
            w = self._stack.widget(0)
            self._stack.removeWidget(w)
            w.deleteLater()
        for page in (
            self._build_generate(graph_max_kmh, graph_max_kn),
            self._build_friction(current_resist),
        ):
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            self._stack.addWidget(page)
        self._tab_strip.set_index(keep, animate=False, emit=False)
        self._stack.setCurrentIndex(keep)
        self.summary.setText("")
        QTimer.singleShot(0, self._sync_scroll_body)

    def _build_generate(self, graph_max_kmh: float, graph_max_kn: float) -> QWidget:
        assert self.cfg is not None
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(10)
        motor = self.cfg.motor
        max_spd = float(motor.get("maxspeed", graph_max_kmh / 3.6)) * 3.6
        if max_spd <= 1:
            max_spd = graph_max_kmh
        peak = 0.0
        for pts in self.cfg.throttle_power.values():
            for _, te in pts:
                peak = max(peak, te)
        if peak <= 0:
            peak = graph_max_kn

        power = _card(lay, "Max Power")
        self.power_kw = _spin(1, 20000, 50, 2000, decimals=1)
        self.power_coeff = _spin(0.1, 5, 0.1, 1.5, decimals=2)
        _pair_row(power, "kW", self.power_kw, "Coeff", self.power_coeff)

        speed = _card(lay, "Max Speed")
        self.speed_kmh = _spin(10, 400, 5, max_spd, decimals=1)
        self.speed_coeff = _spin(0.1, 5, 0.1, 1.0, decimals=2)
        _pair_row(speed, "km/h", self.speed_kmh, "Coeff", self.speed_coeff)

        adh = _card(lay, "Adhesion Limit")
        self.max_te = _spin(1, 1000, 5, peak, decimals=1)
        _solo_row(adh, "Max TE (kN)", self.max_te)
        self.est_te = QCheckBox("Estimate from adhesion weight")
        self.est_te.toggled.connect(self._toggle_est)
        _full_row(adh, self.est_te)
        self.friction_pct = _spin(5, 50, 1, 30, decimals=1)
        self.adhesion_t = _spin(1, 500, 1, 72, decimals=1)
        self.friction_pct.setEnabled(False)
        self.adhesion_t.setEnabled(False)
        self.friction_pct.valueChanged.connect(lambda _v: self._est_maybe())
        self.adhesion_t.valueChanged.connect(lambda _v: self._est_maybe())
        _pair_row(adh, "Friction %", self.friction_pct, "Adhesion (t)", self.adhesion_t)

        curve = _card(lay, "Curve")
        self.notch_coeff = _spin(0, 5, 0.1, 1.0, decimals=2)
        self.node_count = _ispin(2, 39, 20)
        _pair_row(curve, "Notch coeff", self.notch_coeff, "# of nodes", self.node_count)
        self.fit_cb = QCheckBox("Fit graph in window")
        self.fit_cb.setChecked(True)
        self.regen_cb = QCheckBox("Regenerate throttle curves")
        self.regen_cb.setChecked(True)
        _full_row(curve, self.fit_cb)
        _full_row(curve, self.regen_cb)
        tip = QLabel(
            "TE = Power×308/Speed. Diesel coeff ~1–2, electric ~2–3. "
            "Uncheck regenerate to only update resistance."
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        _full_row(curve, tip)
        lay.addStretch(1)
        return w

    def _build_friction(self, current: ResistParams | None) -> QWidget:
        assert self.cfg is not None
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(10)
        motor = self.cfg.motor
        eng_area = float(motor.get("surface-area", 10.0))
        eng_cd = float(motor.get("air-drag-coefficient", 0.0017))
        eng_axles = int(motor.get("axle-count", 4) or 4)
        eng_fric = float(motor.get("moving-friction-coefficient", 0.03))

        if current is not None:
            e, c = current.engine, current.cars
            grade = current.grade_percent
        else:
            e = VehicleResist(72.0, min(eng_area, 15.0), eng_cd, eng_axles, eng_fric, 1)
            c = VehicleResist(40.0, 8.0, 0.0005, 4, 0.045, 10)
            grade = 0.0

        eng = _card(lay, "Engine")
        self.eng_mass = _spin(1, 500, 1, e.mass_t, decimals=1)
        self.eng_area = _spin(0.1, 50, 0.5, e.area_m2, decimals=2)
        _pair_row(eng, "Mass (t)", self.eng_mass, "Area (m²)", self.eng_area)
        self.eng_shape = QComboBox()
        self.eng_shape.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for name in SHAPE_PRESETS:
            self.eng_shape.addItem(f"{name} ({SHAPE_PRESETS[name]})", SHAPE_PRESETS[name])
        self._select_shape(self.eng_shape, e.drag_cd)
        self.eng_axles = _ispin(1, 20, e.axles)
        _pair_row(eng, "Shape", self.eng_shape, "Axles", self.eng_axles)
        self.eng_fric = _spin(0.001, 0.2, 0.001, e.fric_coeff, decimals=4)
        _solo_row(eng, "Fric coeff", self.eng_fric)

        cars = _card(lay, "Cars")
        self.car_count = _ispin(0, 200, c.count)
        self.car_mass = _spin(1, 200, 1, c.mass_t, decimals=1)
        _pair_row(cars, "× count", self.car_count, "Mass (t)", self.car_mass)
        self.car_area = _spin(0.1, 50, 0.5, c.area_m2, decimals=2)
        self.car_shape = QComboBox()
        self.car_shape.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        for name in SHAPE_PRESETS:
            self.car_shape.addItem(f"{name} ({SHAPE_PRESETS[name]})", SHAPE_PRESETS[name])
        self._select_shape(self.car_shape, c.drag_cd)
        _pair_row(cars, "Area (m²)", self.car_area, "Shape", self.car_shape)
        self.car_axles = _ispin(1, 20, c.axles)
        self.car_fric = _spin(0.001, 0.2, 0.001, c.fric_coeff, decimals=4)
        _pair_row(cars, "Axles", self.car_axles, "Fric coeff", self.car_fric)

        track = _card(lay, "Track & acceleration")
        self.grade = _spin(-5, 10, 0.1, grade, decimals=2)
        self.accel_v0 = _spin(0, 300, 5, 0, decimals=1)
        _pair_row(track, "Grade %", self.grade, "From km/h", self.accel_v0)
        self.accel_v1 = _spin(0, 300, 5, 100, decimals=1)
        self.accel_notch = _ispin(0, 8, 8)
        _pair_row(track, "to km/h", self.accel_v1, "on notch", self.accel_notch)
        self.show_resist_cb = QCheckBox("Show resistance overlay")
        self.show_resist_cb.setChecked(True)
        _full_row(track, self.show_resist_cb)
        lay.addStretch(1)
        return w

    @staticmethod
    def _select_shape(combo: QComboBox, cd: float) -> None:
        best = 0
        best_d = 1e9
        for i in range(combo.count()):
            d = abs(float(combo.itemData(i)) - cd)
            if d < best_d:
                best_d = d
                best = i
        combo.setCurrentIndex(best)

    def _toggle_est(self, on: bool) -> None:
        self.friction_pct.setEnabled(on)
        self.adhesion_t.setEnabled(on)
        self.max_te.setEnabled(not on)
        if on:
            self._sync_est_te()

    def _est_maybe(self) -> None:
        if self.est_te.isChecked():
            self._sync_est_te()

    def _sync_est_te(self) -> None:
        te = estimate_max_te_kn(
            friction_pct=self.friction_pct.value(),
            adhesion_weight_t=self.adhesion_t.value(),
        )
        self.max_te.blockSignals(True)
        self.max_te.setValue(te)
        self.max_te.blockSignals(False)

    def _autogen_params(self) -> AutogenParams:
        assert self.cfg is not None
        if self.est_te.isChecked():
            self._sync_est_te()
        max_n = int(self.cfg.motor.get("throttle-notches", 8) or 8)
        return AutogenParams(
            max_power_kw=self.power_kw.value(),
            max_speed_kmh=self.speed_kmh.value(),
            max_te_kn=self.max_te.value(),
            power_coeff=self.power_coeff.value(),
            speed_coeff=self.speed_coeff.value(),
            notch_coeff=self.notch_coeff.value(),
            node_count=self.node_count.value(),
            max_notch=max_n,
        )

    def _resist_params(self) -> ResistParams:
        return ResistParams(
            engine=VehicleResist(
                self.eng_mass.value(),
                self.eng_area.value(),
                float(self.eng_shape.currentData()),
                self.eng_axles.value(),
                self.eng_fric.value(),
                1,
            ),
            cars=VehicleResist(
                self.car_mass.value(),
                self.car_area.value(),
                float(self.car_shape.currentData()),
                self.car_axles.value(),
                self.car_fric.value(),
                self.car_count.value(),
            ),
            grade_percent=self.grade.value(),
        )

    def _preview(self) -> None:
        assert self.cfg is not None
        curves = generate_throttle_power(self._autogen_params())
        rp = self._resist_params()
        hits = balancing_speeds(curves, rp, max_speed_kmh=self.speed_kmh.value())
        notch = self.accel_notch.value()
        acc: AccelResult = acceleration_time(
            curves.get(notch, []),
            rp,
            v0_kmh=self.accel_v0.value(),
            v1_kmh=self.accel_v1.value(),
        )
        parts = [
            f"N{max(curves)} TE0 {curves[max(curves)][0][1]:.1f} kN",
            f"{self.node_count.value()} nodes",
        ]
        if hits:
            bal = ", ".join(f"N{h.notch}@{h.speed_kmh:.0f}" for h in hits[-3:])
            parts.append(bal)
        if acc.time_s is not None:
            parts.append(f"accel {acc.time_s:.1f}s")
        elif acc.note:
            parts.append(acc.note)
        self.summary.setText(" · ".join(parts))

    def _apply(self) -> None:
        assert self.cfg is not None
        p = self._autogen_params()
        if self.regen_cb.isChecked():
            if p.max_power_kw <= 0 or p.max_te_kn <= 0 or p.max_speed_kmh <= 0:
                QMessageBox.warning(self, "Auto Tune", "Power, TE and speed must be > 0.")
                return
            curves = generate_throttle_power(p)
        else:
            curves = {n: list(pts) for n, pts in self.cfg.throttle_power.items()}
        resist = self._resist_params()
        fit = self.fit_cb.isChecked() and self.regen_cb.isChecked()
        show = self.show_resist_cb.isChecked()
        self.applied.emit(curves, resist, fit, show)
