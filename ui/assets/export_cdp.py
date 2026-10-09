"""Assets Export page — paste KUIDs, write one CDP each or one combined CDP."""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...io.cdp_export import cdp_filename, export_cdp, export_succeeded
from ...io.trainz_install import find_trainzutil, probe_launcher
from ..code_edit import CodeEdit
from ..theme import app_font
from .kuid import extract_kuids

_SETTINGS = ("MSTN", "TrainzStudio")
_UTIL_KEY = "trainzutil/exe"
_ROLE = Qt.ItemDataRole.UserRole


class ExportCdpPage(QWidget):
    """Paste a KUID list. Commas, spaces, and newlines are all separators."""

    _note = Signal(str)
    _row = Signal(str, str)
    _idle = Signal()

    def __init__(self, *, on_status, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._on_status = on_status
        self._busy = False
        self._note.connect(self._on_status)
        self._row.connect(self._set_row)
        self._idle.connect(self._clear_busy)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        panel = QFrame()
        panel.setObjectName("glassPanel")
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(16, 16, 16, 16)
        pl.setSpacing(8)
        title = QLabel("Export")
        title.setObjectName("pageHead")
        title.setFont(app_font(16, QFont.Weight.Bold))
        pl.addWidget(title)
        tip = QLabel(
            "Paste KUIDs. Commas are optional. "
            "Export each writes one .cdp per checked asset. "
            "Export one CDP puts every checked asset in a single file. "
            "TrainzUtil createCDP — the Launcher must be open."
        )
        tip.setObjectName("pageBlurb")
        tip.setWordWrap(True)
        pl.addWidget(tip)
        self.paste = CodeEdit(syntax="trainzconfig")
        self.paste.setPlaceholderText(
            "<kuid:1125787:100058>, <kuid:1144998:100002>\n<kuid:972300:100075>"
        )
        pl.addWidget(self.paste, 1)
        self.count_lab = QLabel("0 KUIDs")
        self.count_lab.setObjectName("mutedTip")
        pl.addWidget(self.count_lab)
        self.kuid_list = QListWidget()
        self.kuid_list.setObjectName("exportKuidList")
        pl.addWidget(self.kuid_list, 2)
        lay.addWidget(panel, 1)

    def read_list(self) -> None:
        if self._busy:
            self._on_status("Export is still running")
            return
        kuids = [k.format() for k in extract_kuids(self.paste.toPlainText())]
        self.kuid_list.clear()
        for kuid in kuids:
            item = QListWidgetItem(kuid)
            item.setData(_ROLE, kuid)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self.kuid_list.addItem(item)
        n = len(kuids)
        self.count_lab.setText(f"{n} KUID{'s' if n != 1 else ''}")
        self._on_status(f"Read {n} KUID(s)" if n else "No KUID found")

    def select_all(self) -> None:
        if self._busy:
            return
        for i in range(self.kuid_list.count()):
            item = self.kuid_list.item(i)
            if item is not None:
                item.setCheckState(Qt.CheckState.Checked)

    def export_each(self) -> None:
        kuids = self._checked()
        if not self._ready(kuids):
            return
        folder = QFileDialog.getExistingDirectory(self, "Folder for one CDP per asset")
        if not folder:
            return
        dest = Path(folder)

        def work() -> None:
            exe = self._exe()
            if exe is None:
                return
            wrote = 0
            for kuid in kuids:
                path = dest / cdp_filename(kuid)
                self._note.emit(f"createCDP {path.name}")
                try:
                    text = export_cdp(exe, path, [kuid])
                except Exception as exc:  # noqa: BLE001 — show TrainzUtil/OS failure on the row
                    self._row.emit(kuid, str(exc))
                    continue
                if export_succeeded(text, path):
                    wrote += 1
                    mb = path.stat().st_size / (1024 * 1024)
                    self._row.emit(kuid, f"wrote {path.name} ({mb:.1f} MB)")
                else:
                    self._row.emit(kuid, _fail_line(text))
            self._note.emit(f"Exported {wrote}/{len(kuids)} CDP(s) → {dest}")
            self._idle.emit()

        self._start(work)

    def export_one(self) -> None:
        kuids = self._checked()
        if not self._ready(kuids):
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "One CDP for the checked assets", "assets.cdp", "CDP (*.cdp)"
        )
        if not path:
            return
        dest = Path(path)
        if dest.suffix.lower() != ".cdp":
            dest = dest.with_suffix(".cdp")

        def work() -> None:
            exe = self._exe()
            if exe is None:
                return
            self._note.emit(f"createCDP {dest.name} × {len(kuids)}")
            try:
                text = export_cdp(exe, dest, kuids, timeout=max(600, 120 * len(kuids)))
            except Exception as exc:  # noqa: BLE001
                self._note.emit(str(exc))
                self._idle.emit()
                return
            if export_succeeded(text, dest):
                mb = dest.stat().st_size / (1024 * 1024)
                self._note.emit(f"Wrote {dest.name} ({mb:.1f} MB, {len(kuids)} assets)")
                for kuid in kuids:
                    self._row.emit(kuid, f"in {dest.name}")
            else:
                self._note.emit(_fail_line(text))
            self._idle.emit()

        self._start(work)

    def _checked(self) -> list[str]:
        out: list[str] = []
        for i in range(self.kuid_list.count()):
            item = self.kuid_list.item(i)
            if item is None or item.checkState() != Qt.CheckState.Checked:
                continue
            kuid = item.data(_ROLE)
            if isinstance(kuid, str) and kuid:
                out.append(kuid)
        return out

    def _ready(self, kuids: list[str]) -> bool:
        if self._busy:
            self._on_status("Export is still running")
            return False
        if not kuids:
            self._on_status("Read a list and check at least one KUID")
            return False
        return True

    def _exe(self) -> Path | None:
        saved = str(QSettings(*_SETTINGS).value(_UTIL_KEY, "") or "")
        exe = find_trainzutil(saved)
        if exe is None:
            self._note.emit("TrainzUtil.exe not found — set it on the TrainzUtil page")
            self._idle.emit()
            return None
        ok, detail = probe_launcher(exe)
        if not ok:
            self._note.emit(detail)
            self._idle.emit()
            return None
        return exe

    def _start(self, work) -> None:
        self._busy = True
        threading.Thread(target=work, daemon=True, name="cdp-export").start()

    def _clear_busy(self) -> None:
        self._busy = False

    def _set_row(self, kuid: str, detail: str) -> None:
        for i in range(self.kuid_list.count()):
            item = self.kuid_list.item(i)
            if item is not None and item.data(_ROLE) == kuid:
                item.setText(f"{kuid}  —  {detail}")
                return


def _fail_line(text: str) -> str:
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for ln in reversed(lines):
        if "error" in ln.lower() or ln.startswith("-"):
            return ln[:180]
    return lines[-1][:180] if lines else "createCDP failed"
