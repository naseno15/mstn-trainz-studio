"""Apple-HIG-ish light/dark theme for MSTN Mesh Studio (teal mint — no purple).

Depth layers (soft emboss / inset via QSS edge pairs — Qt has no real box-shadow):
  well   = recessed track / table / editor (nav & tab strips)
  raise  = protruding button / toggle
  pill   = accent selector sitting proud of its well
"""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QWidget

# Default before i18n fonts load — apply_language_font / stylesheet() replace per locale.
FONT_STACK = '"Noto Sans Thai Looped", "Noto Sans", "Segoe UI", system-ui, sans-serif'
MONO_STACK = "Menlo, Consolas, 'Courier New', monospace"


def font_stack(lang: str | None = None) -> str:
    """CSS font-family stack for the active (or given) UI language."""
    try:
        from .i18n.fonts import family_for
        from .i18n.core import current_language

        fam = family_for(lang or current_language())
    except Exception:
        fam = "Noto Sans Thai Looped"
    # Keep Noto Sans + Segoe as fallbacks for missing glyphs / dialogs.
    return f'"{fam}", "Noto Sans", "Segoe UI Variable", "Segoe UI", system-ui, sans-serif'


def invalidate_stylesheet_cache() -> None:
    """Drop cached QSS so the next stylesheet() rebuild picks up the Lang font stack."""
    _SHEET_CACHE.clear()


@dataclass(frozen=True)
class Palette:
    mode: str  # "light" | "dark"
    bg: str
    surface: str
    surface2: str
    ink: str
    muted: str
    accent: str
    accent_hover: str
    accent_soft: str
    line: str
    hairline: str
    glass: str
    glass_border: str
    danger: str
    selection: str
    gl_clear: tuple[float, float, float]
    # depth tokens — light edge / dark edge / fills
    raise_hi: str
    raise_lo: str
    well_lo: str
    well_hi: str
    well_fill: str
    raise_fill: str
    pill_deep: str  # accent pill bottom shade


# Soft gray stage — not paper-white, so well / raise / glass chips stay readable.
LIGHT = Palette(
    mode="light",
    bg="#d8dce3",
    surface="rgba(236, 239, 244, 0.78)",
    surface2="rgba(244, 246, 249, 0.88)",
    ink="#1d1d1f",
    muted="#5c5c63",
    accent="#ff5a1f",
    accent_hover="#e04a12",
    accent_soft="rgba(255, 90, 31, 0.16)",
    line="rgba(0, 0, 0, 0.14)",
    hairline="rgba(0, 0, 0, 0.09)",
    glass="rgba(236, 239, 244, 0.82)",
    glass_border="rgba(255, 255, 255, 0.42)",
    danger="#c41e3a",
    selection="rgba(255, 90, 31, 0.18)",
    gl_clear=(0.847, 0.863, 0.890),
    raise_hi="rgba(255, 255, 255, 0.85)",
    raise_lo="rgba(0, 0, 0, 0.22)",
    well_lo="rgba(0, 0, 0, 0.22)",
    well_hi="rgba(255, 255, 255, 0.70)",
    well_fill="rgba(0, 0, 0, 0.085)",
    raise_fill="rgba(232, 236, 242, 0.96)",
    pill_deep="#c43a10",
)

DARK = Palette(
    mode="dark",
    bg="#0b0d0f",
    surface="rgba(22, 26, 30, 0.52)",
    surface2="rgba(28, 33, 38, 0.68)",
    ink="#f5f5f7",
    muted="#98989d",
    accent="#ff5a1f",
    accent_hover="#ff7a45",
    accent_soft="rgba(255, 90, 31, 0.16)",
    line="rgba(255, 255, 255, 0.10)",
    hairline="rgba(255, 255, 255, 0.07)",
    glass="rgba(36, 42, 50, 0.92)",
    glass_border="rgba(255, 255, 255, 0.14)",
    danger="#ff6b6b",
    selection="rgba(255, 90, 31, 0.20)",
    gl_clear=(0.07, 0.08, 0.10),
    raise_hi="rgba(255, 255, 255, 0.16)",
    raise_lo="rgba(0, 0, 0, 0.62)",
    well_lo="rgba(0, 0, 0, 0.72)",
    well_hi="rgba(255, 255, 255, 0.09)",
    # Not pure black — lists/tab wells on #0b0d0f read as a void if too dark.
    well_fill="rgba(255, 255, 255, 0.07)",
    raise_fill="rgba(48, 54, 62, 0.96)",
    pill_deep="#c43a10",
)


def palette(mode: str) -> Palette:
    return DARK if mode == "dark" else LIGHT


