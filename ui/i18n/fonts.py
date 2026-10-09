"""Bundle Noto UI fonts per language + rebase every widget on Lang change."""
from __future__ import annotations

import math
import struct
from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QPlainTextEdit, QTextEdit, QWidget

from ... import PKG_ROOT
from .core import LANG_EN, LANG_ID, LANG_JA, LANG_TH

_FONT_DIR = PKG_ROOT / "assets" / "fonts"

# EN / ID → Noto Sans · TH → Noto Sans Thai Looped · JA → Noto Sans CJK JP
_LANG_FAMILY: dict[str, str] = {
    LANG_EN: "Noto Sans",
    LANG_TH: "Noto Sans Thai Looped",
    LANG_JA: "Noto Sans CJK JP",
    LANG_ID: "Noto Sans",
}

_FALLBACK = ("Segoe UI Variable", "Segoe UI", "Noto Sans")
_ICON_FAMILIES = frozenset({"Material Icons", "MaterialIcons-Regular", "Material Icons Outlined"})
_ICON_OBJECT_NAMES = frozenset({"navIconBtn", "iconBtn", "accentIconBtn", "homeCardIcon", "homeDropIcon"})
_MONO_FAMILIES = frozenset({
    "Consolas",
    "Cascadia Mono",
    "Cascadia Code",
    "JetBrains Mono",
    "Menlo",
    "Monaco",
    "Courier New",
    "Courier",
})

_LOADED = False
_FAMILY_READY: dict[str, bool] = {}


def _font_files() -> list[Path]:
    names = (
        "NotoSansThaiLooped.ttf",
        "NotoSansJP-Regular.ttf",
        "NotoSansJP-Bold.ttf",
        "NotoSans-Regular.ttf",
        "NotoSans-Medium.ttf",
        "NotoSans-SemiBold.ttf",
        "NotoSans-Bold.ttf",
    )
    return [p for n in names if (p := _FONT_DIR / n).is_file()]


def _drop_stat_table(data: bytes) -> bytes:
    """Drop the STAT table so Qt does not restyle static Noto Sans as Thin Condensed.

    ponytail: directory entry is removed and the table bytes are left in place.
    Upgrade path is a rebuilt static family without STAT, if Qt stops misreading it.
    """
    if len(data) < 28 or data[:4] not in (b"\x00\x01\x00\x00", b"OTTO"):
        return data
    num = struct.unpack_from(">H", data, 4)[0]
    kept: list[bytes] = []
    dropped = False
    for i in range(num):
        rec = data[12 + i * 16 : 28 + i * 16]
        if len(rec) < 16:
            return data
        if rec[:4] == b"STAT":
            dropped = True
            continue
        kept.append(rec)
    if not dropped:
        return data
    out = bytearray(data)
    count = len(kept)
    entry = int(math.log2(count)) if count else 0
    search = (1 << entry) * 16
    struct.pack_into(">HHHH", out, 4, count, search, entry, count * 16 - search)
    blob = b"".join(kept)
    out[12 : 12 + len(blob)] = blob
    old_end = 12 + num * 16
    out[12 + len(blob) : old_end] = b"\x00" * (old_end - 12 - len(blob))
    return bytes(out)


def ensure_ui_fonts() -> None:
    """Load bundled Noto TTFs once (safe before QWidget creation)."""
    global _LOADED
    if _LOADED:
        return
    for path in _font_files():
        # Static Noto Sans ships a STAT table. Qt 6 then matches the family as
        # "Thin Condensed" weight 100. Thai Looped and CJK JP do not.
        if path.name.startswith("NotoSans-"):
            fid = QFontDatabase.addApplicationFontFromData(_drop_stat_table(path.read_bytes()))
        else:
            fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            continue
        for fam in QFontDatabase.applicationFontFamilies(fid):
            _FAMILY_READY[fam] = True
    _LOADED = True


def script_families(primary: str) -> list[str]:
    """UI family first, then fonts that cover Japanese, Thai, and Latin.

    One family cannot draw every script. The list is the fallback order.
    """
    ordered = (
        primary,
        "Noto Sans CJK JP",
        "Noto Sans Thai Looped",
        "Noto Sans",
        "Segoe UI",
    )
    found: list[str] = []
    for name in ordered:
        if name and name not in found:
            found.append(name)
    return found


def family_for(lang: str) -> str:
    ensure_ui_fonts()
    preferred = _LANG_FAMILY.get(lang, _LANG_FAMILY[LANG_EN])
    if _FAMILY_READY.get(preferred):
        return preferred
    for fam in _FALLBACK:
        if _FAMILY_READY.get(fam) or QFont(fam).exactMatch():
            return fam
    return preferred


