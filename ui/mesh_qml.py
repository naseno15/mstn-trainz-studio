"""Mesh Studio page in Qt Quick.

The 3D view stays `MeshView` (full-bleed under the chrome). Both sidebars are
QML. The old sidebar and editor widgets stay hidden and still own the data:
QML reads a snapshot and writes clicks back into them.
"""
from __future__ import annotations

import json

from PySide6.QtCore import QObject, Property, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QRegion
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QWidget

from .frost import FrostGlassFrame


def _list_rows(widget) -> list[str]:
    if widget is None:
        return []
    return [widget.item(i).text() if widget.item(i) is not None else "" for i in range(widget.count())]


def _list_row(widget) -> int:
    if widget is None:
        return -1
    return int(widget.currentRow())


def _tree_rows(tree) -> list[dict]:
    if tree is None:
        return []
    rows: list[dict] = []

    def walk(item, depth: int) -> None:
        rows.append(
            {
                "t": item.text(0),
                "a": item.text(1) if tree.columnCount() > 1 else "",
                "b": item.text(2) if tree.columnCount() > 2 else "",
                "d": depth,
                "on": bool(item.isSelected()),
            }
        )
        for i in range(item.childCount()):
            walk(item.child(i), depth + 1)

    for i in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(i), 0)
    return rows


def _tree_item(tree, flat: int):
    found = {"i": 0, "item": None}

    def walk(item) -> bool:
        if found["i"] == flat:
            found["item"] = item
            return True
        found["i"] += 1
        for i in range(item.childCount()):
            if walk(item.child(i)):
                return True
        return False

    for i in range(tree.topLevelItemCount()):
        if walk(tree.topLevelItem(i)):
            return found["item"]
    return None


def _combo(box) -> dict:
    if box is None:
        return {"i": 0, "items": []}
    return {"i": int(box.currentIndex()), "items": [box.itemText(i) for i in range(box.count())]}


def _checked(box) -> bool:
    return bool(box.isChecked()) if box is not None else False


def _item_checked(item) -> bool:
    # PySide6 checkState() is a CheckState enum; int(enum) raises.
    if item is None:
        return False
    state = item.checkState()
    return int(getattr(state, "value", state)) == 2


def _slider(slider) -> int:
    return int(slider.value()) if slider is not None else 0


def _shown(widget, ancestor) -> bool:
    if widget is None or ancestor is None:
        return False
    return bool(widget.isVisibleTo(ancestor))


