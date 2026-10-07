"""Rounded table / tree / list rows — real radii + hover bubble (QSS can't).

Windows styles often ignore ``border-radius`` on ``::item`` selection, so the
orange selector and hover stay square while the glass shell is round. This
delegate paints a full-row pill; ``install_rounded_rows`` is hooked from
``enable_smooth_scroll`` so every studio table gets it.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QModelIndex, QObject, QPersistentModelIndex, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QRegion
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

ROW_RADIUS = 10.0
ROW_INSET_X = 4
ROW_INSET_Y = 1
VIEW_CLIP_RADIUS = 12


def _theme_mode(widget: QObject | None) -> str:
    app = QApplication.instance()
    if app is not None:
        m = app.property("mstnTheme")
        if m in ("dark", "light"):
            return m
    w = widget
    while w is not None:
        if isinstance(w, QAbstractItemView):
            m = w.property("mstnTheme")
            if m in ("dark", "light"):
                return m
        w = w.parent()  # type: ignore[assignment]
    return "dark"


def _row_fills(widget: QObject | None) -> tuple[QColor, QColor]:
    from .theme import palette

    p = palette(_theme_mode(widget))
    # Stronger wash than p.selection (0.18α reads as hollow orange rim on dark glass).
    if p.mode == "dark":
        sel = QColor(255, 90, 31, 72)
        hover = QColor(255, 255, 255, 28)
    else:
        sel = QColor(255, 90, 31, 56)
        hover = QColor(0, 0, 0, 22)
    return sel, hover


def _view_column_count(view: QAbstractItemView) -> int:
    """Column span for a full-row pill — never call model.columnCount.

    PySide6 traps: table models reject ``columnCount(parent)`` as private;
    ``QAbstractListModel`` rejects the no-arg form. Header count (or 1 for
    lists) is what we paint against anyway.
    """
    for name in ("horizontalHeader", "header"):
        getter = getattr(view, name, None)
        if not callable(getter):
            continue
        try:
            h = getter()
        except Exception:
            continue
        if h is None or not hasattr(h, "count"):
            continue
        try:
            n = int(h.count())
        except Exception:
            continue
        if n >= 1:
            return n
    return 1


def _row_rect(view: QAbstractItemView, index: QModelIndex) -> QRect:
    cols = _view_column_count(view)
    left = view.visualRect(index.sibling(index.row(), 0))
    right = view.visualRect(index.sibling(index.row(), cols - 1))
    if not left.isValid():
        return view.visualRect(index)
    if right.isValid():
        return left.united(right)
    return left


class RoundedRowDelegate(QStyledItemDelegate):
    """Full-row rounded hover bubble + orange selection pill."""

    def __init__(self, view: QAbstractItemView) -> None:
        super().__init__(view)
        self._view = view
        self._hover: QPersistentModelIndex | None = None

    def set_hover(self, index: QModelIndex | None) -> None:
        key = QPersistentModelIndex(index) if index is not None and index.isValid() else None
        prev = self._hover
        if prev is not None and key is not None and prev == key:
            return
        if prev is None and key is None:
            return
        self._hover = key
        vp = self._view.viewport()
        if vp is not None:
            vp.update()

    def _is_hover_row(self, index: QModelIndex) -> bool:
        h = self._hover
        if h is None or not h.isValid():
            return False
        return (
            index.row() == h.row()
            and index.parent() == h.parent()
            and index.model() is h.model()
        )

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        selected = bool(opt.state & QStyle.StateFlag.State_Selected)
        hovered = self._is_hover_row(index) or bool(
            opt.state & QStyle.StateFlag.State_MouseOver
        )
        # Kill square QSS / style selection + hover fills — we paint the pill.
        opt.state &= ~(
            QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_MouseOver
        )
        if selected or hovered:
            # Prevent alternate/stripe panels from covering the rounded pill.
            opt.features &= ~QStyleOptionViewItem.ViewItemFeature.Alternate
            opt.backgroundBrush = QColor(0, 0, 0, 0)

        if selected or hovered:
            row = _row_rect(self._view, index).adjusted(
                ROW_INSET_X, ROW_INSET_Y, -ROW_INSET_X, -ROW_INSET_Y
            )
            if row.width() > 4 and row.height() > 4:
                sel_c, hover_c = _row_fills(self._view)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                # Each column paints its slice of the same rounded path.
                painter.setClipRect(option.rect)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(sel_c if selected else hover_c)
                painter.drawRoundedRect(QRectF(row), ROW_RADIUS, ROW_RADIUS)
                # Soft rim — selected = warm edge; hover = hairline only.
                if selected:
                    rim = QColor(255, 90, 31, 160)
                elif hovered:
                    rim = (
                        QColor(255, 255, 255, 40)
                        if _theme_mode(self._view) == "dark"
                        else QColor(0, 0, 0, 28)
                    )
                else:
                    rim = None
                if rim is not None:
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(rim)
                    painter.drawRoundedRect(
                        QRectF(row).adjusted(0.5, 0.5, -0.5, -0.5),
                        ROW_RADIUS,
                        ROW_RADIUS,
                    )
                painter.restore()

        style = opt.widget.style() if opt.widget is not None else QApplication.style()
        if style is not None:
            style.drawControl(
                QStyle.ControlElement.CE_ItemViewItem, opt, painter, opt.widget
            )
        else:
            super().paint(painter, opt, index)


class _RowHoverFilter(QObject):
    def __init__(self, view: QAbstractItemView, delegate: RoundedRowDelegate) -> None:
        super().__init__(view)
        self._view = view
        self._delegate = delegate

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et in (QEvent.Type.Leave, QEvent.Type.HoverLeave):
            self._delegate.set_hover(None)
            return False
        if et in (
            QEvent.Type.MouseMove,
            QEvent.Type.HoverMove,
            QEvent.Type.HoverEnter,
        ):
            pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            idx = self._view.indexAt(pos)
            if idx.isValid():
                self._delegate.set_hover(idx.sibling(idx.row(), 0))
            else:
                self._delegate.set_hover(None)
        return False


class _ViewClipFilter(QObject):
    """Clip the item view to a rounded mask so chrome matches glass shells."""

    def __init__(self, view: QAbstractItemView, *, radius: int = VIEW_CLIP_RADIUS) -> None:
        super().__init__(view)
        self._view = view
        self._radius = int(radius)
        view.installEventFilter(self)
        QApplication.instance()  # noqa: keep import side-effect free
        self._apply()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self._view and event.type() == QEvent.Type.Resize:
            self._apply()
        return False

    def _apply(self) -> None:
        r = self._view.rect()
        if r.width() < 8 or r.height() < 8:
            self._view.clearMask()
            return
        path = QPainterPath()
        path.addRoundedRect(QRectF(r), float(self._radius), float(self._radius))
        self._view.setMask(QRegion(path.toFillPolygon().toPolygon()))


def install_rounded_rows(view: QAbstractItemView) -> None:
    """Idempotent — rounded selection/hover + clip mask for studio item views."""
    if getattr(view, "_rounded_rows_installed", False):
        return
    view._rounded_rows_installed = True  # type: ignore[attr-defined]
    view.setMouseTracking(True)
    view.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    vp = view.viewport()
    if vp is not None:
        vp.setMouseTracking(True)
        vp.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
    # Full-row select so the orange pill reads as one bubble.
    view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    delegate = RoundedRowDelegate(view)
    view.setItemDelegate(delegate)
    hover = _RowHoverFilter(view, delegate)
    if vp is not None:
        vp.installEventFilter(hover)
    view._row_hover_filter = hover  # type: ignore[attr-defined]
    view._rounded_delegate = delegate  # type: ignore[attr-defined]
    # Clip square Win viewport into the same radius as glass / list_chrome.
    clip = _ViewClipFilter(view)
    view._round_clip = clip  # type: ignore[attr-defined]
