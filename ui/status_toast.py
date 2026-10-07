"""Overlay toast bubble + clickable status-bar log — frost chrome like crash_dialog.

Kinds: save · drop · progress · info. Progress toasts update in place with %.
"""
from __future__ import annotations

import re
from datetime import datetime

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QRadialGradient
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from .frost import FrostGlassFrame
from .theme import app_font

_SAVE_MS = 5000
_DROP_MS = 5000
_DONE_MS = 2800
_LOG_CAP = 400
_PCT_RE = re.compile(r"(?P<pct>\d{1,3})\s*%")

# User-initiated save success (not Autosave / failed / prompts).
_SAVE_POS = (
    "saved",
    "wrote ",
    "wrote\t",
    "exported",
    "บันทึกแล้ว",
    "บันทึกและ",
    "tersimpan",
    "保存しました",
    "保存完了",
)
_SAVE_NEG = (
    "autosaved",
    "autosave",
    "failed",
    "error",
    "ไม่สำเร็จ",
    "needs",
    "to save",
    "to write",
)

_KIND_MARK = {
    "save": ("✓", "rgba(48, 209, 88, 0.22)", "#30d158"),
    "drop": ("↓", "rgba(255, 90, 31, 0.22)", "#ff5a1f"),
    "progress": ("…", "rgba(90, 200, 250, 0.22)", "#64d2ff"),
    "info": ("i", "rgba(255, 214, 10, 0.20)", "#ffd60a"),
}

_KIND_BLOOM = {
    "save": QColor(48, 209, 88),
    "drop": QColor(255, 90, 31),
    "progress": QColor(100, 210, 255),
    "info": QColor(255, 214, 10),
}


def is_save_notice(msg: str) -> bool:
    """True when a status line means a successful user save / export."""
    text = (msg or "").strip()
    if not text:
        return False
    low = text.lower()
    if any(n in low for n in _SAVE_NEG):
        return False
    if any(p in low for p in _SAVE_POS):
        return True
    return low.startswith("wrote")


def parse_progress_pct(msg: str) -> int | None:
    """Extract 0–100 from a status line like ``Exporting mesh… 42%``."""
    text = (msg or "").strip()
    if not text or "%" not in text:
        return None
    m = _PCT_RE.search(text)
    if m is None:
        return None
    return max(0, min(100, int(m.group("pct"))))


def format_drop_detail(paths: list) -> str:
    """Short file-name list for drop toasts."""
    names: list[str] = []
    for p in paths[:6]:
        name = getattr(p, "name", None) or str(p)
        names.append(str(name))
    if len(paths) > 6:
        names.append(f"+{len(paths) - 6}")
    return " · ".join(names)


def _theme_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    mode = app.property("mstnTheme")
    if isinstance(mode, str):
        return mode != "light"
    return True


def _t(key: str) -> str:
    try:
        from .i18n import t

        return t(key)
    except Exception:
        return key


def _anchor_for(host: QWidget) -> QWidget:
    cw = getattr(host, "centralWidget", lambda: None)()
    return cw if cw is not None else host


class _StatusLogLabel(QLabel):
    """Left status chip — click opens the full log."""

    clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("statusLogMsg")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)


class StudioStatusBar(QStatusBar):
    """Status bar that keeps a ring log and signals toast-worthy lines."""

    log_open_requested = Signal()
    save_noticed = Signal(str)
    progress_noticed = Signal(str, int)  # detail, pct
    # Non-% status after a sticky progress toast (Loaded / VE / theme…)
    progress_cleared = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: list[str] = []
        self._chip = _StatusLogLabel(self)
        self._chip.clicked.connect(self.log_open_requested.emit)
        self.addWidget(self._chip, 1)
        self._clear_timer = QTimer(self)
        self._clear_timer.setSingleShot(True)
        self._clear_timer.timeout.connect(self._on_timeout_clear)
        self._had_progress = False

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def showMessage(self, message: str, timeout: int = 0) -> None:  # noqa: N802
        text = str(message or "")
        if text.strip():
            stamp = datetime.now().strftime("%H:%M:%S")
            self._history.append(f"[{stamp}] {text}")
            if len(self._history) > _LOG_CAP:
                self._history = self._history[-_LOG_CAP:]
            self._chip.setText(text)
            self._chip.setToolTip(f"{text}\n\n{_t('Click for status log')}")
            pct = parse_progress_pct(text)
            if pct is not None:
                self._had_progress = True
                self.progress_noticed.emit(text, pct)
            elif is_save_notice(text):
                self._had_progress = False
                self.save_noticed.emit(text)
            elif self._had_progress:
                # Load tops out at 99% ("Handing off") — next plain status must close toast.
                self._had_progress = False
                self.progress_cleared.emit(text)
        else:
            self._chip.clear()
        self._clear_timer.stop()
        if timeout and timeout > 0:
            self._clear_timer.start(int(timeout))

    def clearMessage(self) -> None:  # noqa: N802
        self._clear_timer.stop()

    def _on_timeout_clear(self) -> None:
        pass


