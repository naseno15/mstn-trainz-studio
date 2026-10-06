"""Editor detail panels (list lives on left Scene tab — linked selection)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QEvent, QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..io.tzmf_edit import (
    AttRecord,
    MatBlock,
    bytes255_to_rgba01,
    rgba01_to_bytes255,
)

_MAT_TYPES = (
    "pbrmetal",
    "pbrmetalmasked",
    "pbrmetaldetail",
    "pbrmetalspec",
    "stdonetex",
    "glass",
)


class _NoWheelFilter(QObject):
    """Block wheel on spinboxes so scrolling the dock doesn't nudge values."""

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.Type.Wheel and isinstance(
            obj, (QSpinBox, QDoubleSpinBox)
        ):
            event.ignore()
            return True
        return False


_NO_WHEEL = _NoWheelFilter()


def _float_spin(*, decimals: int = 6, lo: float = -1e6, hi: float = 1e6) -> QDoubleSpinBox:
    sp = QDoubleSpinBox()
    sp.setDecimals(decimals)
    sp.setRange(lo, hi)
    sp.setSingleStep(0.01)
    # arrows OK for click; wheel blocked
    sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    sp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    sp.installEventFilter(_NO_WHEEL)
    return sp


def _int_spin(*, lo: int = 0, hi: int = 255) -> QSpinBox:
    sp = QSpinBox()
    sp.setRange(lo, hi)
    sp.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)
    sp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    sp.installEventFilter(_NO_WHEEL)
    return sp


def _section(title: str) -> QLabel:
    lab = QLabel(title)
    lab.setStyleSheet("font-weight: 600;")
    return lab


def _typed_row(label: str, widget: QWidget, type_name: str = "float") -> QWidget:
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lab = QLabel(f"{label}:")
    lab.setMinimumWidth(72)
    tip = QLabel(f"({type_name})")
    tip.setObjectName("mutedTip")
    lay.addWidget(lab)
    lay.addWidget(widget, 1)
    lay.addWidget(tip)
    return row


class ColorRow(QWidget):
    changed = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spins = [_int_spin() for _ in range(4)]
        for sp in self._spins:
            sp.valueChanged.connect(self._on_edit)
        self._swatch = QPushButton()
        self._swatch.setFixedSize(22, 22)
        self._swatch.clicked.connect(self._pick)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(QLabel(label))
        for sp in self._spins:
            lay.addWidget(sp)
        lay.addWidget(self._swatch)
        lay.addStretch(1)
        self._block = False
        self.set_rgba01((0.8, 0.8, 0.8, 1.0))

    def _on_edit(self, *_a) -> None:
        if self._block:
            return
        self._paint_swatch()
        self.changed.emit()

    def _paint_swatch(self) -> None:
        r, g, b, _a = (sp.value() for sp in self._spins)
        self._swatch.setStyleSheet(
            f"background: rgb({r},{g},{b}); border:1px solid #666;"
        )

    def _pick(self) -> None:
        c = QColorDialog.getColor(
            QColor(self._spins[0].value(), self._spins[1].value(), self._spins[2].value()),
            self,
            "Material color",
        )
        if not c.isValid():
            return
        self._block = True
        self._spins[0].setValue(c.red())
        self._spins[1].setValue(c.green())
        self._spins[2].setValue(c.blue())
        self._block = False
        self._on_edit()

    def set_rgba01(self, rgba: tuple[float, float, float, float]) -> None:
        b = rgba01_to_bytes255(rgba)
        self._block = True
        for sp, v in zip(self._spins, b):
            sp.setValue(int(v))
        self._block = False
        self._paint_swatch()

    def rgba01(self) -> tuple[float, float, float, float]:
        return bytes255_to_rgba01(tuple(sp.value() for sp in self._spins))  # type: ignore[arg-type]


