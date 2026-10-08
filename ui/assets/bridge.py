"""QML chrome for Assets Tools. Pages, queue, and the right dock stay widgets."""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, Property, QPoint, QUrl, Signal, Slot
from PySide6.QtWidgets import QWidget

from ..icons import ensure_material_icons, glyph
from .sidebar import _ACTIONS, _PACKAGE_FOOTER, _PAGE_TITLES

_ASSETS_LEFT = (("packages", "Packages", 108), ("config", "Config", 100))
_ASSETS_RIGHT = (("kuid", "KUID", 96),)
_TEX_LEFT = (("meshops", "Mesh\nLods", 100), ("texture", "Texture\nParams", 116))
_TEX_RIGHT = (("parameter", "Texture\nEditor", 116), ("denoise", "Texture\nDenoiser", 128))


class AssetsBridge(QObject):
    changed = Signal()

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._dark = True
        from ... import PKG_ROOT

        ensure_material_icons()
        font_path = PKG_ROOT / "assets" / "fonts" / "MaterialIcons-Regular.ttf"
        self._icon_url = QUrl.fromLocalFile(str(font_path)).toString()
        self._icon_font = "Material Icons"
        self._home = glyph("home") or "Home"
        self._suite = "assets"
        self._page = "packages"
        self._side_w = 380
        self._dock_on = True
        self._dock_w = 560
        self._brand = "Assets Tools"
        self._page_title = "Packages"
        self._blurb = ""
        self._actions = "[]"
        self._footer = "[]"
        self._left = "[]"
        self._right = "[]"
        self._show_queue = True
        self._nav_tall = False
        self._footer_cap = "CDP / TZarc"
        self._foot_note = "Native writers — no external Software.exe launch."
        self._viewer_on = False
        self._view_title = "Viewer"
        self._view_hint = ""
        self._view_pane = 0
        self._view_editor = False
        self._view_font = "10 pt"
        self._view_nested = False
        self._view_expanded = False
        self._view_save = False
        self._view_engine = False
        self._view_fast = False
        self._view_mesh = False
        self._view_engine_label = "Open in Engine Tuner"
        self._view_fast_label = "Fast preview"
        self._view_mesh_label = "Open in Mesh Studio"
        self._view_repl = "Replace…"
        self._view_fbx = "Delete all .fbx in CDP…"
        self._glyph_back = glyph("arrow_back")
        self._glyph_expand = glyph("fullscreen")
        self._glyph_save = glyph("save")
        self._glyph_delete = glyph("delete")
        self._form_on = False
        self._form_title = ""
        self._form_tabs = "[]"
        self._form_tab = 0
        self._form_tool = False
        self._form_blocks = "[]"

    def _bump(self) -> None:
        self.changed.emit()

    def set_dark(self, on: bool) -> None:
        self._dark = bool(on)
        self._bump()

    def sync_nav(self) -> None:
        from ..i18n import t

        host = self._host
        self._suite = host._suite
        self._nav_tall = self._suite == "texmesh"
        if self._nav_tall:
            self._page = host._sub_page
            left, right = _TEX_LEFT, _TEX_RIGHT
        else:
            page = host._page
            self._page = page if page in ("packages", "config", "kuid") else "packages"
            left, right = _ASSETS_LEFT, _ASSETS_RIGHT
        self._left = json.dumps(
            [{"key": k, "label": t(lab), "w": w} for k, lab, w in left]
        )
        self._right = json.dumps(
            [{"key": k, "label": t(lab), "w": w} for k, lab, w in right]
        )
        self._footer_cap = t("CDP / TZarc")
        self._foot_note = t("Native writers — no external Software.exe launch.")
        self.sync_side()
        self.sync_viewer()

    def sync_side(self) -> None:
        from ..i18n import t

        side = self._host.sidebar
        page = side._page if side._page in _PAGE_TITLES else "packages"
        self._brand = side._brand.text()
        self._page_title = t(_PAGE_TITLES[page])
        self._blurb = side._blurb.text()
        self._show_queue = page == "packages"
        flags = getattr(side, "_action_enabled", {})
        rows = []
        for label, action, accent in _ACTIONS.get(page, []):
            rows.append(
                {
                    "id": action,
                    "label": t(label),
                    "accent": bool(accent),
                    "enabled": bool(flags.get(action, True)),
                }
            )
        self._actions = json.dumps(rows)
        foot = []
        if page == "packages":
            for icon, action, tip, accent in _PACKAGE_FOOTER:
                foot.append(
                    {
                        "id": action,
                        "glyph": glyph(icon),
                        "tip": t(tip),
                        "accent": bool(accent),
                    }
                )
        self._footer = json.dumps(foot)
        self._bump()

    def set_dock(self, on: bool, width: int) -> None:
        host = self._host._right_dock_host
        self._dock_on = bool(on)
        if on:
            dmin, _pref, dmax = self._host._dock_width_budget()
            width = int(width)
            window_w = int(self._host.width())
            if window_w > 900:
                # Leave a center well. Texture's 1040 pref otherwise covers the table.
                room = window_w - self._side_w - 40 - 360
                width = min(width, max(dmin, room))
            self._dock_w = max(dmin, min(dmax, width))
            host.setMaximumWidth(dmax)
            host.show()
        else:
            self._dock_w = 0
            host.hide()
        self.sync_viewer()
        self.sync_form()

    def get_dark(self) -> bool:
        return self._dark

    def get_suite(self) -> str:
        return self._suite

    def get_page(self) -> str:
        return self._page

    def get_side_w(self) -> int:
        return self._side_w

    def get_dock_on(self) -> bool:
        return self._dock_on

    def get_dock_w(self) -> int:
        return self._dock_w

    def get_nav_tall(self) -> bool:
        return self._nav_tall

    def get_show_queue(self) -> bool:
        return self._show_queue

    dark = Property(bool, get_dark, notify=changed)
    suite = Property(str, get_suite, notify=changed)
    page = Property(str, get_page, notify=changed)
    sideW = Property(int, get_side_w, notify=changed)
    dockOn = Property(bool, get_dock_on, notify=changed)
    dockW = Property(int, get_dock_w, notify=changed)
    navTall = Property(bool, get_nav_tall, notify=changed)
    showQueue = Property(bool, get_show_queue, notify=changed)
    brand = Property(str, lambda self: self._brand, notify=changed)
    pageTitle = Property(str, lambda self: self._page_title, notify=changed)
    blurb = Property(str, lambda self: self._blurb, notify=changed)
    actionsJson = Property(str, lambda self: self._actions, notify=changed)
    footerJson = Property(str, lambda self: self._footer, notify=changed)
    leftNavJson = Property(str, lambda self: self._left, notify=changed)
    rightNavJson = Property(str, lambda self: self._right, notify=changed)
    footerCap = Property(str, lambda self: self._footer_cap, notify=changed)
    footNote = Property(str, lambda self: self._foot_note, notify=changed)
    homeLabel = Property(str, lambda self: self._home, notify=changed)
    iconFont = Property(str, lambda self: self._icon_font, notify=changed)
    iconFontUrl = Property(str, lambda self: self._icon_url, notify=changed)
    viewerOn = Property(bool, lambda self: self._viewer_on, notify=changed)
    viewTitle = Property(str, lambda self: self._view_title, notify=changed)
    viewHint = Property(str, lambda self: self._view_hint, notify=changed)
    viewPane = Property(int, lambda self: self._view_pane, notify=changed)
    viewEditor = Property(bool, lambda self: self._view_editor, notify=changed)
    viewFont = Property(str, lambda self: self._view_font, notify=changed)
    viewNested = Property(bool, lambda self: self._view_nested, notify=changed)
    viewExpanded = Property(bool, lambda self: self._view_expanded, notify=changed)
    viewSaveOn = Property(bool, lambda self: self._view_save, notify=changed)
    viewEngine = Property(bool, lambda self: self._view_engine, notify=changed)
    viewFast = Property(bool, lambda self: self._view_fast, notify=changed)
    viewMesh = Property(bool, lambda self: self._view_mesh, notify=changed)
    viewEngineLabel = Property(str, lambda self: self._view_engine_label, notify=changed)
    viewFastLabel = Property(str, lambda self: self._view_fast_label, notify=changed)
    viewMeshLabel = Property(str, lambda self: self._view_mesh_label, notify=changed)
    viewRepl = Property(str, lambda self: self._view_repl, notify=changed)
    viewFbx = Property(str, lambda self: self._view_fbx, notify=changed)
    glyphBack = Property(str, lambda self: self._glyph_back, notify=changed)
    glyphExpand = Property(str, lambda self: self._glyph_expand, notify=changed)
    glyphSave = Property(str, lambda self: self._glyph_save, notify=changed)
    glyphDelete = Property(str, lambda self: self._glyph_delete, notify=changed)
    formOn = Property(bool, lambda self: self._form_on, notify=changed)
    formTitle = Property(str, lambda self: self._form_title, notify=changed)
    formTabs = Property(str, lambda self: self._form_tabs, notify=changed)
    formTab = Property(int, lambda self: self._form_tab, notify=changed)
    formTool = Property(bool, lambda self: self._form_tool, notify=changed)
    formBlocks = Property(str, lambda self: self._form_blocks, notify=changed)

    @Slot(str)
    def setPage(self, page: str) -> None:
        self._host._nav.set_page(page, emit=True)

    @Slot()
    def goHome(self) -> None:
        self._host._on_home()

    @Slot(str)
    def runAction(self, action: str) -> None:
        self._host.sidebar.native_action.emit(str(action))

    @Slot(float)
    def setSideW(self, w: float) -> None:
        self._side_w = max(320, min(560, int(w)))
        self._bump()

    @Slot(float)
    def setDockW(self, w: float) -> None:
        if not self._dock_on:
            return
        dmin, _pref, dmax = self._host._dock_width_budget()
        self._dock_w = max(dmin, min(dmax, int(w)))
        self._host._dock_width_saved = self._dock_w
        self._bump()

    def _place(self, widget: QWidget, x: float, y: float, w: float, h: float, *, hide_small: bool) -> None:
        view = getattr(self._host, "_assets_view", None)
        if view is None:
            return
        if hide_small and (w < 8 or h < 8):
            widget.hide()
            return
        origin = view.mapTo(self._host, QPoint(int(x), int(y)))
        widget.setGeometry(origin.x(), origin.y(), max(1, int(w)), max(1, int(h)))
        widget.show()
        widget.raise_()

    @Slot(float, float, float, float)
    def placeQueue(self, x: float, y: float, w: float, h: float) -> None:
        rail = self._host.packages_page.queue_rail
        if not self._show_queue:
            rail.hide()
            return
        self._place(rail, x, y, w, h, hide_small=True)

    @Slot(float, float, float, float)
    def placeCenter(self, x: float, y: float, w: float, h: float) -> None:
        self._place(self._host._mid_host, x, y, w, h, hide_small=False)

    def sync_viewer(self) -> None:
        page = getattr(self._host, "packages_page", None)
        if page is None:
            return
        self._viewer_on = self._host._page == "packages" and self._dock_on
        self._view_title = page._side_title.text()
        self._view_hint = page.preview_lab.text()
        self._view_pane = 1 if page._pane_mode == "editor" else 0
        tabs = getattr(page, "_pane_mode_tabs", None)
        editor_on = True
        if tabs is not None and len(getattr(tabs, "_buttons", ())) > 1:
            editor_on = tabs._buttons[1].isEnabled()
        self._view_editor = editor_on
        self._view_font = page.font_lab.text()
        self._view_nested = page.btn_nested.isEnabled()
        self._view_expanded = bool(page._viewer_expanded)
        self._view_save = page.btn_save_text.isEnabled()
        self._view_engine = page.btn_engine_tuner.isVisible()
        self._view_fast = page.btn_fast_preview.isVisible()
        self._view_mesh = page.btn_mesh_studio.isVisible()
        self._view_engine_label = page.btn_engine_tuner.text()
        self._view_fast_label = page.btn_fast_preview.text()
        self._view_mesh_label = page.btn_mesh_studio.text()
        self._view_repl = page.btn_repl.text()
        self._view_fbx = page.btn_del_all_fbx.text()
        self._glyph_expand = glyph("fullscreen_exit" if self._view_expanded else "fullscreen")
        self._bump()

    def _page(self):
        return self._host.packages_page

    @Slot(int)
    def setViewerPane(self, index: int) -> None:
        self._page()._on_pane_mode(1 if int(index) == 1 else 0)
        self.sync_viewer()

    @Slot(int)
    def viewerFont(self, delta: int) -> None:
        self._page()._bump_font(int(delta))
        self.sync_viewer()

    @Slot()
    def viewerBack(self) -> None:
        self._page()._nested_back()
        self.sync_viewer()

    @Slot()
    def viewerExpand(self) -> None:
        self._page()._toggle_viewer_expand()
        self.sync_viewer()

    @Slot()
    def viewerSave(self) -> None:
        if self._view_save:
            self._page()._save_preview_text()

    @Slot()
    def viewerEngine(self) -> None:
        self._page()._open_in_engine_tuner()

    @Slot()
    def viewerFast(self) -> None:
        self._page()._start_fast_mesh_preview()

    @Slot()
    def viewerMesh(self) -> None:
        self._page()._open_in_mesh_studio()

    @Slot()
    def viewerReplace(self) -> None:
        self._page()._replace_selected()

    @Slot()
    def viewerDelete(self) -> None:
        self._page()._delete_selected()

    @Slot()
    def viewerSaveCdp(self) -> None:
        self._page().save_active_cdp()

    @Slot()
    def viewerDeleteFbx(self) -> None:
        self._page()._delete_all_fbx()

    @Slot(float, float, float, float)
    def placeDock(self, x: float, y: float, w: float, h: float) -> None:
        host = self._host._right_dock_host
        if not self._dock_on:
            host.hide()
            return
        # Packages Viewer chrome is QML. Keep the host shown (checks) but off the glass.
        # Minimum width from the widget dock would otherwise ignore a 1px geometry.
        if self._viewer_on or self._form_on:
            host.setMinimumWidth(0)
            host.setMaximumWidth(0)
            host.show()
            host.lower()
            return
        host.setMinimumWidth(0)
        host.setMaximumWidth(16777215)
        if w < 8 or h < 8:
            host.show()
            return
        self._place(host, x, y, w, h, hide_small=False)

    @Slot(float, float, float, float)
    def placePreview(self, x: float, y: float, w: float, h: float) -> None:
        stack = self._host.packages_page.preview_stack
        if stack.parent() is not self._host:
            stack.setParent(self._host)
        if not self._viewer_on:
            stack.hide()
            return
        self._place(stack, x, y, w, h, hide_small=True)

    def sync_form(self) -> None:
        """Texture / Mesh / Editor / Denoiser right docks. Widgets stay, QML paints them."""
        host = self._host
        kind = ""
        if getattr(host, "_page", "") == "texmesh" and self._dock_on:
            kind = str(getattr(host, "_sub_page", ""))
        self._form_on = kind in ("texture", "meshops", "parameter", "denoise")
        title = ""
        tabs: list[str] = []
        tab = 0
        tool = False
        blocks: list[dict] = []
        if kind == "texture":
            title = host._tex_props_title.text()
            tabs = ["Params", "Maps", "Resize"]
            tab = int(host._tex_side_stack.currentIndex())
            tool = tab == 1
            if tab == 0:
                blocks = self._texture_param_blocks()
            elif tab == 2:
                blocks = self._texture_prep_blocks()
        elif kind == "meshops":
            title = "Mesh Lods"
            blocks = self._mesh_blocks()
        elif kind == "parameter":
            title = "Texture Editor"
            blocks = self._param_blocks()
        elif kind == "denoise":
            title = "Texture Denoiser"
            blocks = self._denoise_blocks()
        self._form_title = title
        self._form_tabs = json.dumps(tabs)
        self._form_tab = tab
        self._form_tool = tool
        self._form_blocks = json.dumps(blocks)
        self._bump()

    def _pills(self, fid: str, label: str, seg) -> dict:
        return {
            "type": "pills",
            "id": fid,
            "label": label,
            "options": list(seg._options),
            "value": seg.value(),
            "enabled": bool(seg.isEnabled()),
        }

    def _field(self, fid: str, label: str, text: str, *, placeholder: str = "") -> dict:
        return {
            "type": "field",
            "id": fid,
            "label": label,
            "value": text,
            "placeholder": placeholder,
        }

    def _check(self, fid: str, label: str, box) -> dict:
        return {
            "type": "check",
            "id": fid,
            "label": label,
            "on": bool(box.isChecked()),
            "enabled": bool(box.isEnabled()),
        }

    def _texture_param_blocks(self) -> list[dict]:
        host = self._host
        return [
            self._field("primary", "Primary", host.tex_primary.text(), placeholder="body_albedo.tga"),
            self._field("alpha", "Alpha", host.tex_alpha.text(), placeholder="optional alpha map…"),
            self._pills("tile", "Tile", host.tex_tile),
            self._pills("usage", "UsageHint", host.tex_usage),
            self._pills("normal", "NormalMapHint", host.tex_normal),
            self._pills("compress", "Compression", host.tex_compress),
        ]

    def _texture_prep_blocks(self) -> list[dict]:
        host = self._host
        mode = host.prep_resize.value()
        blocks = [
            {
                "type": "note",
                "text": "Scales images from the list into a sibling _prep/ folder.",
            },
            self._check("prepOn", "Use these settings for Resize → _prep…", host.prep_enabled),
            self._pills("prepMap", "Map", host.prep_map),
            self._pills("prepResize", "Resize", host.prep_resize),
            self._pills("prepFmt", "Format", host.prep_fmt),
        ]
        if mode == "%":
            blocks.append(self._field("prepPct", "Percent", str(host.prep_percent.value())))
        elif mode == "exact":
            blocks.append(self._field("prepW", "Width", str(host.prep_w.value())))
            blocks.append(self._field("prepH", "Height", str(host.prep_h.value())))
        elif mode == "max":
            blocks.append(self._field("prepMax", "Max dim", str(host.prep_max.value())))
        blocks.append(self._check("prepFlip", "Flip green (DX ↔ GL)", host.prep_flip_green))
        if mode == "PoT":
            blocks.append(self._check("prepPot", "PoT round down", host.prep_pot_down))
        return blocks

    def _mesh_blocks(self) -> list[dict]:
        host = self._host
        return [
            self._field("lmOffset", "offset", f"{host.lm_offset.value():.3f}"),
            self._pills("lmCalc", "calcPoint", host.lm_calc),
            self._field("lmMult", "multiplier", f"{host.lm_mult.value():.3f}"),
            self._field("lmAnim", "animCutOff", f"{host.lm_anim.value():.3f}"),
            self._field("lmRender", "renderCutOff", f"{host.lm_render.value():.3f}"),
            self._field("lmAtt", "attachCutOff", f"{host.lm_att.value():.3f}"),
        ]

    def _param_blocks(self) -> list[dict]:
        page = self._host.param_page
        blocks: list[dict] = [
            {"type": "note", "text": page._path_lab.text()},
            {"type": "buttons", "items": [{"id": "paramOpen", "label": "Open…", "accent": True}]},
            {"type": "section", "label": "CHANNELS"},
        ]
        for key, label, _idx in (
            ("R", "Emissive", 0),
            ("G", "Roughness", 1),
            ("B", "AO", 2),
            ("A", "Metallic", 3),
        ):
            blocks.append(self._check(f"ch{key}", f"{key} — {label}", page._ch_boxes[key]))
        blocks.append({"type": "section", "label": "ADJUST"})
        blocks.extend(
            [
                self._field("pOffset", "Offset", str(page._offset.value())),
                self._field("pScale", "Scale", f"{page._scale.value():.2f}"),
                self._field("pFill", "Fill", str(page._fill.value())),
                self._field("pBright", "Bright", str(page._bright.value())),
                self._field("pContrast", "Contrast", f"{page._contrast.value():.2f}"),
                self._field("pMean", "→ Mean", str(page._mean.value())),
                {
                    "type": "buttons",
                    "items": [
                        {"id": "doOffset", "label": "Offset", "accent": False},
                        {"id": "doScale", "label": "Scale", "accent": False},
                        {"id": "doFill", "label": "Fill", "accent": False},
                    ],
                },
                {
                    "type": "buttons",
                    "items": [
                        {"id": "doBc", "label": "B/C", "accent": False},
                        {"id": "doMean", "label": "Mean", "accent": False},
                        {"id": "doInvert", "label": "Invert", "accent": False},
                    ],
                },
                {"type": "section", "label": "OVERLAY"},
                {
                    "type": "pills",
                    "id": "ovMode",
                    "label": "Mode",
                    "options": [page._ov_mode.itemText(i) for i in range(page._ov_mode.count())],
                    "value": page._ov_mode.currentText(),
                    "enabled": True,
                },
                {
                    "type": "pills",
                    "id": "ovSrc",
                    "label": "Source",
                    "options": [page._ov_src.itemText(i) for i in range(page._ov_src.count())],
                    "value": page._ov_src.currentText(),
                    "enabled": True,
                },
                self._field("ovOpacity", "Opacity", str(page._ov_opacity.value())),
                {"type": "buttons", "items": [{"id": "paramOverlay", "label": "Overlay image…", "accent": False}]},
                {"type": "section", "label": "PAINT"},
                self._check("paint", "Paint mode", page._paint_chk),
                self._field("brush", "Radius", str(page._brush.value())),
                self._field("paintVal", "Value", str(page._paint_val.value())),
                self._field("hard", "Hardness", str(page._hard.value())),
                {
                    "type": "buttons",
                    "items": [
                        {"id": "paramUndo", "label": "Undo", "accent": False},
                        {"id": "paramRedo", "label": "Redo", "accent": False},
                        {"id": "paramRevert", "label": "Revert", "accent": False},
                    ],
                },
                {"type": "note", "text": page._stats.text()},
                {"type": "buttons", "items": [{"id": "paramSave", "label": "Save (overwrite)", "accent": True}]},
            ]
        )
        return blocks

    def _denoise_blocks(self) -> list[dict]:
        page = self._host.denoise_page
        labels = [page._strength.itemText(i) for i in range(page._strength.count())]
        return [
            {"type": "buttons", "items": [{"id": "denoiseOpen", "label": "Open bake…", "accent": True}]},
            {"type": "note", "text": page._path_lab.text()},
            {
                "type": "pills",
                "id": "strength",
                "label": "Strength",
                "options": labels,
                "value": page._strength.currentText(),
                "enabled": True,
            },
            self._check("oidn", "Prefer Intel OIDN", page._prefer_oidn),
            self._check("lockBlack", "Lock black UV padding", page._preserve),
            self._field("black", "Black ≤", str(page._black.value())),
            {"type": "note", "text": page._prog_lab.text()},
            {"type": "buttons", "items": [{"id": "denoiseRun", "label": "Denoise", "accent": True}]},
            {
                "type": "buttons",
                "items": [
                    {"id": "showOrig", "label": "Show original", "accent": False},
                    {"id": "showWork", "label": "Show result", "accent": False},
                ],
            },
            {"type": "buttons", "items": [{"id": "denoiseRevert", "label": "Revert", "accent": False}]},
            {"type": "buttons", "items": [{"id": "denoiseSave", "label": "Save (overwrite)", "accent": True}]},
        ]

    @Slot(int)
    def setFormTab(self, index: int) -> None:
        host = self._host
        if getattr(host, "_sub_page", "") == "texture":
            host._tex_on_side_tab(int(index))
        self.sync_form()

    @Slot(str, str)
    def setDockField(self, key: str, raw: str) -> None:
        host = self._host
        page = getattr(host, "param_page", None)
        den = getattr(host, "denoise_page", None)
        try:
            if key == "primary":
                host.tex_primary.setText(raw)
            elif key == "alpha":
                host.tex_alpha.setText(raw)
            elif key == "tile":
                host.tex_tile.set_value(raw)
                host._tex_refresh_preview()
            elif key == "usage":
                host.tex_usage.set_value(raw)
                host._tex_on_usage_changed()
            elif key == "normal":
                host.tex_normal.set_value(raw)
                host._tex_refresh_preview()
            elif key == "compress":
                host.tex_compress.set_value(raw)
                host._tex_refresh_preview()
            elif key == "prepOn":
                host.prep_enabled.setChecked(raw == "1")
            elif key == "prepMap":
                host.prep_map.set_value(raw)
            elif key == "prepResize":
                host.prep_resize.set_value(raw)
                host._prep_sync_spins()
            elif key == "prepFmt":
                host.prep_fmt.set_value(raw)
            elif key == "prepPct":
                host.prep_percent.setValue(int(float(raw)))
            elif key == "prepW":
                host.prep_w.setValue(int(float(raw)))
            elif key == "prepH":
                host.prep_h.setValue(int(float(raw)))
            elif key == "prepMax":
                host.prep_max.setValue(int(float(raw)))
            elif key == "prepFlip":
                host.prep_flip_green.setChecked(raw == "1")
            elif key == "prepPot":
                host.prep_pot_down.setChecked(raw == "1")
            elif key == "lmOffset":
                host.lm_offset.setValue(float(raw))
            elif key == "lmCalc":
                host.lm_calc.set_value(raw)
                host._lm_refresh_preview()
            elif key == "lmMult":
                host.lm_mult.setValue(float(raw))
            elif key == "lmAnim":
                host.lm_anim.setValue(float(raw))
            elif key == "lmRender":
                host.lm_render.setValue(float(raw))
            elif key == "lmAtt":
                host.lm_att.setValue(float(raw))
            elif key.startswith("ch") and page is not None and key[2:] in page._ch_boxes:
                page._ch_boxes[key[2:]].setChecked(raw == "1")
            elif key == "pOffset" and page is not None:
                page._offset.setValue(int(float(raw)))
            elif key == "pScale" and page is not None:
                page._scale.setValue(float(raw))
            elif key == "pFill" and page is not None:
                page._fill.setValue(int(float(raw)))
            elif key == "pBright" and page is not None:
                page._bright.setValue(int(float(raw)))
            elif key == "pContrast" and page is not None:
                page._contrast.setValue(float(raw))
            elif key == "pMean" and page is not None:
                page._mean.setValue(int(float(raw)))
            elif key == "paint" and page is not None:
                page._paint_chk.setChecked(raw == "1")
            elif key == "brush" and page is not None:
                page._brush.setValue(int(float(raw)))
            elif key == "paintVal" and page is not None:
                page._paint_val.setValue(int(float(raw)))
            elif key == "hard" and page is not None:
                page._hard.setValue(int(float(raw)))
            elif key == "ovMode" and page is not None:
                idx = page._ov_mode.findText(raw)
                if idx >= 0:
                    page._ov_mode.setCurrentIndex(idx)
            elif key == "ovSrc" and page is not None:
                idx = page._ov_src.findText(raw)
                if idx >= 0:
                    page._ov_src.setCurrentIndex(idx)
            elif key == "ovOpacity" and page is not None:
                page._ov_opacity.setValue(int(float(raw)))
            elif key == "strength" and den is not None:
                idx = den._strength.findText(raw)
                if idx >= 0:
                    den._strength.setCurrentIndex(idx)
            elif key == "oidn" and den is not None:
                den._prefer_oidn.setChecked(raw == "1")
            elif key == "lockBlack" and den is not None:
                den._preserve.setChecked(raw == "1")
            elif key == "black" and den is not None:
                den._black.setValue(int(float(raw)))
        except ValueError:
            return
        self.sync_form()

    @Slot(str)
    def runDock(self, action: str) -> None:
        host = self._host
        page = getattr(host, "param_page", None)
        den = getattr(host, "denoise_page", None)
        calls = {
            "paramOpen": lambda: page and page.open_file(),
            "doOffset": lambda: page and page._do_offset(),
            "doScale": lambda: page and page._do_scale(),
            "doFill": lambda: page and page._do_fill(),
            "doBc": lambda: page and page._do_bc(),
            "doMean": lambda: page and page._do_mean(),
            "doInvert": lambda: page and page._do_invert(),
            "paramUndo": lambda: page and page.undo(),
            "paramRedo": lambda: page and page.redo(),
            "paramRevert": lambda: page and page.revert(),
            "paramSave": lambda: page and page.save(),
            "paramOverlay": lambda: page and page._do_overlay(),
            "denoiseOpen": lambda: den and den.open_file(),
            "denoiseRun": lambda: den and den.run_denoise(),
            "showOrig": lambda: den and den._show_orig(),
            "showWork": lambda: den and den._show_work(),
            "denoiseRevert": lambda: den and den.revert(),
            "denoiseSave": lambda: den and den.save(),
        }
        fn = calls.get(action)
        if fn is not None:
            fn()
        self.sync_form()

    @Slot(float, float, float, float)
    def placeFormTool(self, x: float, y: float, w: float, h: float) -> None:
        panel = getattr(self._host, "_tex_map_panel", None)
        if panel is None:
            return
        if not self._form_tool:
            panel.hide()
            return
        if panel.parent() is not self._host:
            panel.setParent(self._host)
        self._place(panel, x, y, w, h, hide_small=True)
