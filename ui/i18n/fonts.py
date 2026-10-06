"""Bundle Noto UI fonts per language + rebase every widget on Lang change."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

from ... import PKG_ROOT
from .core import LANG_EN, LANG_ID, LANG_JA, LANG_TH

_FONT_DIR = PKG_ROOT / "assets" / "fonts"

# User: EN/TH → Noto Sans Thai Looped · JA → Noto Sans Japanese (CJK JP) · ID → Noto Sans
_LANG_FAMILY: dict[str, str] = {
    LANG_EN: "Noto Sans Thai Looped",
    LANG_TH: "Noto Sans Thai Looped",
    LANG_JA: "Noto Sans CJK JP",
    LANG_ID: "Noto Sans",
}

_FALLBACK = ("Segoe UI Variable", "Segoe UI", "Noto Sans")
_ICON_FAMILIES = frozenset({"Material Icons", "MaterialIcons-Regular", "Material Icons Outlined"})
_ICON_OBJECT_NAMES = frozenset({"navIconBtn", "iconBtn", "accentIconBtn", "homeCardIcon", "homeDropIcon"})

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


def ensure_ui_fonts() -> None:
    """Load bundled Noto TTFs once (safe before QWidget creation)."""
    global _LOADED
    if _LOADED:
        return
    for path in _font_files():
        fid = QFontDatabase.addApplicationFont(str(path))
        if fid < 0:
            continue
        for fam in QFontDatabase.applicationFontFamilies(fid):
            _FAMILY_READY[fam] = True
    _LOADED = True


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
    f = QFont(fam)
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


def rebase_widget_fonts(root: QWidget | None, family: str) -> None:
    """Swap font family on every widget under root; keep size/weight. Skip icon glyphs."""
    if root is None:
        return
    stack = [root]
    stack.extend(root.findChildren(QWidget))
    for w in stack:
        if _is_icon_font_widget(w):
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

    Material Icons buttons are left alone. Mono/code editors keep their own
    family when it is already a monospace stack (not rebased blindly onto Noto
    if the widget opted into Consolas/Menlo via QSS #codeEdit — those selectors
    still win after stylesheet rebuild).
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

    return font