class TextureSlotRow(QWidget):
    changed = Signal(str, str)

    def __init__(self, key: str, value: str = "", *, readonly: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.key = key
        self._edit = QLineEdit(value)
        self._edit.setReadOnly(readonly)
        self._btn = QPushButton("…")
        self._btn.setFixedWidth(28)
        self._btn.setEnabled(not readonly)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lab = QLabel(key)
        lab.setMinimumWidth(110)
        lay.addWidget(lab)
        lay.addWidget(self._edit, 1)
        lay.addWidget(self._btn)
        self._edit.editingFinished.connect(self._emit)
        self._btn.clicked.connect(self._browse)

    def _emit(self) -> None:
        self.changed.emit(self.key, self._edit.text().strip())

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            f"Select {self.key}",
            "",
            "Trainz texture (*.texture *.texture.txt *.tga *.png);;All (*.*)",
        )
        if not path:
            return
        name = Path(path).name
        if name.lower().endswith(".texture.txt"):
            name = name[: -len(".txt")]
        self._edit.setText(name)
        self._emit()

    def set_value(self, value: str) -> None:
        self._edit.blockSignals(True)
        self._edit.setText(value)
        self._edit.blockSignals(False)

    def value(self) -> str:
        return self._edit.text().strip()


class MeshDetail(QWidget):
    changed = Signal()
    two_sided_changed = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._index = -1
        self._block = False
        self._slot_keys: list[str] = []

        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems(list(_MAT_TYPES))
        self.double_sided = QCheckBox("Double Sided")
        self.vfmt = QLabel("—")
        self.vfmt.setObjectName("mutedTip")
        self.vfmt.setWordWrap(True)

        self.mat_color = ColorRow("Material Color")
        self.emis = ColorRow("matEmissive")
        self.spec = ColorRow("matSpecular")
        self.spec_power = _float_spin()

        self._tex_host = QVBoxLayout()
        self._tex_rows: dict[str, TextureSlotRow] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Material Type", self.type_combo)
        lay.addLayout(form)
        lay.addWidget(self.double_sided)
        lay.addWidget(QLabel("Vertex Format"))
        lay.addWidget(self.vfmt)

        lay.addWidget(_section("Texture Data"))
        lay.addLayout(self._tex_host)

        lay.addWidget(_section("Color Data"))
        for w in (self.mat_color, self.emis, self.spec):
            lay.addWidget(w)
        lay.addWidget(_typed_row("specPower", self.spec_power, "float"))

        self.name_edit.editingFinished.connect(self._emit)
        self.type_combo.currentIndexChanged.connect(self._emit)
        self.double_sided.toggled.connect(self._on_two)
        self.spec_power.valueChanged.connect(self._emit)
        for w in (self.mat_color, self.emis, self.spec):
            w.changed.connect(self._emit)

    def _emit(self, *_a) -> None:
        if self._block or self._index < 0:
            return
        self.changed.emit()

    def _on_two(self, on: bool) -> None:
        if self._block or self._index < 0:
            return
        self.two_sided_changed.emit(on)
        self.changed.emit()

    def clear(self) -> None:
        self._index = -1
        self.setEnabled(False)

    def load(self, index: int, mat: MatBlock, *, two_sided: bool = True) -> None:
        self._block = True
        self._index = index
        self.setEnabled(True)
        self.name_edit.setText(mat.name)
        idx = self.type_combo.findText(mat.type_name)
        self.type_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.double_sided.setChecked(two_sided)
        self.vfmt.setText(mat.vertex_format or "—")
        self.mat_color.set_rgba01(mat.color)
        self.emis.set_rgba01(mat.emissive)
        self.spec.set_rgba01(mat.specular)
        self.spec_power.setValue(mat.spec_power)

        keys = [s.key for s in mat.textures]
        if keys != self._slot_keys:
            while self._tex_host.count():
                item = self._tex_host.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
            self._tex_rows.clear()
            self._slot_keys = keys
            for slot in mat.textures:
                readonly = slot.key.lower().startswith("txenv") or slot.value.startswith("$")
                row = TextureSlotRow(slot.key, slot.value, readonly=readonly)
                row.changed.connect(self._emit)
                self._tex_host.addWidget(row)
                self._tex_rows[slot.key] = row
        else:
            for slot in mat.textures:
                row = self._tex_rows.get(slot.key)
                if row is not None:
                    row.set_value(slot.value)
        self._block = False

    @property
    def index(self) -> int:
        return self._index

    def collect(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "type_name": self.type_combo.currentText().strip(),
            "color": self.mat_color.rgba01(),
            "emissive": self.emis.rgba01(),
            "specular": self.spec.rgba01(),
            "spec_power": float(self.spec_power.value()),
            "textures": {k: r.value() for k, r in self._tex_rows.items()},
            "two_sided": self.double_sided.isChecked(),
        }