def app_font(point_size: int = 13, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    try:
        from .i18n import ui_font

        return ui_font(point_size=point_size, weight=weight)
    except Exception:
        f = QFont("Noto Sans Thai Looped")
        if not f.exactMatch():
            f = QFont("Segoe UI")
        f.setPointSize(point_size)
        f.setWeight(weight)
        return f


# --- depth helpers (Qt QSS: paired edges fake emboss / inset) -----------------

def _css_raised(p: Palette, fill: str | None = None) -> str:
    bg = fill if fill is not None else p.raise_fill
    return (
        f"background: {bg};"
        f"border-top: 1px solid {p.raise_hi};"
        f"border-left: 1px solid {p.raise_hi};"
        f"border-bottom: 1px solid {p.raise_lo};"
        f"border-right: 1px solid {p.raise_lo};"
    )


def _css_well(p: Palette, fill: str | None = None) -> str:
    bg = fill if fill is not None else p.well_fill
    return (
        f"background: {bg};"
        f"border-top: 1px solid {p.well_lo};"
        f"border-left: 1px solid {p.well_lo};"
        f"border-bottom: 1px solid {p.well_hi};"
        f"border-right: 1px solid {p.well_hi};"
    )


def _css_raised_accent(p: Palette) -> str:
    # proud orange pill — specular top, deep bottom
    return (
        f"background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
        f" stop:0 {p.accent_hover}, stop:0.42 {p.accent}, stop:1 {p.pill_deep});"
        f"border-top: 1px solid rgba(255, 214, 180, 0.55);"
        f"border-left: 1px solid rgba(255, 180, 140, 0.32);"
        f"border-bottom: 1px solid rgba(60, 16, 0, 0.55);"
        f"border-right: 1px solid rgba(60, 16, 0, 0.40);"
    )


_SHEET_CACHE: dict[str, str] = {}
_QPAL_CACHE: dict[str, QPalette] = {}
_APP_FONT_SET = False


def warm_theme_cache() -> None:
    """Build dark+light sheets/palettes once — theme toggle only swaps cached blobs."""
    for mode in ("dark", "light"):
        stylesheet(palette(mode))
        qpalette_for(mode)


def theme_assets_ready() -> bool:
    """True when both mode sheets + palettes are cached (boot preload done)."""
    try:
        from .i18n.core import current_language

        lang = current_language()
    except Exception:
        lang = "en"
    return (
        f"dark:{lang}" in _SHEET_CACHE
        and f"light:{lang}" in _SHEET_CACHE
        and "dark" in _QPAL_CACHE
        and "light" in _QPAL_CACHE
    )


def stylesheet(p: Palette) -> str:
    # Cache per theme mode + language — font-family in * {} follows Lang.
    try:
        from .i18n.core import current_language

        lang = current_language()
    except Exception:
        lang = "en"
    key = f"{p.mode}:{lang}"
    hit = _SHEET_CACHE.get(key)
    if hit is not None:
        return hit
    css = _build_stylesheet(p, lang=lang)
    _SHEET_CACHE[key] = css
    return css


def _build_stylesheet(p: Palette, *, lang: str | None = None) -> str:
    stack = font_stack(lang)
    raised = _css_raised(p)
    raised_soft = _css_raised(p, p.surface2)
    well = _css_well(p)
    well_glass = _css_well(p, p.glass)
    # Opaque fills — rgba on QHeaderView / item views composites over Windows Base
    list_fill = "#1a1f26" if p.mode == "dark" else "#eceff3"
    list_alt = "#151a20" if p.mode == "dark" else "#e2e6ec"
    header_fill = "#252b33" if p.mode == "dark" else "#d5dae2"
    edit_fill = "#14181d" if p.mode == "dark" else "#e8ebf0"
    well_list = _css_well(p, edit_fill)
    # Recessed slot: dark lip on top, light catch on the bottom. Flat #14181d
    # sat on the glass and the narrow RGBA boxes disappeared.
    if p.mode == "dark":
        edit_well = (
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #07090c, stop:0.38 #1a212b, stop:1 #3e4a56);"
            "border-top: 1px solid rgba(0, 0, 0, 0.90);"
            "border-left: 1px solid rgba(0, 0, 0, 0.60);"
            "border-bottom: 1px solid rgba(255, 255, 255, 0.46);"
            "border-right: 1px solid rgba(255, 255, 255, 0.18);"
        )
    else:
        edit_well = (
            "background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 #c5ccd4, stop:0.4 #e6eaef, stop:1 #fbfcfd);"
            "border-top: 1px solid rgba(0, 0, 0, 0.28);"
            "border-left: 1px solid rgba(0, 0, 0, 0.14);"
            "border-bottom: 1px solid rgba(255, 255, 255, 0.95);"
            "border-right: 1px solid rgba(255, 255, 255, 0.75);"
        )
    list_chrome = _css_raised(p, list_fill)
    raised_accent = _css_raised_accent(p)
    pressed = _css_well(p, p.well_fill)

    return f"""
    * {{
        font-family: {stack};
        font-size: 13px;
    }}
    /* ponytail: never paint QWidget globally — QOpenGLWidget freezes on style polish */
    QMainWindow {{
        background: {p.bg};
        color: {p.ink};
    }}
    QDialog {{
        background: {p.bg};
        color: {p.ink};
    }}
    /* Solid shell plates — without these, light QSS ink sat on leftover black hosts */
    QWidget#appShell, QWidget#centerHost, QWidget#viewerPane,
    QWidget#glHost, QLabel#glPlaceholder {{
        background: {p.bg};
        color: {p.ink};
    }}
    QLabel#glPlaceholder {{
        color: {p.muted};
    }}
    QOpenGLWidget {{
        background: transparent;
        border: none;
    }}
    QLabel {{
        color: {p.ink};
        background: transparent;
    }}
    QMenuBar {{
        background: {p.glass};
        color: {p.ink};
        border-bottom: 1px solid {p.hairline};
        padding: 4px 8px;
    }}
    QMenuBar::item {{
        padding: 6px 10px;
        border-radius: 8px;
    }}
    QMenuBar::item:selected {{
        background: {p.accent_soft};
    }}
    QMenu {{
        background: {p.surface2};
        color: {p.ink};
        border: 1px solid {p.hairline};
        border-radius: 12px;
        padding: 8px;
    }}
    QMenu::item {{
        padding: 8px 14px;
        border-radius: 8px;
    }}
    QMenu::item:selected {{
        background: {p.accent};
        color: white;
    }}
    QMenu::separator {{
        height: 1px;
        background: {p.hairline};
        margin: 6px 10px;
    }}
    QStatusBar {{
        background: {p.glass};
        color: {p.muted};
        border-top: 1px solid {p.hairline};
        padding: 2px 8px;
        min-height: 28px;
    }}
    QLabel#statusLogMsg {{
        color: {p.muted};
        background: transparent;
        border: none;
        padding: 0 4px;
    }}
    QLabel#statusLogMsg:hover {{
        color: {p.ink};
    }}
    QLabel#shortcutBar {{
        color: {p.muted};
        background: transparent;
        border: none;
        font-size: 11px;
        letter-spacing: 0.2px;
        padding: 2px 8px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 6px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {p.line};
        border-radius: 5px;
        min-height: 28px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QLabel#brandTitle {{
        color: {p.ink};
        font-weight: 700;
        letter-spacing: -0.3px;
    }}
    QLabel#welcomeTitle {{
        color: {p.ink};
        font-weight: 700;
        font-size: 34px;
        letter-spacing: -0.8px;
    }}
    QLabel#mutedTip {{
        color: {p.muted};
        padding: 1px 0 2px 0; /* keep g/y descenders inside title bar */
    }}
    QLabel#overlayBrand {{
        color: {p.ink};
        font-weight: 700;
        font-size: 18px;
        letter-spacing: -0.4px;
    }}
    QLabel#overlayStage {{
        color: {p.muted};
        font-size: 13px;
    }}
    QLabel#overlayPct {{
        color: {p.accent};
        font-weight: 700;
        font-size: 12px;
        letter-spacing: 0.2px;
    }}
    /* frost painted in FrostGlassFrame / _paint_glass_chip — QSS must stay clear */
    QFrame#glassPanel, QFrame#editorDock, QFrame#sidePanel {{
        background: transparent;
        border: none;
        border-radius: 14px;
    }}
    QScrollArea#sideScroll,
    QScrollArea#editorScroll {{
        background: transparent;
        border: none;
    }}
    /* viewport paints QPalette.Base by default — that was the white/black slabs */
    QScrollArea#sideScroll > QWidget,
    QScrollArea#editorScroll > QWidget,
    QScrollArea#sideScroll QWidget#qt_scrollarea_viewport,
    QScrollArea#editorScroll QWidget#qt_scrollarea_viewport {{
        background: transparent;
    }}
    /* chrome pills: paintEvent draws glass — no QSS fill (looked like flat lines) */
    QFrame#bottomNav, QFrame#bakeNav, QFrame#pbrHud {{
        background: transparent;
        border: none;
        border-radius: 30px;
    }}
    QFrame#fpsHud {{
        background: transparent;
        border: none;
    }}
    QLabel#bakeStage {{
        font-weight: 600;
        min-width: 140px;
    }}
    QFrame#bakeNav QProgressBar {{
        {_css_well(p, p.well_fill)}
        border-radius: 5px;
    }}
    QFrame#bakeNav QProgressBar::chunk {{
        background: {p.accent};
        border-radius: 5px;
    }}
    QToolButton#panelEdgeBtn {{
        background: {"rgba(232, 236, 242, 0.90)" if p.mode == "light" else "rgba(28, 34, 42, 0.72)"};
        color: {p.ink};
        border: 1px solid {"rgba(0, 0, 0, 0.12)" if p.mode == "light" else "rgba(255, 255, 255, 0.14)"};
        border-radius: 11px;
        font-weight: 700;
        font-size: 14px;
        padding: 0;
    }}
    QToolButton#panelEdgeBtn:hover {{
        background: rgba(255, 90, 31, 0.85);
        color: white;
        border: 1px solid rgba(255, 255, 255, 0.28);
    }}
    QFrame#loadingCard {{
        {_css_raised(p, "rgba(255, 255, 255, 0.42)" if p.mode == "light" else "rgba(28, 34, 40, 0.52)")}
        border-radius: 26px;
    }}
    QFrame#separatorLine {{
        background: {p.hairline};
        max-height: 1px;
        min-height: 1px;
        border: none;
    }}
    QToolButton, QPushButton {{
        {raised}
        color: {p.ink};
        border-radius: 12px;
        padding: 8px 14px;
        font-weight: 500;
        outline: none;
    }}
    /* ponytail: lift = brighter/darker 1px edges only — NEVER change border width
       (2px bottom/right was growing the widget and shifting page layout on hover). */
    QToolButton:hover, QPushButton:hover {{
        {_css_raised(p, "rgba(72, 80, 92, 1.0)" if p.mode == "dark" else "rgba(255, 255, 255, 1.0)")}
        border-top: 1px solid {"rgba(255, 255, 255, 0.34)" if p.mode == "dark" else "rgba(255, 255, 255, 1.0)"};
        border-left: 1px solid {"rgba(255, 255, 255, 0.26)" if p.mode == "dark" else "rgba(255, 255, 255, 0.98)"};
        border-bottom: 1px solid {"rgba(0, 0, 0, 0.50)" if p.mode == "dark" else "rgba(0, 0, 0, 0.20)"};
        border-right: 1px solid {"rgba(0, 0, 0, 0.40)" if p.mode == "dark" else "rgba(0, 0, 0, 0.16)"};
        color: {p.ink};
    }}
    /* chromeLift — same 1px box, stronger contrast (ButtonHoverChrome) */
    QToolButton[chromeLift="true"], QPushButton[chromeLift="true"] {{
        border-top: 1px solid {"rgba(255, 255, 255, 0.42)" if p.mode == "dark" else "rgba(255, 255, 255, 1.0)"};
        border-left: 1px solid {"rgba(255, 255, 255, 0.34)" if p.mode == "dark" else "rgba(255, 255, 255, 1.0)"};
        border-bottom: 1px solid {"rgba(0, 0, 0, 0.58)" if p.mode == "dark" else "rgba(0, 0, 0, 0.24)"};
        border-right: 1px solid {"rgba(0, 0, 0, 0.48)" if p.mode == "dark" else "rgba(0, 0, 0, 0.18)"};
    }}
    QPushButton#accentBtn[chromeLift="true"], QPushButton#accentIconBtn[chromeLift="true"] {{
        border-top: 1px solid rgba(255, 220, 190, 0.70);
        border-left: 1px solid rgba(255, 190, 150, 0.45);
        border-bottom: 1px solid rgba(40, 10, 0, 0.65);
        border-right: 1px solid rgba(40, 10, 0, 0.50);
    }}
    QToolButton:pressed, QPushButton:pressed {{
        {pressed}
        color: {p.ink};
    }}
    QToolButton:focus, QPushButton:focus {{
        outline: none;
    }}
    QPushButton#accentBtn {{
        {raised_accent}
        color: white;
        font-weight: 600;
        border-radius: 14px;
        /* Pad only — never pair with setFixedHeight(36); Qt pads inside the
           fixed box and clips descenders (Denoise / Save). */
        padding: 10px 18px;
        min-height: 20px;
    }}
    QPushButton#accentBtn:hover {{
        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
            stop:0 #ff9a6a, stop:0.4 {p.accent_hover}, stop:1 {p.accent});
        color: white;
    }}
    QPushButton#accentBtn:pressed {{
        background: {p.pill_deep};
        border-top: 1px solid rgba(0, 0, 0, 0.35);
        border-left: 1px solid rgba(0, 0, 0, 0.28);
        border-bottom: 1px solid rgba(255, 200, 160, 0.25);
        border-right: 1px solid rgba(255, 200, 160, 0.18);
        color: white;
    }}
    QPushButton#accentBtn:disabled {{
        background: {p.muted};
        color: {p.surface};
        border: 1px solid {p.line};
    }}
    QPushButton#navBtn {{
        background: transparent;
        border: none;
        border-radius: 14px;
        /* Tight pad — two-line labels (Texture\\nParams) need room inside FLOAT_NAV. */
        padding: 4px 10px;
        font-weight: 600;
        min-width: 72px;
        color: {p.muted};
    }}
    QPushButton#navBtn:checked {{
        background: transparent;
        color: white;
    }}
    QPushButton#navBtn:hover:!checked {{
        background: transparent;
        color: {p.ink};
    }}
    QPushButton#navBtn:pressed {{
        background: transparent;
        border: none;
    }}
    /* FloatTitleBar File/Edit/… — must fit MENU_BTN_H with descenders. */
    QPushButton#titleNavBtn {{
        background: transparent;
        border: none;
        border-radius: 12px;
        padding: 4px 14px;
        font-weight: 600;
        min-width: 52px;
        color: {p.muted};
    }}
    QPushButton#titleNavBtn:checked {{
        background: transparent;
        color: white;
    }}
    QPushButton#titleNavBtn:hover:!checked {{
        background: transparent;
        color: {p.ink};
    }}
    QPushButton#titleNavBtn:pressed {{
        background: transparent;
        border: none;
    }}
    /* Material Icons — center Home / Theme. Opaque fill required: translucent
       float parents click-through low-alpha children on Windows (theme looked dead). */
    QPushButton#navIconBtn {{
        background: {"#cfd5de" if p.mode == "light" else "#323842"};
        border: none;
        border-radius: 18px;
        padding: 0;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        max-height: 36px;
        font-family: "Material Icons";
        font-size: 20px;
        font-weight: 400;
        color: {p.ink};
    }}
    QPushButton#navIconBtn:hover {{
        color: white;
        background: {p.accent};
    }}
    QPushButton#navIconBtn:pressed {{
        color: white;
        background: {p.pill_deep};
    }}
    QPushButton#iconBtn {{
        {raised};
        border-radius: 10px;
        padding: 0;
        min-width: 36px;
        max-width: 36px;
        min-height: 36px;
        font-family: "Material Icons";
        font-size: 20px;
        font-weight: 400;
        color: {p.ink};
    }}
    QPushButton#iconBtn:hover {{
        {raised_soft};
        color: {p.ink};
    }}
    QPushButton#iconBtn:pressed {{
        {pressed};
    }}
    QPushButton#iconBtn:disabled {{
        color: {p.muted};
        background: {p.surface};
        border: 1px solid {p.line};
    }}
    QPushButton#accentIconBtn {{
        {raised_accent};
        border-radius: 10px;
        padding: 0;
        min-width: 40px;
        max-width: 40px;
        min-height: 40px;
        font-family: "Material Icons";
        font-size: 22px;
        font-weight: 400;
        color: white;
    }}
    QPushButton#accentIconBtn:hover {{
        background: {p.accent_hover};
        color: white;
    }}
    QPushButton#accentIconBtn:pressed {{
        background: {p.pill_deep};
        color: white;
    }}
    QPushButton#accentIconBtn:disabled {{
        background: {p.muted};
        color: {p.surface};
        border: 1px solid {p.line};
    }}
    QPushButton#segBtn {{
        background: transparent;
        border: none;
        border-radius: 10px;
        /* Compact HUD uses fixedHeight 28 — 7px pad left only ~14px for glyphs. */
        padding: 4px 12px;
        font-weight: 600;
        font-size: 12px;
        color: {p.muted};
        min-width: 52px;
    }}
    QPushButton#segBtn:checked {{
        background: transparent;
        color: white;
    }}
    QPushButton#segBtn:hover:!checked {{
        background: transparent;
        color: {p.ink};
    }}
    QPushButton#segBtn:pressed {{
        background: transparent;
        border: none;
    }}
    QPushButton#segBtn:disabled,
    QPushButton#segBtn:disabled:checked {{
        color: {"rgba(110, 110, 115, 0.45)" if p.mode == "light" else "rgba(235, 235, 245, 0.28)"};
    }}
    QPushButton#sideTab {{
        background: transparent;
        border: none;
        border-radius: 11px;
        text-align: center;
        padding: 5px 8px;
        font-weight: 650;
        font-size: 12px;
        color: {p.muted};
        min-height: 22px;
    }}
    QPushButton#sideTab:checked {{
        background: transparent;
        color: white;
    }}
    QPushButton#sideTab:hover:!checked {{
        background: transparent;
        color: {p.ink};
    }}
    QPushButton#sideTab:pressed {{
        background: transparent;
        border: none;
    }}
    QPushButton#sideTab:disabled {{
        background: transparent;
        color: {"rgba(255, 255, 255, 0.22)" if p.mode == "dark" else "rgba(0, 0, 0, 0.22)"};
    }}
    QFrame#sideTabStrip {{
        {well}
        border-radius: 14px;
    }}
    QFrame#sideTabPill {{
        {raised_accent}
        border-radius: 11px;
    }}
    QFrame#meshInfoSection {{
        background: transparent;
        border: none;
    }}
    QPushButton#meshInfoToggle {{
        {raised}
        text-align: left;
        padding: 8px 12px;
        font-weight: 650;
        color: {p.ink};
        border-radius: 12px;
        outline: none;
    }}
    QPushButton#meshInfoToggle:hover {{
        {_css_raised(p, "rgba(62, 70, 80, 0.98)" if p.mode == "dark" else "rgba(255, 255, 255, 1.0)")}
        color: {p.ink};
    }}
    QPushButton#meshInfoToggle:pressed {{
        {pressed}
        color: {p.ink};
    }}
    QFrame#meshInfoBody {{
        background: transparent;
        border: none;
    }}
    QFrame#statsCard {{
        {_css_well(p, p.well_fill)}
        border-radius: 12px;
    }}
    QFrame#logoPlate {{
        background: transparent;
        border: none;
    }}
    QLabel#sideLogo {{
        background: transparent;
    }}
    /* HOME — paintEvent draws frost; QSS stays clear */
    QFrame#homePage {{
        background: transparent;
        border: none;
    }}
    QFrame#homeStudioCard, QFrame#homeDropZone {{
        background: transparent;
        border: none;
    }}
    QLabel#homeBrand {{
        color: {p.ink};
        font-weight: 750;
        letter-spacing: -1.0px;
    }}
    QLabel#homeSub {{
        color: {p.muted};
        letter-spacing: 0.6px;
    }}
    QLabel#homeCopy {{
        color: {p.muted};
    }}
    QLabel#homeCardTitle {{
        color: {p.ink};
        font-weight: 700;
        letter-spacing: -0.35px;
    }}
    QLabel#homeCardBlurb {{
        color: {p.muted};
        font-size: 11px;
    }}
    QLabel#homeCardCta {{
        color: {p.accent};
        letter-spacing: 0.3px;
    }}
    QWidget#homeCardHost {{
        background: transparent;
        border: none;
    }}
    QLabel#homeDropIcon {{
        color: {p.accent};
        background: {"rgba(255, 90, 31, 0.12)" if p.mode == "light" else "rgba(255, 90, 31, 0.18)"};
        border-radius: 10px;
    }}
    QLabel#homeDropTitle {{
        color: {p.ink};
        font-weight: 650;
    }}
    QLabel#homeDropTypes {{
        color: {p.muted};
        font-size: 11px;
        font-weight: 500;
    }}
    QLabel#statsValue {{
        color: {p.ink};
        font-weight: 600;
        font-size: 13px;
    }}
    QLabel#statsKey {{
        color: {p.muted};
        font-size: 12px;
    }}
    QFrame#navPill, QFrame#segPill {{
        {raised_accent}
        border-radius: 12px;
    }}
    QFrame#lampControls {{
        background: transparent;
        border-top: 1px solid {p.hairline};
        padding-top: 2px;
    }}
    /* Studio-wide lists/tables — opaque fill (rgba headers were white slabs on Win) */
    QListWidget, QTreeWidget, QTableWidget,
    QTreeWidget#matTable, QTreeWidget#lampTable, QTreeWidget#engineTable,
    QTableWidget#studioTable {{
        {list_chrome}
        border-radius: 12px;
        padding: 0;
        outline: none;
        show-decoration-selected: 1;
        alternate-background-color: {list_alt};
        color: {p.ink};
    }}
    QListWidget::item, QTreeWidget::item, QTableWidget::item,
    QTreeWidget#matTable::item, QTreeWidget#lampTable::item,
    QTreeWidget#engineTable::item {{
        /* radii painted by table_chrome.RoundedRowDelegate — keep QSS fill clear */
        border-radius: 10px;
        margin: 1px 3px;
        padding: 4px 8px;
        min-height: 24px;
        color: {p.ink};
        border-bottom: 1px solid {"rgba(255, 255, 255, 0.055)" if p.mode == "dark" else "rgba(0, 0, 0, 0.055)"};
        border-right: 1px solid {"rgba(255, 255, 255, 0.04)" if p.mode == "dark" else "rgba(0, 0, 0, 0.04)"};
    }}
    QFrame#pkgFinderShell {{
        {_css_raised(p, "rgba(255, 255, 255, 0.05)" if p.mode == "dark" else "rgba(236, 239, 244, 0.92)")}
        border-radius: 16px;
    }}
    QLabel#pkgFinderHeading {{
        color: {p.ink};
    }}
    QLabel#pkgFinderMeta {{
        color: {p.muted};
        font-size: 11px;
    }}
    QFrame#pkgFinderCrumbs {{
        background: {"rgba(255, 255, 255, 0.04)" if p.mode == "dark" else "rgba(0, 0, 0, 0.035)"};
        border: 1px solid {"rgba(255, 255, 255, 0.08)" if p.mode == "dark" else "rgba(0, 0, 0, 0.06)"};
        border-radius: 10px;
    }}
    QPushButton#pkgCrumbBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        color: {p.accent};
        font-weight: 600;
        font-size: 12px;
        padding: 3px 8px;
        min-height: 22px;
    }}
    QPushButton#pkgCrumbBtn:hover {{
        background: {p.accent_soft};
    }}
    QLabel#pkgCrumbCurrent {{
        background: {p.accent_soft};
        border-radius: 6px;
        color: {p.ink};
        font-weight: 700;
        font-size: 12px;
        padding: 3px 8px;
    }}
    QLabel#pkgCrumbSep {{
        color: {p.muted};
        font-size: 12px;
        padding: 0 2px;
    }}
    QPushButton#pkgFinderBack {{
        {_css_raised(p, "rgba(255, 255, 255, 0.08)" if p.mode == "dark" else "rgba(228, 232, 238, 0.96)")}
        border-radius: 9px;
        font-weight: 700;
        font-size: 14px;
        padding: 0;
    }}
    QPushButton#pkgFinderBack:disabled {{
        color: {p.muted};
        background: transparent;
        border: 1px solid {"rgba(255, 255, 255, 0.06)" if p.mode == "dark" else "rgba(0, 0, 0, 0.06)"};
    }}
    QLineEdit#pkgFinderSearch {{
        {_css_raised(p, "rgba(255, 255, 255, 0.06)" if p.mode == "dark" else "rgba(232, 236, 242, 0.96)")}
        border-radius: 9px;
        padding: 4px 10px;
        font-size: 12px;
    }}
    QPushButton#pkgFinderScan {{
        {_css_raised(p, "rgba(255, 255, 255, 0.08)" if p.mode == "dark" else "rgba(228, 232, 238, 0.96)")}
        border-radius: 9px;
        font-weight: 700;
        font-size: 12px;
        padding: 4px 10px;
        min-width: 48px;
    }}
    QPushButton#pkgFinderScan:checked {{
        background: {p.accent_soft};
        color: {p.accent};
        border: 1px solid {p.accent};
    }}
    QLabel#pkgFinderTitle, QLabel#pkgFinderSub {{
        /* Beat global * {{ font-size: 13px }}; no pad (pad shrinks paint box under fixed height). */
        background: transparent;
        padding: 0;
        margin: 0;
    }}
    QLabel#pkgFinderTitle {{
        color: {p.ink};
        font-size: 12px;
        font-weight: 600;
    }}
    QLabel#pkgFinderSub {{
        color: {p.muted};
        font-size: 11px;
        font-weight: 400;
    }}
    QHeaderView#pkgFinderHeader {{
        background: transparent;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
    }}
    QHeaderView#pkgFinderHeader::section {{
        background: {"#2a313a" if p.mode == "dark" else "#d5dae2"};
        color: {p.muted};
        border: none;
        border-bottom: 1px solid {"rgba(255, 255, 255, 0.08)" if p.mode == "dark" else "rgba(0, 0, 0, 0.08)"};
        padding: 6px 12px;
        font-size: 11px;
        font-weight: 600;
    }}
    QTableWidget#pkgFinder {{
        background: transparent;
        border: none;
        border-radius: 12px;
        outline: none;
        padding: 0;
        alternate-background-color: transparent;
    }}
    QTableWidget#pkgFinder::item {{
        /* No vertical pad/margin — stole height from cell widgets → clipped descenders.
           Horizontal inset only; _FinderNameCell owns vertical spacing. */
        padding: 0 4px;
        min-height: 0;
        color: {p.ink};
        border: none;
        border-bottom: 1px solid {"rgba(255, 255, 255, 0.045)" if p.mode == "dark" else "rgba(0, 0, 0, 0.045)"};
        border-radius: 12px;
        margin: 0 4px;
    }}
    QTableWidget#pkgFinder::item:selected,
    QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected,
    QTreeWidget#matTable::item:selected, QTreeWidget#lampTable::item:selected,
    QTreeWidget#engineTable::item:selected {{
        /* delegate paints AccentPill bubble — never solid Highlight slab */
        background: transparent;
        color: #ffffff;
        border-radius: 12px;
    }}
    QTableWidget#pkgFinder::item:hover:!selected,
    QListWidget::item:hover:!selected, QTreeWidget::item:hover:!selected,
    QTableWidget::item:hover:!selected,
    QTreeWidget#matTable::item:hover:!selected, QTreeWidget#lampTable::item:hover:!selected,
    QTreeWidget#engineTable::item:hover:!selected {{
        background: transparent;
        border-radius: 10px;
    }}
    QHeaderView {{
        background: {header_fill};
        color: {p.muted};
        border: none;
        border-top-left-radius: 12px;
        border-top-right-radius: 12px;
    }}
    QHeaderView::section,
    QHeaderView#studioTableHeader::section,
    QHeaderView#engineTableHeader::section,
    QHeaderView#pkgFinderHeader::section {{
        background: {header_fill};
        color: {p.muted};
        border: none;
        border-bottom: 1px solid {"rgba(255, 255, 255, 0.10)" if p.mode == "dark" else "rgba(0, 0, 0, 0.10)"};
        border-right: 1px solid {"rgba(255, 255, 255, 0.06)" if p.mode == "dark" else "rgba(0, 0, 0, 0.06)"};
        padding: 4px 8px;
        font-size: 11px;
        font-weight: 600;
    }}
    QHeaderView::section:first,
    QHeaderView#studioTableHeader::section:first,
    QHeaderView#engineTableHeader::section:first,
    QHeaderView#pkgFinderHeader::section:first {{
        border-top-left-radius: 12px;
    }}
    QHeaderView::section:last,
    QHeaderView#studioTableHeader::section:last,
    QHeaderView#engineTableHeader::section:last,
    QHeaderView#pkgFinderHeader::section:last {{
        border-top-right-radius: 12px;
        border-right: none;
    }}
    QTableCornerButton::section {{
        background: {header_fill};
        border: none;
        border-top-left-radius: 12px;
    }}
    QTreeWidget::branch {{
        background: transparent;
        border: none;
        width: 14px;
    }}
    QTreeWidget::branch:has-children:!has-siblings:closed,
    QTreeWidget::branch:closed:has-children:has-siblings {{
        image: none;
        {_css_raised(p, p.surface)}
        border-radius: 3px;
        margin: 2px 1px;
    }}
    QTreeWidget::branch:open:has-children:!has-siblings,
    QTreeWidget::branch:open:has-children:has-siblings {{
        image: none;
        {_css_raised(p, p.surface2)}
        border-radius: 3px;
        margin: 2px 1px;
    }}
    QTreeWidget::indicator {{
        width: 0px;
        height: 0px;
        border: none;
        background: transparent;
        margin: 0;
        padding: 0;
    }}
    QComboBox {{
        {raised}
        border-radius: 12px;
        padding: 8px 12px;
        min-height: 22px;
    }}
    QComboBox:pressed {{
        {pressed}
    }}
    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}
    QComboBox QAbstractItemView {{
        background: {p.surface2};
        border: 1px solid {p.hairline};
        border-radius: 10px;
        selection-background-color: {p.selection};
        selection-color: {p.ink};
        padding: 4px;
    }}
    QPlainTextEdit, QTextEdit, QTextEdit#codeView, QPlainTextEdit#codeView {{
        {well_list}
        color: {p.ink};
        border-radius: 14px;
        padding: 10px;
        font-family: {MONO_STACK};
        font-size: 12px;
        selection-background-color: {p.selection};
    }}
    QFrame#codeFindBar {{
        background: {"rgba(30, 30, 30, 0.96)" if p.mode == "dark" else "rgba(245, 245, 245, 0.96)"};
        border: 1px solid {p.hairline};
        border-radius: 0px;
        border-bottom: 1px solid {p.line};
    }}
    QFrame#codeFindBar QLineEdit {{
        border-radius: 6px;
        padding: 4px 8px;
        min-height: 22px;
    }}
    QFrame#codeFindBar QToolButton {{
        min-width: 28px;
        min-height: 26px;
        border-radius: 6px;
        padding: 2px 6px;
    }}
    QFrame#codeFindBar QPushButton {{
        min-height: 26px;
        padding: 4px 10px;
        border-radius: 6px;
    }}
    QLineEdit {{
        {well_list}
        color: {p.ink};
        border-radius: 10px;
        padding: 6px 10px;
        selection-background-color: {p.selection};
    }}
    QLineEdit:disabled {{
        color: {"rgba(110, 110, 115, 0.50)" if p.mode == "light" else "rgba(235, 235, 245, 0.32)"};
        background: {"rgba(0, 0, 0, 0.04)" if p.mode == "light" else "rgba(255, 255, 255, 0.04)"};
    }}
    QDoubleSpinBox, QSpinBox {{
        {well_list}
        color: {p.ink};
        border-radius: 10px;
        padding: 8px 12px;
        min-height: 28px;
        selection-background-color: {p.selection};
    }}
    QDoubleSpinBox:disabled, QSpinBox:disabled {{
        color: {"rgba(110, 110, 115, 0.50)" if p.mode == "light" else "rgba(235, 235, 245, 0.32)"};
        background: {"rgba(0, 0, 0, 0.04)" if p.mode == "light" else "rgba(255, 255, 255, 0.04)"};
    }}
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 20px;
        border: none;
        background: transparent;
    }}
    /* Editor dock — one control height. Vertical padding is 0: Qt adds
       padding on top of min-height, which made rows 42px and clipped setFixedHeight(36).
       Inset edge is 1px inside that 36 (setFixedHeight), not extra layout. */
    QFrame#editorDock QLineEdit,
    QFrame#editorDock QComboBox,
    QFrame#editorDock QDoubleSpinBox,
    QFrame#editorDock QSpinBox {{
        padding: 0 10px;
        /* 34 + 1px inset edge = the 36px setFixedHeight. 36 here made spins 46. */
        min-height: 34px;
        max-height: 34px;
        border-radius: 8px;
        {edit_well}
    }}
    QFrame#editorDock QLineEdit:focus,
    QFrame#editorDock QComboBox:focus,
    QFrame#editorDock QDoubleSpinBox:focus,
    QFrame#editorDock QSpinBox:focus {{
        border-bottom: 1px solid {p.accent};
    }}
    /* Spin/combo paint the well. Their inner editor must not cover it with a flat fill. */
    QFrame#editorDock QSpinBox QLineEdit,
    QFrame#editorDock QDoubleSpinBox QLineEdit,
    QFrame#editorDock QComboBox QLineEdit {{
        background: transparent;
        border: none;
        padding: 0;
        min-height: 0px;
        max-height: 36px;
    }}
    /* RGBA number only — the letter is a label beside the box, so the well stays narrow. */
    QFrame#editorDock QSpinBox#rgbaChannel {{
        padding: 0 2px;
    }}
    QFrame#editorDock QDoubleSpinBox::up-button, QFrame#editorDock QDoubleSpinBox::down-button,
    QFrame#editorDock QSpinBox::up-button, QFrame#editorDock QSpinBox::down-button {{
        width: 14px;
    }}
    /* Texture Maps viewer — role / channel chrome */
    QFrame#mapRoleWell {{
        {well_list}
        border-radius: 14px;
    }}
    QLabel#mapSectionLabel {{
        color: {p.muted};
        font-size: 10px;
        font-weight: 700;
        letter-spacing: 0.08em;
    }}
    QPushButton#mapRoleAlbedo, QPushButton#mapRoleNormal, QPushButton#mapRoleParam {{
        background: {"rgba(0,0,0,0.04)" if p.mode == "light" else "rgba(255,255,255,0.04)"};
        border: 1px solid {p.line};
        border-radius: 10px;
        padding: 4px 8px;
        font-weight: 650;
        font-size: 12px;
        color: {p.muted};
    }}
    QPushButton#mapRoleAlbedo:checked {{
        background: rgba(48, 209, 88, 0.22);
        border: 1px solid rgba(48, 209, 88, 0.55);
        color: {"#1a7a38" if p.mode == "light" else "#6dff9a"};
    }}
    QPushButton#mapRoleNormal:checked {{
        background: rgba(100, 210, 255, 0.20);
        border: 1px solid rgba(100, 210, 255, 0.55);
        color: {"#0a6a9a" if p.mode == "light" else "#9ae4ff"};
    }}
    QPushButton#mapRoleParam:checked {{
        background: rgba(255, 159, 10, 0.20);
        border: 1px solid rgba(255, 159, 10, 0.55);
        color: {"#9a5a00" if p.mode == "light" else "#ffc46a"};
    }}
    QPushButton#mapRoleAlbedo:disabled, QPushButton#mapRoleNormal:disabled,
    QPushButton#mapRoleParam:disabled {{
        color: {"rgba(110,110,115,0.35)" if p.mode == "light" else "rgba(235,235,245,0.22)"};
        border-color: {"rgba(0,0,0,0.06)" if p.mode == "light" else "rgba(255,255,255,0.06)"};
        background: transparent;
    }}
    QPushButton#mapChR, QPushButton#mapChG, QPushButton#mapChB, QPushButton#mapChA {{
        background: {"rgba(0,0,0,0.03)" if p.mode == "light" else "rgba(255,255,255,0.04)"};
        border: 1px solid {p.line};
        border-radius: 10px;
        font-weight: 750;
        font-size: 13px;
        letter-spacing: 0.04em;
    }}
    QPushButton#mapChR {{ color: #ff6b63; }}
    QPushButton#mapChG {{ color: #3dd068; }}
    QPushButton#mapChB {{ color: #6ad4ff; }}
    QPushButton#mapChA {{ color: {p.muted}; }}
    QPushButton#mapChR:checked {{
        background: rgba(255, 69, 58, 0.28);
        border: 1px solid rgba(255, 69, 58, 0.65);
        color: #ff8f88;
    }}
    QPushButton#mapChG:checked {{
        background: rgba(48, 209, 88, 0.26);
        border: 1px solid rgba(48, 209, 88, 0.65);
        color: #6dff9a;
    }}
    QPushButton#mapChB:checked {{
        background: rgba(100, 210, 255, 0.26);
        border: 1px solid rgba(100, 210, 255, 0.65);
        color: #9ae4ff;
    }}
    QPushButton#mapChA:checked {{
        background: {"rgba(0,0,0,0.08)" if p.mode == "light" else "rgba(255,255,255,0.12)"};
        border: 1px solid {p.line};
        color: {p.ink};
    }}
    QPushButton#mapToolBtn {{
        {raised}
        border-radius: 10px;
        padding: 4px 8px;
        font-weight: 600;
        font-size: 11px;
        color: {p.ink};
    }}
    QPushButton#mapToolBtn:hover {{
        color: {p.ink};
    }}
    QPushButton#mapGhostBtn {{
        background: transparent;
        border: 1px solid {p.line};
        border-radius: 10px;
        padding: 4px 10px;
        font-weight: 600;
        font-size: 11px;
        color: {p.muted};
    }}
    QPushButton#mapGhostBtn:hover {{
        color: {p.ink};
        border-color: {p.muted};
    }}
    QWidget#mapPreviewStage {{
        background: transparent;
        border: none;
    }}
    QFrame#lmField {{
        {well_list}
        border-radius: 12px;
    }}
    QFrame#lmField:disabled {{
        background: {"rgba(0, 0, 0, 0.03)" if p.mode == "light" else "rgba(255, 255, 255, 0.03)"};
    }}
    QLabel#lmFieldLabel {{
        color: {p.muted};
        font-size: 11px;
        font-weight: 650;
        letter-spacing: 0.02em;
    }}
    QLabel#lmFieldLabel:disabled {{
        color: {"rgba(110, 110, 115, 0.40)" if p.mode == "light" else "rgba(235, 235, 245, 0.26)"};
    }}
    /* Track painted in _SegPills — keep QSS clear so chip isn't double-black. */
    QFrame#lmCalcSeg {{
        background: transparent;
        border: none;
        border-radius: 12px;
    }}
    QFrame#lmCalcSeg:disabled {{
        background: transparent;
    }}
    QSlider::groove:horizontal {{
        height: 4px;
        {_css_well(p, p.line)}
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        width: 16px;
        height: 16px;
        margin: -6px 0;
        {raised_accent}
        border-radius: 8px;
    }}
    QGroupBox {{
        font-weight: 600;
        {_css_well(p, "transparent")}
        border-radius: 14px;
        margin-top: 14px;
        padding-top: 16px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 14px;
        padding: 0 6px;
        color: {p.ink};
    }}
    QCheckBox {{
        spacing: 10px;
        color: {p.ink};
        min-height: 28px;
    }}
    QCheckBox:disabled {{
        color: {"rgba(110, 110, 115, 0.45)" if p.mode == "light" else "rgba(235, 235, 245, 0.30)"};
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 6px;
        {raised}
    }}
    QCheckBox::indicator:checked {{
        {raised_accent}
    }}
    QCheckBox::indicator:pressed {{
        {pressed}
    }}
    QCheckBox::indicator:disabled {{
        background: {"rgba(0, 0, 0, 0.06)" if p.mode == "light" else "rgba(255, 255, 255, 0.06)"};
        border: 1px solid {"rgba(0, 0, 0, 0.08)" if p.mode == "light" else "rgba(255, 255, 255, 0.08)"};
    }}
    QProgressBar {{
        {_css_well(p, p.line)}
        border-radius: 4px;
        height: 6px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {p.accent};
        border-radius: 4px;
    }}
    QTabWidget::pane {{
        border: none;
        background: transparent;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {p.muted};
        padding: 10px 14px;
        margin-right: 2px;
        border-radius: 10px;
        font-weight: 600;
    }}
    QTabBar::tab:selected {{
        {raised}
        color: {p.ink};
    }}
    QTabBar::tab:hover:!selected {{
        background: {"rgba(255, 255, 255, 0.06)" if p.mode == "dark" else "rgba(0, 0, 0, 0.04)"};
        color: {p.ink};
    }}
    /* Opaque — transparent stamped black WA_SetPalette on Win stacks, so
       Assets/Sounds/Engine hub pages stayed void under light Theme. */
    QStackedWidget {{
        background: {p.bg};
        color: {p.ink};
    }}
    /* Editor dock stack must not paint a square black slab over the frost. */
    QStackedWidget#editorTabStack {{
        background: transparent;
    }}
    QWidget#loadingOverlay {{
        background: transparent;
    }}
    """


def _theme_qpalette(p: Palette) -> QPalette:
    """Full palette — empty QPalette() leaves Light/Base roles on Windows defaults (white slabs)."""
    if p.mode == "dark":
        window = QColor("#0b0d0f")
        base = QColor("#161a1e")
        alt = QColor("#1c2126")
        button = QColor("#2a3038")
        text = QColor("#f5f5f7")
        muted = QColor("#98989d")
        light = QColor("#3a424c")
        mid = QColor("#1c2126")
        dark = QColor("#050607")
    else:
        window = QColor("#d8dce3")
        base = QColor("#e8ebf0")
        alt = QColor("#dde2e9")
        button = QColor("#e4e8ee")
        text = QColor("#1d1d1f")
        muted = QColor("#5c5c63")
        light = QColor("#f2f4f7")
        mid = QColor("#c4cad3")
        dark = QColor("#7a7a82")
    qp = QPalette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        qp.setColor(group, QPalette.ColorRole.Window, window)
        qp.setColor(group, QPalette.ColorRole.WindowText, text if group != QPalette.ColorGroup.Disabled else muted)
        qp.setColor(group, QPalette.ColorRole.Base, base)
        qp.setColor(group, QPalette.ColorRole.AlternateBase, alt)
        qp.setColor(group, QPalette.ColorRole.Text, text if group != QPalette.ColorGroup.Disabled else muted)
        qp.setColor(group, QPalette.ColorRole.Button, button)
        qp.setColor(group, QPalette.ColorRole.ButtonText, text if group != QPalette.ColorGroup.Disabled else muted)
        qp.setColor(group, QPalette.ColorRole.ToolTipBase, base)
        qp.setColor(group, QPalette.ColorRole.ToolTipText, text)
        qp.setColor(group, QPalette.ColorRole.BrightText, QColor("#ffffff"))
        qp.setColor(group, QPalette.ColorRole.PlaceholderText, muted)
        qp.setColor(group, QPalette.ColorRole.Light, light)
        qp.setColor(group, QPalette.ColorRole.Midlight, alt)
        qp.setColor(group, QPalette.ColorRole.Mid, mid)
        qp.setColor(group, QPalette.ColorRole.Dark, dark)
        qp.setColor(group, QPalette.ColorRole.Shadow, QColor("#000000"))
        qp.setColor(group, QPalette.ColorRole.Highlight, QColor(p.accent))
        qp.setColor(group, QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        qp.setColor(group, QPalette.ColorRole.Link, QColor(p.accent))
        qp.setColor(group, QPalette.ColorRole.LinkVisited, QColor(p.accent_hover))
    return qp


def qpalette_for(mode: str) -> QPalette:
    mode = mode if mode in ("dark", "light") else "dark"
    hit = _QPAL_CACHE.get(mode)
    if hit is not None:
        return QPalette(hit)
    qp = _theme_qpalette(palette(mode))
    _QPAL_CACHE[mode] = qp
    return QPalette(qp)


def apply_theme(
    target: QApplication | QWidget,
    mode: str = "dark",
    *,
    rebind_font: bool = True,
) -> Palette:
    """Swap cached QSS + QPalette. Prefer QApplication (MainWindow sheet freezes GL).

    Theme toggle should pass ``rebind_font=False`` — setFont after the sheet
    was a second full polish (2–5s hitch). Hub hosts push palette in
    ``set_theme``; MainWindow pushes stacks via ``_push_hub_theme_palettes``.
    """
    global _APP_FONT_SET
    p = palette(mode)
    sheet = stylesheet(p)  # cached after warm_theme_cache / first build
    qp = qpalette_for(p.mode)
    app = QApplication.instance()
    if isinstance(target, QApplication):
        app = target
    if app is not None:
        app.setProperty("mstnTheme", p.mode)
        # Palette before sheet — one polish wave (not sheet then N× setPalette).
        app.setPalette(qp)
        app.setStyleSheet(sheet)
        if rebind_font or not _APP_FONT_SET:
            app.setFont(app_font(13))
            _APP_FONT_SET = True
        # Hub stacks / studio hosts: MainWindow._push_hub_theme_palettes (cheap).
    elif isinstance(target, QWidget):
        target.setProperty("mstnTheme", p.mode)
        target.setPalette(qp)
        target.setStyleSheet(sheet)
    return p
