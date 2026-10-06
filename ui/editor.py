"""Texture.txt / config.txt editors + MeshEditor-style Editor dock."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..io.texture import check_texture_txt, material_family, texture_stem
from .code_edit import CodeEdit
from .frost import FrostGlassFrame, make_frost_pixmap, prepare_frost_scroll  # re-export for callers

__all__ = ["EditorWorkspace", "FrostGlassFrame", "make_frost_pixmap"]


def _parse_texture_txt_keys(text: str) -> dict[str, str]:
    keys: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        keys[k.strip()] = v.strip()
    return keys


def _set_texture_txt_key(text: str, key: str, value: str) -> str:
    """Replace or append Key=value (wiki form, no spaces around =)."""
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    found = False
    prefix = f"{key}="
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(prefix) or (
            "=" in stripped and stripped.split("=", 1)[0].strip() == key
        ):
            nl = "\n" if line.endswith("\n") else ""
            out.append(f"{key}={value}{nl}")
            found = True
        else:
            out.append(line)
    if not found:
        body = "".join(out)
        if body and not body.endswith("\n"):
            body += "\n"
        body += f"{key}={value}\n"
        return body
    return "".join(out)


class TextureTxtEditor(QWidget):
    """MeshEditor-style texture browser: list all .texture.txt → edit / save."""

    saved = Signal(object)  # Path
    texture_selected = Signal(object)  # Path | None
    rescan_requested = Signal()
    # Material preview: enabled, emis, rough, metal, specular (0–1 / emis 0–2)
    material_preview_changed = Signal(bool, float, float, float, float)
    # Two-sided (mesh meta): on, material_name
    two_sided_changed = Signal(bool, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Path | None = None
        self._block_props = False
        self._block_mat = False
        self._block_two = False
        self._meta_path: Path | None = None

        self._hint = QLabel(
            "Textures next to the open mesh — pick one to edit .texture.txt + Material preview."
        )
        self._hint.setObjectName("mutedTip")
        self._hint.setWordWrap(True)
        self._hint.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        from .smooth_scroll import enable_smooth_scroll

        self._list = QListWidget()
        self._list.setMinimumHeight(90)
        self._list.setToolTip("All .texture.txt under the mesh folder(s)")
        enable_smooth_scroll(self._list)
        self._list.currentItemChanged.connect(self._on_list_item)

        self._status = QLabel("")
        self._status.setObjectName("mutedTip")
        self._status.setWordWrap(True)
        self._status.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self._path_lbl = QLabel("")
        self._path_lbl.setObjectName("mutedTip")
        self._path_lbl.setWordWrap(True)
        self._path_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        # —— Material (Trainz PBR / MeshEditor-like) ——
        mat_title = QLabel("Material (preview)")
        mat_title.setStyleSheet("font-weight: 600;")
        self._mat_tip = QLabel(
            "Trainz parameter map: R=Emissive · G=Roughness · B=AO · A=Metal. "
            "Sliders preview selected family in 3D. Permanent write → paint *_parameter "
            "or edit Meshes tab + Save"
        )
        self._mat_tip.setObjectName("mutedTip")
        self._mat_tip.setWordWrap(True)
        self._mat_tip.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        self._mat_enable = QCheckBox("Override PBR on selection")
        self._mat_enable.setToolTip("Apply Emissive / Rough / Metal / Specular to matching parts in the viewport")
        self._mat_enable.toggled.connect(self._emit_material_preview)

        self._emis_lab = QLabel("Emissive 0.00")
        self._emis = QSlider(Qt.Orientation.Horizontal)
        self._emis.setRange(0, 200)  # 0–2.00
        self._emis.setValue(0)
        self._emis.valueChanged.connect(self._on_mat_slider)

        self._rough_lab = QLabel("Roughness 0.55")
        self._rough = QSlider(Qt.Orientation.Horizontal)
        self._rough.setRange(4, 100)  # 0.04–1.00
        self._rough.setValue(55)
        self._rough.valueChanged.connect(self._on_mat_slider)

        self._metal_lab = QLabel("Metal 0.00")
        self._metal = QSlider(Qt.Orientation.Horizontal)
        self._metal.setRange(0, 100)
        self._metal.setValue(0)
        self._metal.valueChanged.connect(self._on_mat_slider)

        self._spec_lab = QLabel("Specular 1.00")
        self._spec = QSlider(Qt.Orientation.Horizontal)
        self._spec.setRange(0, 200)  # 0–2× dielectric F0
        self._spec.setValue(100)
        self._spec.valueChanged.connect(self._on_mat_slider)

        self._mat_clear_btn = QPushButton("Clear override")
        self._mat_clear_btn.clicked.connect(self._clear_material_preview)

        # Two-sided / two faces (Trainz mesh metadata — not .texture.txt)
        self._two_sided = QCheckBox("Two-sided (two faces)")
        self._two_sided.setToolTip(
            "Trainz mesh metadata: materials { name { two-sided 1 } }. "
            "No backface cull — fences / thin panels / glass. "
            "Writes sibling mesh.txt (not .trainzmesh binary)."
        )
        self._two_sided.toggled.connect(self._on_two_sided_toggled)
        self._two_mat = QLineEdit()
        self._two_mat.setPlaceholderText("material name (FBX / submesh)")
        self._two_mat.setToolTip("Exact material name for materials { … } in mesh metadata")
        self._two_mat.textChanged.connect(self._on_two_mat_text)
        self._two_meta_lbl = QLabel("")
        self._two_meta_lbl.setObjectName("mutedTip")
        self._two_meta_lbl.setWordWrap(True)
        self._two_save_btn = QPushButton("Save two-sided → mesh.txt")
        self._two_save_btn.setEnabled(False)
        self._two_save_btn.clicked.connect(self._save_two_sided_meta)

        # Quick props (common Trainz texture.txt keys)
        self._primary = QLineEdit()
        self._primary.setPlaceholderText("image.tga")
        self._compression = QComboBox()
        self._compression.addItems(["", "none", "dxt1", "dxt3", "dxt5"])
        self._alpha_hint = QComboBox()
        self._alpha_hint.addItems(["", "opaque", "semitransparent", "masked"])
        self._tile = QComboBox()
        self._tile.addItems(["", "none", "s", "t", "st"])
        self._usage = QComboBox()
        self._usage.addItems(["", "albedo", "normal", "parameter"])
        self._apply_props_btn = QPushButton("Apply props → text")
        self._apply_props_btn.setEnabled(False)
        self._apply_props_btn.clicked.connect(self._apply_props_to_text)

        props = QFormLayout()
        props.addRow("Primary", self._primary)
        props.addRow("Compression", self._compression)
        props.addRow("AlphaHint", self._alpha_hint)
        props.addRow("Tile", self._tile)
        props.addRow("UsageHint", self._usage)

        self._edit = CodeEdit(syntax="trainzconfig")
        self._edit.setEnabled(False)
        self._edit.setPlaceholderText(".texture.txt contents…")

        from .icons import apply_icon

        self._save_btn = QPushButton()
        apply_icon(self._save_btn, "save", tip="Save", kind="accent", size=20, square=36)
        self._save_btn.setEnabled(False)
        self._save_btn.clicked.connect(self.save)
        self._reload_btn = QPushButton()
        apply_icon(self._reload_btn, "refresh", tip="Reload", kind="icon", size=20, square=36)
        self._reload_btn.setEnabled(False)
        self._reload_btn.clicked.connect(self._reload)
        self._rescan_btn = QPushButton()
        apply_icon(
            self._rescan_btn,
            "folder_open",
            tip="Rescan texture list from mesh folder",
            kind="icon",
            size=20,
            square=36,
        )
        self._rescan_btn.clicked.connect(self.rescan_requested.emit)

        row = QHBoxLayout()
        row.addWidget(self._save_btn)
        row.addWidget(self._reload_btn)
        row.addWidget(self._rescan_btn)
        row.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(5)
        lay.addWidget(self._hint)
        lay.addWidget(self._list, 2)
        lay.addWidget(self._status)
        lay.addWidget(self._path_lbl)
        lay.addWidget(mat_title)
        lay.addWidget(self._mat_tip)
        lay.addWidget(self._mat_enable)
        lay.addWidget(self._emis_lab)
        lay.addWidget(self._emis)
        lay.addWidget(self._rough_lab)
        lay.addWidget(self._rough)
        lay.addWidget(self._metal_lab)
        lay.addWidget(self._metal)
        lay.addWidget(self._spec_lab)
        lay.addWidget(self._spec)
        lay.addWidget(self._mat_clear_btn)
        lay.addWidget(self._two_sided)
        two_form = QFormLayout()
        two_form.addRow("Material", self._two_mat)
        lay.addLayout(two_form)
        lay.addWidget(self._two_meta_lbl)
        lay.addWidget(self._two_save_btn)
        lay.addLayout(props)
        lay.addWidget(self._apply_props_btn)
        lay.addWidget(self._edit, 2)
        lay.addLayout(row)

    @property
    def path(self) -> Path | None:
        return self._path

    def clear(self) -> None:
        self._path = None
        self._list.blockSignals(True)
        self._list.clear()
        self._list.blockSignals(False)
        self._edit.clear()
        self._edit.setEnabled(False)
        self._save_btn.setEnabled(False)
        self._reload_btn.setEnabled(False)
        self._apply_props_btn.setEnabled(False)
        self._path_lbl.setText("")
        self._status.setText("")
        self._clear_props()
        self._clear_material_preview()
        self.set_two_sided_context(None, "", True, tip="")
        self._hint.setText(
            "Open a mesh — textures from its folder appear here for edit."
        )
        self.texture_selected.emit(None)

    def set_files(
        self,
        paths: list[Path],
        *,
        select: Path | None = None,
    ) -> None:
        """Fill browser from absolute .texture.txt paths (deduped, sorted)."""
        uniq: list[Path] = []
        seen: set[str] = set()
        for p in paths:
            p = Path(p)
            key = str(p.resolve()) if p.exists() else str(p)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(p)
        uniq.sort(key=lambda x: x.name.lower())

        keep = select
        if keep is None and self._path is not None:
            keep = self._path

        self._list.blockSignals(True)
        self._list.clear()
        select_row = -1
        for i, p in enumerate(uniq):
            report = check_texture_txt(p) if p.is_file() else None
            ok = report.ok if report is not None else False
            mark = "OK" if ok else ("!" if report is not None else "?")
            item = QListWidgetItem(f"[{mark}]  {p.name}")
            item.setData(Qt.ItemDataRole.UserRole, p)
            item.setData(Qt.ItemDataRole.UserRole + 1, report)
            tip = str(p)
            if report is not None and report.issues:
                tip += "\n" + "; ".join(i.message for i in report.issues[:4])
            item.setToolTip(tip)
            self._list.addItem(item)
            if keep is not None and p.resolve() == Path(keep).resolve():
                select_row = i
            elif keep is not None and p.name.lower() == Path(keep).name.lower():
                select_row = i
        self._list.blockSignals(False)

        n = len(uniq)
        self._hint.setText(
            f"{n} texture.txt — select to edit props + text · Save writes disk."
            if n
            else "No .texture.txt next to this mesh. Drop/open an asset folder with maps."
        )
        if select_row >= 0:
            self._list.setCurrentRow(select_row)
        elif n == 1:
            self._list.setCurrentRow(0)
        elif self._path is not None and not any(
            Path(p).resolve() == self._path.resolve() for p in uniq if p.exists()
        ):
            # previous file not in list — clear editor body
            self._path = None
            self._edit.clear()
            self._edit.setEnabled(False)
            self._save_btn.setEnabled(False)
            self._reload_btn.setEnabled(False)
            self._apply_props_btn.setEnabled(False)
            self._path_lbl.setText("")
            self._status.setText("")
            self._clear_props()

    def load_path(self, path: Path | None) -> bool:
        if path is None:
            self._path = None
            self._edit.clear()
            self._edit.setEnabled(False)
            self._save_btn.setEnabled(False)
            self._reload_btn.setEnabled(False)
            self._apply_props_btn.setEnabled(False)
            self._path_lbl.setText("")
            self._status.setText("")
            self._clear_props()
            self.texture_selected.emit(None)
            return False
        path = Path(path)
        # ensure list contains this file
        found = False
        for i in range(self._list.count()):
            item = self._list.item(i)
            p = item.data(Qt.ItemDataRole.UserRole) if item else None
            if p is not None and Path(p).resolve() == path.resolve():
                self._list.blockSignals(True)
                self._list.setCurrentRow(i)
                self._list.blockSignals(False)
                found = True
                break
        if not found and path.is_file():
            self.set_files(
                [Path(self._list.item(i).data(Qt.ItemDataRole.UserRole)) for i in range(self._list.count())]
                + [path],
                select=path,
            )
            return self._path is not None and self._path.resolve() == path.resolve()
        return self._load_into_editor(path)

    def _on_list_item(
        self, cur: QListWidgetItem | None, _prev: QListWidgetItem | None
    ) -> None:
        if cur is None:
            return
        path = cur.data(Qt.ItemDataRole.UserRole)
        if path is None:
            return
        self._load_into_editor(Path(path))

    def _load_into_editor(self, path: Path) -> bool:
        if not path.is_file():
            self._hint.setText(f"File not found:\n{path}")
            return False
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            self._hint.setText(f"Could not read:\n{e}")
            return False
        self._path = path
        self._edit.setPlainText(text)
        self._edit.setEnabled(True)
        self._save_btn.setEnabled(True)
        self._reload_btn.setEnabled(True)
        self._apply_props_btn.setEnabled(True)
        self._path_lbl.setText(str(path))
        report = check_texture_txt(path)
        if report.ok:
            self._status.setText(f"OK · {report.summary}")
        else:
            msgs = "; ".join(i.message for i in report.issues[:5])
            self._status.setText(f"Issues · {msgs}")
        self._fill_props_from_text(text)
        fam, role = material_family(texture_stem(path.name))
        if role == "parameter":
            self._mat_tip.setText(
                f"Parameter map · family «{fam}» — R=Emissive G=Rough B=AO A=Metal. "
                "Tick Override to preview. Permanent: edit Meshes tab + Save."
            )
            # seed sliders from typical mid values when enabling later
        elif role:
            self._mat_tip.setText(
                f"{role} · family «{fam}» — Override applies to the whole family in 3D. "
                "Permanent PBR write → Meshes tab + Save (.trainzmesh)."
            )
        self.texture_selected.emit(path)
        return True

    def _on_mat_slider(self, _v: int = 0) -> None:
        if self._block_mat:
            return
        self._emis_lab.setText(f"Emissive {self._emis.value() / 100.0:.2f}")
        self._rough_lab.setText(f"Roughness {self._rough.value() / 100.0:.2f}")
        self._metal_lab.setText(f"Metal {self._metal.value() / 100.0:.2f}")
        self._spec_lab.setText(f"Specular {self._spec.value() / 100.0:.2f}")
        if self._mat_enable.isChecked():
            self._emit_material_preview()

    def _emit_material_preview(self, *_args) -> None:
        self.material_preview_changed.emit(
            self._mat_enable.isChecked(),
            self._emis.value() / 100.0,
            self._rough.value() / 100.0,
            self._metal.value() / 100.0,
            self._spec.value() / 100.0,
        )

    def _clear_material_preview(self) -> None:
        self._block_mat = True
        self._mat_enable.setChecked(False)
        self._emis.setValue(0)
        self._rough.setValue(55)
        self._metal.setValue(0)
        self._spec.setValue(100)
        self._emis_lab.setText("Emissive 0.00")
        self._rough_lab.setText("Roughness 0.55")
        self._metal_lab.setText("Metal 0.00")
        self._spec_lab.setText("Specular 1.00")
        self._block_mat = False
        self.material_preview_changed.emit(False, 0.0, 0.55, 0.0, 1.0)

    def material_preview_state(self) -> tuple[bool, float, float, float, float]:
        return (
            self._mat_enable.isChecked(),
            self._emis.value() / 100.0,
            self._rough.value() / 100.0,
            self._metal.value() / 100.0,
            self._spec.value() / 100.0,
        )

    def set_two_sided_context(
        self,
        meta_path: Path | None,
        material: str,
        checked: bool,
        *,
        tip: str = "",
    ) -> None:
        """Bind Two-sided UI to mesh metadata for the selected texture family."""
        self._meta_path = Path(meta_path) if meta_path is not None else None
        self._block_two = True
        self._two_mat.setText(material or "")
        self._two_sided.setChecked(bool(checked))
        self._block_two = False
        if tip:
            self._two_meta_lbl.setText(tip)
        elif self._meta_path is not None:
            exists = "exists" if self._meta_path.is_file() else "will create"
            self._two_meta_lbl.setText(f"Mesh meta ({exists}): {self._meta_path.name}")
        else:
            self._two_meta_lbl.setText("No mesh open — open FBX/IM/trainzmesh for mesh.txt write.")
        self._two_save_btn.setEnabled(self._meta_path is not None and bool(material.strip()))

    def two_sided_state(self) -> tuple[bool, str]:
        return self._two_sided.isChecked(), self._two_mat.text().strip()

    def _on_two_mat_text(self, _t: str = "") -> None:
        if self._block_two:
            return
        self._two_save_btn.setEnabled(
            self._meta_path is not None and bool(self._two_mat.text().strip())
        )

    def _on_two_sided_toggled(self, _on: bool = False) -> None:
        if self._block_two:
            return
        self._on_two_mat_text()
        self.two_sided_changed.emit(
            self._two_sided.isChecked(), self._two_mat.text().strip()
        )

    def _save_two_sided_meta(self) -> bool:
        from ..io.mesh_meta import write_two_sided

        if self._meta_path is None:
            QMessageBox.information(
                self,
                "Two-sided",
                "Open a mesh first — metadata is written next to the mesh file.",
            )
            return False
        material = self._two_mat.text().strip()
        if not material:
            QMessageBox.information(
                self, "Two-sided", "Material name is required for materials { … }."
            )
            return False
        try:
            path = write_two_sided(
                self._meta_path, material, self._two_sided.isChecked()
            )
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return False
        flag = "1" if self._two_sided.isChecked() else "0"
        self._two_meta_lbl.setText(f"Saved · {path.name} · {material} two-sided {flag}")
        self._status.setText(
            f"Two-sided {flag} → {path.name} (Trainz mesh metadata; not .texture.txt)"
        )
        self.two_sided_changed.emit(self._two_sided.isChecked(), material)
        return True

    def _clear_props(self) -> None:
        self._block_props = True
        self._primary.clear()
        self._compression.setCurrentIndex(0)
        self._alpha_hint.setCurrentIndex(0)
        self._tile.setCurrentIndex(0)
        self._usage.setCurrentIndex(0)
        self._block_props = False

    def _fill_props_from_text(self, text: str) -> None:
        keys = _parse_texture_txt_keys(text)
        self._block_props = True
        self._primary.setText(keys.get("Primary", ""))
        self._set_combo(self._compression, keys.get("Compression", ""))
        self._set_combo(self._alpha_hint, keys.get("AlphaHint", ""))
        self._set_combo(self._tile, keys.get("Tile", ""))
        self._set_combo(self._usage, keys.get("UsageHint", ""))
        self._block_props = False

    @staticmethod
    def _set_combo(combo: QComboBox, value: str) -> None:
        v = (value or "").strip()
        idx = combo.findText(v)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _apply_props_to_text(self) -> None:
        if self._path is None:
            return
        text = self._edit.toPlainText()
        primary = self._primary.text().strip()
        if primary:
            text = _set_texture_txt_key(text, "Primary", primary)
        for key, combo in (
            ("Compression", self._compression),
            ("AlphaHint", self._alpha_hint),
            ("Tile", self._tile),
            ("UsageHint", self._usage),
        ):
            val = combo.currentText().strip()
            if val:
                text = _set_texture_txt_key(text, key, val)
        self._edit.setPlainText(text)
        self._status.setText("Props applied to text — Save to write disk.")

    def _reload(self) -> None:
        if self._path is not None:
            self._load_into_editor(self._path)

    def save(self) -> bool:
        if self._path is None:
            return False
        try:
            self._path.write_text(self._edit.toPlainText(), encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return False
        # refresh list mark + status
        report = check_texture_txt(self._path)
        for i in range(self._list.count()):
            item = self._list.item(i)
            p = item.data(Qt.ItemDataRole.UserRole) if item else None
            if p is not None and Path(p).resolve() == self._path.resolve():
                mark = "OK" if report.ok else "!"
                item.setText(f"[{mark}]  {self._path.name}")
                item.setData(Qt.ItemDataRole.UserRole + 1, report)
                break
        if report.ok:
            self._status.setText(f"Saved OK · {report.summary}")
        else:
            msgs = "; ".join(i.message for i in report.issues[:5])
            self._status.setText(f"Saved with issues · {msgs}")
        self.saved.emit(self._path)
        return True


def find_config_txt(mesh_path: Path | None, mesh_folder: Path | None = None) -> Path | None:
    """Locate config.txt next to the mesh or in parent asset folders (Trainz layout)."""
    roots: list[Path] = []
    if mesh_path is not None:
        roots.append(mesh_path.parent)
        if mesh_path.parent.parent not in roots:
            roots.append(mesh_path.parent.parent)
    if mesh_folder is not None and mesh_folder not in roots:
        roots.append(mesh_folder)
    for root in roots:
        cand = root / "config.txt"
        if cand.is_file():
            return cand
    return None


class EditorWorkspace(FrostGlassFrame):
    """Studio Editor dock: Attachments | Meshes (+ binary Save, no external app)."""

    att_apply = Signal()
    att_add = Signal()
    att_delete = Signal()
    att_save = Signal()
    att_save_as = Signal()
    att_selected = Signal(int)  # row
    material_changed = Signal(int, dict)
    attachment_tree_changed = Signal(int, dict)
    two_sided_changed = Signal(int, bool, str)
    editor_mode_changed = Signal(str)  # "attachments" | "meshes"

    def __init__(self, parent=None) -> None:
        super().__init__(parent, radius=14.0)
        self.setObjectName("editorDock")
        # min 0 — a fixed minWidth here grows MainWindow when the dock opens
        self.setMinimumWidth(0)
        self.setMaximumWidth(520)

        from .mesh_prop_tree import AttachmentsPage, MeshesPage

        self.attachments_page = AttachmentsPage()
        self.meshes_page = MeshesPage()
        # Keep TextureTxtEditor for .texture.txt helpers / two-sided preview wiring
        self.texture = TextureTxtEditor()
        self.texture.setVisible(False)

        # Compatibility shims for app.py viewport drag sync (Y-up)
        self.att_list = QListWidget()
        self.att_list.setVisible(False)
        self.att_name = QLineEdit()
        self.att_name.setPlaceholderText("a.point")
        self.att_x = QDoubleSpinBox()
        self.att_y = QDoubleSpinBox()
        self.att_z = QDoubleSpinBox()
        for sp in (self.att_x, self.att_y, self.att_z):
            sp.setDecimals(4)
            sp.setRange(-1e6, 1e6)
            sp.setSingleStep(0.01)
            sp.setVisible(False)
        self.att_name.setVisible(False)

        self.att_tip = self.attachments_page.tip
        self.att_apply_btn = self.attachments_page.apply_btn
        self.att_add_btn = self.attachments_page.add_btn
        self.att_del_btn = self.attachments_page.del_btn
        self.att_save_btn = self.attachments_page.save_btn
        self.att_save_as_btn = self.attachments_page.save_as_btn

        from .app import SideTabStrip

        self.tab_strip = SideTabStrip(("Attachments", "Meshes"))
        self.tabs = QStackedWidget()
        self.tabs.setObjectName("editorTabStack")
        for page in (self.attachments_page, self.meshes_page):
            page.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            self.tabs.addWidget(page)
        self.tab_strip.index_changed.connect(self._on_tab)

        scroll = QScrollArea()
        scroll.setObjectName("editorScroll")
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(0)
        body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        body_lay.addWidget(self.tabs)
        scroll.setWidget(body)
        prepare_frost_scroll(scroll)
        self._scroll = scroll
        self.tab_strip.index_changed.connect(self._sync_scroll_body)

        from .icons import apply_icon

        self.save_btn = QPushButton()
        apply_icon(
            self.save_btn,
            "save",
            tip="Write .trainzmesh / .im from this Editor (Studio-owned)",
            kind="accent",
            size=20,
            square=36,
        )
        self.save_btn.clicked.connect(self.att_save.emit)
        self.save_as_btn = QPushButton()
        apply_icon(self.save_as_btn, "save_as", tip="Save As…", kind="icon", size=20, square=36)
        self.save_as_btn.clicked.connect(self.att_save_as.emit)

        title = QLabel("Editor")
        title.setStyleSheet("font-weight: 600; font-size: 14px;")
        sub = QLabel("Pick on the left · edit here · Save")
        sub.setObjectName("mutedTip")
        sub.setWordWrap(True)
        sub.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 16)
        lay.setSpacing(8)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addWidget(self.tab_strip)
        lay.addWidget(scroll, 1)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_btn)
        save_row.addWidget(self.save_as_btn)
        lay.addLayout(save_row)

        self.att_list.currentRowChanged.connect(self.att_selected.emit)
        self.attachments_page.apply_clicked.connect(self.att_apply.emit)
        self.attachments_page.add_clicked.connect(self.att_add.emit)
        self.attachments_page.delete_clicked.connect(self.att_delete.emit)
        self.attachments_page.save_clicked.connect(self.att_save.emit)
        self.attachments_page.save_as_clicked.connect(self.att_save_as.emit)
        self.attachments_page.attachment_changed.connect(self.attachment_tree_changed)
        self.meshes_page.material_changed.connect(self.material_changed)
        self.meshes_page.two_sided_changed.connect(self.two_sided_changed)
        QTimer.singleShot(0, self._sync_scroll_body)

    def _on_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self._sync_scroll_body()
        mode = "meshes" if index == 1 else "attachments"
        self.editor_mode_changed.emit(mode)

    def current_mode(self) -> str:
        return "meshes" if self.tabs.currentIndex() == 1 else "attachments"

    def _sync_scroll_body(self, *_args) -> None:
        """Size scroll body to the active page (same idea as left #sideScroll)."""
        page = self.tabs.currentWidget()
        body = self._scroll.widget()
        if page is None or body is None:
            return
        page.adjustSize()
        hint = page.sizeHint()
        body.setMinimumHeight(max(hint.height(), page.minimumSizeHint().height(), 1))
        body.adjustSize()

    def set_im_writable(self, writable: bool) -> None:
        self.attachments_page.set_writable(writable)
        self.save_btn.setEnabled(writable)
        self.save_as_btn.setEnabled(writable)

    def set_trainzmesh_writable(self, writable: bool) -> None:
        """Enable Save for .trainzmesh binary (materials + attachments)."""
        self.att_save_btn.setEnabled(writable)
        self.att_save_as_btn.setEnabled(writable)
        self.att_apply_btn.setEnabled(writable)
        # Add/Delete still limited for tzMF table rebuild
        self.att_add_btn.setEnabled(False)
        self.att_del_btn.setEnabled(False)
        self.save_btn.setEnabled(writable)
        self.save_as_btn.setEnabled(writable)

    def show_texture_tab(self) -> None:
        """Compat: Meshes tab replaces Texture."""
        self.show_meshes_tab()

    def show_meshes_tab(self) -> None:
        self.tab_strip.set_index(1, animate=True, emit=True)  # → _on_tab

    def show_attachments_tab(self) -> None:
        self.tab_strip.set_index(0, animate=True, emit=True)  # → _on_tab
