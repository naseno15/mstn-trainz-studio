"""Throttle-power table + interactive TE/speed graph (matplotlib QtAgg)."""
from __future__ import annotations

from collections.abc import Callable

import matplotlib.ticker as mticker
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...lib.engine_tuner.config_io import EngineConfig
from ...lib.engine_tuner.throttle_round import (
    fmt_kmh,
    fmt_kn,
    normalize_points,
    round_point,
)
from ..smooth_scroll import enable_smooth_scroll_area, enable_smooth_table
from ..theme import palette

MS_TO_KMH = 3.6
GRAPH_SNAP = 10  # Ctrl/Cmd while dragging → snap to this grid
NOTCH_COL_W = 120  # floor width — row scrolls L/R instead of squashing
HIT_PX = 18.0


class _NotchRowHScroll(QObject):
    """Wheel / trackpad → horizontal bar (row has no vertical scroll)."""

    def __init__(self, area: QScrollArea) -> None:
        super().__init__(area)
        self._area = area
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        try:
            vp = self._area.viewport()
        except RuntimeError:
            return False
        if obj is not vp or event.type() != QEvent.Type.Wheel:
            return False
        hbar = self._area.horizontalScrollBar()
        if hbar.maximum() <= hbar.minimum():
            return False
        # prefer native X delta; else map vertical wheel → left/right
        pix = event.pixelDelta()
        ang = event.angleDelta()
        if pix.x() != 0:
            delta = -pix.x()
        elif pix.y() != 0:
            delta = -pix.y()
        elif ang.x() != 0:
            delta = -ang.x() // 2
        elif ang.y() != 0:
            delta = -ang.y() // 2
        else:
            return False
        hbar.setValue(hbar.value() + int(delta))
        event.accept()
        return True

# TEE-ish notch palette (0 idle → 8 full)
NOTCH_COLORS = {
    0: "#94a3b8",
    1: "#22c55e",
    2: "#84cc16",
    3: "#eab308",
    4: "#f59e0b",
    5: "#f97316",
    6: "#ef4444",
    7: "#ec4899",
    8: "#a855f7",
}


def _ctrl_held(event) -> bool:
    key = getattr(event, "key", None) or ""
    parts = {p.lower() for p in key.split("+") if p}
    if parts & {"cmd", "ctrl", "control", "meta", "super"}:
        return True
    gui = getattr(event, "guiEvent", None)
    if gui is not None and hasattr(gui, "modifiers"):
        mods = gui.modifiers()
        if mods is not None and mods & (
            Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.MetaModifier
        ):
            return True
    return False


def _coords_from_drag_event(event) -> tuple[float, float] | None:
    """Fine drag by default (0.1). Hold Ctrl/Cmd to snap km/h to GRAPH_SNAP."""
    if event.xdata is None or event.ydata is None:
        return None
    x_kmh = max(0.0, event.xdata)
    y_kn = max(0.0, event.ydata)
    if _ctrl_held(event):
        x_kmh = round(x_kmh / GRAPH_SNAP) * GRAPH_SNAP
        y_kn = round(y_kn / GRAPH_SNAP) * GRAPH_SNAP
    return round_point(x_kmh / MS_TO_KMH, y_kn)


def _shift_held(event) -> bool:
    key = getattr(event, "key", None) or ""
    if "shift" in str(key).lower():
        return True
    gui = getattr(event, "guiEvent", None)
    if gui is not None:
        mods = gui.modifiers() if hasattr(gui, "modifiers") else None
        if mods is not None and mods & Qt.KeyboardModifier.ShiftModifier:
            return True
    return False


def apply_mpl_theme(fig: Figure, ax, theme: str) -> None:
    pal = palette(theme if theme in ("dark", "light") else "dark")
    dark = pal.mode == "dark"
    face = "#161a1e" if dark else "#e8ebf0"
    fig.patch.set_facecolor(face)
    ax.set_facecolor(face)
    ink = pal.ink
    muted = pal.muted
    ax.tick_params(colors=ink, labelsize=8)
    ax.xaxis.label.set_color(ink)
    ax.yaxis.label.set_color(ink)
    ax.title.set_color(ink)
    for spine in ax.spines.values():
        spine.set_color(muted)
    ax.grid(True, alpha=0.25, color=muted)
    legend = ax.get_legend()
    if legend is not None:
        legend.get_frame().set_facecolor(face)
        legend.get_frame().set_edgecolor(muted)
        for text in legend.get_texts():
            text.set_color(ink)