class MeshesPage(QWidget):
    """Right Editor — material detail only (list on left Scene tab)."""

    material_changed = Signal(int, dict)
    two_sided_changed = Signal(int, bool, str)
    material_selected = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._mats: list[MatBlock] = []
        self._two_sided: dict[str, bool] = {}
        self.detail = MeshDetail()
        self.detail.setEnabled(False)

        tip = QLabel("Select a mesh on the left · edit here · Save writes .trainzmesh")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)
        lay.addWidget(tip)
        lay.addWidget(self.detail)
        lay.addStretch(1)

        self.detail.changed.connect(self._on_detail)
        self.detail.two_sided_changed.connect(self._on_two)

    def clear(self) -> None:
        self._mats = []
        self._two_sided = {}
        self.detail.clear()

    def set_info(self, **_kwargs) -> None:
        """Compat no-op — Mesh Information removed."""

    def set_materials(
        self,
        mats: list[MatBlock],
        *,
        two_sided: dict[str, bool] | None = None,
    ) -> None:
        keep = self.detail.index
        self._mats = list(mats)
        self._two_sided = dict(two_sided or {})
        if self._mats:
            row = keep if 0 <= keep < len(self._mats) else 0
            self.select_row(row)
        else:
            self.detail.clear()

    def select_row(self, row: int) -> None:
        if row < 0 or row >= len(self._mats):
            self.detail.clear()
            return
        mat = self._mats[row]
        self.detail.load(
            row, mat, two_sided=bool(self._two_sided.get(mat.name, True))
        )
        self.material_selected.emit(row)

    def material_names(self) -> list[str]:
        return [m.name for m in self._mats]

    def _on_detail(self) -> None:
        idx = self.detail.index
        if idx < 0:
            return
        fields = self.detail.collect()
        if 0 <= idx < len(self._mats) and fields.get("name"):
            # keep name in cached mat for left-list sync
            m = self._mats[idx]
            m.name = fields["name"]
        self.material_changed.emit(idx, fields)

    def _on_two(self, on: bool) -> None:
        idx = self.detail.index
        if idx < 0:
            return
        name = self.detail.collect().get("name") or ""
        self._two_sided[name] = on
        self.two_sided_changed.emit(idx, on, name)