def _side_snapshot(host) -> dict:
    tabs = getattr(host, "_side_tabs", None)
    stack = getattr(host, "_side_stack", None)
    labels = [b.text() for b in getattr(tabs, "_buttons", [])] if tabs is not None else []
    info = getattr(host, "_mesh_info", None)
    stats = []
    for key, lab in getattr(host, "_stat_labels", {}).items():
        stats.append({"k": key, "v": lab.text()})
    meshes = []
    table = getattr(host, "mesh_list", None)
    if table is not None:
        for r in range(table.rowCount()):
            show = table.item(r, 0)
            atts = table.item(r, 1)
            name = table.item(r, 2)
            meshes.append(
                {
                    "name": name.text() if name is not None else "",
                    "show": _item_checked(show),
                    "atts": _item_checked(atts),
                    "on": table.currentRow() == r,
                }
            )
    scene_meshes = []
    sm = getattr(host, "scene_mesh_list", None)
    if sm is not None and _shown(sm, getattr(host, "_side_panel", None)):
        for i in range(sm.count()):
            it = sm.item(i)
            scene_meshes.append(
                {
                    "t": it.text() if it is not None else "",
                    "on": sm.currentRow() == i,
                    "ck": _item_checked(it),
                }
            )
    lights = []
    for cb in getattr(host, "_light_checks", []):
        lights.append({"t": cb.text(), "on": cb.isChecked()})
    return {
        "tab": int(stack.currentIndex()) if stack is not None else 0,
        "tabs": labels,
        "infoOpen": bool(getattr(info, "_expanded", True)),
        "stats": stats,
        "meshes": meshes,
        "atts": _list_rows(getattr(host, "att_list", None)),
        "att": _list_row(getattr(host, "att_list", None)),
        "attTitle": getattr(getattr(host, "_scene_list_title", None), "text", lambda: "")(),
        "cap": getattr(getattr(host, "_scene_cap_tip", None), "text", lambda: "")(),
        "note": getattr(getattr(host, "_scene_editor_note", None), "text", lambda: "")(),
        "face": _checked(getattr(host, "_face_orient_cb", None)),
        "dsAll": _checked(getattr(host, "_mesh_ds_all", None)),
        "dsLabel": getattr(getattr(host, "_mesh_ds_apply", None), "text", lambda: "")(),
        "dsOn": bool(getattr(host, "_mesh_ds_apply", None) and host._mesh_ds_apply.isEnabled()),
        "showDs": _shown(getattr(host, "_mesh_ds_bar", None), getattr(host, "_side_panel", None)),
        "sceneMeshes": scene_meshes,
        "tex": _combo(getattr(host, "tex_mode_combo", None)),
        "mats": _tree_rows(getattr(host, "tex_tree", None)),
        "lamps": _tree_rows(getattr(host, "lamp_tree", None)),
        "lampOn": _checked(getattr(host, "_lamp_enabled", None)),
        "bright": _slider(getattr(host, "_lamp_bright", None)),
        "brightLab": getattr(getattr(host, "_lamp_bright_lab", None), "text", lambda: "")(),
        "range": _slider(getattr(host, "_lamp_range", None)),
        "rangeLab": getattr(getattr(host, "_lamp_range_lab", None), "text", lambda: "")(),
        "moon": _checked(getattr(host, "_moon_cb", None)),
        "moonInt": _slider(getattr(host, "_moon_int", None)),
        "moonLab": getattr(getattr(host, "_moon_int_lab", None), "text", lambda: "")(),
        "gizmo": _checked(getattr(host, "_lamp_gizmo_cb", None)),
        "bake": _combo(getattr(host, "_bake_quality", None)),
        "cuda": _checked(getattr(host, "_bake_cuda_cb", None)),
        "cudaOn": bool(getattr(host, "_bake_cuda_cb", None) and host._bake_cuda_cb.isEnabled()),
        "anims": _list_rows(getattr(host, "anim_list", None)),
        "anim": _list_row(getattr(host, "anim_list", None)),
        "animEmpty": _shown(getattr(host, "_anim_empty", None), getattr(host, "_side_panel", None)),
        "frame": _slider(getattr(host, "_frame_slider", None)),
        "frameMax": int(host._frame_slider.maximum()) if getattr(host, "_frame_slider", None) else 1,
        "env": _combo(getattr(host, "_env_combo", None)),
        "ground": _checked(getattr(host, "_ground_cb", None)),
        "sun": _checked(getattr(host, "_sun_mode_cb", None)),
        "az": _slider(getattr(host, "_sun_az", None)),
        "el": _slider(getattr(host, "_sun_el", None)),
        "sunInt": _slider(getattr(host, "_sun_int", None)),
        "azLab": getattr(getattr(host, "_sun_az_lab", None), "text", lambda: "")(),
        "elLab": getattr(getattr(host, "_sun_el_lab", None), "text", lambda: "")(),
        "intLab": getattr(getattr(host, "_sun_int_lab", None), "text", lambda: "")(),
        "emis": _slider(getattr(host, "_emis_slider", None)),
        "emisLab": getattr(getattr(host, "_emis_lab", None), "text", lambda: "")(),
        "lights": lights,
    }


def _rgba(row) -> list[int]:
    if row is None:
        return [0, 0, 0, 255]
    return [int(sp.value()) for sp in row._spins]