def ui_font(
    lang: str | None = None,
    point_size: int = 13,
    weight: QFont.Weight = QFont.Weight.Normal,
) -> QFont:
    from .core import current_language

    fam = family_for(lang or current_language())
    f = QFont()
    f.setFamilies(script_families(fam))
    f.setPointSize(point_size)
    f.setWeight(weight)
    f.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
    f.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return f


def _is_icon_font_widget(w: QWidget) -> bool:
    if w.property("mi_name"):
        return True
    if w.objectName() in _ICON_OBJECT_NAMES:
        return True
    fam = w.font().family()
    if fam in _ICON_FAMILIES or "Material Icon" in fam:
        return True
    return False


def _is_mono_widget(w: QWidget) -> bool:
    """Code / log editors stay Consolas (or the mono stack). Lang swap must not touch them."""
    if isinstance(w, (QPlainTextEdit, QTextEdit)):
        return True
    fam = w.font().family()
    return fam in _MONO_FAMILIES or "Cascadia" in fam


def _keep_text_family(family: str) -> bool:
    if family in _MONO_FAMILIES or "Cascadia" in family:
        return True
    if family in _ICON_FAMILIES or "Material Icon" in family:
        return True
    return False


def rebase_quick_fonts(family: str) -> None:
    """Point existing QML text at the language family. Editors and icon glyphs stay put.

    Item has no font property, and Text does not follow a later QApplication.setFont.
    """
    app = QApplication.instance()
    if app is None:
        return
    from PySide6.QtQuick import QQuickItem
    from PySide6.QtQuickWidgets import QQuickWidget

    for widget in app.allWidgets():
        if not isinstance(widget, QQuickWidget):
            continue
        root = widget.rootObject()
        if isinstance(root, QQuickItem):
            _rebase_quick_item(root, family)


def _rebase_quick_item(item, family: str) -> None:
    stack = [item]
    while stack:
        cur = stack.pop()
        stack.extend(cur.childItems())
        if cur.metaObject().className() not in ("QQuickText", "QQuickTextInput", "QQuickTextEdit"):
            continue
        font = cur.property("font")
        if not isinstance(font, QFont):
            continue
        if _keep_text_family(font.family()):
            continue
        want = script_families(family)
        if list(font.families()) == want:
            continue
        font.setFamilies(want)
        cur.setProperty("font", font)


def rebase_widget_fonts(root: QWidget | None, family: str) -> None:
    """Swap font family on every widget under root; keep size/weight. Skip icons and editors."""
    if root is None:
        return
    stack = [root]
    stack.extend(root.findChildren(QWidget))
    for w in stack:
        if _is_icon_font_widget(w) or _is_mono_widget(w):
            continue
        old = w.font()
        if old.family() == family:
            continue
        neo = QFont(old)
        neo.setFamily(family)
        # PreferQuality so CJK/Thai hinting stays clean after swap
        neo.setStyleStrategy(QFont.StyleStrategy.PreferQuality)
        w.setFont(neo)


def apply_language_font(lang: str | None = None, root: QWidget | None = None) -> QFont:
    """App font + QSS stack + every widget font → active language family.

    Material Icons buttons are left alone. Plain/text editors and any widget
    already on Consolas (or another mono family) are left alone.
    """
    from .core import current_language

    ensure_ui_fonts()
    code = lang or current_language()
    family = family_for(code)
    font = ui_font(code, 13)

    app = QApplication.instance()
    if app is not None:
        app.setFont(font)
        # Rebuild * { font-family } for this language (was frozen to Segoe).
        try:
            from ..theme import apply_theme, invalidate_stylesheet_cache, warm_theme_cache

            invalidate_stylesheet_cache()
            warm_theme_cache()  # dark+light sheets with this language's font stack
            mode = app.property("mstnTheme")
            if not isinstance(mode, str) or mode not in ("dark", "light"):
                mode = "dark"
            apply_theme(app, mode)
            # apply_theme sets app font again via app_font() — keep language family
            app.setFont(font)
        except Exception:
            pass

        targets: list[QWidget] = []
        if root is not None:
            targets.append(root)
        else:
            targets.extend(w for w in app.topLevelWidgets() if isinstance(w, QWidget))
        for w in targets:
            rebase_widget_fonts(w, family)
        rebase_quick_fonts(family)

    return font