class NotchTree(QTreeWidget):
    """Notch point list — drag-reorder rows · multi-select for − delete."""

    def __init__(self, column: "NotchColumn") -> None:
        super().__init__()
        self._column = column
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        super().dropEvent(event)
        self._column.commit_visual_order()


class NotchColumn(QFrame):
    def __init__(self, notch: int, editor: "ThrottleEditor") -> None:
        super().__init__()
        self.notch = notch
        self.editor = editor
        self._refreshing = False
        self.setObjectName("glassPanel")
        self.setMinimumWidth(NOTCH_COL_W)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)
        title = QLabel(f"N{notch}")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: 650;")
        lay.addWidget(title)
        self.tree = NotchTree(self)
        self.tree.setHeaderLabels(["km/h", "kN"])
        self.tree.setUniformRowHeights(True)
        self.tree.setMinimumWidth(72)
        self.tree.setMinimumHeight(80)
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        enable_smooth_table(self.tree, horizontal=False)
        hdr = self.tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setStretchLastSection(False)  # 50/50 — don't let last column steal width
        hdr.setMinimumSectionSize(28)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tree.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tree.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        self.tree.raise_()
        self.tree.itemSelectionChanged.connect(lambda: editor.set_focus_notch(notch))
        self.tree.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.tree, 1)
        row = QHBoxLayout()
        row.setSpacing(4)
        add_btn = QPushButton("+")
        add_btn.setToolTip(f"Add point on N{notch}")
        add_btn.setMinimumHeight(28)
        add_btn.setMaximumHeight(28)
        add_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        add_btn.clicked.connect(lambda: editor.add_point(notch))
        del_btn = QPushButton("−")
        del_btn.setToolTip(f"Remove selected point(s) on N{notch}")
        del_btn.setMinimumHeight(28)
        del_btn.setMaximumHeight(28)
        del_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        del_btn.clicked.connect(lambda: editor.del_point(notch))
        row.addWidget(add_btn, 1)
        row.addWidget(del_btn, 1)
        lay.addLayout(row)

    def refresh(self, pts: list[tuple[float, float]]) -> None:
        self._refreshing = True
        self.tree.blockSignals(True)
        self.tree.clear()
        for i, (sp, te) in enumerate(sorted(pts, key=lambda p: p[0])):
            item = QTreeWidgetItem([fmt_kmh(sp), fmt_kn(te)])
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            item.setTextAlignment(0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tree.addTopLevelItem(item)
        self.tree.blockSignals(False)
        self._refreshing = False

    def selected_indices(self) -> list[int]:
        idxs: list[int] = []
        for item in self.tree.selectedItems():
            raw = item.data(0, Qt.ItemDataRole.UserRole)
            if raw is not None:
                idxs.append(int(raw))
        return sorted(set(idxs), reverse=True)

    def selected_index(self) -> int | None:
        idxs = self.selected_indices()
        return idxs[0] if idxs else None

    def commit_visual_order(self) -> None:
        """After InternalMove — read rows top→bottom and write curve (then speed-sort)."""
        if self._refreshing:
            return
        pts: list[tuple[float, float]] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is None:
                continue
            try:
                kmh = float(str(item.text(0)).strip().replace(",", ""))
                kn = float(str(item.text(1)).strip().replace(",", ""))
            except ValueError:
                continue
            pts.append((max(0.0, kmh) / MS_TO_KMH, max(0.0, kn)))
        self.editor.reorder_points(self.notch, pts)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if self._refreshing:
            return
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is None:
            return
        self.editor.commit_cell_edit(self.notch, int(idx), column, item.text(column))


class ThrottleEditor(QWidget):
    def __init__(
        self,
        get_cfg: Callable[[], EngineConfig],
        on_change: Callable[[], None],
        begin_edit: Callable[[], None] | None = None,
        record_undo: Callable[[EngineConfig], None] | None = None,
        status_cb: Callable[[str], None] | None = None,
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.get_cfg = get_cfg
        self.on_change = on_change
        self.begin_edit = begin_edit or (lambda: None)
        self.record_undo = record_undo or (lambda _snap: None)
        self.status_cb = status_cb or (lambda _m: None)
        self._theme = theme_mode
        self.focus_notch: int | None = None
        self.drag_notch: int | None = None
        self.drag_idx: int | None = None
        self.columns: dict[int, NotchColumn] = {}
        self.selected: set[tuple[int, int]] = set()
        self._marquee_origin: tuple[float, float] | None = None
        self._marquee_rect: Rectangle | None = None
        self._marquee_bg = None  # blit cache while rubber-band selecting
        self._move_origin: dict[tuple[int, int], tuple[float, float]] = {}
        self._move_anchor_kmh: float | None = None
        self._move_anchor_kn: float | None = None
        self._pre_drag: EngineConfig | None = None
        self._xlim: tuple[float, float] | None = None
        self._ylim: tuple[float, float] | None = None
        self._marquee_additive = False
        self._last_live_xy: tuple[float, float] | None = None
        self._resist_params = None  # ResistParams | None
        self._show_resist = False
        self._build()

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        self._redraw_graph_only(fit=False)

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Vertical split — tables above · graph (+ toolbar) below
        self._split = QSplitter(Qt.Orientation.Vertical)
        self._split.setObjectName("throttleSplit")
        self._split.setChildrenCollapsible(True)
        self._split.setHandleWidth(6)

        # Notch tables — one horizontal row; scroll L/R when Auto Tune steals width
        table_scroll = QScrollArea()
        table_scroll.setObjectName("notchTableScroll")
        table_scroll.setWidgetResizable(True)  # grow height + widen when room
        table_scroll.setFrameShape(QFrame.Shape.NoFrame)
        table_scroll.setMinimumHeight(100)
        table_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        table_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        table_scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        enable_smooth_scroll_area(table_scroll)

        table_host = QWidget()
        table_host.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Expanding
        )
        table_row = QHBoxLayout(table_host)
        table_row.setContentsMargins(0, 0, 0, 0)
        table_row.setSpacing(4)
        notches = [0, *range(1, 9)]
        for n in notches:
            col = NotchColumn(n, self)
            self.columns[n] = col
            table_row.addWidget(col, 1)  # share extra width when roomy
        # floor = full comfortable row → scrollbar when viewport narrower
        row_w = len(notches) * NOTCH_COL_W + 4 * (len(notches) - 1)
        table_host.setMinimumWidth(row_w)
        table_scroll.setWidget(table_host)
        self._table_scroll = table_scroll
        self._table_host = table_host
        self._notch_hscroll = _NotchRowHScroll(table_scroll)  # keep ref
        self._split.addWidget(table_scroll)

        graph_host = QWidget()
        graph_host.setMinimumHeight(120)
        gh = QVBoxLayout(graph_host)
        gh.setContentsMargins(0, 0, 0, 0)
        gh.setSpacing(6)
        gh.addWidget(self._build_graph_toolbar())

        self.fig = Figure(figsize=(12, 4.2), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.canvas.setMinimumHeight(100)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        gh.addWidget(self.canvas, 1)
        self._split.addWidget(graph_host)

        self._split.setStretchFactor(0, 2)
        self._split.setStretchFactor(1, 3)
        self._split.setSizes([220, 360])
        root.addWidget(self._split, 1)

        self.canvas.mpl_connect("button_press_event", self._on_press)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

    def _build_graph_toolbar(self) -> QWidget:
        """Slim graph header — Clone lives on the left sidebar now."""
        bar = QWidget()
        top = QHBoxLayout(bar)
        top.setContentsMargins(0, 2, 0, 0)
        top.setSpacing(8)

        tune_box = QFrame()
        tune_box.setObjectName("glassPanel")
        tl = QHBoxLayout(tune_box)
        tl.setContentsMargins(10, 6, 10, 6)
        self.resist_cb = QCheckBox("Resistance")
        self.resist_cb.setToolTip("Show Davis train-resistance curve + balancing speeds")
        self.resist_cb.toggled.connect(self._toggle_resist)
        tl.addWidget(self.resist_cb)
        top.addWidget(tune_box)

        lim_box = QFrame()
        lim_box.setObjectName("glassPanel")
        ll = QHBoxLayout(lim_box)
        ll.setContentsMargins(10, 6, 10, 6)
        ll.addWidget(QLabel("Graph max km/h"))
        self.max_kmh = QDoubleSpinBox()
        self.max_kmh.setRange(10, 400)
        self.max_kmh.setSingleStep(10)
        self.max_kmh.setDecimals(2)
        self.max_kmh.setValue(120)
        self.max_kmh.valueChanged.connect(lambda _v: self.apply_graph_max())
        ll.addWidget(self.max_kmh)
        ll.addWidget(QLabel("kN"))
        self.max_kn = QDoubleSpinBox()
        self.max_kn.setRange(1, 500)
        self.max_kn.setSingleStep(5)
        self.max_kn.setDecimals(2)
        self.max_kn.setValue(80)
        self.max_kn.valueChanged.connect(lambda _v: self.apply_graph_max())
        ll.addWidget(self.max_kn)
        fit_btn = QPushButton("Fit")
        fit_btn.clicked.connect(self.fit_graph)
        ll.addWidget(fit_btn)
        top.addWidget(lim_box)

        tip = QLabel(
            "Clone on left sidebar · click cell · drag points · Ctrl=snap 10 · "
            "drag empty=select · Shift+drag add"
        )
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        top.addWidget(tip, 1)
        return bar

    def set_focus_notch(self, notch: int) -> None:
        self.focus_notch = notch
        self._redraw_graph_only(fit=False)

    def reload_all(self) -> None:
        self.selected.clear()
        self._xlim = None
        self._ylim = None
        self._redraw(fit=True)

    def fit_graph(self) -> None:
        self._redraw_graph_only(fit=True)

    def apply_graph_max(self) -> None:
        mx = float(self.max_kmh.value())
        my = float(self.max_kn.value())
        if mx <= 0 or my <= 0:
            return
        self._xlim = (0.0, mx)
        self._ylim = (-0.5, my)
        self._redraw_graph_only(fit=False)

    def _sync_max_vars(self) -> None:
        if self._xlim is not None:
            self.max_kmh.blockSignals(True)
            self.max_kmh.setValue(round(self._xlim[1], 1))
            self.max_kmh.blockSignals(False)
        if self._ylim is not None:
            self.max_kn.blockSignals(True)
            self.max_kn.setValue(round(self._ylim[1], 1))
            self.max_kn.blockSignals(False)

    def _set_notch_points(self, notch: int, pts: list[tuple[float, float]]) -> None:
        cfg = self.get_cfg()
        cfg.throttle_power[notch] = normalize_points(pts)
        self.on_change()

    def _refresh_columns(self) -> None:
        cfg = self.get_cfg()
        for notch, col in self.columns.items():
            col.refresh(cfg.throttle_power.get(notch, []))

    def _redraw_graph_only(self, *, fit: bool = False, live: bool = False) -> None:
        cfg = self.get_cfg()
        highlight = self.focus_notch
        keep_marquee = self._marquee_rect
        self.ax.clear()
        self.ax.set_xlabel("Speed (km/h)")
        self.ax.set_ylabel("Tractive effort (kN)")
        self.ax.xaxis.set_major_locator(mticker.MultipleLocator(10))
        self.ax.yaxis.set_major_locator(mticker.MultipleLocator(10))

        all_x_kmh: list[float] = []
        all_y: list[float] = []
        max_notch = int(cfg.motor.get("throttle-notches", 8))

        for notch in range(0, max_notch + 1):
            pts = cfg.throttle_power.get(notch, [])
            if not pts:
                continue
            xs_kmh = [p[0] * MS_TO_KMH for p in pts]
            ys = [p[1] for p in pts]
            all_x_kmh.extend(xs_kmh)
            all_y.extend(ys)
            color = NOTCH_COLORS.get(notch, "#64748b")
            is_hi = notch == highlight
            linestyle = "-" if is_hi else (":" if live else "-")
            lw = 2.2 if is_hi else (1.0 if live else 1.35)
            ms = 7.5 if is_hi else (4.0 if live else 5.0)
            alpha = 1.0 if is_hi else (0.35 if live else 0.78)
            label = f"N{notch}" if (not live or is_hi) else "_nolegend_"
            self.ax.plot(
                xs_kmh,
                ys,
                linestyle,
                color=color,
                linewidth=lw,
                marker="o",
                markersize=ms,
                markeredgewidth=1.0 if is_hi else 0.6,
                markeredgecolor="#ffffff" if is_hi else color,
                markerfacecolor=color,
                alpha=alpha,
                label=label,
                zorder=5 if is_hi else 3,
                solid_capstyle="round",
            )
            sel_x = [xs_kmh[i] for i, _ in enumerate(pts) if (notch, i) in self.selected]
            sel_y = [ys[i] for i, _ in enumerate(pts) if (notch, i) in self.selected]
            if sel_x:
                self.ax.scatter(
                    sel_x,
                    sel_y,
                    s=110,
                    color="#fbbf24",
                    zorder=7,
                    edgecolors="#111827",
                    linewidths=1.1,
                )

        self._draw_resistance_overlay(cfg, live=live)

        if all_x_kmh:
            if fit or self._xlim is None or self._ylim is None:
                self._xlim = (min(0.0, min(all_x_kmh) - 3.0), max(all_x_kmh) + 5.0)
                self._ylim = (-0.5, max(all_y + [1.0]) * 1.1)
                self._sync_max_vars()
            self.ax.set_xlim(*self._xlim)
            self.ax.set_ylim(*self._ylim)
            if not live:
                self.ax.legend(loc="upper right", fontsize=7, ncol=4, framealpha=0.92)
        if keep_marquee is not None and self._marquee_origin is not None:
            self.ax.add_patch(keep_marquee)
            self._marquee_rect = keep_marquee
        apply_mpl_theme(self.fig, self.ax, self._theme)
        # ponytail: tight_layout every motion frame = stutter; only on idle redraws
        if not live:
            self.fig.tight_layout()
        self.canvas.draw_idle()

    def _redraw(self, *, fit: bool = False) -> None:
        self._refresh_columns()
        self._redraw_graph_only(fit=fit)

    def _nearest(self, event) -> tuple[int, int] | None:
        if event.x is None or event.y is None:
            return None
        best: tuple[int, int] | None = None
        best_d = 1e9
        cfg = self.get_cfg()
        for notch, pts in cfg.throttle_power.items():
            for i, (sp, te) in enumerate(pts):
                px, py = self.ax.transData.transform((sp * MS_TO_KMH, te))
                d = (px - event.x) ** 2 + (py - event.y) ** 2
                if d < best_d:
                    best_d = d
                    best = (int(notch), i)
        if best is None or best_d > HIT_PX**2:
            return None
        return best

    def _begin_group_drag(self, hit: tuple[int, int]) -> None:
        self.drag_notch, self.drag_idx = hit
        key = (self.drag_notch, self.drag_idx)
        if key not in self.selected:
            self.selected = {key}
        self.focus_notch = self.drag_notch
        cfg = self.get_cfg()
        self._pre_drag = cfg.clone()
        self._move_origin = {}
        for n, i in self.selected:
            pts = cfg.throttle_power.get(n, [])
            if 0 <= i < len(pts):
                self._move_origin[(n, i)] = pts[i]
        grab = self._move_origin.get(key)
        if grab is not None:
            self._move_anchor_kmh = grab[0] * MS_TO_KMH
            self._move_anchor_kn = grab[1]
        self._last_live_xy = None
        self._redraw_graph_only(fit=False)

    def _on_press(self, event) -> None:
        if event.inaxes != self.ax:
            return
        self.canvas.setFocus()
        shift = _shift_held(event)
        if getattr(event, "dblclick", False) and self._nearest(event) is None:
            self.selected.clear()
            self._redraw_graph_only(fit=True)
            return
        hit = self._nearest(event)
        if hit is None:
            self._start_marquee(event, additive=shift)
            return
        if shift:
            if hit in self.selected:
                self.selected.discard(hit)
            else:
                self.selected.add(hit)
            self.focus_notch = hit[0]
            self._redraw_graph_only(fit=False)
            return
        self._begin_group_drag(hit)

    def _event_data_xy(self, event) -> tuple[float, float] | None:
        """Data coords even when cursor leaves the axes (pixel → data)."""
        if event.xdata is not None and event.ydata is not None:
            return float(event.xdata), float(event.ydata)
        if event.x is None or event.y is None:
            return None
        try:
            x, y = self.ax.transData.inverted().transform((event.x, event.y))
        except Exception:
            return None
        return float(x), float(y)

    def _start_marquee(self, event, *, additive: bool) -> None:
        xy = self._event_data_xy(event)
        if xy is None:
            return
        self._marquee_additive = additive
        if not additive:
            self.selected.clear()
        self._marquee_origin = xy
        self._marquee_rect = None
        # Flush a clean frame, then blit only the rubber-band (no full redraws)
        self._redraw_graph_only(fit=False)
        self.canvas.draw()
        self._marquee_bg = self.canvas.copy_from_bbox(self.ax.bbox)
        accent = palette(self._theme).accent
        self._marquee_rect = Rectangle(
            xy,
            0.0,
            0.0,
            fill=True,
            facecolor=accent,
            alpha=0.22,
            edgecolor=accent,
            linewidth=1.6,
            linestyle="--",
            zorder=8,
            animated=True,
        )
        self.ax.add_patch(self._marquee_rect)
        self.ax.draw_artist(self._marquee_rect)
        self.canvas.blit(self.ax.bbox)

    def _paint_marquee(self, x1: float, y1: float) -> None:
        if self._marquee_origin is None or self._marquee_rect is None:
            return
        x0, y0 = self._marquee_origin
        self._marquee_rect.set_xy((min(x0, x1), min(y0, y1)))
        self._marquee_rect.set_width(abs(x1 - x0))
        self._marquee_rect.set_height(abs(y1 - y0))
        if self._marquee_bg is not None:
            self.canvas.restore_region(self._marquee_bg)
            self.ax.draw_artist(self._marquee_rect)
            self.canvas.blit(self.ax.bbox)
        else:
            self.canvas.draw_idle()

    def _on_motion(self, event) -> None:
        if self._marquee_origin is not None:
            xy = self._event_data_xy(event)
            if xy is None:
                return
            self._paint_marquee(*xy)
            return
        if self.drag_notch is None or self.drag_idx is None or event.inaxes != self.ax:
            return
        coords = _coords_from_drag_event(event)
        if coords is None or self._move_anchor_kmh is None or self._move_anchor_kn is None:
            return
        new_kmh = coords[0] * MS_TO_KMH
        new_kn = coords[1]
        live_xy = (round(new_kmh, 1), round(new_kn, 1))
        if live_xy == self._last_live_xy:
            return
        self._last_live_xy = live_xy
        d_kmh = new_kmh - self._move_anchor_kmh
        d_kn = new_kn - self._move_anchor_kn
        cfg = self.get_cfg()
        by_notch: dict[int, list[tuple[float, float]]] = {
            n: list(pts) for n, pts in cfg.throttle_power.items()
        }
        for (n, i), (sp0, te0) in self._move_origin.items():
            if n not in by_notch or not (0 <= i < len(by_notch[n])):
                continue
            kmh = max(0.0, sp0 * MS_TO_KMH + d_kmh)
            kn = max(0.0, te0 + d_kn)
            by_notch[n][i] = round_point(kmh / MS_TO_KMH, kn)
        for n, pts in by_notch.items():
            cfg.throttle_power[n] = pts
        # ponytail: skip table rebuild while dragging — sync on release
        self._redraw_graph_only(fit=False, live=True)

    def _on_release(self, event) -> None:
        if self._marquee_origin is not None:
            x0, y0 = self._marquee_origin
            xy = self._event_data_xy(event)
            x1, y1 = xy if xy is not None else (x0, y0)
            xmin, xmax = min(x0, x1), max(x0, x1)
            ymin, ymax = min(y0, y1), max(y0, y1)
            picked: set[tuple[int, int]] = set()
            cfg = self.get_cfg()
            for notch, pts in cfg.throttle_power.items():
                for i, (sp, te) in enumerate(pts):
                    kmh = sp * MS_TO_KMH
                    if xmin <= kmh <= xmax and ymin <= te <= ymax:
                        picked.add((int(notch), i))
            if self._marquee_additive:
                self.selected |= picked
            else:
                self.selected = picked
            self._marquee_origin = None
            self._marquee_rect = None
            self._marquee_bg = None
            self._marquee_additive = False
            self._redraw_graph_only(fit=False)
            return
        if self.drag_notch is not None:
            cfg = self.get_cfg()
            moved = {
                (n, i): round_point(*cfg.throttle_power[n][i])
                for (n, i) in self._move_origin
                if n in cfg.throttle_power and 0 <= i < len(cfg.throttle_power[n])
            }
            touched = {n for n, _ in self._move_origin}
            for n in touched:
                cfg.throttle_power[n] = normalize_points(cfg.throttle_power.get(n, []))
                self.on_change()
            if self._pre_drag is not None and self._pre_drag.throttle_power != cfg.throttle_power:
                self.record_undo(self._pre_drag)
            new_sel: set[tuple[int, int]] = set()
            wanted = set(moved.values())
            for n, pts in cfg.throttle_power.items():
                for i, pt in enumerate(pts):
                    if round_point(*pt) in wanted:
                        new_sel.add((int(n), i))
            self.selected = new_sel
            self._redraw(fit=False)
        self.drag_notch = None
        self.drag_idx = None
        self._move_origin = {}
        self._move_anchor_kmh = None
        self._move_anchor_kn = None
        self._last_live_xy = None
        self._pre_drag = None

    def add_point(self, notch: int) -> None:
        self.begin_edit()
        cfg = self.get_cfg()
        pts = list(cfg.throttle_power.get(notch, [(0.0, 0.0)]))
        if not pts:
            pts = [(0.0, 0.0)]
        else:
            last_x = max(p[0] for p in pts)
            last_y = pts[-1][1]
            pts.append((last_x + 2.0, last_y))
        self.focus_notch = notch
        self._set_notch_points(notch, pts)
        self._redraw()

    def del_point(self, notch: int) -> None:
        col = self.columns.get(notch)
        if not col:
            return
        idxs = col.selected_indices()
        if not idxs:
            return
        self.begin_edit()
        cfg = self.get_cfg()
        pts = sorted(cfg.throttle_power.get(notch, []), key=lambda p: p[0])
        for idx in idxs:  # already high→low
            if 0 <= idx < len(pts):
                pts.pop(idx)
        self.focus_notch = notch
        self._set_notch_points(notch, pts)
        self._redraw()

    def reorder_points(self, notch: int, pts: list[tuple[float, float]]) -> None:
        """Commit table drag-reorder (normalize sorts by speed for the curve)."""
        self.begin_edit()
        self.focus_notch = notch
        self._set_notch_points(notch, pts)
        self._redraw()
        self.status_cb(f"N{notch} reordered · sorted by speed")

    def commit_cell_edit(self, notch: int, idx: int, column: int, text: str) -> None:
        """Inline table edit — no popup. column 0 = km/h, 1 = kN."""
        cfg = self.get_cfg()
        pts = sorted(cfg.throttle_power.get(notch, []), key=lambda p: p[0])
        if not (0 <= idx < len(pts)):
            self._refresh_columns()
            return
        try:
            val = float(str(text).strip().replace(",", ""))
        except ValueError:
            self._refresh_columns()
            return
        x, y = pts[idx]
        if column == 0:
            new_pt = round_point(max(0.0, val / MS_TO_KMH), y)
        else:
            new_pt = round_point(x, max(0.0, val))
        if new_pt == (x, y):
            self._refresh_columns()
            return
        self.begin_edit()
        pts[idx] = new_pt
        self.focus_notch = notch
        self._set_notch_points(notch, pts)
        self._redraw()

    def apply_clone(self, src: int, targets: list[int]) -> None:
        targets = [n for n in targets if n != src]
        if not targets:
            QMessageBox.information(self, "Clone", "เลือก notch ปลายทาง (1–8) อย่างน้อย 1 อัน")
            return
        self._clone_notch(src, targets)

    def clone_to_higher(self, src: int) -> None:
        targets = [n for n in range(src + 1, 9) if n != src]
        if not targets:
            QMessageBox.information(self, "Clone", f"N{src} ไม่มี notch สูงกว่าให้ copy")
            return
        self._clone_notch(src, targets)

    def set_layout_animating(self, on: bool) -> None:
        """Freeze matplotlib while the Auto Tune dock squeezes the pane."""
        on = bool(on)
        self.setUpdatesEnabled(not on)
        self.canvas.setUpdatesEnabled(not on)
        if not on:
            self.canvas.draw_idle()

    def _clone_notch(self, src: int, targets: list[int]) -> None:
        self.begin_edit()
        cfg = self.get_cfg()
        src_pts = normalize_points(cfg.throttle_power.get(src, [(0.0, 0.0)]))
        for n in targets:
            cfg.throttle_power[n] = list(src_pts)
        self.on_change()
        self._redraw()
        self.status_cb(f"Cloned N{src} → {', '.join(f'N{t}' for t in targets)}")

    def _toggle_resist(self, on: bool) -> None:
        self._show_resist = bool(on)
        if on and self._resist_params is None:
            self.status_cb("Open Auto Tune (bottom bar) to set consist friction first")
        self._redraw_graph_only(fit=False)

    def _draw_resistance_overlay(self, cfg: EngineConfig, *, live: bool) -> None:
        if live or not self._show_resist or self._resist_params is None:
            return
        from ...lib.engine_tuner.autotune import balancing_speeds, resistance_curve

        max_kmh = float(self._xlim[1]) if self._xlim else float(self.max_kmh.value())
        curve = resistance_curve(self._resist_params, max_speed_kmh=max_kmh, samples=80)
        xs = [p[0] * MS_TO_KMH for p in curve]
        ys = [p[1] for p in curve]
        ink = "#0f172a" if self._theme == "light" else "#e2e8f0"
        self.ax.plot(
            xs,
            ys,
            color=ink,
            linewidth=1.85,
            label="Resistance",
            zorder=4,
            solid_capstyle="round",
        )
        hits = balancing_speeds(
            cfg.throttle_power, self._resist_params, max_speed_kmh=max_kmh
        )
        for h in hits:
            self.ax.axvline(
                h.speed_kmh, color="#22c55e", alpha=0.35, linewidth=1.0, zorder=2
            )
            self.ax.scatter(
                [h.speed_kmh],
                [h.force_kn],
                s=48,
                facecolors="none",
                edgecolors="#22c55e",
                linewidths=1.6,
                zorder=6,
            )

    def autotune_graph_limits(self) -> tuple[float, float]:
        max_kmh = float(self._xlim[1]) if self._xlim else float(self.max_kmh.value())
        max_kn = float(self._ylim[1]) if self._ylim else float(self.max_kn.value())
        return max_kmh, max_kn

    def apply_autotune(self, curves, resist, fit: bool, show: bool) -> None:
        cfg = self.get_cfg()
        self.begin_edit()
        cfg.throttle_power.clear()
        cfg.throttle_power.update(curves)
        self._resist_params = resist
        self._show_resist = show
        self.resist_cb.blockSignals(True)
        self.resist_cb.setChecked(show)
        self.resist_cb.blockSignals(False)
        self.on_change()
        if fit and curves:
            peak_te = max((te for pts in curves.values() for _, te in pts), default=80.0)
            self._xlim = (0.0, float(self.speed_cap_from_curves(curves)))
            self._ylim = (-0.5, peak_te * 1.08)
            self._sync_max_vars()
        self._redraw(fit=fit)
        if curves:
            n8 = curves.get(8) or curves.get(max(curves))
            tip = f"Auto Tune applied — N{max(curves)} standstill {n8[0][1]:.1f} kN"
            self.status_cb(tip)

    @staticmethod
    def speed_cap_from_curves(curves: dict[int, list[tuple[float, float]]]) -> float:
        mx = 0.0
        for pts in curves.values():
            for sp, _ in pts:
                mx = max(mx, sp * MS_TO_KMH)
        return mx if mx > 1.0 else 120.0