class GlassToastBubble(QWidget):
    """Center-bottom overlay bubble — slide + fade; optional progress bar."""

    def __init__(
        self,
        host: QWidget,
        *,
        kind: str,
        title: str,
        detail: str = "",
        ms: int = _SAVE_MS,
        progress: int | None = None,
    ) -> None:
        super().__init__(host)
        self._host = host
        self._kind = kind if kind in _KIND_MARK else "info"
        self._dark = _theme_dark()
        self._ms = int(ms)
        self._dismissing = False
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self.dismiss)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 14)

        card = FrostGlassFrame(radius=18.0)
        card.setObjectName("sidePanel")
        card.set_dark(self._dark)
        self._card = card
        cl = QVBoxLayout(card)
        cl.setContentsMargins(16, 12, 18, 12)
        cl.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(12)
        mark_ch, mark_bg, mark_fg = _KIND_MARK[self._kind]
        self._mark = QLabel(mark_ch)
        self._mark.setFixedSize(34, 34)
        self._mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mark.setObjectName("toastMark")
        self._mark.setStyleSheet(
            f"QLabel#toastMark {{ background: {mark_bg}; color: {mark_fg};"
            f" border-radius: 10px; font-weight: 800; font-size: 16px; }}"
        )
        row.addWidget(self._mark)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self._title = QLabel(title)
        self._title.setObjectName("welcomeTitle")
        self._title.setFont(app_font(13, QFont.Weight.Bold))
        texts.addWidget(self._title)
        self._detail = QLabel(detail.strip())
        self._detail.setObjectName("mutedTip")
        self._detail.setWordWrap(True)
        self._detail.setMaximumWidth(440)
        self._detail.setFont(app_font(11, QFont.Weight.Medium))
        self._detail.setVisible(bool(detail.strip()))
        texts.addWidget(self._detail)
        row.addLayout(texts, 1)

        self._pct_lab = QLabel("")
        self._pct_lab.setObjectName("mutedTip")
        self._pct_lab.setFont(app_font(12, QFont.Weight.DemiBold))
        self._pct_lab.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self._pct_lab.setMinimumWidth(44)
        row.addWidget(self._pct_lab)
        cl.addLayout(row)

        self._bar = QProgressBar()
        self._bar.setObjectName("toastProgress")
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(6)
        self._bar.setStyleSheet(
            "QProgressBar#toastProgress {"
            " background: rgba(127,127,127,0.22); border: none; border-radius: 3px; }"
            "QProgressBar#toastProgress::chunk {"
            " background: #64d2ff; border-radius: 3px; }"
        )
        cl.addWidget(self._bar)
        root.addWidget(card)

        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)

        if progress is not None or self._kind == "progress":
            self._apply_progress(0 if progress is None else int(progress))
        else:
            self._bar.hide()
            self._pct_lab.hide()

        self.adjustSize()
        host.installEventFilter(self)
        self._play_in()
        if self._ms > 0 and self._kind != "progress":
            self._hold_timer.start(self._ms)

    @property
    def kind(self) -> str:
        return self._kind

    def eventFilter(self, obj, event):  # noqa: N802
        if obj is self._host and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            self._reposition(animate=False)
        return super().eventFilter(obj, event)

    def set_content(
        self,
        *,
        kind: str | None = None,
        title: str | None = None,
        detail: str | None = None,
        progress: int | None = None,
        ms: int | None = None,
    ) -> None:
        if kind is not None and kind in _KIND_MARK:
            self._kind = kind
            ch, bg, fg = _KIND_MARK[kind]
            self._mark.setText(ch)
            self._mark.setStyleSheet(
                f"QLabel#toastMark {{ background: {bg}; color: {fg};"
                f" border-radius: 10px; font-weight: 800; font-size: 16px; }}"
            )
            self.update()
        if title is not None:
            self._title.setText(title)
        if detail is not None:
            self._detail.setText(detail.strip())
            self._detail.setVisible(bool(detail.strip()))
        if progress is not None:
            self._apply_progress(progress)
        elif kind is not None and kind != "progress":
            self._bar.hide()
            self._pct_lab.hide()
        if ms is not None:
            self._ms = int(ms)
            self._hold_timer.stop()
            if self._ms > 0 and self._kind != "progress":
                self._hold_timer.start(self._ms)
        self.adjustSize()
        self._reposition(animate=False)

    def _apply_progress(self, pct: int) -> None:
        pct = max(0, min(100, int(pct)))
        self._bar.show()
        self._pct_lab.show()
        self._bar.setValue(pct)
        self._pct_lab.setText(f"{pct}%")

    def _bottom_clearance(self) -> int:
        """Sit above floating bottom nav / shortcut / bake bar (not on top of them)."""
        # Status bar is outside the central widget — only clear in-content chrome.
        gap = 14
        win = self._host.window() if self._host is not None else None
        extra = 0
        for name in ("_bake_bar", "_shortcut_bar", "_nav"):
            bar = getattr(win, name, None) if win is not None else None
            if bar is not None and bar.isVisible():
                extra += max(0, int(bar.height())) + 8
        # Mesh chrome: nav 64 + shortcut ~26 + pads ≈ matches _reposition_viewer_chrome
        if extra > 0:
            return extra + gap
        return 20

    def _rest_rect(self) -> QRect:
        host = self._host
        margin = self._bottom_clearance()
        self.adjustSize()
        w, h = self.width(), self.height()
        x = max(8, (host.width() - w) // 2)
        y = max(8, host.height() - h - margin)
        return QRect(x, y, w, h)

    def _reposition(self, *, animate: bool) -> None:
        del animate
        if self._dismissing:
            return
        self.setGeometry(self._rest_rect())
        self.raise_()

    def _play_in(self) -> None:
        rest = self._rest_rect()
        start = QRect(rest.x(), rest.y() + 28, rest.width(), rest.height())
        self.setGeometry(start)
        self.show()
        self.raise_()
        self._eff.setOpacity(0.0)
        group = QParallelAnimationGroup(self)
        geo = QPropertyAnimation(self, b"geometry", self)
        geo.setDuration(320)
        geo.setStartValue(start)
        geo.setEndValue(rest)
        geo.setEasingCurve(QEasingCurve.Type.OutCubic)
        op = QPropertyAnimation(self._eff, b"opacity", self)
        op.setDuration(280)
        op.setStartValue(0.0)
        op.setEndValue(1.0)
        op.setEasingCurve(QEasingCurve.Type.OutCubic)
        group.addAnimation(geo)
        group.addAnimation(op)
        group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def dismiss(self) -> None:
        if self._dismissing:
            return
        self._dismissing = True
        self._hold_timer.stop()
        rest = self.geometry()
        end = QRect(rest.x(), rest.y() + 22, rest.width(), rest.height())
        group = QParallelAnimationGroup(self)
        geo = QPropertyAnimation(self, b"geometry", self)
        geo.setDuration(220)
        geo.setStartValue(rest)
        geo.setEndValue(end)
        geo.setEasingCurve(QEasingCurve.Type.InCubic)
        op = QPropertyAnimation(self._eff, b"opacity", self)
        op.setDuration(200)
        op.setStartValue(float(self._eff.opacity()))
        op.setEndValue(0.0)
        op.setEasingCurve(QEasingCurve.Type.InCubic)
        group.addAnimation(geo)
        group.addAnimation(op)
        group.finished.connect(self._finish_dismiss)
        group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _finish_dismiss(self) -> None:
        host = self._host
        if host is not None:
            try:
                host.removeEventFilter(self)
            except Exception:
                pass
        self.hide()
        self.deleteLater()

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        if self._card is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        bloom_c = _KIND_BLOOM.get(self._kind, _KIND_BLOOM["info"])
        cr = self._card.geometry()
        bloom = cr.adjusted(-20, -14, 20, 22)
        glow = QRadialGradient(bloom.center(), max(bloom.width(), 1) * 0.55)
        a0 = 40 if self._dark else 28
        glow.setColorAt(0.0, QColor(bloom_c.red(), bloom_c.green(), bloom_c.blue(), a0))
        glow.setColorAt(0.55, QColor(bloom_c.red(), bloom_c.green(), bloom_c.blue(), 10))
        glow.setColorAt(1.0, QColor(bloom_c.red(), bloom_c.green(), bloom_c.blue(), 0))
        p.fillRect(bloom, glow)


class ToastHost:
    """One live overlay bubble on the main window central widget."""

    def __init__(self, window: QWidget) -> None:
        self._window = window
        self._toast: GlassToastBubble | None = None
        self._last_prog_ms = 0.0
        self._last_prog_pct = -1
        self._finishing = False

    def _anchor(self) -> QWidget:
        return _anchor_for(self._window)

    def _bind(self, toast: GlassToastBubble) -> None:
        self._toast = toast
        # Keep a back-ref on the window for dismiss cleanup / tests.
        self._window._save_toast = toast  # type: ignore[attr-defined]

        def _clear() -> None:
            if self._toast is toast:
                self._toast = None
            if getattr(self._window, "_save_toast", None) is toast:
                self._window._save_toast = None  # type: ignore[attr-defined]

        toast.destroyed.connect(_clear)

    def notify(
        self,
        kind: str,
        title: str,
        detail: str = "",
        *,
        ms: int = _SAVE_MS,
        progress: int | None = None,
    ) -> None:
        kind = kind if kind in _KIND_MARK else "info"
        toast = self._toast
        # Reuse sticky progress bubble when updating the same kind.
        if (
            toast is not None
            and not toast._dismissing
            and toast.kind == "progress"
            and kind == "progress"
        ):
            toast.set_content(
                title=title, detail=detail, progress=progress, ms=0
            )
            return
        if toast is not None and not toast._dismissing:
            toast.dismiss()
            self._toast = None
        bubble = GlassToastBubble(
            self._anchor(),
            kind=kind,
            title=title,
            detail=detail,
            ms=0 if kind == "progress" else ms,
            progress=progress,
        )
        self._bind(bubble)

    def progress(self, title: str, pct: int, detail: str = "") -> None:
        """Sticky progress bubble — throttled; finishes itself at 100%."""
        import time

        pct = max(0, min(100, int(pct)))
        now = time.monotonic()
        # ~12 Hz / every 2% — keep UI light during mesh load / bake / export
        if (
            pct < 100
            and pct - self._last_prog_pct < 2
            and now - self._last_prog_ms < 0.08
        ):
            return
        self._last_prog_ms = now
        self._last_prog_pct = pct
        sub = detail.strip() or title
        self.notify("progress", title, sub, ms=0, progress=pct)
        if pct >= 100:
            self.finish(detail or title)

    def finish(self, detail: str = "") -> None:
        """Close sticky progress even when the job never emitted 100%."""
        self._last_prog_pct = -1
        toast = self._toast
        if (
            self._finishing
            or toast is None
            or toast._dismissing
            or toast.kind != "progress"
        ):
            return
        self._finishing = True
        # Snap bar to full, then Done (covers LoadWorker ending at 99%).
        toast.set_content(progress=100)
        sub = (detail or "").strip()

        def _done() -> None:
            self._finishing = False
            self.notify("save", _t("Done"), sub, ms=_DONE_MS)

        QTimer.singleShot(180, _done)

    def drop(self, paths: list, *, title: str | None = None) -> None:
        if not paths:
            return
        detail = format_drop_detail(paths)
        n = len(paths)
        if title is None:
            title = _t("Dropped") if n == 1 else _t("Dropped files")
            if n > 1:
                title = f"{title} · {n}"
        self.notify("drop", title, detail, ms=_DROP_MS)

    def save(self, detail: str = "") -> None:
        title = _t("Saved")
        sub = (detail or "").strip()
        if sub.lower() in {title.lower(), "saved", "บันทึกแล้ว"}:
            sub = ""
        self.notify("save", title, sub, ms=_SAVE_MS)


class _GlassStatusLogDialog(QDialog):
    """Frameless frost sheet listing recent status-bar lines."""

    def __init__(
        self,
        lines: list[str],
        *,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = _theme_dark()
        title = _t("Status log")
        tip = _t("Recent status messages — click the footer anytime")
        close_lab = _t("Close")
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(480, 360)
        self.resize(560, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = FrostGlassFrame(radius=18.0)
        card.setObjectName("sidePanel")
        card.set_dark(self._dark)
        card.setFixedWidth(520)
        self._card = card
        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 20, 24, 18)
        cl.setSpacing(10)

        head = QHBoxLayout()
        head.setSpacing(12)
        mark = QLabel("≡")
        mark.setFixedSize(36, 36)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            "QLabel {"
            " background: rgba(255, 90, 31, 0.18); color: #ff5a1f;"
            " border-radius: 11px; font-weight: 800; font-size: 16px; }"
        )
        head.addWidget(mark)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        tlab = QLabel(title)
        tlab.setObjectName("welcomeTitle")
        tlab.setFont(app_font(15, QFont.Weight.Bold))
        titles.addWidget(tlab)
        sub = QLabel(tip)
        sub.setObjectName("mutedTip")
        sub.setWordWrap(True)
        sub.setFont(app_font(11, QFont.Weight.Medium))
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        cl.addLayout(head)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setUndoRedoEnabled(False)
        body.setPlainText("\n".join(lines) if lines else "(empty)")
        body.setObjectName("crashTrace")
        body.setMinimumHeight(220)
        body.setStyleSheet(self._trace_qss())
        mono = QFont("Cascadia Mono", 10)
        if not mono.exactMatch():
            mono = QFont("Consolas", 10)
        body.setFont(mono)
        cl.addWidget(body, 1)

        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton(close_lab)
        ok.setObjectName("accentBtn")
        ok.setMinimumWidth(100)
        ok.setMinimumHeight(34)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        cl.addLayout(row)
        root.addWidget(card)

    def _trace_qss(self) -> str:
        if self._dark:
            return (
                "QPlainTextEdit#crashTrace {"
                " background: rgba(8, 10, 14, 0.55);"
                " color: rgba(235, 235, 245, 0.88);"
                " border: 1px solid rgba(255, 255, 255, 0.10);"
                " border-radius: 12px; padding: 10px; }"
            )
        return (
            "QPlainTextEdit#crashTrace {"
            " background: rgba(255, 255, 255, 0.72);"
            " color: #1d1d1f;"
            " border: 1px solid rgba(0, 0, 0, 0.10);"
            " border-radius: 12px; padding: 10px; }"
        )

    def paintEvent(self, event) -> None:  # noqa: N802
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if self._dark:
            p.fillRect(self.rect(), QColor(8, 10, 14, 160))
            veil = QRadialGradient(
                self.rect().center(), max(self.width(), self.height()) * 0.65
            )
            veil.setColorAt(0.0, QColor(255, 90, 31, 28))
            veil.setColorAt(0.45, QColor(18, 22, 28, 90))
            veil.setColorAt(1.0, QColor(6, 8, 10, 170))
            p.fillRect(self.rect(), veil)
        else:
            p.fillRect(self.rect(), QColor(240, 242, 245, 170))


def show_save_toast(
    host: QWidget | None,
    detail: str = "",
    *,
    ms: int = _SAVE_MS,
) -> None:
    """Compat: show a save bubble (uses ToastHost when present)."""
    if host is None:
        return
    hub = getattr(host, "_toasts", None)
    if not isinstance(hub, ToastHost):
        hub = ToastHost(host)
        host._toasts = hub  # type: ignore[attr-defined]
    title = _t("Saved")
    sub = (detail or "").strip()
    if sub.lower() in {title.lower(), "saved", "บันทึกแล้ว"}:
        sub = ""
    hub.notify("save", title, sub, ms=ms)


def show_status_log_dialog(
    parent: QWidget | None,
    lines: list[str],
) -> None:
    """Modal frost dialog with the status-bar history."""
    dlg = _GlassStatusLogDialog(lines, parent=parent)
    if parent is not None:
        win = parent.window() or parent
        dlg.setGeometry(win.frameGeometry())
    dlg.exec()