class AttachmentDetail(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._index = -1
        self._block = False

        self.name_edit = QLineEdit()
        self.parent_edit = QLineEdit()
        self.parent_edit.setPlaceholderText("(none)")
        self.loc = [_float_spin() for _ in range(3)]
        self.rot = [_float_spin() for _ in range(4)]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        form = QFormLayout()
        form.addRow("Name", self.name_edit)
        form.addRow("Parent", self.parent_edit)
        lay.addLayout(form)

        lay.addWidget(_section("Location"))
        for lab, sp in zip(("X", "Y", "Z"), self.loc):
            lay.addWidget(_typed_row(lab, sp, "float"))
            sp.valueChanged.connect(self._emit)

        lay.addWidget(_section("Rotation"))
        for lab, sp in zip(("X", "Y", "Z", "W"), self.rot):
            lay.addWidget(_typed_row(lab, sp, "float"))
            sp.valueChanged.connect(self._emit)

        self.name_edit.editingFinished.connect(self._emit)

    def _emit(self, *_a) -> None:
        if self._block or self._index < 0:
            return
        self.changed.emit()

    def clear(self) -> None:
        self._index = -1
        self.setEnabled(False)

    def load(self, index: int, rec: AttRecord) -> None:
        self._block = True
        self._index = index
        self.setEnabled(True)
        self.name_edit.setText(rec.name)
        self.parent_edit.clear()
        for sp, v in zip(self.loc, rec.pos_zup):
            sp.setValue(float(v))
        for sp, v in zip(self.rot, rec.quat_zup):
            sp.setValue(float(v))
        self._block = False

    @property
    def index(self) -> int:
        return self._index

    def set_pos_zup(self, pos: tuple[float, float, float]) -> None:
        if self._index < 0:
            return
        self._block = True
        for sp, v in zip(self.loc, pos):
            sp.setValue(float(v))
        self._block = False

    def set_quat_zup(self, quat: tuple[float, float, float, float]) -> None:
        if self._index < 0:
            return
        self._block = True
        for sp, v in zip(self.rot, quat):
            sp.setValue(float(v))
        self._block = False

    def collect(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "parent": self.parent_edit.text().strip(),
            "pos_zup": tuple(sp.value() for sp in self.loc),
            "quat_zup": tuple(sp.value() for sp in self.rot),
        }


class AttachmentsPage(QWidget):
    """Right Editor — attachment detail only (list on left Scene tab)."""

    attachment_changed = Signal(int, dict)
    attachment_selected = Signal(int)
    apply_clicked = Signal()
    add_clicked = Signal()
    delete_clicked = Signal()
    save_clicked = Signal()
    save_as_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._recs: list[AttRecord] = []
        self.tip = QLabel("")
        self.tip.setObjectName("mutedTip")
        self.tip.setWordWrap(True)

        self.detail = AttachmentDetail()
        self.detail.setEnabled(False)

        from .icons import apply_icon

        self.apply_btn = QPushButton()
        apply_icon(self.apply_btn, "check", tip="Apply", kind="accent", size=20, square=36)
        self.add_btn = QPushButton()
        apply_icon(self.add_btn, "add", tip="Add", kind="icon", size=20, square=36)
        self.del_btn = QPushButton()
        apply_icon(self.del_btn, "delete", tip="Delete", kind="icon", size=20, square=36)
        # compat aliases — dock Save is primary
        self.save_btn = QPushButton()
        apply_icon(self.save_btn, "save", tip="Save", kind="accent", size=20, square=36)
        self.save_btn.hide()
        self.save_as_btn = QPushButton()
        apply_icon(self.save_as_btn, "save_as", tip="Save As…", kind="icon", size=20, square=36)
        self.save_as_btn.hide()

        row1 = QHBoxLayout()
        for b in (self.apply_btn, self.add_btn, self.del_btn):
            row1.addWidget(b)
        row1.addStretch(1)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 4)
        lay.setSpacing(8)
        lay.addWidget(self.tip)
        lay.addWidget(self.detail)
        lay.addLayout(row1)
        lay.addStretch(1)

        self.apply_btn.clicked.connect(self.apply_clicked.emit)
        self.add_btn.clicked.connect(self.add_clicked.emit)
        self.del_btn.clicked.connect(self.delete_clicked.emit)
        self.save_btn.clicked.connect(self.save_clicked.emit)
        self.save_as_btn.clicked.connect(self.save_as_clicked.emit)
        self.detail.changed.connect(self._on_detail)

    def clear(self) -> None:
        self._recs = []
        self.detail.clear()

    def set_attachments(self, recs: list[AttRecord]) -> None:
        keep = self.detail.index
        self._recs = list(recs)
        if self._recs:
            row = keep if 0 <= keep < len(self._recs) else 0
            self.select_row(row)
        else:
            self.detail.clear()

    def select_row(self, row: int) -> None:
        if row < 0 or row >= len(self._recs):
            self.detail.clear()
            return
        self.detail.load(row, self._recs[row])
        self.attachment_selected.emit(row)

    def _on_detail(self) -> None:
        idx = self.detail.index
        if idx < 0:
            return
        fields = self.detail.collect()
        if 0 <= idx < len(self._recs):
            rec = self._recs[idx]
            self._recs[idx] = AttRecord(
                name=fields.get("name") or rec.name,
                name_off=rec.name_off,
                floats_off=rec.floats_off,
                pos_zup=tuple(fields["pos_zup"]),  # type: ignore[arg-type]
                quat_zup=tuple(fields["quat_zup"]),  # type: ignore[arg-type]
            )
        self.attachment_changed.emit(idx, fields)

    def editor_at(self, index: int) -> AttachmentDetail | None:
        if self.detail.index == index:
            return self.detail
        return None

    def set_writable(self, writable: bool) -> None:
        for w in (self.apply_btn, self.add_btn, self.del_btn, self.save_btn, self.save_as_btn):
            w.setEnabled(writable)
