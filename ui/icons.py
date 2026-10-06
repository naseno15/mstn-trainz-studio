"""Material Icons helpers — glyph buttons for chrome actions (not menus / page nav).

Bottom page labels (Preview / Editor / …) and the menubar stay plain text.
Home / Theme and Save / Undo / Open-folder style actions use Material Icons.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QAbstractButton, QPushButton, QWidget

from .. import PKG_ROOT

# Subset of MaterialIcons-Regular.codepoints (Apache-2.0).
GLYPHS: dict[str, str] = {
    "home": "\ue88a",
    "dark_mode": "\ue51c",
    "light_mode": "\ue518",
    "save": "\ue161",
    "save_as": "\ueb60",
    "undo": "\ue166",
    "redo": "\ue15a",
    "folder": "\ue2c7",
    "folder_open": "\ue2c8",
    "file_open": "\ueaf3",
    "refresh": "\ue5d5",
    "close": "\ue5cd",
    "clear": "\ue14c",
    "cancel": "\ue5c9",
    "add": "\ue145",
    "delete": "\ue872",
    "check": "\ue5ca",
    "arrow_back": "\ue5c4",
    "play_arrow": "\ue037",
    "stop": "\ue047",
    "archive": "\ue149",
    "unarchive": "\ue169",
    "content_copy": "\ue14d",
    "inventory_2": "\ue1a1",
    "folder_zip": "\ueb2c",
    "fullscreen": "\ue5d0",
    "fullscreen_exit": "\ue5d1",
    # HOME studio tiles
    "view_in_ar": "\uef4f",
    "layers": "\ue53b",
    "graphic_eq": "\ue1b8",
    "tune": "\ue429",
    "upload_file": "\ue9fc",
}

_FAMILY = "Material Icons"
_FONT_ID = -1
_READY = False

_FONT_PATH = PKG_ROOT / "assets" / "fonts" / "MaterialIcons-Regular.ttf"


def ensure_material_icons() -> bool:
    """Load the bundled TTF once. Safe to call before any icon button is styled."""
    global _FONT_ID, _READY
    if _READY:
        return True
    if not _FONT_PATH.is_file():
        return False
    _FONT_ID = QFontDatabase.addApplicationFont(str(_FONT_PATH))
    if _FONT_ID < 0:
        return False
    families = QFontDatabase.applicationFontFamilies(_FONT_ID)
    _READY = bool(families) and _FAMILY in families
    return _READY


def glyph(name: str) -> str:
    return GLYPHS.get(name, "")


def icon_font(point_size: int = 20) -> QFont:
    ensure_material_icons()
    f = QFont(_FAMILY)
    f.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    f.setPixelSize(max(12, int(point_size)))
    return f


def apply_icon(
    btn: QAbstractButton,
    name: str,
    *,
    tip: str = "",
    kind: str = "icon",
    size: int = 20,
    square: int | None = None,
) -> None:
    """Turn a push button into a Material Icon control.

    kind:
      nav     → #navIconBtn (Home / Theme on bottom glass)
      icon    → #iconBtn (plain chrome action)
      accent  → #accentIconBtn (primary Save / Open)
    """
    g = glyph(name)
    if not g or not ensure_material_icons():
        # Fallback: keep / restore readable text from tip.
        if tip and not btn.text():
            btn.setText(tip.split("·")[0].strip() or name)
        if tip:
            from .motion import attach_glass_tip

            attach_glass_tip(btn, tip, highlight=True)
        return
    obj = {"nav": "navIconBtn", "accent": "accentIconBtn"}.get(kind, "iconBtn")
    btn.setObjectName(obj)
    btn.setFont(icon_font(size))
    btn.setText(g)
    btn.setProperty("mi_name", name)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    side = square if square is not None else (40 if kind == "nav" else 36)
    btn.setFixedSize(side, side)
    # Re-polish if already in a live tree (objectName / font changed).
    style = btn.style()
    if style is not None:
        style.unpolish(btn)
        style.polish(btn)
    if tip:
        from .motion import attach_glass_tip

        # nav bars already have HoverBubble — tip text only; chrome icons get both
        attach_glass_tip(btn, tip, highlight=(kind != "nav"))


def set_theme_toggle_icon(
    btn: QAbstractButton, mode: str, *, square: int = 36
) -> None:
    """Show the mode you switch *to* (sun when dark, moon when light)."""
    tip = "Light theme" if mode == "dark" else "Dark theme"
    name = "light_mode" if mode == "dark" else "dark_mode"
    apply_icon(btn, name, tip=tip, kind="nav", size=20, square=square)


def set_home_icon(
    btn: QAbstractButton, *, back: bool = False, square: int = 36
) -> None:
    if back:
        apply_icon(
            btn,
            "arrow_back",
            tip="Back",
            kind="nav",
            size=20,
            square=square,
        )
    else:
        apply_icon(
            btn,
            "home",
            tip="Home",
            kind="nav",
            size=20,
            square=square,
        )


def sync_theme_icons(root: QWidget, mode: str) -> None:
    """Retarget every #navIconBtn that holds a theme glyph after a mode flip."""
    mode = mode if mode in ("dark", "light") else "dark"
    for btn in root.findChildren(QPushButton):
        if btn.objectName() != "navIconBtn":
            continue
        name = btn.property("mi_name")
        if name in ("dark_mode", "light_mode"):
            set_theme_toggle_icon(btn, mode)


def font_path() -> Path:
    return _FONT_PATH
