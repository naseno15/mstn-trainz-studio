"""Editor detail panels (list lives on left Scene tab — linked selection)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal, QEvent, QObject, QSize
from PySide6.QtGui import QColor, QFontMetrics
from PySide6.QtWidgets import (
    QAbstractSlider,
    QAbstractSpinBox,
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollBar,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .icons import apply_icon, glyph, icon_font

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
    """Wheel never changes editor inputs or dropdowns.

    Object filters run after the dock's scroll filter, so a tall page still
    scrolls. When the page cannot scroll, this eats the wheel instead of
    stepping a spin, combo, or slider.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        et = event.type()
        if et == QEvent.Type.ChildAdded:
            child = event.child()
            if isinstance(child, QWidget):
                guard_inputs(child)
            return False
        if et == QEvent.Type.Wheel and _wheel_changes_value(obj):
            event.ignore()
            return True
        return False


_NO_WHEEL = _NoWheelFilter()


def _wheel_changes_value(obj: object) -> bool:
    if isinstance(obj, QScrollBar):
        return False
    if isinstance(obj, (QAbstractSpinBox, QComboBox, QAbstractSlider)):
        return True
    if isinstance(obj, QLineEdit):
        parent = obj.parentWidget()
        return isinstance(parent, (QAbstractSpinBox, QComboBox))
    return False


def guard_inputs(root: QWidget) -> None:
    """Install the wheel block on this widget and everything under it."""
    pending = [root]
    while pending:
        widget = pending.pop()
        if widget.property("_mstnNoWheel"):
            continue
        widget.setProperty("_mstnNoWheel", True)
        widget.installEventFilter(_NO_WHEEL)
        if isinstance(widget, (QAbstractSpinBox, QComboBox)) or (
            isinstance(widget, QAbstractSlider) and not isinstance(widget, QScrollBar)
        ):
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        pending.extend(
            widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)
        )


# One control height for the right Editor so rows share a baseline.
_FIELD_H = 36
_LABEL_SAMPLES = (
    "txEnvIrradiance",
    "Material Color",
    "specPower",
    "Vertices",
    "Double Sided",
)


def _label_w() -> int:
    """Widest form label, measured once so every value column starts together.

    ponytail: width freezes at first Editor open. A later language switch with
    longer labels clips until restart. Upgrade: recompute on language_changed.
    """
    app = QApplication.instance()
    font = app.font() if app is not None else QLabel().font()
    fm = QFontMetrics(font)
    return max(fm.horizontalAdvance(s) for s in _LABEL_SAMPLES) + 12


def _uniform(widget: QWidget) -> QWidget:
    widget.setFixedHeight(_FIELD_H)
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    return widget


class _FillDouble(QDoubleSpinBox):
    """specPower. Hint stays narrow; the value column stretches it to the text fields."""

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(72, _FIELD_H)


class _FieldCombo(QComboBox):
    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(72, _FIELD_H)


def _float_spin(
    *,
    decimals: int = 6,
    lo: float = -1e6,
    hi: float = 1e6,
    width: int = 76,
    expand: bool = False,
) -> QDoubleSpinBox:
    sp = _FillDouble() if expand else QDoubleSpinBox()
    sp.setDecimals(decimals)
    sp.setRange(lo, hi)
    sp.setSingleStep(0.01)
    sp.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
    sp.setAlignment(Qt.AlignmentFlag.AlignRight)
    sp.setFixedHeight(_FIELD_H)
    sp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    if expand:
        sp.setMinimumWidth(72)
        sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    else:
        sp.setFixedWidth(width)
    return sp


class _EvenSpin(QSpinBox):
    """RGBA channel. Hint stays narrow; the row stretch makes the four equal."""

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(24, _FIELD_H)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(56, _FIELD_H)


def _int_spin(*, lo: int = 0, hi: int = 255) -> QSpinBox:
    sp = _EvenSpin()
    sp.setRange(lo, hi)
    # Four channels share one row — arrows would force the dock wide again.
    sp.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
    sp.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sp.setFixedHeight(_FIELD_H)
    sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    sp.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    sp.setObjectName("rgbaChannel")
    return sp


