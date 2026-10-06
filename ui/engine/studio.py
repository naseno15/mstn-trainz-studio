"""Engine Tuner host — paged like Mesh (Tuner · Simulation · Parameters)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...lib.engine_tuner.config_io import (
    EngineConfig,
    config_to_text,
    load_config,
    load_config_from_text,
    save_config,
)
from ...lib.engine_tuner.physics import SimControls, SimParams, simulate
from ..smooth_scroll import enable_smooth_table
from ..theme import app_font
from .nav import EnginePageNav
from .pressure import (
    fmt_bar,
    fmt_kpa,
    fmt_native,
    from_bar,
    from_kpa,
    to_bar,
    to_kpa,
)
from .sidebar import EngineSidebar
from .throttle_panel import ThrottleEditor, apply_mpl_theme


class UndoStack:
    """ponytail: full-config snapshots. Ceiling 50."""

    def __init__(self, limit: int = 50) -> None:
        self.undo: list[EngineConfig] = []
        self.redo: list[EngineConfig] = []
        self.limit = limit
        self.locked = False

    def clear(self) -> None:
        self.undo.clear()
        self.redo.clear()

    def record(self, snapshot: EngineConfig) -> None:
        if self.locked:
            return
        self.undo.append(snapshot)
        if len(self.undo) > self.limit:
            del self.undo[0]
        self.redo.clear()

    def pop_undo(self, current: EngineConfig) -> EngineConfig | None:
        if self.locked or not self.undo:
            return None
        self.redo.append(current.clone())
        return self.undo.pop()

    def pop_redo(self, current: EngineConfig) -> EngineConfig | None:
        if self.locked or not self.redo:
            return None
        self.undo.append(current.clone())
        return self.redo.pop()


class DictEditor(QFrame):
    def __init__(
        self,
        title: str,
        on_change: Callable[[], None],
        begin_edit: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.on_change = on_change
        self.begin_edit = begin_edit or (lambda: None)
        self.data: dict[str, float] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        lab = QLabel(title)
        lab.setStyleSheet("font-weight: 650;")
        lay.addWidget(lab)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Value"])
        self.tree.setUniformRowHeights(True)
        enable_smooth_table(self.tree)
        self.tree.raise_()
        self.tree.itemDoubleClicked.connect(self._edit_cell)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(32)
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("−")
        del_btn.setFixedWidth(32)
        del_btn.clicked.connect(self.del_row)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        lay.addLayout(row)

    def set_data(self, data: dict[str, float]) -> None:
        self.data = dict(data)
        self.refresh()

    def get_data(self) -> dict[str, float]:
        return dict(self.data)

    def refresh(self) -> None:
        self.tree.clear()
        for k in sorted(self.data):
            item = QTreeWidgetItem([k, self._fmt(self.data[k])])
            item.setData(0, Qt.ItemDataRole.UserRole, k)
            self.tree.addTopLevelItem(item)

    @staticmethod
    def _fmt(v: float) -> str:
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return f"{v:g}"

    def add_row(self) -> None:
        self.begin_edit()
        key = f"new_key_{len(self.data)}"
        self.data[key] = 0.0
        self.refresh()
        self.on_change()

    def del_row(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        self.begin_edit()
        for item in items:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            self.data.pop(key, None)
        self.refresh()
        self.on_change()

    def _edit_cell(self, item: QTreeWidgetItem, column: int) -> None:
        old_key = item.data(0, Qt.ItemDataRole.UserRole)
        old_val = self.data[old_key]
        if column == 0:
            text, ok = QInputDialog.getText(self, "Edit key", "Key", text=str(old_key))
            if not ok or not text.strip() or text.strip() == old_key:
                return
            self.begin_edit()
            self.data[text.strip()] = self.data.pop(old_key)
        else:
            text, ok = QInputDialog.getText(self, "Edit value", "Value", text=self._fmt(old_val))
            if not ok:
                return
            try:
                value = float(text)
            except ValueError:
                QMessageBox.warning(self, "Invalid", "Enter a number.")
                return
            self.begin_edit()
            self.data[old_key] = value
        self.refresh()
        self.on_change()


class PressureEditor(QFrame):
    """pressure{} — Trainz native + live bar / kPa columns (edit any)."""

    def __init__(
        self,
        on_change: Callable[[], None],
        begin_edit: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("glassPanel")
        self.on_change = on_change
        self.begin_edit = begin_edit or (lambda: None)
        self.data: dict[str, float] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        lab = QLabel("pressure")
        lab.setStyleSheet("font-weight: 650;")
        head.addWidget(lab)
        tip = QLabel("Trainz ×1000 ≈ bar · 1 bar = 100 kPa · dbl-click any value")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        head.addWidget(tip, 1)
        lay.addLayout(head)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Key", "Trainz", "bar", "kPa"])
        self.tree.setUniformRowHeights(True)
        enable_smooth_table(self.tree)
        self.tree.raise_()
        self.tree.itemDoubleClicked.connect(self._edit_cell)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        add_btn = QPushButton("+")
        add_btn.setFixedWidth(32)
        add_btn.clicked.connect(self.add_row)
        del_btn = QPushButton("−")
        del_btn.setFixedWidth(32)
        del_btn.clicked.connect(self.del_row)
        row.addWidget(add_btn)
        row.addWidget(del_btn)
        row.addStretch(1)
        lay.addLayout(row)

    def set_data(self, data: dict[str, float]) -> None:
        self.data = dict(data)
        self.refresh()

    def get_data(self) -> dict[str, float]:
        return dict(self.data)

    def refresh(self) -> None:
        self.tree.clear()
        for k in sorted(self.data):
            v = self.data[k]
            item = QTreeWidgetItem([k, fmt_native(v), fmt_bar(v), fmt_kpa(v)])
            item.setData(0, Qt.ItemDataRole.UserRole, k)
            item.setToolTip(2, f"{to_bar(v):.4f} bar")
            item.setToolTip(3, f"{to_kpa(v):.2f} kPa")
            self.tree.addTopLevelItem(item)
        for col in range(4):
            self.tree.resizeColumnToContents(col)

    def add_row(self) -> None:
        self.begin_edit()
        key = f"new_key_{len(self.data)}"
        self.data[key] = 0.0
        self.refresh()
        self.on_change()

    def del_row(self) -> None:
        items = self.tree.selectedItems()
        if not items:
            return
        self.begin_edit()
        for item in items:
            key = item.data(0, Qt.ItemDataRole.UserRole)
            self.data.pop(key, None)
        self.refresh()
        self.on_change()

    def _edit_cell(self, item: QTreeWidgetItem, column: int) -> None:
        old_key = item.data(0, Qt.ItemDataRole.UserRole)
        old_val = self.data[old_key]
        if column == 0:
            text, ok = QInputDialog.getText(self, "Edit key", "Key", text=str(old_key))
            if not ok or not text.strip() or text.strip() == old_key:
                return
            self.begin_edit()
            self.data[text.strip()] = self.data.pop(old_key)
            self.refresh()
            self.on_change()
            return

        if column == 1:
            prompt, initial, unit = "Trainz native", fmt_native(old_val), "native"
        elif column == 2:
            prompt, initial, unit = "Pressure (bar)", fmt_bar(old_val), "bar"
        else:
            prompt, initial, unit = "Pressure (kPa)", fmt_kpa(old_val), "kpa"

        text, ok = QInputDialog.getText(self, f"Edit — {old_key}", prompt, text=initial)
        if not ok:
            return
        try:
            entered = float(text)
        except ValueError:
            QMessageBox.warning(self, "Invalid", "Enter a number.")
            return
        if unit == "bar":
            native = from_bar(entered)
        elif unit == "kpa":
            native = from_kpa(entered)
        else:
            native = entered
        self.begin_edit()
        self.data[old_key] = native
        self.refresh()
        self.on_change()


class SimulationPanel(QWidget):
    def __init__(
        self,
        get_cfg: Callable[[], EngineConfig],
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.get_cfg = get_cfg
        self._theme = theme_mode
        self.params = SimParams()
        self.controls = SimControls()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        card = QFrame()
        card.setObjectName("glassPanel")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(12, 12, 12, 12)
        cl.setSpacing(8)

        title = QLabel("Simulation preview")
        title.setObjectName("welcomeTitle")
        title.setFont(app_font(16, QFont.Weight.Bold))
        cl.addWidget(title)

        ctrl = QHBoxLayout()
        self.mass = QDoubleSpinBox()
        self.mass.setRange(1, 2000)
        self.mass.setValue(self.params.consist_mass_t)
        self.motors = QSpinBox()
        self.motors.setRange(1, 32)
        self.motors.setValue(self.params.motor_count)
        self.grade = QDoubleSpinBox()
        self.grade.setRange(-20, 20)
        self.grade.setSingleStep(0.1)
        self.grade.setValue(self.params.grade_percent)
        self.duration = QDoubleSpinBox()
        self.duration.setRange(10, 3600)
        self.duration.setValue(self.params.duration_s)
        self.notch = QSpinBox()
        self.notch.setRange(0, 8)
        self.notch.setValue(self.controls.throttle_notch)
        self.brake = QDoubleSpinBox()
        self.brake.setRange(0, 1)
        self.brake.setSingleStep(0.05)
        self.brake.setValue(self.controls.brake_handle)
        self.emergency = QCheckBox("Emergency")
        fields = [
            ("Mass (t)", self.mass),
            ("Motors", self.motors),
            ("Grade %", self.grade),
            ("Duration s", self.duration),
            ("Notch", self.notch),
            ("Brake 0–1", self.brake),
        ]
        for label, widget in fields:
            ctrl.addWidget(QLabel(label))
            ctrl.addWidget(widget)
        ctrl.addWidget(self.emergency)
        run_btn = QPushButton("Run simulation")
        run_btn.setObjectName("accentBtn")
        run_btn.clicked.connect(self.run)
        ctrl.addWidget(run_btn)
        ctrl.addStretch(1)
        cl.addLayout(ctrl)

        self.stats = QLabel("Run simulation to preview speed / brake / air (MR·BP·BC in bar).")
        self.stats.setObjectName("mutedTip")
        self.stats.setWordWrap(True)
        cl.addWidget(self.stats)

        self.fig = Figure(figsize=(12, 4.5), dpi=100)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(280)
        cl.addWidget(self.canvas, 1)
        lay.addWidget(card, 1)

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        if self.fig.axes:
            apply_mpl_theme(self.fig, self.fig.axes[0], self._theme)
            self.canvas.draw_idle()

    def _collect(self) -> tuple[SimParams, SimControls]:
        p = SimParams(
            consist_mass_t=float(self.mass.value()),
            motor_count=int(self.motors.value()),
            grade_percent=float(self.grade.value()),
            duration_s=float(self.duration.value()),
        )
        c = SimControls(
            throttle_notch=int(self.notch.value()),
            brake_handle=float(self.brake.value()),
            emergency=self.emergency.isChecked(),
        )
        return p, c

    def run(self) -> None:
        cfg = self.get_cfg()
        params, controls = self._collect()
        result = simulate(cfg, params, controls)
        if not result.samples:
            return
        ts = [s.t for s in result.samples]
        speed = [s.speed_kmh for s in result.samples]
        dist = [s.distance_m for s in result.samples]
        te = [s.te_kn for s in result.samples]
        brake = [s.brake_kn for s in result.samples]
        # Trainz native ×1000 → bar
        mr = [to_bar(s.mr_pressure) for s in result.samples]
        bp = [to_bar(s.bp_pressure) for s in result.samples]
        bc = [to_bar(s.bc_pressure) for s in result.samples]
        air = [s.air_used_rel for s in result.samples]

        self.fig.clear()
        ax = self.fig.add_subplot(111)
        ax.plot(ts, speed, color="#2563eb", linewidth=1.0, label="Speed km/h")
        ax.plot(ts, dist, color="#059669", linewidth=1.0, label="Distance m")
        ax.plot(ts, te, color="#ff5a1f", linewidth=1.0, label="TE kN")
        ax.plot(ts, brake, color="#dc2626", linewidth=1.0, label="Brake kN")
        ax.plot(ts, mr, color="#98989d", linewidth=1.0, alpha=0.85, label="MR bar")
        ax.plot(ts, bp, color="#6e6e73", linewidth=1.0, alpha=0.85, label="BP bar")
        ax.plot(ts, bc, color="#d97706", linewidth=1.0, alpha=0.85, label="BC bar")
        ax.plot(ts, air, color="#64748b", linewidth=1.0, linestyle="--", label="Air rel")
        ax.set_xlabel("Time (s)")
        ax.set_title("Simulation — air pressures in bar", fontsize=9)
        ax.legend(loc="upper right", fontsize=7, ncol=3)
        ax.tick_params(labelsize=7)
        apply_mpl_theme(self.fig, ax, self._theme)
        self.fig.tight_layout()
        self.canvas.draw_idle()

        lines = [
            f"Peak {result.peak_speed_kmh:.1f} km/h",
            f"→60 {result.time_to_60_kmh:.0f}s" if result.time_to_60_kmh else "→60 —",
            f"→90 {result.time_to_90_kmh:.0f}s" if result.time_to_90_kmh else "→90 —",
        ]
        if result.brake_apply_s is not None:
            lines.append(f"Brake {result.brake_apply_s:.0f}s")
        if result.brake_full_s is not None:
            lines.append(f"Full {result.brake_full_s:.0f}s")
        final = result.samples[-1]
        lines.append(
            f"{final.distance_m:.0f}m · MR {to_bar(final.mr_pressure):.2f} bar "
            f"({to_kpa(final.mr_pressure):.0f} kPa) · air {final.air_used_rel:.3f}"
        )
        self.stats.setText(" · ".join(lines))


class EngineTunerHost(QWidget):
    """Engine Tuner — top actions · stacked pages · Mesh-style bottom nav."""

    status = Signal(str)

    def __init__(
        self,
        *,
        on_home: Callable[[], None],
        on_theme: Callable[[], None] | None = None,
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_home = on_home
        self._on_theme = on_theme
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self.cfg = EngineConfig()
        self.history = UndoStack()
        # CDP session: Save writes back via callback then returns to Packages
        self._cdp_on_save: Callable[[str], None] | None = None
        self._cdp_on_done: Callable[[], None] | None = None
        self._cdp_on_back: Callable[[], None] | None = None
        self._build()
        self._bind_shortcuts()

    def set_theme(self, mode: str) -> None:
        from ..theme import qpalette_for

        self._theme = mode if mode in ("dark", "light") else "dark"
        self.setPalette(qpalette_for(self._theme))
        self.throttle_editor.set_theme(self._theme)
        self.sim_panel.set_theme(self._theme)
        self.sidebar.set_theme(self._theme)
        self._nav.set_theme(self._theme)
        if hasattr(self, "_autotune_panel"):
            self._autotune_panel.set_theme(self._theme)

    def _build(self) -> None:
        from .autotune_dialog import AutotunePanel

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self._split = QSplitter(Qt.Orientation.Horizontal)
        self._split.setObjectName("engineSplit")
        self._split.setChildrenCollapsible(False)
        self._split.setHandleWidth(6)

        # ── left sidebar (Mesh frost theme) — drag handle to resize ──
        self.sidebar = EngineSidebar()
        self.sidebar.set_theme(self._theme)
        self.sidebar.open_clicked.connect(self.open_file)
        self.sidebar.back_clicked.connect(self.back_to_packages)
        self.sidebar.save_clicked.connect(self.save_file)
        self.sidebar.save_as_clicked.connect(self.save_file_as)
        self.sidebar.undo_clicked.connect(self.undo)
        self.sidebar.redo_clicked.connect(self.redo)
        self.sidebar.clone_requested.connect(self._on_sidebar_clone)
        self.sidebar.clone_higher_requested.connect(self._on_sidebar_clone_higher)
        self._split.addWidget(self.sidebar)

        # ── center: pages · bottom nav ──
        right_host = QWidget()
        right = QVBoxLayout(right_host)
        right.setContentsMargins(10, 0, 0, 0)
        right.setSpacing(8)

        self.path_lab = QLabel("Open an engine config.txt to begin.")
        self.path_lab.setObjectName("mutedTip")
        right.addWidget(self.path_lab)

        self._stack = QStackedWidget()

        tuner_page = QWidget()
        tl = QVBoxLayout(tuner_page)
        tl.setContentsMargins(0, 0, 0, 0)
        throttle_box = QFrame()
        throttle_box.setObjectName("glassPanel")
        tb = QVBoxLayout(throttle_box)
        tb.setContentsMargins(10, 10, 10, 10)
        self.throttle_editor = ThrottleEditor(
            lambda: self.cfg,
            self._on_throttle_change,
            begin_edit=self._begin_edit,
            record_undo=self.history.record,
            status_cb=lambda m: self.status.emit(m),
            theme_mode=self._theme,
        )
        tb.addWidget(self.throttle_editor, 1)
        tl.addWidget(throttle_box, 1)
        self._stack.addWidget(tuner_page)  # 0 tuner

        self.sim_panel = SimulationPanel(lambda: self._pull_all(), theme_mode=self._theme)
        self._stack.addWidget(self.sim_panel)  # 1 simulation

        params_page = QWidget()
        pl = QVBoxLayout(params_page)
        pl.setContentsMargins(0, 0, 0, 0)
        params = QFrame()
        params.setObjectName("glassPanel")
        pbody = QVBoxLayout(params)
        pbody.setContentsMargins(12, 12, 12, 12)
        p_title = QLabel("Engine & air brake parameters")
        p_title.setObjectName("welcomeTitle")
        p_title.setFont(app_font(16, QFont.Weight.Bold))
        pbody.addWidget(p_title)
        row = QHBoxLayout()
        self.motor_editor = DictEditor("motor", self._sync_motor, begin_edit=self._begin_edit)
        self.mass_editor = DictEditor("mass", self._sync_mass, begin_edit=self._begin_edit)
        self.flow_editor = DictEditor("flowsize", self._sync_flow, begin_edit=self._begin_edit)
        self.vol_editor = DictEditor("volume", self._sync_vol, begin_edit=self._begin_edit)
        for ed in (self.motor_editor, self.mass_editor, self.flow_editor, self.vol_editor):
            row.addWidget(ed, 1)
        pbody.addLayout(row, 1)
        self.press_editor = PressureEditor(self._sync_press, begin_edit=self._begin_edit)
        pbody.addWidget(self.press_editor, 2)
        pl.addWidget(params, 1)
        self._stack.addWidget(params_page)  # 2 parameters

        right.addWidget(self._stack, 1)

        nav_wrap = QHBoxLayout()
        nav_wrap.addStretch(1)
        self._nav = EnginePageNav()
        self._nav.page_changed.connect(self._on_page)
        self._nav.home_clicked.connect(self._home_or_back)
        self._nav.theme_clicked.connect(self._theme_clicked)
        self._nav.autotune_toggled.connect(self._on_autotune_toggled)
        nav_wrap.addWidget(self._nav)
        nav_wrap.addStretch(1)
        right.addLayout(nav_wrap)

        self._split.addWidget(right_host)
        self._split.setStretchFactor(0, 0)
        self._split.setStretchFactor(1, 1)
        self._split.setSizes([360, 1000])
        root.addWidget(self._split, 1)

        # ── right Auto Tune dock (layout sibling — freezes left width while open) ──
        self._autotune_open = False
        self._sidebar_lock_w: int | None = None
        self._drawer_host = QWidget()
        self._drawer_host.setMaximumWidth(0)
        self._drawer_host.setMinimumWidth(0)
        dh = QHBoxLayout(self._drawer_host)
        dh.setContentsMargins(8, 0, 0, 0)
        dh.setSpacing(0)
        self._autotune_panel = AutotunePanel()
        self._autotune_panel.set_theme(self._theme)
        self._autotune_panel.applied.connect(self._on_autotune_applied)
        self._autotune_panel.closed.connect(self.close_autotune)
        dh.addWidget(self._autotune_panel)
        root.addWidget(self._drawer_host, 0)

        self.sidebar.refresh_info(self.cfg)

    def _theme_clicked(self) -> None:
        if self._on_theme is not None:
            self._on_theme()

    def _on_autotune_toggled(self, on: bool) -> None:
        if on:
            self.open_autotune()
        else:
            self.close_autotune()

    def open_autotune(self) -> None:
        from ..motion import animate_max_width
        from .autotune_dialog import AutotunePanel

        if self._autotune_open:
            self._nav.set_autotune_checked(True)
            return
        # Auto Tune edits throttle curves — jump to Tuner page
        self._nav.set_page("tuner", emit=True, animate=True)
        max_kmh, max_kn = self.throttle_editor.autotune_graph_limits()
        self._autotune_panel.bind(
            self.cfg,
            graph_max_kmh=max_kmh,
            graph_max_kn=max_kn,
            current_resist=self.throttle_editor._resist_params,
        )
        # Freeze left sidebar width so the dock only steals from center content
        sizes = self._split.sizes()
        self._sidebar_lock_w = sizes[0] if sizes else self.sidebar.width()
        self.sidebar.setMinimumWidth(self._sidebar_lock_w)
        self.sidebar.setMaximumWidth(self._sidebar_lock_w)
        self._autotune_open = True
        self._nav.set_autotune_checked(True)
        target = AutotunePanel.PANEL_W + 8
        self.throttle_editor.set_layout_animating(True)

        def _done() -> None:
            self._keep_sidebar_lock()
            self.throttle_editor.set_layout_animating(False)

        animate_max_width(
            self._drawer_host,
            target,
            360,
            on_tick=self._keep_sidebar_lock,
            on_done=_done,
            min_frame_ms=40,
        )
        self.status.emit("Auto Tune sidebar")

    def close_autotune(self) -> None:
        from ..motion import animate_max_width

        self._nav.set_autotune_checked(False)
        if not self._autotune_open and self._drawer_host.maximumWidth() == 0:
            return
        self._autotune_open = False
        self.throttle_editor.set_layout_animating(True)

        def _unlock() -> None:
            self.sidebar.setMinimumWidth(280)
            self.sidebar.setMaximumWidth(520)
            self._sidebar_lock_w = None
            self.throttle_editor.set_layout_animating(False)

        animate_max_width(
            self._drawer_host,
            0,
            320,
            on_tick=self._keep_sidebar_lock,
            on_done=_unlock,
            min_frame_ms=40,
        )

    def _keep_sidebar_lock(self) -> None:
        w = self._sidebar_lock_w
        if w is None:
            return
        total = sum(self._split.sizes())
        self._split.setSizes([w, max(80, total - w)])

    def _on_sidebar_clone(self, src: int, targets) -> None:
        self.throttle_editor.apply_clone(int(src), list(targets or []))

    def _on_sidebar_clone_higher(self, src: int) -> None:
        self.throttle_editor.clone_to_higher(int(src))

    def _on_autotune_applied(self, curves, resist, fit: bool, show: bool) -> None:
        self.throttle_editor.apply_autotune(curves, resist, fit, show)
        self.sidebar.refresh_info(self.cfg)

    def _in_cdp_session(self) -> bool:
        return self._cdp_on_save is not None or self._cdp_on_back is not None

    def _home_or_back(self) -> None:
        """Home → MSTN hub; during CDP session → Packages instead."""
        if self._in_cdp_session():
            self.back_to_packages()
            return
        self._on_home()

    def back_to_packages(self) -> None:
        """Leave CDP session without writing; return to Assets Packages."""
        if not self._in_cdp_session():
            self._on_home()
            return
        if self.history.undo:
            ans = QMessageBox.question(
                self,
                "Leave Engine Tuner?",
                "มีแก้ที่ยังไม่ได้ Save เข้า CDP — กลับ Packages โดยไม่เขียนทับ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return
        back = self._cdp_on_back
        self.clear_cdp_session()
        if back is not None:
            back()
        else:
            self._on_home()

    def _on_page(self, page: str) -> None:
        idx = {"tuner": 0, "simulation": 1, "parameters": 2}.get(page, 0)
        self._stack.setCurrentIndex(idx)
        if page == "simulation":
            self.status.emit("Engine Tuner — Simulation")
        elif page == "parameters":
            self.status.emit("Engine Tuner — Parameters")
        else:
            self.status.emit("Engine Tuner — Tuner")

    def _bind_shortcuts(self) -> None:
        QShortcut(QKeySequence.StandardKey.Undo, self, self.undo)
        QShortcut(QKeySequence.StandardKey.Redo, self, self.redo)
        QShortcut(QKeySequence("Ctrl+Shift+Z"), self, self.redo)
        QShortcut(QKeySequence.StandardKey.Open, self, self.open_file)
        QShortcut(QKeySequence.StandardKey.Save, self, self.save_file)

    def _begin_edit(self) -> None:
        self._pull_all()
        self.history.record(self.cfg.clone())

    def undo(self) -> None:
        restored = self.history.pop_undo(self._pull_all())
        if restored is None:
            self.status.emit("Nothing to undo")
            self.path_lab.setText("Nothing to undo")
            return
        self._restore_cfg(restored, "Undo")

    def redo(self) -> None:
        restored = self.history.pop_redo(self._pull_all())
        if restored is None:
            self.status.emit("Nothing to redo")
            self.path_lab.setText("Nothing to redo")
            return
        self._restore_cfg(restored, "Redo")

    def _restore_cfg(self, cfg: EngineConfig, label: str) -> None:
        self.history.locked = True
        try:
            self.cfg = cfg
            self._sync_editors_from_cfg()
            path = self.cfg.source_path or "unsaved"
            msg = f"{label} — {path}"
            self.path_lab.setText(msg)
            self.status.emit(msg)
        finally:
            self.history.locked = False

    def _sync_editors_from_cfg(self) -> None:
        self.motor_editor.set_data(self.cfg.motor)
        self.mass_editor.set_data(self.cfg.mass)
        self.flow_editor.set_data(self.cfg.flowsize)
        self.vol_editor.set_data(self.cfg.volume)
        self.press_editor.set_data(self.cfg.pressure)
        self.throttle_editor.reload_all()
        self.sidebar.refresh_info(self.cfg)

    def _on_throttle_change(self) -> None:
        self._mark_dirty()
        self.throttle_editor._redraw()
        self.sidebar.refresh_info(self.cfg)

    def _mark_dirty(self) -> None:
        path = self.cfg.source_path or "unsaved"
        msg = f"Edited — {path}"
        self.path_lab.setText(msg)
        self.status.emit(msg)
        self.sidebar.refresh_info(self.cfg)

    def _pull_all(self) -> EngineConfig:
        self.cfg.motor = self.motor_editor.get_data()
        self.cfg.mass = self.mass_editor.get_data()
        self.cfg.flowsize = self.flow_editor.get_data()
        self.cfg.volume = self.vol_editor.get_data()
        self.cfg.pressure = self.press_editor.get_data()
        return self.cfg

    def _sync_mass(self) -> None:
        self.cfg.mass = self.mass_editor.get_data()
        self._mark_dirty()

    def _sync_motor(self) -> None:
        self.cfg.motor = self.motor_editor.get_data()
        self._mark_dirty()
        self.throttle_editor.reload_all()

    def _sync_flow(self) -> None:
        self.cfg.flowsize = self.flow_editor.get_data()
        self._mark_dirty()

    def _sync_vol(self) -> None:
        self.cfg.volume = self.vol_editor.get_data()
        self._mark_dirty()

    def _sync_press(self) -> None:
        self.cfg.pressure = self.press_editor.get_data()
        self._mark_dirty()

    def _load_into_ui(self) -> None:
        self.history.clear()
        self._sync_editors_from_cfg()
        msg = f"Loaded {self.cfg.source_path}"
        self.path_lab.setText(msg)
        self.status.emit(msg)

    def _config_start_dir(self) -> str:
        from ... import REPO_ROOT

        root = REPO_ROOT
        for name in ("editing", "backups"):
            path = root / name
            if path.is_dir():
                return str(path)
        return str(root)

    def clear_cdp_session(self) -> None:
        self._cdp_on_save = None
        self._cdp_on_done = None
        self._cdp_on_back = None
        self.sidebar.set_cdp_session(False)
        self._nav.set_home_mode(cdp=False)

    def open_cdp_session(
        self,
        *,
        text: str,
        label: str,
        on_save: Callable[[str], None],
        on_done: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
    ) -> bool:
        """Load enginespec text from Packages CDP; Save writes back then returns."""
        try:
            self.cfg = load_config_from_text(text, source_path=label)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return False
        self._cdp_on_save = on_save
        self._cdp_on_done = on_done
        self._cdp_on_back = on_back
        self._load_into_ui()
        self.sidebar.set_cdp_session(True, label=label)
        self._nav.set_home_mode(cdp=True)
        self.path_lab.setText(f"CDP session — {label}")
        self.status.emit(f"Opened from CDP — {label}")
        return True

    def open_file(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open engine config.txt",
            self._config_start_dir(),
            "Trainz config (config.txt);;All (*.*)",
        )
        if not path:
            return False
        try:
            self.cfg = load_config(path)
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return False
        self.clear_cdp_session()
        self._load_into_ui()
        return True

    def save_file(self) -> None:
        if self._cdp_on_save is not None:
            self._pull_all()
            text = config_to_text(self.cfg)
            try:
                self._cdp_on_save(text)
            except Exception as exc:
                QMessageBox.critical(self, "Save into CDP failed", str(exc))
                return
            label = self.cfg.source_path or "CDP"
            msg = f"Saved into CDP — {label}"
            self.path_lab.setText(msg)
            self.status.emit(msg)
            done = self._cdp_on_done
            self.clear_cdp_session()
            if done is not None:
                done()
            return
        if not self.cfg.source_path:
            self.save_file_as()
            return
        self._pull_all()
        save_config(self.cfg, self.cfg.source_path)
        msg = f"Saved {self.cfg.source_path}"
        self.path_lab.setText(msg)
        self.status.emit(msg)

    def save_file_as(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save engine config.txt",
            self._config_start_dir(),
            "Trainz config (config.txt);;All (*.*)",
        )
        if not path:
            return
        out = Path(path)
        if out.name.lower() != "config.txt" and out.suffix.lower() != ".txt":
            out = out.with_name("config.txt")
        self._pull_all()
        save_config(self.cfg, out)
        self.cfg.source_path = str(out)
        self.clear_cdp_session()
        msg = f"Saved {out}"
        self.path_lab.setText(msg)
        self.status.emit(msg)


def build_engine_tuner(
    *,
    on_home: Callable[[], None],
    on_theme: Callable[[], None] | None = None,
    theme_mode: str = "dark",
) -> EngineTunerHost:
    return EngineTunerHost(on_home=on_home, on_theme=on_theme, theme_mode=theme_mode)