def _dock_snapshot(host) -> dict:
    editor = getattr(host, "editor", None)
    if editor is None:
        return {"mode": "meshes", "title": "", "on": False}
    meshes = editor.current_mode() == "meshes"
    detail = editor.meshes_page.detail if meshes else editor.attachments_page.detail
    mat = {}
    att = {}
    if meshes:
        box = detail.type_combo
        mat = {
            "on": detail.isEnabled(),
            "name": detail.name_edit.text(),
            "type": int(box.currentIndex()),
            "types": [box.itemText(i) for i in range(box.count())],
            "two": detail.double_sided.isChecked(),
            "vfmt": detail.vfmt.text(),
            "spec": float(detail.spec_power.value()),
            "color": _rgba(detail.mat_color),
            "emis": _rgba(detail.emis),
            "specC": _rgba(detail.spec),
            "tex": [
                {"k": key, "v": row.value(), "lock": row._edit.isReadOnly()}
                for key, row in detail._tex_rows.items()
            ],
        }
    else:
        att = {
            "on": detail.isEnabled(),
            "name": detail.name_edit.text(),
            "parent": detail.parent_edit.text(),
            "loc": [float(sp.value()) for sp in detail.loc],
            "rot": [float(sp.value()) for sp in detail.rot],
        }
    page = editor.attachments_page
    return {
        "mode": "meshes" if meshes else "attachs",
        "title": editor._title.text(),
        "sub": "Pick on the left · edit here · Save",
        "tip": page.tip.text(),
        "saveOn": editor.save_btn.isEnabled(),
        "applyOn": page.apply_btn.isEnabled(),
        "addOn": page.add_btn.isEnabled(),
        "delOn": page.del_btn.isEnabled(),
        "mat": mat,
        "att": att,
    }


