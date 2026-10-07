"""Assets Studio left sidebar — native page actions (no external exes)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..frost import FrostGlassFrame
from ..icons import apply_icon
from ..motion import fade_widget
from ..smooth_scroll import enable_smooth_scroll_area
from ..theme import app_font

_ASSETS = Path(__file__).resolve().parents[2] / "assets"
_LOGO_WHITE = _ASSETS / "mstn_logo_white.png"
_LOGO_CACHE: QPixmap | None = None

_PAGE_TITLES = {
    "packages": "Packages",
    "config": "Config",
    "texture": "Texture",
    "meshops": "Mesh Ops",
    "kuid": "KUID",
}

# page → list of (label, action_id, accent?)
_ACTIONS: dict[str, list[tuple[str, str, bool]]] = {
    "packages": [],  # icon footer — see _PACKAGE_FOOTER
    "config": [
        ("Open config.chump…", "open_chump", True),
        ("Save config.chump…", "save_chump", False),
        ("Open config.txt → chump…", "txt_to_chump", False),
        ("Export to config.txt…", "export_config_txt", False),
        ("Rules scan (folder)…", "cfg_rules_scan", True),
    ],
    "texture": [
        ("New from image…", "tex_from_image", False),
        ("Save .texture.txt…", "tex_save", False),
        ("Save all…", "tex_save_all", True),
        ("Resize → _prep…", "tex_resize", True),
        ("Rules scan", "tex_rules_scan", True),
        ("Rules fix…", "tex_rules_fix", True),
        ("VE39 scan", "tex_ve39_scan", False),
        ("VE39 fix…", "tex_ve39_fix", False),
        ("Check file…", "open_texture", False),
        ("Scan folder…", "scan_folder", False),
    ],
    "meshops": [
        ("Add mesh row", "lm_add", False),
        ("Remove selected", "lm_remove", False),
        ("Rules scan", "lm_rules_scan", True),
        ("Rules fix…", "lm_rules_fix", True),
        ("Scan materials", "lm_mat_scan", False),
        ("Fix material names…", "lm_mat_fix", True),
        ("Load .lm.txt…", "lm_load", False),
        ("Save all…", "lm_save", True),
    ],
    "kuid": [
        ("Normalize list", "normalize_kuids", True),
        ("Hex + hash", "kuid_hash", False),
        ("Copy list", "copy_kuids", False),
    ],
}

# (icon, action_id, tooltip, accent?)
_PACKAGE_FOOTER: list[tuple[str, str, str, bool]] = [
    ("file_open", "open_cdp", "Open CDP", True),
    ("archive", "pack_cdp", "Pack CDP", True),
    ("unarchive", "extract_cdp", "Extract CDP", False),
    ("inventory_2", "open_tzarc", "Open TZarc", False),
    ("folder_zip", "extract_tzarc", "Extract TZarc", False),
    ("content_copy", "copy_pkg_kuids", "Copy KUIDs", False),
]


def _trim_transparent(pix: QPixmap) -> QPixmap:
    img = pix.toImage()
    if img.isNull():
        return pix
    w, h = img.width(), img.height()
    left, top, right, bottom = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() > 8:
                left = min(left, x)
                right = max(right, x)
                top = min(top, y)
                bottom = max(bottom, y)
    if right < left:
        return pix
    return pix.copy(left, top, right - left + 1, bottom - top + 1)


def _logo_pixmap(width: int = 120, *, mode: str = "dark") -> QPixmap:
    global _LOGO_CACHE
    if not _LOGO_WHITE.is_file():
        empty = QPixmap(width, max(28, width // 4))
        empty.fill(QColor(0, 0, 0, 0))
        return empty
    if _LOGO_CACHE is None or _LOGO_CACHE.isNull():
        raw = QPixmap(str(_LOGO_WHITE))
        _LOGO_CACHE = _trim_transparent(raw) if not raw.isNull() else raw
    pix = _LOGO_CACHE.scaledToWidth(width, Qt.TransformationMode.SmoothTransformation)
    if mode == "light":
        out = QPixmap(pix.size())
        out.fill(Qt.GlobalColor.transparent)
        p = QPainter(out)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(out.rect(), QColor("#1d1d1f"))
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
        p.drawPixmap(0, 0, pix)
        p.end()
        return out
    return pix


class AssetsSidebar(FrostGlassFrame):
    native_action = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent, radius=14.0)
        self.setObjectName("sidePanel")
        self.setMinimumWidth(360)
        self.setMaximumWidth(560)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._theme = "dark"
        self._page = "packages"
        self._page_anim = None
        self._queue_rail: QWidget | None = None

        outer = QVBoxLayout(self)
        # inset for shadow ring painted inside FrostGlassFrame (same as Mesh)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(10)

        logo_plate = QFrame()
        logo_plate.setObjectName("logoPlate")
        lp = QVBoxLayout(logo_plate)
        lp.setContentsMargins(2, 0, 2, 0)
        lp.setSpacing(6)
        self._logo = QLabel()
        self._logo.setObjectName("sideLogo")
        self._logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo.setPixmap(_logo_pixmap(108, mode=self._theme))
        lp.addWidget(self._logo)
        brand = QLabel("Assets Tools")
        brand.setObjectName("brandTitle")
        brand.setFont(app_font(15, QFont.Weight.Bold))
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setProperty("mstn_i18n_src", "Assets Tools")
        self._brand = brand
        lp.addWidget(brand)
        outer.addWidget(logo_plate)

        self.page_lab = QLabel("Packages")
        self.page_lab.setObjectName("welcomeTitle")
        self.page_lab.setFont(app_font(14, QFont.Weight.DemiBold))
        outer.addWidget(self.page_lab)

        self._blurb = QLabel("")
        self._blurb.setObjectName("mutedTip")
        self._blurb.setWordWrap(True)
        outer.addWidget(self._blurb)

        # Packages queue fills the middle (outside scroll so the table can stretch).
        self._packages_host = QWidget()
        self._packages_host.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        self._packages_host_lay = QVBoxLayout(self._packages_host)
        self._packages_host_lay.setContentsMargins(0, 0, 0, 0)
        self._packages_host_lay.setSpacing(0)
        outer.addWidget(self._packages_host, 1)

        # Other pages: scrollable text actions
        scroll = QScrollArea()
        scroll.setObjectName("sideScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 2, 0, 0)
        self._body_lay.setSpacing(8)
        self._body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._actions_host = QWidget()
        self._actions_lay = QVBoxLayout(self._actions_host)
        self._actions_lay.setContentsMargins(0, 0, 0, 0)
        self._actions_lay.setSpacing(8)
        self._actions_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._body_lay.addWidget(self._actions_host)
        self._body_lay.addStretch(1)
        # setWidget before enable_smooth (→ prepare_frost_scroll) —
        # otherwise body keeps Base fill (black slab, sharp corners)
        scroll.setWidget(self._body)
        enable_smooth_scroll_area(scroll)
        self._actions_scroll = scroll
        outer.addWidget(scroll, 1)

        # Packages action footer (Material icons + tooltips)
        self._footer = QFrame()
        self._footer.setObjectName("pkgSideFooter")
        fl = QVBoxLayout(self._footer)
        fl.setContentsMargins(0, 4, 0, 0)
        fl.setSpacing(6)
        foot_lab = QLabel("CDP / TZarc")
        foot_lab.setObjectName("mutedTip")
        foot_lab.setFont(app_font(11, QFont.Weight.DemiBold))
        fl.addWidget(foot_lab)
        self._footer_row = QHBoxLayout()
        self._footer_row.setContentsMargins(0, 0, 0, 0)
        self._footer_row.setSpacing(6)
        fl.addLayout(self._footer_row)
        outer.addWidget(self._footer)

        tip = QLabel("Native writers — no external Software.exe launch.")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        outer.addWidget(tip)

        self._rebuild_actions()

    def mount_packages_queue(self, rail: QWidget) -> None:
        """Park Packages drop+table into the left sidebar (owns layout slot)."""
        if self._queue_rail is rail:
            return
        if self._queue_rail is not None:
            self._packages_host_lay.removeWidget(self._queue_rail)
            self._queue_rail.setParent(None)
        self._queue_rail = rail
        self._packages_host_lay.addWidget(rail, 1)
        self._sync_packages_visibility()

    def set_theme(self, mode: str) -> None:
        self._theme = mode if mode in ("dark", "light") else "dark"
        self._logo.setPixmap(_logo_pixmap(108, mode=self._theme))
        self.set_frost(None, dark=self._theme != "light")

    def set_brand(self, title: str) -> None:
        """Sidebar masthead — Assets Tools vs Texture / Mesh Tools."""
        self._brand.setProperty("mstn_i18n_src", title)
        try:
            from ..i18n import t

            self._brand.setText(t(title))
        except Exception:
            self._brand.setText(title)

    def set_page(self, page: str, *, animate: bool = True) -> None:
        if page not in _PAGE_TITLES:
            page = "packages"
        if page == self._page:
            return
        self._page = page
        self.page_lab.setText(_PAGE_TITLES[page])
        if not animate:
            self._stop_page_anim()
            self._rebuild_actions()
            return
        self._animate_actions()

    def _stop_page_anim(self) -> None:
        anim = self._page_anim
        if anim is not None:
            anim.stop()
            self._page_anim = None
        if self._body.graphicsEffect() is not None:
            self._body.setGraphicsEffect(None)

    def _animate_actions(self) -> None:
        """Fade out → swap action buttons → fade in (top-bar / bottom page changes)."""
        from ..motion import clear_button_hover_chrome

        self._stop_page_anim()
        clear_button_hover_chrome()  # don't leave bubble glued to a dying button
        target = self._page
        anim = fade_widget(self._body, 1.0, 0.0, 140)
        self._page_anim = anim

        def _swap() -> None:
            if self._page != target:
                return
            clear_button_hover_chrome()
            self._rebuild_actions()
            fade_in = fade_widget(self._body, 0.0, 1.0, 180)
            self._page_anim = fade_in

            def _done() -> None:
                if self._page_anim is fade_in:
                    self._page_anim = None
                # drop effect so frost/scroll stay sharp after transition
                if isinstance(self._body.graphicsEffect(), QGraphicsOpacityEffect):
                    self._body.setGraphicsEffect(None)

            fade_in.finished.connect(_done)

        anim.finished.connect(_swap)

    def _clear_actions(self) -> None:
        from ..motion import clear_button_hover_chrome

        clear_button_hover_chrome()
        while self._actions_lay.count():
            item = self._actions_lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _clear_footer(self) -> None:
        while self._footer_row.count():
            item = self._footer_row.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _sync_packages_visibility(self) -> None:
        is_pkg = self._page == "packages"
        self._packages_host.setVisible(is_pkg and self._queue_rail is not None)
        self._actions_scroll.setVisible(not is_pkg)
        self._footer.setVisible(is_pkg)

    def _rebuild_footer(self) -> None:
        self._clear_footer()
        if self._page != "packages":
            self._footer.setVisible(False)
            return
        self._footer.setVisible(True)
        self._footer_row.addStretch(1)
        for icon, action, tip, accent in _PACKAGE_FOOTER:
            btn = QPushButton()
            apply_icon(
                btn,
                icon,
                tip=tip,
                kind="accent" if accent else "icon",
                size=20,
                square=40,
            )
            btn.clicked.connect(lambda _=False, a=action: self.native_action.emit(a))
            self._footer_row.addWidget(btn)
        self._footer_row.addStretch(1)

    def _rebuild_actions(self) -> None:
        from ..i18n import g, t

        blurbs = {
            "packages": "Queue — ลากโฟลเดอร์ asset หรือ .cdp · Pack ≤500 / ≤800 / max 1 GB",
            "config": "Edit config.chump · pack/export config.txt · VE rules on asset folder.",
            "texture": "Texture rules (VE37/39/65…) · .texture.txt · Resize → _prep/.",
            "meshops": "Mesh/LOD/material rules · .lm.txt · .m.pbrmetal / .m.onetex.",
            "kuid": "Normalize · hex · hash-XX folder (chump buckets).",
        }
        blurb = blurbs.get(self._page, "")
        self._blurb.setText(t(blurb) if blurb else "")
        if self._page == "texture":
            self._blurb.setToolTip(g("rules.tip"))
        elif self._page == "meshops":
            self._blurb.setToolTip(g("rules.mesh.tip"))
        else:
            self._blurb.setToolTip("")
        self._clear_actions()
        self._action_btns: dict[str, QPushButton] = {}
        self._sync_packages_visibility()
        self._rebuild_footer()

        if self._page == "packages":
            return

        from ..i18n.glossary_ve import GLOSSARY as _VE
        from ..motion import attach_glass_tip

        ve39_src = {
            "tex_ve39_scan": _VE["ve39.scan"],
            "tex_ve39_fix": _VE["ve39.fix"],
        }
        for label, action, accent in _ACTIONS.get(self._page, []):
            btn = QPushButton(t(label))
            btn.setProperty("mstn_i18n_src", label)
            if accent:
                btn.setObjectName("accentBtn")
            btn.setMinimumHeight(36)
            src_tip = ve39_src.get(action)
            if src_tip:
                # glass tip only — setToolTip here would re-enable native Qt tip
                attach_glass_tip(btn, src_tip)
            btn.clicked.connect(lambda _=False, a=action: self.native_action.emit(a))
            self._actions_lay.addWidget(btn)
            self._action_btns[action] = btn
        for action, on in getattr(self, "_action_enabled", {}).items():
            self.set_action_enabled(action, on)

    def set_action_enabled(self, action: str, enabled: bool) -> None:
        """Enable/disable a sidebar action button (persists across page rebuilds)."""
        flags = getattr(self, "_action_enabled", None)
        if flags is None:
            flags = {}
            self._action_enabled = flags
        flags[action] = bool(enabled)
        btn = getattr(self, "_action_btns", {}).get(action)
        if btn is not None:
            btn.setEnabled(bool(enabled))
