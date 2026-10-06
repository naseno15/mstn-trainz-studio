"""Glassmorphism crash / previous-session error dialog — matches Studio frost chrome."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QRectF, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QPainter,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .frost import FrostGlassFrame
from .theme import app_font


def _theme_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    mode = app.property("mstnTheme")
    if isinstance(mode, str):
        return mode != "light"
    return True


class _GlassCrashDialog(QDialog):
    """Frameless dim veil + frost card (live error or previous-session notify)."""

    def __init__(
        self,
        *,
        title: str,
        summary: str,
        detail: str,
        log_path: Path,
        kind: str = "error",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = _theme_dark()
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumSize(520, 420)
        self.resize(640, 520)
        self._copy_blob = f"{title}\n{summary}\n\n{detail}\n\nLog: {log_path}"

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = FrostGlassFrame(radius=18.0)
        card.setObjectName("sidePanel")
        card.set_dark(self._dark)
        card.setFixedWidth(560)
        self._card = card
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 22)
        cl.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(14)
        mark = QLabel("!" if kind == "warning" else "×")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setObjectName("crashMark")
        mark.setStyleSheet(self._mark_qss(kind))
        head.addWidget(mark)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("welcomeTitle")
        t.setFont(app_font(16, QFont.Weight.Bold))
        titles.addWidget(t)
        sub = QLabel(summary)
        sub.setObjectName("mutedTip")
        sub.setWordWrap(True)
        sub.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        sub.setFont(app_font(12, QFont.Weight.Medium))
        titles.addWidget(sub)
        head.addLayout(titles, 1)
        cl.addLayout(head)

        tip = QLabel("Traceback — select text or use Copy")
        tip.setObjectName("mutedTip")
        tip.setFont(app_font(11, QFont.Weight.DemiBold))
        cl.addWidget(tip)

        body = QPlainTextEdit()
        body.setReadOnly(True)
        body.setUndoRedoEnabled(False)
        body.setPlainText(detail)
        body.setObjectName("crashTrace")
        body.setMinimumHeight(220)
        body.setStyleSheet(self._trace_qss())
        body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        mono = QFont("Cascadia Mono", 10)
        if not mono.exactMatch():
            mono = QFont("Consolas", 10)
        body.setFont(mono)
        self._body = body
        cl.addWidget(body, 1)

        log_lab = QLabel(str(log_path))
        log_lab.setObjectName("mutedTip")
        log_lab.setWordWrap(True)
        log_lab.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        cl.addWidget(log_lab)

        row = QHBoxLayout()
        row.setSpacing(10)
        open_btn = QPushButton("Open log folder")
        open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(log_path.parent))
            )
        )
        row.addWidget(open_btn)
        copy_btn = QPushButton("Copy error")
        copy_btn.setToolTip("Copy title, summary, traceback, and log path")
        copy_btn.clicked.connect(self._copy_error)
        self._copy_btn = copy_btn
        row.addWidget(copy_btn)
        row.addStretch(1)
        ok = QPushButton("OK")
        ok.setObjectName("accentBtn")
        ok.setMinimumWidth(110)
        ok.setMinimumHeight(36)
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(ok)
        cl.addLayout(row)

        root.addWidget(card)

    def _copy_error(self) -> None:
        clip = QApplication.clipboard()
        if clip is None:
            return
        # Selection wins if user highlighted a slice; else full report.
        selected = self._body.textCursor().selectedText().replace("\u2029", "\n")
        clip.setText(selected if selected.strip() else self._copy_blob)
        self._copy_btn.setText("Copied")
        QTimer.singleShot(1400, lambda: self._copy_btn.setText("Copy error"))

    def _mark_qss(self, kind: str) -> str:
        if kind == "warning":
            bg, fg = "rgba(255, 159, 10, 0.22)", "#ff9f0a"
        else:
            bg, fg = "rgba(255, 69, 58, 0.22)", "#ff453a"
        return (
            f"QLabel#crashMark {{ background: {bg}; color: {fg};"
            f" border-radius: 12px; font-weight: 800; font-size: 20px; }}"
        )

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
        # Dim glass veil over whatever is behind the dialog.
        if self._dark:
            p.fillRect(self.rect(), QColor(8, 10, 14, 160))
            veil = QRadialGradient(self.rect().center(), max(self.width(), self.height()) * 0.65)
            veil.setColorAt(0.0, QColor(255, 90, 31, 28))
            veil.setColorAt(0.45, QColor(18, 22, 28, 90))
            veil.setColorAt(1.0, QColor(6, 8, 10, 170))
            p.fillRect(self.rect(), veil)
        else:
            p.fillRect(self.rect(), QColor(240, 242, 245, 170))
        # Soft orange bloom behind the card.
        if self._card is not None:
            cr = self._card.geometry()
            bloom = QRectF(cr).adjusted(-24, -18, 24, 28)
            glow = QRadialGradient(bloom.center(), bloom.width() * 0.55)
            glow.setColorAt(0.0, QColor(255, 90, 31, 40 if self._dark else 28))
            glow.setColorAt(0.5, QColor(255, 90, 31, 12))
            glow.setColorAt(1.0, QColor(255, 90, 31, 0))
            p.fillRect(bloom, glow)


def show_crash_dialog(
    *,
    title: str,
    summary: str,
    detail: str,
    log_path: Path,
    kind: str = "error",
    parent: QWidget | None = None,
) -> None:
    """Modal glass dialog — safe to call from excepthook / boot notify."""
    dlg = _GlassCrashDialog(
        title=title,
        summary=summary,
        detail=detail,
        log_path=log_path,
        kind=kind,
        parent=parent,
    )
    if parent is not None:
        win = parent.window() or parent
        dlg.setGeometry(win.frameGeometry())
    else:
        screen = QApplication.primaryScreen()
        if screen is not None:
            ag = screen.availableGeometry()
            dlg.resize(min(640, ag.width() - 80), min(520, ag.height() - 80))
            dlg.move(
                ag.center().x() - dlg.width() // 2,
                ag.center().y() - dlg.height() // 2,
            )
    dlg.exec()