class MeshBridge(QObject):
    changed = Signal()

    def __init__(self, host: QWidget) -> None:
        super().__init__(host)
        self._host = host
        self._view: QQuickWidget | None = None
        self._dark = True
        self._mesh = False
        self._page = "preview"
        self._side_open = True
        self._editor_open = False
        self._settings_open = False
        self._welcome = True
        self._instant = False
        self._pbr = 0
        self._pbr_on = False
        self._bake_on = False
        self._bake_stage = ""
        self._bake_pct = 0
        self._bake_eta = ""
        self._shortcut = ""
        self._preview = "Preview"
        self._meshes = "Meshes Editor"
        self._attachs = "Attachs Editor"
        self._settings_label = "Settings"
        self._home_glyph = "⌂"
        self._close_glyph = "×"
        self._open_glyph = "●"
        self._folder_glyph = "●"
        self._save_glyph = "●"
        self._icon_font = "Material Icons"
        self._icon_url = ""
        self._welcome_title = "Mesh Studio"
        self._welcome_body = ""
        self._open_label = "Open mesh…"
        self._fixture_label = "Open bumper.fbx fixture"
        self._home_label = "Home"
        self._tip = ""
        self._copy = "Copyright MSTN Production"
        self._pbr_labels = ["Lit", "Albedo", "Normal", "Rough", "Metal", "AO"]
        self._side_json = "{}"
        self._dock_json = "{}"
        self._sig: tuple | None = None
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._poll)
        from PySide6.QtCore import QUrl as _Url

        from .. import PKG_ROOT
        from .icons import ensure_material_icons

        ensure_material_icons()
        font_path = PKG_ROOT / "assets" / "fonts" / "MaterialIcons-Regular.ttf"
        self._icon_url = _Url.fromLocalFile(str(font_path)).toString() if font_path.is_file() else ""

    def bind_view(self, view: QQuickWidget) -> None:
        self._view = view
        self._timer.start()

    def _bump(self) -> None:
        self.changed.emit()

    def sync(self) -> None:
        host = self._host
        from .app import PBR_MODES
        from .i18n import t
        from .icons import glyph

        scene = getattr(host, "_scene", None)
        parts = bool(getattr(scene, "parts", None))
        atts = bool(getattr(scene, "attachments", None))
        page = str(getattr(host, "_page", "preview") or "preview")
        nav = getattr(host, "_nav", None)
        bar = getattr(host, "_bake_bar", None)
        shortcut = getattr(host, "_shortcut_bar", None)
        from ..util.hw import prefer_instant_panels

        self._dark = getattr(host, "_theme_mode", "dark") != "light"
        self._mesh = getattr(host, "_studio_mode", "") == "mesh"
        self._page = page
        self._side_open = bool(getattr(host, "_side_open", True))
        self._editor_open = bool(getattr(host, "_editor_dock_open", False))
        self._settings_open = bool(getattr(host, "_settings_open", False))
        self._welcome = not (parts or atts)
        self._instant = bool(prefer_instant_panels())
        self._pbr = int(getattr(host, "_debug_mode", 0) or 0)
        bake = bool(getattr(host, "_bake_busy", False))
        self._pbr_on = bool(
            self._mesh
            and not self._settings_open
            and not bake
            and ((page == "preview" and (parts or atts)) or (page == "meshes" and parts))
        )
        self._bake_on = bake
        self._bake_stage = bar._stage.text() if bar is not None else ""
        self._bake_pct = int(bar.bar.value()) if bar is not None else 0
        self._bake_eta = bar._eta.text() if bar is not None else ""
        self._shortcut = shortcut.text() if shortcut is not None else ""
        if nav is not None:
            self._preview = nav.preview_btn.text()
            self._meshes = nav.meshes_btn.text()
            self._attachs = nav.attachs_btn.text()
            self._settings_label = nav.settings_btn.text()
        self._home_glyph = glyph("home") or "⌂"
        self._close_glyph = glyph("close") or "×"
        self._open_glyph = glyph("file_open") or "●"
        self._folder_glyph = glyph("folder_open") or "●"
        self._save_glyph = glyph("save") or "●"
        self._welcome_title = t("Mesh Studio")
        self._welcome_body = ""
        self._open_label = t("Open mesh…")
        self._fixture_label = t("Open bumper.fbx fixture")
        self._home_label = t("Home")
        self._tip = ""
        self._copy = t("Copyright MSTN Production")
        page = None
        hub = getattr(host, "_hub", None)
        if hub is not None:
            from .app import HUB_MESH

            page = hub.widget(HUB_MESH)
        if page is not None:
            from PySide6.QtWidgets import QLabel

            title = page.findChild(QLabel, "welcomeTitle")
            if title is not None and title.text():
                self._welcome_title = title.text()
            tips = [lab.text() for lab in page.findChildren(QLabel, "mutedTip") if lab.text()]
            if tips:
                self._welcome_body = tips[0]
            if len(tips) > 1:
                self._tip = tips[1]
            if len(tips) > 2:
                self._copy = tips[2]
            buttons = getattr(host, "_welcome_btns", ())
            if len(buttons) >= 1 and buttons[0].text():
                self._open_label = buttons[0].text()
            if len(buttons) >= 2 and buttons[1].text():
                self._fixture_label = buttons[1].text()
            if len(buttons) >= 3 and buttons[2].text():
                self._home_label = buttons[2].text()
        self._pbr_labels = [t(name) for name, _mode in PBR_MODES]
        self._side_json = json.dumps(_side_snapshot(host), ensure_ascii=False)
        self._dock_json = json.dumps(_dock_snapshot(host), ensure_ascii=False)
        sig = (
            self._dark,
            self._mesh,
            self._page,
            self._side_open,
            self._editor_open,
            self._settings_open,
            self._welcome,
            self._instant,
            self._pbr,
            self._pbr_on,
            self._bake_on,
            self._bake_stage,
            self._bake_pct,
            self._bake_eta,
            self._shortcut,
            self._preview,
            self._meshes,
            self._attachs,
            self._settings_label,
            self._welcome_title,
            self._welcome_body,
            self._open_label,
            self._fixture_label,
            self._home_label,
            self._tip,
            self._copy,
            tuple(self._pbr_labels),
            self._side_json,
            self._dock_json,
        )
        if sig == self._sig:
            return
        self._sig = sig
        self._bump()

    def _poll(self) -> None:
        view = self._view
        if view is None or not view.isVisible():
            return
        win = view.quickWindow()
        item = win.activeFocusItem() if win is not None else None
        if item is not None and "TextInput" in item.metaObject().className():
            return
        self.sync()

    def _get_side_json(self) -> str:
        return self._side_json

    sideJson = Property(str, _get_side_json, notify=changed)

    def _get_dock_json(self) -> str:
        return self._dock_json

    dockJson = Property(str, _get_dock_json, notify=changed)

    def _get_dark(self) -> bool:
        return self._dark

    dark = Property(bool, _get_dark, notify=changed)

    def _get_mesh(self) -> bool:
        return self._mesh

    mesh = Property(bool, _get_mesh, notify=changed)

    def _get_page(self) -> str:
        return self._page

    page = Property(str, _get_page, notify=changed)

    def _get_side_open(self) -> bool:
        return self._side_open

    sideOpen = Property(bool, _get_side_open, notify=changed)

    def _get_editor_open(self) -> bool:
        return self._editor_open

    editorOpen = Property(bool, _get_editor_open, notify=changed)

    def _get_settings_open(self) -> bool:
        return self._settings_open

    settingsOpen = Property(bool, _get_settings_open, notify=changed)

    def _get_welcome(self) -> bool:
        return self._welcome

    welcome = Property(bool, _get_welcome, notify=changed)

    def _get_instant(self) -> bool:
        return self._instant

    instant = Property(bool, _get_instant, notify=changed)

    def _get_pbr(self) -> int:
        return self._pbr

    pbr = Property(int, _get_pbr, notify=changed)

    def _get_pbr_on(self) -> bool:
        return self._pbr_on

    pbrOn = Property(bool, _get_pbr_on, notify=changed)

    def _get_bake_on(self) -> bool:
        return self._bake_on

    bakeOn = Property(bool, _get_bake_on, notify=changed)

    def _get_bake_stage(self) -> str:
        return self._bake_stage

    bakeStage = Property(str, _get_bake_stage, notify=changed)

    def _get_bake_pct(self) -> int:
        return self._bake_pct

    bakePct = Property(int, _get_bake_pct, notify=changed)

    def _get_bake_eta(self) -> str:
        return self._bake_eta

    bakeEta = Property(str, _get_bake_eta, notify=changed)

    def _get_shortcut(self) -> str:
        return self._shortcut

    shortcut = Property(str, _get_shortcut, notify=changed)

    def _get_preview(self) -> str:
        return self._preview

    preview = Property(str, _get_preview, notify=changed)

    def _get_meshes(self) -> str:
        return self._meshes

    meshes = Property(str, _get_meshes, notify=changed)

    def _get_attachs(self) -> str:
        return self._attachs

    attachs = Property(str, _get_attachs, notify=changed)

    def _get_settings_label(self) -> str:
        return self._settings_label

    settingsLabel = Property(str, _get_settings_label, notify=changed)

    def _get_home_glyph(self) -> str:
        return self._home_glyph

    homeGlyph = Property(str, _get_home_glyph, notify=changed)

    def _get_open_glyph(self) -> str:
        return self._open_glyph

    openGlyph = Property(str, _get_open_glyph, notify=changed)

    def _get_folder_glyph(self) -> str:
        return self._folder_glyph

    folderGlyph = Property(str, _get_folder_glyph, notify=changed)

    def _get_save_glyph(self) -> str:
        return self._save_glyph

    saveGlyph = Property(str, _get_save_glyph, notify=changed)

    def _get_close_glyph(self) -> str:
        return self._close_glyph

    closeGlyph = Property(str, _get_close_glyph, notify=changed)

    def _get_icon_font(self) -> str:
        return self._icon_font

    iconFont = Property(str, _get_icon_font, notify=changed)

    def _get_icon_url(self) -> str:
        return self._icon_url

    iconFontUrl = Property(str, _get_icon_url, notify=changed)

    def _get_welcome_title(self) -> str:
        return self._welcome_title

    welcomeTitle = Property(str, _get_welcome_title, notify=changed)

    def _get_welcome_body(self) -> str:
        return self._welcome_body

    welcomeBody = Property(str, _get_welcome_body, notify=changed)

    def _get_open_label(self) -> str:
        return self._open_label

    openLabel = Property(str, _get_open_label, notify=changed)

    def _get_fixture_label(self) -> str:
        return self._fixture_label

    fixtureLabel = Property(str, _get_fixture_label, notify=changed)

    def _get_home_label(self) -> str:
        return self._home_label

    homeLabel = Property(str, _get_home_label, notify=changed)

    def _get_tip(self) -> str:
        return self._tip

    tip = Property(str, _get_tip, notify=changed)

    def _get_copy(self) -> str:
        return self._copy

    copy = Property(str, _get_copy, notify=changed)

    def _get_pbr_labels(self) -> list:
        return self._pbr_labels

    pbrLabels = Property("QVariantList", _get_pbr_labels, notify=changed)

    @Slot(str)
    def setPage(self, page: str) -> None:
        host = self._host
        if hasattr(host, "_set_page"):
            host._set_page(str(page))

    @Slot()
    def goHome(self) -> None:
        self._host.go_home()

    @Slot()
    def browse(self) -> None:
        self._host._browse()

    @Slot()
    def openFixture(self) -> None:
        from .app import FIXTURES

        self._host.open_path(FIXTURES / "bumper.fbx")

    @Slot(int)
    def setPbr(self, mode: int) -> None:
        self._host._set_pbr_mode(int(mode))

    @Slot()
    def cancelBake(self) -> None:
        self._host._cancel_lamp_bake()

    @Slot(list)
    def dropUrls(self, urls: list) -> None:
        from pathlib import Path

        paths: list[Path] = []
        for raw in urls:
            text = str(raw)
            if text.startswith("file:"):
                local = QUrl(text).toLocalFile()
                if local:
                    paths.append(Path(local))
            elif text:
                paths.append(Path(text))
        if paths:
            self._host._handle_dropped_paths(paths)

    @Slot(int)
    def setSideTab(self, index: int) -> None:
        tabs = getattr(self._host, "_side_tabs", None)
        if tabs is not None:
            tabs.set_index(int(index), emit=True)
        self.sync()

    @Slot(str, int)
    def pickList(self, which: str, row: int) -> None:
        host = self._host
        row = int(row)
        if which == "atts":
            host.att_list.setCurrentRow(row)
        elif which == "anim":
            host.anim_list.setCurrentRow(row)
        elif which == "scene":
            host.scene_mesh_list.setCurrentRow(row)
        elif which == "mesh":
            host.mesh_list.setCurrentCell(row, 2)
        elif which == "lamp":
            item = host.lamp_tree.topLevelItem(row)
            if item is not None:
                host.lamp_tree.setCurrentItem(item)
        self.sync()

    @Slot(int)
    def pickMat(self, flat: int) -> None:
        item = _tree_item(self._host.tex_tree, int(flat))
        if item is not None:
            self._host.tex_tree.setCurrentItem(item)
        self.sync()

    @Slot(int, int)
    def toggleMesh(self, row: int, col: int) -> None:
        from PySide6.QtCore import Qt

        item = self._host.mesh_list.item(int(row), int(col))
        if item is None:
            return
        on = _item_checked(item)
        item.setCheckState(Qt.CheckState.Unchecked if on else Qt.CheckState.Checked)
        self.sync()

    @Slot(int)
    def toggleSceneMesh(self, row: int) -> None:
        from PySide6.QtCore import Qt

        item = self._host.scene_mesh_list.item(int(row))
        if item is None:
            return
        on = _item_checked(item)
        item.setCheckState(Qt.CheckState.Unchecked if on else Qt.CheckState.Checked)
        self.sync()

    @Slot(str, bool)
    def setChecked(self, name: str, on: bool) -> None:
        host = self._host
        widget = {
            "face": host._face_orient_cb,
            "dsAll": host._mesh_ds_all,
            "lamp": host._lamp_enabled,
            "moon": host._moon_cb,
            "gizmo": host._lamp_gizmo_cb,
            "cuda": host._bake_cuda_cb,
            "ground": host._ground_cb,
            "sun": host._sun_mode_cb,
            "two": host.editor.meshes_page.detail.double_sided,
        }.get(name)
        if name.startswith("light"):
            idx = int(name[5:] or 0)
            checks = host._light_checks
            if 0 <= idx < len(checks):
                widget = checks[idx]
        if widget is not None:
            widget.setChecked(bool(on))
        self.sync()

    @Slot(str, int)
    def setSlider(self, name: str, value: int) -> None:
        host = self._host
        widget = {
            "bright": host._lamp_bright,
            "range": host._lamp_range,
            "moon": host._moon_int,
            "frame": host._frame_slider,
            "az": host._sun_az,
            "el": host._sun_el,
            "sunInt": host._sun_int,
            "emis": host._emis_slider,
        }.get(name)
        if widget is not None:
            widget.setValue(int(value))
        self.sync()

    @Slot(str, int)
    def setCombo(self, name: str, index: int) -> None:
        host = self._host
        widget = {
            "tex": host.tex_mode_combo,
            "bake": host._bake_quality,
            "env": host._env_combo,
            "type": host.editor.meshes_page.detail.type_combo,
        }.get(name)
        if widget is not None:
            widget.setCurrentIndex(int(index))
        self.sync()

    @Slot(str, str)
    def setText(self, name: str, text: str) -> None:
        host = self._host
        meshes = host.editor.meshes_page.detail
        atts = host.editor.attachments_page.detail
        if name == "matName":
            meshes.name_edit.setText(text)
            meshes.name_edit.editingFinished.emit()
        elif name == "attName":
            atts.name_edit.setText(text)
            atts.name_edit.editingFinished.emit()
        elif name == "attParent":
            atts.parent_edit.setText(text)
            atts.parent_edit.editingFinished.emit()
        elif name.startswith("tex:"):
            row = meshes._tex_rows.get(name[4:])
            if row is not None:
                row._edit.setText(text)
                row._edit.editingFinished.emit()
        self.sync()

    @Slot(str, float)
    def setSpin(self, name: str, value: float) -> None:
        host = self._host
        detail = host.editor.attachments_page.detail
        meshes = host.editor.meshes_page.detail
        if name == "spec":
            meshes.spec_power.setValue(float(value))
        elif name.startswith("loc"):
            detail.loc[int(name[3])].setValue(float(value))
        elif name.startswith("rot"):
            detail.rot[int(name[3])].setValue(float(value))
        self.sync()

    @Slot(str, int, int)
    def setChannel(self, which: str, index: int, value: int) -> None:
        detail = self._host.editor.meshes_page.detail
        row = {"color": detail.mat_color, "emis": detail.emis, "spec": detail.spec}.get(which)
        if row is None or not (0 <= int(index) < 4):
            return
        row._spins[int(index)].setValue(int(value))
        self.sync()

    @Slot(str)
    def clickId(self, name: str) -> None:
        host = self._host
        editor = host.editor
        page = editor.attachments_page
        action = {
            "open": host._open_btn,
            "folder": host._folder_btn,
            "meshRemove": getattr(host, "_mesh_remove_btn", None),
            "meshClear": getattr(host, "_mesh_clear_btn", None),
            "dsApply": host._mesh_ds_apply,
            "play": host._play_btn,
            "lampAdd": host._lamp_add_btn,
            "lampRemove": host._lamp_remove_btn,
            "lampRescan": host._lamp_rescan_btn,
            "bake": host._bake_btn,
            "resetCam": host._reset_cam_btn,
            "lampColor": host._lamp_color_btn,
            "save": editor.save_btn,
            "saveAs": editor.save_as_btn,
            "apply": page.apply_btn,
            "add": page.add_btn,
            "del": page.del_btn,
        }.get(name)
        if name == "info":
            info = host._mesh_info
            info.set_expanded(not info._expanded, animate=False)
        elif name == "color":
            host.editor.meshes_page.detail.mat_color._pick()
        elif name == "emisPick":
            host.editor.meshes_page.detail.emis._pick()
        elif name == "specPick":
            host.editor.meshes_page.detail.spec._pick()
        elif name.startswith("texBrowse:"):
            row = host.editor.meshes_page.detail._tex_rows.get(name.split(":", 1)[1])
            if row is not None and hasattr(row._btn, "click"):
                row._btn.click()
        elif action is not None:
            action.click()
        self.sync()

    def _place(self, widget: QWidget | None, x: float, y: float, w: float, h: float) -> None:
        if widget is None:
            return
        if w < 8 or h < 8:
            widget.hide()
            return
        widget.setGeometry(int(x), int(y), max(1, int(w)), max(1, int(h)))
        widget.show()
        if hasattr(self._host, "_layout_panel_edge_btns"):
            self._host._layout_panel_edge_btns()
        self._host._raise_mesh_qml_stack()

    @Slot(float, float, float, float)
    def placeSide(self, x: float, y: float, w: float, h: float) -> None:
        host = self._host
        side = getattr(host, "_side_panel", None)
        if side is None:
            return
        if getattr(host, "_studio_mode", "") != "mesh" or self._settings_open:
            side.hide()
            return
        if w < 8 or h < 8:
            side.hide()
            return
        side.setGeometry(int(x), int(y), max(1, int(w)), max(1, int(h)))
        side.hide()
        if hasattr(host, "_layout_panel_edge_btns"):
            host._layout_panel_edge_btns()

    @Slot(float, float, float, float)
    def placeEditor(self, x: float, y: float, w: float, h: float) -> None:
        host = self._host
        editor = getattr(host, "editor", None)
        if editor is None:
            return
        if w < 8 or h < 8:
            editor.hide()
            return
        editor.setGeometry(int(x), int(y), max(1, int(w)), max(1, int(h)))
        editor.hide()
        if hasattr(host, "_layout_panel_edge_btns"):
            host._layout_panel_edge_btns()

    @Slot(float, float, float, float)
    def placeSettings(self, x: float, y: float, w: float, h: float) -> None:
        panel = getattr(self._host, "_settings_panel", None)
        if not self._settings_open:
            if panel is not None:
                panel.hide()
            return
        self._place(panel, x, y, w, h)

    @Slot("QVariant")
    def noteChrome(self, packed) -> None:
        view = self._view
        if view is None:
            return
        from PySide6.QtQml import QJSValue

        if isinstance(packed, QJSValue):
            packed = packed.toVariant()
        try:
            vals = [float(v) for v in list(packed)]
        except (TypeError, ValueError):
            vals = []
        region = QRegion()
        for i in range(0, len(vals) - 3, 4):
            w = int(vals[i + 2])
            h = int(vals[i + 3])
            if w < 2 or h < 2:
                continue
            region = region.united(QRegion(int(vals[i]), int(vals[i + 1]), w, h))
        from PySide6.QtCore import Qt

        if region.isEmpty():
            view.clearMask()
            view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            return
        view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        view.setMask(region)


