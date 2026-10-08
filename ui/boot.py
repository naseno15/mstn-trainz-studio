"""Ultra-thin entry — QApplication before heavy MainWindow import."""
from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    # Before any OpenGL import (MeshView) — per-call glGetError kills orbit FPS.
    os.environ.setdefault("PYOPENGL_ERROR_CHECKING", "0")
    os.environ.setdefault("PYOPENGL_ERROR_LOGGING", "0")

    # Fast path: Explorer / Quick Preview — never import MainWindow.
    if any(a in ("--preview", "-p", "--explorer-preview") for a in argv[1:]):
        from .mesh_preview import run_preview

        return int(run_preview(argv))

    try:
        from ..util.hw import apply_all

        apply_all()
    except Exception:
        pass

    from PySide6.QtWidgets import QApplication, QMessageBox

    from .i18n import apply_language_font, ensure_ui_fonts, i18n
    from .icons import ensure_material_icons
    from .motion import install_button_hover_chrome
    from .theme import apply_theme, warm_theme_cache

    app = QApplication(argv)
    app.setApplicationName("MSTN Trainz Studio")
    app.setStyle("Fusion")
    ensure_material_icons()
    ensure_ui_fonts()
    i18n()  # load persisted language before first paint
    # Pre-build dark+light QSS for the persisted language (font-family in * {}).
    warm_theme_cache()
    apply_theme(app, "dark")
    apply_language_font()  # app font + QSS stack + rebase any early widgets
    # Every QPushButton / QToolButton: soft hover bubble + emboss (+ glass tip when set)
    install_button_hover_chrome(app)

    # Overlap heavy hub imports with MainWindow import + ctor.
    from ..util.preload import join_hub_module_preload, start_hub_module_preload

    start_hub_module_preload()

    try:
        # Heavy MainWindow AFTER QApplication exists (Qt already warm).
        from .app import (
            MainWindow,
            _install_crash_log,
            offer_pending_crash_report,
            warm_logo_cache,
        )

        crash_log = _install_crash_log()
        warm_logo_cache()  # dark+light logo pixmaps ready before first Theme click
        win = MainWindow()
    except Exception as exc:
        text = traceback.format_exc()
        crash_log = Path.home() / ".cache" / "trainz_studio" / "crash_last.txt"
        notify = crash_log.parent / "last_error.notify"
        try:
            crash_log.parent.mkdir(parents=True, exist_ok=True)
            crash_log.write_text(text, encoding="utf-8")
            # Also flag the standard last_error path used by offer_pending_crash_report.
            last = crash_log.parent / "last_error.txt"
            last.write_text(text, encoding="utf-8")
            notify.write_text("1", encoding="utf-8")
        except OSError:
            pass
        QMessageBox.critical(
            None,
            "Trainz Studio failed to start",
            f"{exc}\n\nDetails written to:\n{crash_log}",
        )
        return 1

    initials = [Path(a) for a in argv[1:] if a and not str(a).startswith("-")]

    from PySide6.QtCore import Qt

    # Cover → warm Mesh → reveal HOME. Sounds/Engine/Assets warm idle after.
    win.go_home()
    # MeshView must exist before first show — otherwise Windows recreates the HWND
    # when the first QOpenGLWidget lands (looks like close + reopen mid-warm).
    win.prewarm_mesh_gl()
    # GL prewarm can create the HWND at default size — force maximized on first show
    # and again after warm (drag / compositor can leave it restored).
    win.setWindowState(Qt.WindowState.WindowMaximized)
    win.showMaximized()
    win.raise_()
    win.activateWindow()
    win._layout_viewer_pane()
    win._overlay.set_brand("Trainz Studio")
    win._overlay.set_stage("Starting…", 12)
    # Skip frost grab at boot — grab+blur was a big first-paint tax; dim card is enough.
    win._overlay.set_frost(None)
    win._overlay.setGeometry(win.rect())
    win._overlay.show()
    win._overlay.raise_()
    # Title bar above cover: drag / traffic lights while Mesh warms.
    win._raise_overlay_chrome()
    app.processEvents()
    if not win.isMaximized():
        win.showMaximized()

    win._overlay.set_stage("Warming Mesh Studio…", 35)
    app.processEvents()

    # Finish background imports before building Mesh chrome trees.
    join_hub_module_preload(timeout=12.0)

    _last_pe = [0.0]

    def _boot_stage(text: str, pct: int) -> None:
        win._overlay.set_stage(text, pct)
        # Keep title bar above cover — processEvents / resize can bury it.
        win._raise_overlay_chrome()
        # Throttle processEvents — every stage was re-entering the event loop hard.
        import time

        now = time.monotonic()
        if now - _last_pe[0] >= 0.05 or pct >= 100:
            _last_pe[0] = now
            app.processEvents()

    win.warmup_hub_studios(on_stage=_boot_stage)
    win._layout_viewer_pane()
    # Theme/logo already warm before MainWindow — no second rebuild here.
    win._overlay.set_stage("Ready", 100)
    app.processEvents()
    win._hide_overlay()
    # Boot must end maximized — frameless drag / early HWND create can leave restored.
    win.showMaximized()
    win.setWindowState(win.windowState() | Qt.WindowState.WindowMaximized)

    if initials:
        from ..audio.classify import partition_paths

        buckets = partition_paths(initials)
        if buckets["mesh"]:
            win.open_paths(buckets["mesh"], mode="replace")
        elif buckets["audio"] or buckets["video"]:
            win.enter_sounds_studio(buckets["audio"] + buckets["video"])
        else:
            win.open_paths(initials, mode="replace")
    from ..io.project import has_crash_recovery

    # Pending Python crash from last run (fade/opacity / uncaught exception).
    offer_pending_crash_report(win)

    if has_crash_recovery():
        win._offer_crash_restore()

    return app.exec()
