"""QML crash / previous-session error dialog — same glass as the studios."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Property, QObject, Qt, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .qml_host import _qml_ok, _quick

_QML = Path(__file__).resolve().parent / "qml" / "CrashDialog.qml"


def _theme_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return True
    mode = app.property("mstnTheme")
    if isinstance(mode, str):
        return mode != "light"
    return True


class _CrashBridge(QObject):
    changed = Signal()

    def __init__(
        self,
        dialog: QDialog,
        *,
        title: str,
        summary: str,
        detail: str,
        log_path: Path,
        kind: str,
        dark: bool,
        quit_on_ok: bool,
    ) -> None:
        super().__init__(dialog)
        self._dialog = dialog
        self._title = title
        self._summary = summary
        self._detail = detail
        self._log_path = str(log_path)
        self._folder = str(log_path.parent)
        self._kind = kind
        self._dark = dark
        self._quit_on_ok = quit_on_ok
        self._copy_label = "Copy error"
        self._blob = f"{title}\n{summary}\n\n{detail}\n\nLog: {log_path}"

    def _get_dark(self) -> bool:
        return self._dark

    def _get_title(self) -> str:
        return self._title

    def _get_summary(self) -> str:
        return self._summary

    def _get_detail(self) -> str:
        return self._detail

    def _get_log_path(self) -> str:
        return self._log_path

    def _get_kind(self) -> str:
        return self._kind

    def _get_quit(self) -> bool:
        return self._quit_on_ok

    def _get_copy_label(self) -> str:
        return self._copy_label

    dark = Property(bool, _get_dark, notify=changed)
    title = Property(str, _get_title, notify=changed)
    summary = Property(str, _get_summary, notify=changed)
    detail = Property(str, _get_detail, notify=changed)
    logPath = Property(str, _get_log_path, notify=changed)
    kind = Property(str, _get_kind, notify=changed)
    quitOnOk = Property(bool, _get_quit, notify=changed)
    copyLabel = Property(str, _get_copy_label, notify=changed)

    @Slot()
    def openFolder(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._folder))

    @Slot(str)
    def copyError(self, selected: str) -> None:
        clip = QApplication.clipboard()
        if clip is None:
            return
        clip.setText(selected.strip() or self._blob)
        self._copy_label = "Copied"
        self.changed.emit()
        QTimer.singleShot(1400, self._reset_copy)

    def _reset_copy(self) -> None:
        self._copy_label = "Copy error"
        self.changed.emit()

    @Slot()
    def dismiss(self) -> None:
        self._dialog.accept()


class _GlassCrashDialog(QDialog):
    """Frameless QML sheet (live error or previous-session notify)."""

    def __init__(
        self,
        *,
        title: str,
        summary: str,
        detail: str,
        log_path: Path,
        kind: str = "error",
        quit_on_ok: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dark = _theme_dark()
        self._quit_on_ok = bool(quit_on_ok)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setMinimumSize(520, 420)
        self.resize(680, 560)

        self._bridge = _CrashBridge(
            self,
            title=title,
            summary=summary,
            detail=detail,
            log_path=log_path,
            kind=kind,
            dark=self._dark,
            quit_on_ok=self._quit_on_ok,
        )
        self._view = _quick(_QML, self._bridge)
        self._ok = _qml_ok(self._view)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        if self._ok:
            root.addWidget(self._view)
            return
        fallback = QLabel(f"{summary}\n\n{detail}\n\n{log_path}")
        fallback.setWordWrap(True)
        fallback.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.setContentsMargins(24, 24, 24, 24)
        root.addWidget(fallback)
        ok = QPushButton("OK")
        ok.clicked.connect(self.accept)
        root.addWidget(ok)

    @property
    def ok(self) -> bool:
        return self._ok


def _find_quit_host(parent: QWidget | None) -> QWidget | None:
    """Main window (or parent window) that owns the quit fade."""
    if parent is not None:
        win = parent.window()
        if win is not None and win is not parent:
            return win
        if parent.isWindow():
            return parent
    app = QApplication.instance()
    if app is None:
        return None
    from PySide6.QtWidgets import QMainWindow

    for w in app.topLevelWidgets():
        if isinstance(w, QMainWindow) and w.isVisible():
            return w
    return None


def show_crash_dialog(
    *,
    title: str,
    summary: str,
    detail: str,
    log_path: Path,
    kind: str = "error",
    quit_on_ok: bool | None = None,
    parent: QWidget | None = None,
) -> None:
    """Modal glass dialog — safe to call from excepthook / boot notify.

    Live ``kind="error"`` closes the main window after OK (quit fade runs).
    Previous-session ``kind="warning"`` only dismisses so boot can continue.
    """
    if quit_on_ok is None:
        quit_on_ok = kind == "error"
    dlg = _GlassCrashDialog(
        title=title,
        summary=summary,
        detail=detail,
        log_path=log_path,
        kind=kind,
        quit_on_ok=quit_on_ok,
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
    if not quit_on_ok:
        return
    host = _find_quit_host(parent)
    if host is not None:
        # MainWindow.closeEvent runs animate_window_quit, then real close.
        host.close()
        return
    app = QApplication.instance()
    if app is not None:
        app.exit(1)
    raise SystemExit(1)