def mount_mesh_qml(host: QWidget) -> bool:
    """Build the QML page over the mesh viewport. False keeps the widget chrome."""
    from pathlib import Path

    from PySide6.QtCore import Qt

    from .app import _logo_pixmap
    from .qml_host import _qml_ok, _quick

    qml = Path(__file__).resolve().parent / "qml" / "MeshPage.qml"
    if not qml.is_file():
        return False
    bridge = MeshBridge(host)
    view = _quick(qml, bridge, logo=lambda mode: _logo_pixmap(180, mode=mode))
    if not _qml_ok(view):
        view.deleteLater()
        return False
    view.setClearColor(QColor(0, 0, 0, 0))
    view.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    view.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    view.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)
    view.setAcceptDrops(True)
    view.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    view.setParent(host._center_host)
    view.hide()
    bridge.bind_view(view)
    host._mesh_bridge = bridge
    host._mesh_view = view

    for panel in (
        getattr(host, "_side_panel", None),
        getattr(host, "editor", None),
        getattr(host, "_settings_panel", None),
    ):
        if isinstance(panel, FrostGlassFrame):
            panel.set_paint_plate(False)
        if panel is not None:
            panel.setAutoFillBackground(False)
            panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    editor = getattr(host, "editor", None)
    if editor is not None:
        editor.setMinimumWidth(0)
        editor.setMaximumWidth(520)
    layer = getattr(host, "_chrome_layer", None)
    if layer is not None:
        layer.hide()
    for widget in (
        getattr(host, "_nav", None),
        getattr(host, "_shortcut_bar", None),
        getattr(host, "_bake_bar", None),
        getattr(host, "pbr_hud", None),
    ):
        if widget is not None:
            widget.hide()
    bar = getattr(host, "_bake_bar", None)
    if bar is not None:
        orig = bar.set_progress

        def set_progress(stage: str, pct: int, eta_sec: float, _orig=orig) -> None:
            _orig(stage, pct, eta_sec)
            bridge.sync()

        bar.set_progress = set_progress  # type: ignore[method-assign]
    bridge.sync()
    return True