class _RgbaChannel(QWidget):
    """Letter sits beside the box. The spin text is the number only."""

    def __init__(self, letter: str, spin: QSpinBox) -> None:
        super().__init__()
        self.tag = QLabel(letter)
        self.tag.setObjectName("mutedTip")
        self.tag.setFixedSize(16, _FIELD_H)
        self.tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tag.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.tag.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lay.addWidget(self.tag)
        lay.addWidget(spin, 1)
        self.setFixedHeight(_FIELD_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, _FIELD_H)


def _section(title: str) -> QLabel:
    lab = QLabel(title)
    lab.setStyleSheet("font-weight: 600; padding-top: 8px;")
    return lab


def _form_label(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("mutedTip")
    lab.setFixedWidth(_label_w())
    lab.setFixedHeight(_FIELD_H)
    lab.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return lab


def _action_gap() -> QWidget:
    """Empty slot the same size as a row icon, so fields without one still align."""
    gap = QWidget()
    gap.setFixedSize(_FIELD_H, _FIELD_H)
    return gap


def _field_row(label: str, widget: QWidget, *, stretch: bool = True) -> QWidget:
    """Label | control | icon slot. Stretching controls share one width."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(_form_label(label))
    _uniform(widget)
    if stretch:
        widget.setMinimumWidth(48)
        widget.setMaximumWidth(16777215)
        lay.addWidget(widget, 1)
        lay.addWidget(_action_gap())
    else:
        lay.addWidget(widget, 0)
        lay.addStretch(1)
    return row


class ColorRow(QWidget):
    changed = Signal()

    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spins = [_int_spin() for _ in range(4)]
        self._channels = [_RgbaChannel(name, sp) for name, sp in zip("RGBA", self._spins)]
        for sp in self._spins:
            sp.valueChanged.connect(self._on_edit)
        self._swatch = QPushButton()
        self._swatch.setObjectName("colorSwatch")
        self._swatch.setFont(icon_font(18))
        self._swatch.setText(glyph("palette"))
        self._swatch.setFixedSize(_FIELD_H, _FIELD_H)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.setToolTip("Pick color")
        self._swatch.clicked.connect(self._pick)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_form_label(label))
        for ch in self._channels:
            lay.addWidget(ch, 1)
        lay.addWidget(self._swatch)
        self._block = False
        self.set_rgba01((0.8, 0.8, 0.8, 1.0))

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        # ponytail: four real channel mins plus the Noto label exceed the 360
        # meshes cap. The dock stretches this row; the hint only stops the window growing.
        return QSize(_label_w() + 88, _FIELD_H)

    def _on_edit(self, *_a) -> None:
        if self._block:
            return
        self._paint_swatch()
        self.changed.emit()

    def _paint_swatch(self) -> None:
        r, g, b, _a = (sp.value() for sp in self._spins)
        # Palette glyph stays readable on the swatch (white metal vs black emissive).
        ink = "#1a1a1a" if (0.2126 * r + 0.7152 * g + 0.0722 * b) > 150 else "#f4f4f5"
        self._swatch.setStyleSheet(
            "QPushButton {"
            f"background: rgb({r},{g},{b}); color: {ink};"
            "border: 1px solid rgba(255,255,255,0.28);"
            "border-radius: 8px; padding: 0;"
            'font-family: "Material Icons"; font-size: 18px;'
            "}"
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
        self._edit = _uniform(QLineEdit(value))
        self._edit.setReadOnly(readonly)
        self._edit.setMinimumWidth(48)
        if readonly:
            # $pbr-env* slots are studio maps — a lock, not a dead ellipsis button.
            self._btn = QLabel(glyph("lock"))
            self._btn.setObjectName("mutedTip")
            self._btn.setFont(icon_font(18))
            self._btn.setFixedSize(_FIELD_H, _FIELD_H)
            self._btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._btn.setToolTip("Built-in environment map")
            self._btn.setProperty("mi_name", "lock")
        else:
            self._btn = QPushButton()
            apply_icon(
                self._btn,
                "folder_open",
                tip="Browse texture file",
                kind="icon",
                size=18,
                square=_FIELD_H,
            )
            self._btn.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_form_label(key))
        lay.addWidget(self._edit, 1)
        lay.addWidget(self._btn)
        self._edit.editingFinished.connect(self._emit)

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
        self.type_combo = _FieldCombo()
        self.type_combo.addItems(list(_MAT_TYPES))
        self.double_sided = QCheckBox("Double Sided")
        self.double_sided.setFixedHeight(_FIELD_H)
        self.vfmt = QLineEdit()
        self.vfmt.setReadOnly(True)
        self.vfmt.setPlaceholderText("—")
        self.vfmt.setToolTip("Vertex format (read-only)")

        self.mat_color = ColorRow("Material Color")
        self.emis = ColorRow("matEmissive")
        self.spec = ColorRow("matSpecular")
        self.spec_power = _float_spin(expand=True)

        self._tex_host = QVBoxLayout()
        self._tex_rows: dict[str, TextureSlotRow] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)

        lay.addWidget(_field_row("Name", self.name_edit))
        lay.addWidget(_field_row("Type", self.type_combo))
        self.type_combo.setToolTip("Material Type")
        ds = QWidget()
        ds_lay = QHBoxLayout(ds)
        ds_lay.setContentsMargins(0, 0, 0, 0)
        ds_lay.setSpacing(8)
        ds_lay.addWidget(_form_label(""))
        ds_lay.addWidget(self.double_sided, 1)
        ds_lay.addWidget(_action_gap())
        lay.addWidget(ds)
        lay.addWidget(_field_row("Vertices", self.vfmt))

        lay.addWidget(_section("Textures"))
        lay.addLayout(self._tex_host)

        lay.addWidget(_section("Color"))
        for w in (self.mat_color, self.emis, self.spec):
            lay.addWidget(w)
        lay.addWidget(_field_row("specPower", self.spec_power))
        guard_inputs(self)

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
        # Preview-only flag. Do not emit material changed — that rewrites
        # the tzMF buffer and reloads the viewport (hang + camera reset).
        self.two_sided_changed.emit(on)

    def clear(self) -> None:
        self._index = -1
        self.setEnabled(False)

    def load(self, index: int, mat: MatBlock, *, two_sided: bool = False) -> None:
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

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)
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
            row, mat, two_sided=bool(self._two_sided.get(mat.name, False))
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

    def note_two_sided(self, names: list[str], on: bool) -> None:
        """Remember flags from a batch apply. Does not emit (caller updates preview)."""
        keys = {(n or "").strip().lower() for n in names if (n or "").strip()}
        for name in names:
            key = (name or "").strip()
            if key:
                self._two_sided[key] = on
        cur = (self.detail.name_edit.text() or "").strip().lower()
        if not cur or cur not in keys:
            return
        self.detail._block = True
        self.detail.double_sided.setChecked(on)
        self.detail._block = False


class AttachmentDetail(QWidget):
    changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._index = -1
        self._block = False

        self.name_edit = QLineEdit()
        self.parent_edit = QLineEdit()
        self.parent_edit.setPlaceholderText("(none)")
        self.loc = [_float_spin(expand=True) for _ in range(3)]
        self.rot = [_float_spin(expand=True) for _ in range(4)]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)

        lay.addWidget(_field_row("Name", self.name_edit))
        lay.addWidget(_field_row("Parent", self.parent_edit))

        lay.addWidget(_section("Location"))
        for lab, sp in zip(("X", "Y", "Z"), self.loc):
            lay.addWidget(_field_row(lab, sp))
            sp.valueChanged.connect(self._emit)

        lay.addWidget(_section("Rotation"))
        for lab, sp in zip(("X", "Y", "Z", "W"), self.rot):
            lay.addWidget(_field_row(lab, sp))
            sp.valueChanged.connect(self._emit)

        self.name_edit.editingFinished.connect(self._emit)
        guard_inputs(self)

    def _emit(self, *_a) -> None:
        if self._block or self._index < 0:
            return
        self.changed.emit()

    def clear(self) -> None:
        """No attachment selected — blank the fields. Stale text looked like a real a.*."""
        self._block = True
        self._index = -1
        self.name_edit.clear()
        self.parent_edit.clear()
        for sp in (*self.loc, *self.rot):
            sp.setValue(0.0)
        self._block = False
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
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(4)
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
