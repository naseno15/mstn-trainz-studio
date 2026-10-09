"""TrainzUtil studio — QML installer. Launcher must be open before a database command."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Property,
    QSettings,
    Qt,
    QThread,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QVBoxLayout, QWidget

from ..io.cdp import format_bytes
from ..io.trainz_install import (
    InstallJob,
    LibraryAsset,
    category_is_enginespec,
    category_label,
    classify_trainz_line,
    classify_trainz_log,
    author_label,
    collect_script_files,
    config_credits,
    config_in_editing,
    create_cdp,
    decode_status,
    dependency_kuids,
    encrypt_scripts,
    describe_backup,
    find_asset_backups,
    find_trainzutil,
    installation_data_path,
    install_staged,
    launcher_blocked,
    load_installed_library,
    probe_launcher,
    index_content,
    read_asset_dates,
    scan_archive_meta,
    read_library_cache,
    run_trainzutil,
    scan_nested_zip,
    scan_path,
    source_row,
    stage_job,
    status_bits,
    status_rank,
    stream_trainzutil,
    task_outcome,
    tidy_trainzutil,
    trainz_data_dir,
    trainz_editing_dir,
    asset_browse_dir,
    asset_cover_path,
    archive_index,
    editing_index,
    write_library_cache,
)
from .icons import ensure_material_icons, glyph, icon_font


def _installation_folder(exe: Path | None) -> Path | None:
    if exe is None or not exe.is_file():
        return None
    try:
        return installation_data_path(exe)
    except (OSError, subprocess.TimeoutExpired):
        return None


def _fmt_mtime(stamp: float) -> str:
    if not stamp:
        return ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(stamp))
from .qml_host import _qml_ok, _quick

_QML = Path(__file__).resolve().parent / "qml" / "TrainzUtilPage.qml"
_SETTINGS = ("MSTN", "TrainzStudio")
_KEY = "trainzutil/exe"


def _cdp_stem(name: str, kuid: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in " ._-" else "_" for ch in name).strip(" ._")
    if not raw:
        raw = kuid.strip("<>").replace(":", "_")
    return raw[:80]


def _asset_count(job: InstallJob) -> int:
    match = re.search(r"(\d+)\s+assets?", job.detail)
    if match:
        return max(1, int(match.group(1)))
    return 1


class _Queue(QThread):
    """One dispatcher. Parallel cap and the gap are read live from the UI."""

    jobDone = Signal(str, bool, str)
    jobProgress = Signal(str, int, str)
    launcherLost = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._wake = threading.Condition()
        self._pending: list[InstallJob] = []
        self._stop = False
        self._pause = False
        self._active = 0
        self._last_start = 0.0
        self.parallel = 1
        self.gap = 3.0
        self.burst = False
        self.launcher_ok = False
        self.exe: Path | None = None

    def enqueue(self, jobs: list[InstallJob]) -> None:
        with self._wake:
            self._pending.extend(jobs)
            self._pause = False
            self._wake.notify_all()

    def pause(self) -> None:
        with self._wake:
            self._pending.clear()
            self._pause = True
            self._wake.notify_all()

    def shutdown(self) -> None:
        with self._wake:
            self._stop = True
            self._pending.clear()
            self._wake.notify_all()

    def _cap(self) -> int:
        if self.burst:
            return 32
        return max(1, min(10, int(self.parallel)))

    def run(self) -> None:
        while not self._stop:
            job: InstallJob | None = None
            with self._wake:
                if self._stop:
                    return
                cap = self._cap()
                ready = (
                    not self._pause
                    and self.launcher_ok
                    and self.exe is not None
                    and self._active < cap
                    and bool(self._pending)
                )
                if not ready:
                    self._wake.wait(timeout=0.4)
                    continue
                wait = 0.0
                if self._last_start and not self.burst and self.gap > 0:
                    wait = self.gap - (time.monotonic() - self._last_start)
                if wait > 0:
                    self._wake.wait(timeout=wait)
                    continue
                job = self._pending.pop(0)
                self._active += 1
                self._last_start = time.monotonic()
                exe = self.exe
            assert job is not None and exe is not None
            threading.Thread(
                target=self._run_one,
                args=(job, exe),
                daemon=True,
                name="trainzutil-install",
            ).start()

    def _run_one(self, job: InstallJob, exe: Path) -> None:
        ok = False
        msg = ""
        tmp = Path(tempfile.mkdtemp(prefix="mstn-tu-"))
        try:
            self.jobProgress.emit(job.id, 4, "Preparing")
            kind, staged = stage_job(job, tmp)
            count = _asset_count(job)

            def _pulse(pct: int, status: str) -> None:
                self.jobProgress.emit(job.id, int(pct), status)

            raw = install_staged(exe, kind, staged, _pulse, asset_count=count)
            if launcher_blocked(raw):
                with self._wake:
                    self.launcher_ok = False
                    self._pause = True
                    self._pending.insert(0, job)
                self.launcherLost.emit("Open the Trainz Launcher, then refresh")
                msg = "Paused — Launcher is not running"
            elif raw.lower().startswith("error") or "\nerror" in raw.lower():
                msg = raw[-400:]
            else:
                ok = True
                msg = raw[-400:] or "Installed"
                self.jobProgress.emit(job.id, 100, "Installed")
        except Exception as exc:
            msg = str(exc)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
            with self._wake:
                self._active = max(0, self._active - 1)
                self._wake.notify_all()
        self.jobDone.emit(job.id, ok, msg or "Install failed")


class LibraryModel(QAbstractListModel):
    """Installed CM assets. Faulty rows sort first. The view only builds visible rows."""

    picksChanged = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._all: list[LibraryAsset] = []
        self._rows: list[LibraryAsset] = []
        self._query = ""
        self._credits: dict[str, str] = {}
        self._authors: dict[str, str] = {}
        self._builds: dict[str, str] = {}
        self._disk_names: dict[str, str] = {}
        self._picked: set[str] = set()
        self._sizes: dict[str, str] = {}
        self._file_sizes: dict[str, int] = {}
        self._installed: dict[str, float] = {}
        self._modified: dict[str, float] = {}
        self._editing: dict[str, float] = {}
        self._sort_col = "modified"
        self._sort_desc = True
        self._drag_anchor = ""
        self._drag_on = True
        self._drag_snapshot: set[str] = set()
        self._drag_span: tuple[int, int] | None = None
        self._click_anchor = ""

    def roleNames(self) -> dict[int, bytes]:
        base = int(Qt.ItemDataRole.UserRole)
        return {
            base + 1: b"kuid",
            base + 2: b"assetName",
            base + 3: b"faulty",
            base + 4: b"category",
            base + 5: b"credits",
            base + 6: b"picked",
            base + 7: b"packed",
            base + 8: b"engineSpec",
            base + 9: b"statusText",
            base + 10: b"installed",
            base + 11: b"modified",
            base + 12: b"authorName",
            base + 13: b"buildVersion",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return len(self._rows)

    def data(self, index: QModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        base = int(Qt.ItemDataRole.UserRole)
        if role == base + 1:
            return row.kuid
        if role == base + 2:
            return row.name
        if role == base + 3:
            return row.faulty
        if role == base + 4:
            return category_label(row.category) or row.category
        if role == base + 5:
            return self._credits.get(row.kuid, "")
        if role == base + 6:
            return row.kuid in self._picked
        if role == base + 7:
            measured = self._sizes.get(row.kuid, "")
            if measured:
                return measured
            size = self._file_sizes.get(row.kuid, 0)
            return format_bytes(size) if size else ""
        if role == base + 8:
            return category_is_enginespec(row.category)
        if role == base + 9:
            return ", ".join(self._bits(row))
        if role == base + 10:
            return _fmt_mtime(self._installed_at(row.kuid))
        if role == base + 11:
            return _fmt_mtime(self._modified_at(row.kuid))
        if role == base + 12:
            return self._author(row.kuid)
        if role == base + 13:
            return self._build(row.kuid)
        return None

    def _credit_parts(self, kuid: str) -> list[str]:
        return [part.strip() for part in self._credits.get(kuid, "").split("·") if part.strip()]

    def _author(self, kuid: str) -> str:
        direct = author_label(self._authors.get(kuid, ""), self._builds.get(kuid, ""))
        if direct:
            return direct
        parts = self._credit_parts(kuid)
        if not parts:
            return ""
        return author_label(parts[0], self._builds.get(kuid, "") or (parts[-1] if len(parts) >= 3 else ""))

    def _build(self, kuid: str) -> str:
        direct = self._builds.get(kuid, "")
        if direct:
            return direct
        parts = self._credit_parts(kuid)
        return parts[-1] if len(parts) >= 3 else ""

    def _bits(self, row: LibraryAsset) -> list[str]:
        return status_bits(
            row.flags,
            open_for_edit=row.kuid in self._editing,
            locally_modified=row.kuid in self._modified,
        )

    def _installed_at(self, kuid: str) -> float:
        return self._installed.get(kuid, 0.0)

    def _modified_at(self, kuid: str) -> float:
        return max(self._modified.get(kuid, 0.0), self._editing.get(kuid, 0.0))

    def sort_mark(self) -> str:
        return self._sort_col + (":desc" if self._sort_desc else "")

    def set_sort(self, column: str) -> None:
        column = column.strip() or "name"
        if column == self._sort_col:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_col = column
            self._sort_desc = column in {"installed", "modified", "size"}
        self._apply()

    def set_dates(
        self,
        installed: dict[str, float],
        modified: dict[str, float],
        editing: dict[str, float],
        sizes: dict[str, int] | None = None,
    ) -> None:
        self._installed = installed
        self._modified = modified
        self._editing = editing
        if sizes is not None:
            self._file_sizes = {str(kuid): int(size) for kuid, size in sizes.items() if int(size) > 0}
        self._apply()

    def set_assets(self, rows: list[LibraryAsset]) -> None:
        self._credits = {}
        self._picked = set()
        self._sizes = {}
        self._all = [self._with_disk_name(row) for row in rows]
        self._apply()
        self.picksChanged.emit()

    def _with_disk_name(self, row: LibraryAsset) -> LibraryAsset:
        name = self._disk_names.get(row.kuid, "")
        if not name or name == row.name:
            return row
        return replace(row, name=name)

    def merge_names(self, names: dict[str, str]) -> None:
        """Real usernames from config files. TrainzUtil prints ``?`` for Japanese."""
        incoming = {str(kuid): name for kuid, name in names.items() if name}
        if not incoming:
            return
        self._disk_names.update(incoming)

        def apply(rows: list[LibraryAsset]) -> list[LibraryAsset]:
            out = rows
            for index, row in enumerate(rows):
                name = incoming.get(row.kuid, "")
                if not name or name == row.name:
                    continue
                if out is rows:
                    out = list(rows)
                out[index] = replace(row, name=name)
            return out

        self._all = apply(self._all)
        if self._query:
            self._apply()
            return
        self._rows = apply(self._rows)
        if not self._rows:
            return
        role = int(Qt.ItemDataRole.UserRole) + 2
        self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0), [role])

    def toggle_picked(self, kuid: str) -> None:
        if kuid in self._picked:
            self._picked.discard(kuid)
        else:
            self._picked.add(kuid)
        self._touch(kuid, 6)
        self.picksChanged.emit()

    def click_pick(self, kuid: str, *, shift: bool, ctrl: bool) -> None:
        """Windows list: click one, Shift through the last, Ctrl toggles."""
        rows = self._rows
        index_of = {row.kuid: index for index, row in enumerate(rows)}
        if kuid not in index_of:
            return
        index = index_of[kuid]
        anchor = self._click_anchor if self._click_anchor in index_of else kuid
        if shift:
            lo, hi = sorted((index_of[anchor], index))
            span = {row.kuid for row in rows[lo : hi + 1]}
            self._picked = set(self._picked) | span if ctrl else span
        else:
            self._click_anchor = kuid
            if ctrl:
                if kuid in self._picked:
                    self._picked.discard(kuid)
                else:
                    self._picked.add(kuid)
            else:
                self._picked = {kuid}
        self._emit_picks()

    def _emit_picks(self) -> None:
        if self._rows:
            role = int(Qt.ItemDataRole.UserRole) + 6
            self.dataChanged.emit(self.index(0, 0), self.index(len(self._rows) - 1, 0), [role])
        self.picksChanged.emit()

    def set_visible_picked(self, on: bool) -> None:
        visible = {row.kuid for row in self._rows}
        if on:
            self._picked.update(visible)
        else:
            self._picked.difference_update(visible)
        self._apply()
        self.picksChanged.emit()

    def selected_kuids(self) -> list[str]:
        order = [row.kuid for row in self._rows if row.kuid in self._picked]
        extra = [kuid for kuid in self._picked if kuid not in order]
        return order + extra

    def name_for(self, kuid: str) -> str:
        for row in self._all:
            if row.kuid == kuid:
                return row.name
        return kuid

    def flags_for(self, kuid: str) -> str:
        for row in self._all:
            if row.kuid == kuid:
                return row.flags
        return ""

    def tuner_kuid(self) -> str:
        """Selected engine spec, or the first selected row when none is tagged ESPC."""
        picked = [row for row in self._rows if row.kuid in self._picked]
        for row in picked:
            if category_is_enginespec(row.category):
                return row.kuid
        return picked[0].kuid if picked else ""

    def end_drag_pick(self) -> None:
        self._drag_anchor = ""
        self._drag_span = None

    def begin_drag_pick(self, kuid: str) -> None:
        """Hold-drag from a checkbox. The starting box sets check or clear for the whole swipe."""
        self._drag_snapshot = set(self._picked)
        self._drag_on = kuid not in self._picked
        self._drag_anchor = kuid
        self._click_anchor = kuid
        self._drag_span = None
        self._paint_drag(kuid)

    def drag_pick(self, kuid: str) -> None:
        if not self._drag_anchor:
            return
        self._paint_drag(kuid)

    def _paint_drag(self, kuid: str) -> None:
        rows = self._rows
        index_of = {row.kuid: index for index, row in enumerate(rows)}
        if self._drag_anchor not in index_of or kuid not in index_of:
            return
        lo, hi = sorted((index_of[self._drag_anchor], index_of[kuid]))
        previous = self._drag_span
        self._picked = set(self._drag_snapshot)
        for row in rows[lo : hi + 1]:
            if self._drag_on:
                self._picked.add(row.kuid)
            else:
                self._picked.discard(row.kuid)
        self._drag_span = (lo, hi)
        start, end = lo, hi
        if previous is not None:
            start = min(start, previous[0])
            end = max(end, previous[1])
        role = int(Qt.ItemDataRole.UserRole) + 6
        self.dataChanged.emit(self.index(start, 0), self.index(end, 0), [role])
        self.picksChanged.emit()

    def packed_label(self, kuid: str) -> str:
        measured = self._sizes.get(kuid, "")
        if measured:
            return measured
        size = self._file_sizes.get(kuid, 0)
        return format_bytes(size) if size else ""

    def set_size(self, kuid: str, text: str) -> None:
        self._sizes[kuid] = text
        self._touch(kuid, 7)

    def _touch(self, kuid: str, role_offset: int) -> None:
        role = int(Qt.ItemDataRole.UserRole) + role_offset
        for index, row in enumerate(self._rows):
            if row.kuid == kuid:
                model_index = self.index(index, 0)
                self.dataChanged.emit(model_index, model_index, [role])
                return

    def merge_meta(self, authors: dict[str, str], builds: dict[str, str]) -> None:
        for kuid, author in authors.items():
            label = author_label(str(author), str(builds.get(kuid, "")))
            if label:
                self._authors[str(kuid)] = label
        for kuid, build in builds.items():
            if build:
                self._builds[str(kuid)] = str(build)
        if self._query:
            self._apply()
            return
        if not self._rows:
            return
        base = int(Qt.ItemDataRole.UserRole)
        self.dataChanged.emit(
            self.index(0, 0),
            self.index(len(self._rows) - 1, 0),
            [base + 12, base + 13],
        )

    def set_credits(self, kuid: str, text: str) -> None:
        self._credits[kuid] = text
        parts = self._credit_parts(kuid)
        build = parts[-1] if len(parts) >= 3 else self._builds.get(kuid, "")
        if len(parts) == 1 and not author_label(parts[0], build or parts[0]):
            build = parts[0]
        name = author_label(parts[0], build) if parts else ""
        if name:
            self._authors[kuid] = name
        elif kuid in self._authors and not author_label(self._authors[kuid], build):
            self._authors.pop(kuid, None)
        if len(parts) >= 3 or (len(parts) == 1 and not name):
            if build:
                self._builds[kuid] = build
        self._touch(kuid, 5)
        self._touch(kuid, 12)
        self._touch(kuid, 13)

    def set_query(self, query: str) -> None:
        self._query = query.strip().casefold()
        self._apply()

    def summary(self) -> str:
        shown = len(self._rows)
        faulty = sum(1 for row in self._rows if row.faulty)
        picked = len(self._picked)
        tail = f" · {picked} selected" if picked else ""
        if self._query:
            return f"{shown} match · {faulty} faulty{tail}"
        if not self._all:
            return "Installed assets from Content Manager"
        return f"{shown} installed · {faulty} faulty{tail}"

    def _apply(self) -> None:
        self.beginResetModel()
        if not self._query:
            rows = list(self._all)
        else:
            query = self._query
            rows = [
                row
                for row in self._all
                if self._matches(row, query)
            ]
        rows.sort(key=self._sort_value, reverse=self._sort_desc)
        self._rows = rows
        self.endResetModel()

    def _matches(self, row: LibraryAsset, query: str) -> bool:
        """Every word may sit anywhere in the name, KUID, category, author, or status."""
        hay = " ".join(
            (
                row.name,
                row.kuid,
                row.category,
                category_label(row.category),
                " ".join(self._bits(row)),
                self._credits.get(row.kuid, ""),
                self._author(row.kuid),
                self._build(row.kuid),
                _fmt_mtime(self._installed_at(row.kuid)),
                _fmt_mtime(self._modified_at(row.kuid)),
            )
        ).casefold()
        return all(word in hay for word in query.split() if word)

    def _sort_value(self, row: LibraryAsset) -> tuple:
        name = row.name.casefold()
        column = self._sort_col
        if column == "kuid":
            return (row.kuid.casefold(), name)
        if column == "category":
            return (category_label(row.category).casefold(), name)
        if column == "status":
            return (status_rank(self._bits(row)), name)
        if column == "installed":
            stamp = self._installed_at(row.kuid)
            return (stamp if stamp or self._sort_desc else 1e18, name)
        if column == "modified":
            stamp = self._modified_at(row.kuid)
            return (stamp if stamp or self._sort_desc else 1e18, name)
        if column == "size":
            stamp = float(self._file_sizes.get(row.kuid, 0))
            return (stamp if stamp or self._sort_desc else 1e18, name)
        if column == "author":
            return (self._author(row.kuid).casefold(), name)
        if column == "build":
            return (self._build(row.kuid).casefold(), name)
        if column == "type":
            return (category_label(row.category).casefold(), name)
        return (name, row.kuid)


class TrainzUtilBridge(QObject):
    changed = Signal()
    contentsReady = Signal("QVariantList")
    sourcesReady = Signal("QVariantList")
    backupsReady = Signal("QVariantList")
    scriptsReady = Signal("QVariantList")
    logLine = Signal(str)
    jobState = Signal(str, str)

    def __init__(self, host: TrainzUtilHost) -> None:
        super().__init__()
        self._host = host
        self._dark = True
        self._launcher_ok = False
        self._launcher_text = "Checking Launcher…"
        self._util_path = ""
        self._parallel = 1
        self._gap = 3
        self._burst = False
        self._sources: list[dict[str, str]] = []
        self._scripts: list[dict[str, str]] = []
        self._crumb = "Installed assets from Content Manager"
        self._status_text = ""
        self._page = "library"
        self._library_on = True
        self._library_user = False
        self._library_summary = "Installed assets from Content Manager"
        self._library = LibraryModel()
        self._library.modelReset.connect(self._on_library_reset)
        self._library.picksChanged.connect(self._on_library_picks)
        self._busy = False
        self._load_on = False
        self._load_detail = ""
        self._load_log = ""
        self._load_lines: list[str] = []
        self._report = ""
        self._report_on = False
        self._detail_on = False
        self._detail_kuid = ""
        self._detail_title = ""
        self._detail_body = ""
        self._detail_deps: list[dict[str, str]] = []
        self._detail_card: dict[str, str] = {}
        self._detail_status: list[str] = []
        self._detail_cards: list[dict[str, str]] = []
        self._cover_url = ""
        self._cover_busy = False
        self._task_summary = "Open, submit, or validate an asset"
        self._task_percent = 0
        self._task_busy = False
        self._backup_query = ""
        self._backup_summary = "Find backups for an asset"
        self._backup_pick = ""
        ensure_material_icons()
        font = icon_font(16)
        self._icon_font = font.family() if font is not None else ""
        from .. import PKG_ROOT

        font_path = PKG_ROOT / "assets" / "fonts" / "MaterialIcons-Regular.ttf"
        self._icon_url = QUrl.fromLocalFile(str(font_path)).toString() if font_path.is_file() else ""

    def _emit(self) -> None:
        self.changed.emit()

    def _get_dark(self) -> bool:
        return self._dark

    dark = Property(bool, _get_dark, notify=changed)

    def _get_launcher_ok(self) -> bool:
        return self._launcher_ok

    launcherOk = Property(bool, _get_launcher_ok, notify=changed)

    def _get_launcher_text(self) -> str:
        return self._launcher_text

    launcherText = Property(str, _get_launcher_text, notify=changed)

    def _get_util_path(self) -> str:
        return self._util_path

    utilPath = Property(str, _get_util_path, notify=changed)

    def _get_parallel(self) -> int:
        return self._parallel

    parallel = Property(int, _get_parallel, notify=changed)

    def _get_gap(self) -> int:
        return self._gap

    gap = Property(int, _get_gap, notify=changed)

    def _get_burst(self) -> bool:
        return self._burst

    burst = Property(bool, _get_burst, notify=changed)

    def _get_sources(self) -> list:
        return self._sources

    sources = Property("QVariantList", _get_sources, notify=changed)

    def _get_crumb(self) -> str:
        return self._crumb

    crumb = Property(str, _get_crumb, notify=changed)

    def _get_status_text(self) -> str:
        return self._status_text

    statusText = Property(str, _get_status_text, notify=changed)

    def _get_icon_font(self) -> str:
        return self._icon_font

    iconFont = Property(str, _get_icon_font, notify=changed)

    def _get_library_on(self) -> bool:
        return self._page == "library"

    libraryOn = Property(bool, _get_library_on, notify=changed)

    def _get_page(self) -> str:
        return self._page

    page = Property(str, _get_page, notify=changed)

    def set_page(self, page: str) -> None:
        if page not in ("library", "files", "install", "backups", "encrypt"):
            return
        if self._page == page:
            return
        self._page = page
        self._library_on = page == "library"
        if page == "library":
            self._crumb = self._library.summary()
            if not self._library.rowCount():
                self._host.load_library()
        if page == "backups":
            if not self._backup_query and self._detail_kuid:
                self._backup_query = self._detail_kuid
            self._publish_backups(self._backup_query)
            return
        self._emit()

    def _get_backup_query(self) -> str:
        return self._backup_query

    backupQuery = Property(str, _get_backup_query, notify=changed)

    def _get_backup_summary(self) -> str:
        return self._backup_summary

    backupSummary = Property(str, _get_backup_summary, notify=changed)

    def _get_backup_pick(self) -> str:
        return self._backup_pick

    backupPick = Property(str, _get_backup_pick, notify=changed)

    def _publish_backups(self, query: str) -> None:
        data = self._host.data_folder()
        needle = query.strip()
        if data is None and not self._host.data_ready:
            self._backup_summary = "Reading the Trainz data folder…"
            self.backupsReady.emit([])
            self._emit()
            return
        if data is None:
            self._backup_summary = "Trainz data folder was not found"
            self.backupsReady.emit([])
            self._emit()
            return
        root = data / "backups"
        if not root.is_dir():
            self._backup_summary = f"No backups folder · {root}"
            self.backupsReady.emit([])
            self._emit()
            return
        rows = find_asset_backups(data, needle)
        days = len({row.day_key for row in rows})
        shown = f"{len(rows)} backup" if len(rows) == 1 else f"{len(rows)} backups"
        when = f" · {days} days" if days else ""
        if rows:
            self._backup_summary = f"{shown}{when} · {root}"
        elif needle:
            self._backup_summary = f"No backups for {needle}"
        else:
            self._backup_summary = f"No backups · {root}"
        payload = [
            {
                "day": row.day,
                "dayKey": row.day_key,
                "mtime": row.mtime,
                "title": row.name,
                "kind": row.kind,
                "detail": " · ".join(
                    part
                    for part in (
                        row.kuid,
                        format_bytes(row.size) if row.size else "",
                        row.when,
                    )
                    if part
                ),
                "path": row.path,
            }
            for row in rows
        ]
        self.backupsReady.emit(payload)
        self._emit()

    def _get_library_summary(self) -> str:
        return self._library_summary

    def _get_sort_mark(self) -> str:
        return self._library.sort_mark()

    librarySummary = Property(str, _get_library_summary, notify=changed)
    sortMark = Property(str, _get_sort_mark, notify=changed)

    def _library_model(self) -> LibraryModel:
        return self._library

    libraryModel = Property(QObject, _library_model, constant=True)

    def _on_library_reset(self) -> None:
        self._library_summary = self._library.summary()
        if self._library_on:
            self._crumb = self._library_summary
        self._emit()

    def _on_library_picks(self) -> None:
        self._on_library_reset()
        if self._page == "library":
            self._host.sync_library_details()

    def _get_glyph_home(self) -> str:
        return glyph("home") or "H"

    glyphHome = Property(str, _get_glyph_home, notify=changed)

    def _glyph(self, name: str) -> str:
        return glyph(name) or ""

    glyphFolder = Property(str, lambda self: self._glyph("folder_open"), notify=changed)
    glyphRefresh = Property(str, lambda self: self._glyph("refresh"), notify=changed)
    glyphMesh = Property(str, lambda self: self._glyph("layers"), notify=changed)
    glyphSounds = Property(str, lambda self: self._glyph("graphic_eq"), notify=changed)
    glyphEngine = Property(str, lambda self: self._glyph("tune"), notify=changed)
    glyphAssets = Property(str, lambda self: self._glyph("inventory_2"), notify=changed)
    glyphSearch = Property(str, lambda self: self._glyph("search"), notify=changed)
    glyphHistory = Property(str, lambda self: self._glyph("history"), notify=changed)
    glyphEdit = Property(str, lambda self: self._glyph("edit"), notify=changed)
    glyphPublish = Property(str, lambda self: self._glyph("publish"), notify=changed)
    glyphCheck = Property(str, lambda self: self._glyph("fact_check"), notify=changed)
    glyphChevronLeft = Property(str, lambda self: self._glyph("chevron_left"), notify=changed)
    glyphChevronRight = Property(str, lambda self: self._glyph("chevron_right"), notify=changed)
    glyphClose = Property(str, lambda self: self._glyph("close"), notify=changed)
    glyphCopy = Property(str, lambda self: self._glyph("content_copy"), notify=changed)

    def _get_icon_url(self) -> str:
        return self._icon_url

    iconFontUrl = Property(str, _get_icon_url, notify=changed)

    def _get_busy(self) -> bool:
        return self._busy

    busy = Property(bool, _get_busy, notify=changed)

    def _get_report(self) -> str:
        return self._report

    reportText = Property(str, _get_report, notify=changed)

    def _get_report_on(self) -> bool:
        return self._report_on

    reportOn = Property(bool, _get_report_on, notify=changed)

    def _get_detail_on(self) -> bool:
        return self._detail_on

    detailOn = Property(bool, _get_detail_on, notify=changed)

    def _get_detail_kuid(self) -> str:
        return self._detail_kuid

    detailKuid = Property(str, _get_detail_kuid, notify=changed)

    def _get_detail_title(self) -> str:
        return self._detail_title

    detailTitle = Property(str, _get_detail_title, notify=changed)

    def _get_detail_body(self) -> str:
        return self._detail_body

    detailBody = Property(str, _get_detail_body, notify=changed)

    def _get_detail_deps(self) -> list:
        return self._detail_deps

    detailDeps = Property("QVariantList", _get_detail_deps, notify=changed)

    def _get_detail_card(self) -> dict:
        return self._detail_card

    detailCard = Property("QVariantMap", _get_detail_card, notify=changed)

    def _get_detail_status(self) -> list:
        return self._detail_status

    detailStatus = Property("QVariantList", _get_detail_status, notify=changed)

    def _get_detail_cards(self) -> list:
        return self._detail_cards

    detailCards = Property("QVariantList", _get_detail_cards, notify=changed)

    def _get_task_summary(self) -> str:
        return self._task_summary

    taskSummary = Property(str, _get_task_summary, notify=changed)

    def _get_task_percent(self) -> int:
        return self._task_percent

    taskPercent = Property(int, _get_task_percent, notify=changed)

    def _get_task_busy(self) -> bool:
        return self._task_busy

    taskBusy = Property(bool, _get_task_busy, notify=changed)

    tasksReady = Signal("QVariantList")

    def publish_tasks(self, rows: list, summary: str, percent: int, busy: bool) -> None:
        self._task_summary = summary
        self._task_percent = max(0, min(100, int(percent)))
        self._task_busy = busy
        self.tasksReady.emit(rows)
        self._emit()

    def set_detail(self, kuid: str, title: str, body: str, deps: list, card: dict | None = None) -> None:
        self._detail_on = True
        self._detail_kuid = kuid
        self._detail_title = title
        self._detail_body = body
        self._detail_deps = list(deps)
        incoming = card or {}
        self._detail_card = {
            "kuid": str(incoming.get("kuid", kuid)),
            "category": str(incoming.get("category", "")),
            "installed": str(incoming.get("installed", "")),
            "modified": str(incoming.get("modified", "")),
            "size": str(incoming.get("size", "")),
            "author": str(incoming.get("author", "")),
            "build": str(incoming.get("build", "")),
            "note": str(incoming.get("note", body)),
        }
        self._detail_status = [str(bit) for bit in incoming.get("status") or []]
        self._detail_cards = [self._card_row(self._detail_kuid, self._detail_title)]
        self._emit()

    def _card_row(self, kuid: str, title: str) -> dict[str, str]:
        card = self._detail_card
        return {
            "kuid": str(card.get("kuid", kuid)),
            "title": title,
            "category": str(card.get("category", "")),
            "statusText": " · ".join(self._detail_status),
            "build": str(card.get("build", "")),
            "modified": str(card.get("modified", "")),
            "size": str(card.get("size", "")),
            "author": str(card.get("author", "")),
            "note": str(card.get("note", "")),
        }

    def set_details(self, cards: list[dict[str, str]], focus: str, deps: list | None = None) -> None:
        """One sidebar card per selected asset. Dependencies belong to the focused card."""
        self._detail_cards = [dict(card) for card in cards]
        chosen = next((card for card in self._detail_cards if card["kuid"] == focus), None)
        if chosen is None:
            self.clear_detail()
            return
        same = self._detail_kuid == chosen["kuid"]
        self._detail_on = True
        self._detail_kuid = chosen["kuid"]
        self._detail_title = chosen["title"]
        self._detail_body = chosen["note"]
        if deps is not None:
            self._detail_deps = list(deps)
        elif not same:
            self._detail_deps = []
        self._detail_card = {
            "kuid": chosen["kuid"],
            "category": chosen["category"],
            "installed": "",
            "modified": chosen["modified"],
            "size": chosen["size"],
            "author": chosen["author"],
            "build": chosen["build"],
            "note": chosen["note"],
        }
        self._detail_status = [bit for bit in chosen["statusText"].split(" · ") if bit]
        self._emit()

    def clear_detail(self) -> None:
        self._detail_on = False
        self._detail_kuid = ""
        self._detail_title = ""
        self._detail_body = ""
        self._detail_deps = []
        self._detail_card = {}
        self._detail_status = []
        self._detail_cards = []
        self._emit()

    def set_cover(self, url: str, busy: bool) -> None:
        self._cover_url = url
        self._cover_busy = busy
        self._emit()

    def _get_cover_url(self) -> str:
        return self._cover_url

    coverUrl = Property(str, _get_cover_url, notify=changed)

    def _get_cover_busy(self) -> bool:
        return self._cover_busy

    coverBusy = Property(bool, _get_cover_busy, notify=changed)

    def set_detail_title(self, kuid: str, title: str) -> None:
        if not title:
            return
        changed = False
        cards: list[dict[str, str]] = []
        for card in self._detail_cards:
            if card["kuid"] == kuid and card["title"] != title:
                copied = dict(card)
                copied["title"] = title
                cards.append(copied)
                changed = True
            else:
                cards.append(card)
        if self._detail_kuid == kuid and title != self._detail_title:
            self._detail_title = title
            changed = True
        if not changed:
            return
        self._detail_cards = cards
        self._emit()

    def set_busy(self, on: bool) -> None:
        self._busy = on
        self._emit()

    def _get_load_on(self) -> bool:
        return self._load_on

    loadOn = Property(bool, _get_load_on, notify=changed)

    def _get_load_detail(self) -> str:
        return self._load_detail

    loadDetail = Property(str, _get_load_detail, notify=changed)

    def _get_load_log(self) -> str:
        return self._load_log

    loadLog = Property(str, _get_load_log, notify=changed)

    def show_load(self, detail: str, *, on: bool) -> None:
        detail = " ".join(str(detail).split())
        if detail and (not self._load_lines or self._load_lines[-1] != detail):
            self._load_lines.append(detail)
            self._load_lines = self._load_lines[-8:]
        self._load_on = on
        self._load_detail = detail
        self._load_log = "\n".join(self._load_lines[:-1])
        if not on:
            self._load_lines = []
            self._load_log = ""
            self._load_detail = ""
        self._emit()

    def show_report(self, text: str) -> None:
        self._report = text
        self._report_on = bool(text.strip())
        self._emit()

    def set_dark(self, dark: bool) -> None:
        self._dark = dark
        self._emit()

    def set_launcher(self, ok: bool, text: str) -> None:
        self._launcher_ok = ok
        self._launcher_text = text
        self._host.queue.launcher_ok = ok
        self._emit()

    def set_util_path(self, path: str) -> None:
        self._util_path = path
        self._emit()

    def note(self, text: str) -> None:
        self.logLine.emit(text)

    def replace_sources(self, rows: list[dict[str, str]]) -> None:
        self._sources = rows
        self.sourcesReady.emit(rows)
        self._emit()

    def patch_source(self, source_id: str, status: str, percent: int | None = None) -> None:
        rows: list[dict] = []
        for row in self._sources:
            copied = dict(row)
            if copied["sourceId"] == source_id:
                copied["status"] = status
                if percent is not None:
                    copied["percent"] = int(percent)
            rows.append(copied)
        self._sources = rows
        self.sourcesReady.emit(rows)
        self._emit()

    @Slot()
    def goHome(self) -> None:
        self._host.go_home()

    @Slot(str)
    def openStudio(self, name: str) -> None:
        if name == "home":
            self._host.go_home()
            return
        self._host.open_studio(name)

    @Slot()
    def closeReport(self) -> None:
        self._report_on = False
        self._emit()

    @Slot()
    def browseData(self) -> None:
        folder = self._host.data_folder()
        if folder is None:
            if self._host.data_ready:
                self.note("Trainz data folder was not found")
            else:
                self.note("Reading the Trainz data folder…")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    @Slot()
    def browseUtil(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._host,
            "Choose TrainzUtil.exe",
            self._host.browse_start(),
            "TrainzUtil (TrainzUtil.exe)",
        )
        if not path:
            return
        chosen = Path(path)
        if chosen.name.lower() != "trainzutil.exe":
            self.note("Choose the file named TrainzUtil.exe")
            return
        self._host.use_exe(chosen)

    @Slot()
    def refreshLauncher(self) -> None:
        self._host.refresh_launcher()

    @Slot()
    def addFiles(self) -> None:
        if self._page == "encrypt":
            self.addScripts()
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self._host,
            "Zip or CDP",
            str(Path.home()),
            "Trainz packages (*.zip *.cdp)",
        )
        if paths:
            self._host.add_paths([Path(p) for p in paths])

    @Slot()
    def addScripts(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self._host,
            "GameScript files",
            str(Path.home()),
            "GameScript (*.gs)",
        )
        if paths:
            self._host.add_script_paths([Path(p) for p in paths])

    @Slot("QVariantList")
    def dropUrls(self, urls: list) -> None:
        paths: list[Path] = []
        for raw in urls:
            text = str(raw)
            if text.startswith("file:"):
                local = QUrl(text).toLocalFile()
                if local:
                    paths.append(Path(local))
            elif text:
                paths.append(Path(text))
        if not paths:
            return
        scripts = [p for p in paths if p.is_dir() or p.suffix.lower() == ".gs"]
        packs = [p for p in paths if p not in scripts]
        if self._page == "encrypt" or (scripts and not packs):
            self._host.add_script_paths(paths if self._page == "encrypt" else scripts)
            return
        if packs:
            self._host.add_paths(packs)
        if scripts:
            self._host.add_script_paths(scripts)

    @Slot(str)
    def selectSource(self, source_id: str) -> None:
        self._host.show_source(source_id)

    @Slot(str)
    def removeSource(self, source_id: str) -> None:
        self._host.remove_source(source_id)

    @Slot()
    def clearSources(self) -> None:
        if self._page == "encrypt":
            self.clearScripts()
            return
        self._host.clear_sources()

    def publish_scripts(self, rows: list[dict[str, str]]) -> None:
        self._scripts = rows
        self.scriptsReady.emit(rows)
        self._emit()

    @Slot(str)
    def removeScript(self, script_id: str) -> None:
        self._scripts = [row for row in self._scripts if row["scriptId"] != script_id]
        self.scriptsReady.emit(self._scripts)
        self._emit()

    @Slot()
    def clearScripts(self) -> None:
        self._scripts = []
        self.scriptsReady.emit([])
        self._emit()

    @Slot()
    def encryptScripts(self) -> None:
        self._host.encrypt_queued()

    @Slot(str)
    def openEntry(self, job_id: str) -> None:
        self._host.open_entry(job_id)

    @Slot()
    def backContents(self) -> None:
        self._host.back_contents()

    @Slot("QVariantList")
    def installIds(self, ids: list) -> None:
        self._host.install_ids([str(i) for i in ids])

    @Slot()
    def installChecked(self) -> None:
        ids = [str(row["sourceId"]) for row in self._sources if row.get("checked")]
        self._host.install_sources(ids)

    @Slot(bool)
    def setSourcesChecked(self, on: bool) -> None:
        rows = []
        for row in self._sources:
            copied = dict(row)
            copied["checked"] = bool(on)
            rows.append(copied)
        self._sources = rows
        self.sourcesReady.emit(rows)
        self._emit()

    @Slot(str, bool)
    def setSourceChecked(self, source_id: str, on: bool) -> None:
        for row in self._sources:
            if row["sourceId"] == source_id:
                row["checked"] = bool(on)
        self.sourcesReady.emit(self._sources)
        self._emit()

    @Slot()
    def stopQueue(self) -> None:
        self._host.queue.pause()
        self.note("Queue stopped — installs already running will finish")

    @Slot(int)
    def setParallel(self, value: int) -> None:
        self._parallel = max(1, min(10, int(value)))
        self._host.queue.parallel = self._parallel
        self._emit()

    @Slot(int)
    def setGap(self, value: int) -> None:
        self._gap = max(0, min(30, int(value)))
        self._host.queue.gap = float(self._gap)
        self._emit()

    @Slot(bool)
    def setBurst(self, on: bool) -> None:
        self._burst = bool(on)
        self._host.queue.burst = self._burst
        self._emit()

    @Slot(str)
    def showPage(self, page: str) -> None:
        self._library_user = True
        self.set_page(page)

    @Slot(str)
    def findBackups(self, text: str) -> None:
        self._backup_query = text
        if self._page != "backups":
            self.set_page("backups")
            return
        self._publish_backups(text)

    @Slot()
    def openPackages(self) -> None:
        self._host.open_packages()

    @Slot()
    def findSelectedBackups(self) -> None:
        self._backup_query = self._detail_kuid
        if self._page != "backups":
            self.set_page("backups")
            return
        self._publish_backups(self._backup_query)

    @Slot(str)
    def showBackup(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            self.note("That backup is no longer there")
            return
        try:
            info = describe_backup(target)
        except OSError as exc:
            self.note(str(exc))
            return
        self._backup_pick = str(target)
        self.set_detail(
            info["kuid"],
            info["title"],
            info["note"],
            [],
            {
                "kuid": info["kuid"],
                "category": info["category"],
                "installed": info["installed"],
                "modified": info["modified"],
                "size": info["size"],
                "author": info["author"],
                "build": info["build"],
                "note": info["note"],
                "status": [info["status"], info["installed"]],
            },
        )

    @Slot(str)
    def openBackup(self, path: str) -> None:
        target = Path(path)
        if not target.exists():
            self.note("That backup is no longer there")
            return
        if target.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", f"/select,{target}"])
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.parent)))

    @Slot(bool)
    def showLibrary(self, on: bool) -> None:
        self._library_user = True
        self.set_page("library" if on else "files")

    @Slot()
    def toggleLibrary(self) -> None:
        self._library_user = True
        self.set_page("files" if self._page == "library" else "library")

    @Slot()
    def scanLibrary(self) -> None:
        self._page = "library"
        self._library_on = True
        self._crumb = "Reading Content Manager…"
        self._emit()
        self._host.load_library()

    @Slot(str)
    def filterLibrary(self, text: str) -> None:
        self._library.set_query(text)

    @Slot(str)
    def pickLibrary(self, kuid: str) -> None:
        self._host.describe_asset(kuid)

    @Slot(str)
    def togglePicked(self, kuid: str) -> None:
        self._library.toggle_picked(kuid)
        self._on_library_reset()

    @Slot(str)
    def beginDragPick(self, kuid: str) -> None:
        self._library.begin_drag_pick(kuid)
        self._on_library_reset()

    @Slot(str)
    def dragPick(self, kuid: str) -> None:
        self._library.drag_pick(kuid)
        self._on_library_reset()

    @Slot()
    def endDragPick(self) -> None:
        self._library.end_drag_pick()
        self._on_library_reset()

    @Slot(str)
    def focusAsset(self, kuid: str) -> None:
        self._host.focus_asset(kuid)

    @Slot(str, int)
    def clickPick(self, kuid: str, modifiers: int) -> None:
        flags = int(modifiers)
        shift = bool(flags & Qt.KeyboardModifier.ShiftModifier.value)
        ctrl = bool(flags & Qt.KeyboardModifier.ControlModifier.value)
        self._library.click_pick(kuid, shift=shift, ctrl=ctrl)
        self._host.focus_asset(kuid)

    @Slot(str)
    def copyText(self, text: str) -> None:
        body = str(text or "")
        if not body.strip():
            self.note("Nothing to copy")
            return
        QApplication.clipboard().setText(body)
        self.note("Copied")

    @Slot(str, result=int)
    def rowIndex(self, kuid: str) -> int:
        for index, row in enumerate(self._library._rows):
            if row.kuid == kuid:
                return index
        return -1

    @Slot(str, result=bool)
    def libraryHas(self, kuid: str) -> bool:
        return any(row.kuid == kuid for row in self._library._all)

    @Slot(bool)
    def pickVisible(self, on: bool) -> None:
        self._library.set_visible_picked(on)

    @Slot(str, result="QVariantList")
    def classifyLog(self, text: str) -> list:
        return classify_trainz_log(text)

    @Slot()
    def openForEditing(self) -> None:
        self._host.run_asset_action("edit")

    @Slot()
    def submitEdit(self) -> None:
        self._host.run_asset_action("commit")

    @Slot()
    def validateAssets(self) -> None:
        self._host.run_asset_action("validate")

    @Slot()
    def inspectStatus(self) -> None:
        self._host.inspect_library("status")

    @Slot()
    def inspectErrors(self) -> None:
        self._host.inspect_library("validate")

    @Slot()
    def inspectDepends(self) -> None:
        self._host.inspect_library("dependencies")

    @Slot()
    def measurePacked(self) -> None:
        self._host.measure_selected()

    @Slot()
    def exportTogether(self) -> None:
        self._host.export_selected(separate=False)

    @Slot()
    def exportEach(self) -> None:
        self._host.export_selected(separate=True)

    @Slot(str)
    def sortLibrary(self, column: str) -> None:
        self._library.set_sort(column)
        self._on_library_reset()

    @Slot(str)
    def openEngine(self, kuid: str) -> None:
        self._host.open_in_tuner(kuid)

    @Slot(str)
    def lookupKuid(self, kuid: str) -> None:
        self._host.lookup_kuid(kuid.strip())

    def show_contents(self, crumb: str, jobs: list[InstallJob]) -> None:
        self._crumb = crumb
        self.contentsReady.emit([job.row() for job in jobs])
        self._emit()

    def set_status_text(self, text: str) -> None:
        self._status_text = text
        self._emit()


class TrainzUtilHost(QWidget):
    probeDone = Signal(bool, str)
    scanDone = Signal(str, object)
    scanFailed = Signal(str, str)
    statusDone = Signal(str)
    libraryDone = Signal(object, str)
    creditsDone = Signal(str, str)
    reportDone = Signal(str)
    sizesDone = Signal(object)
    tunerReady = Signal(str, str, str)
    datesDone = Signal(object)
    metaDone = Signal(int, object, object, object, bool)
    fillEvent = Signal(int, str, str)
    reportView = Signal(str)
    detailReady = Signal(str, str, str, object)
    encryptDone = Signal(object)
    dataDirDone = Signal(int, str)
    taskStep = Signal(int, object, str, int, bool)
    coverReady = Signal(int, str, str)
    packagesReady = Signal(str)

    def __init__(
        self,
        *,
        on_home,
        on_studio=None,
        theme_mode: str = "dark",
        start_probe: bool = True,
        shell: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("trainzUtilPage")
        self._on_home = on_home
        self._on_studio = on_studio
        self._theme = theme_mode if theme_mode in ("dark", "light") else "dark"
        self._auto_library = start_probe
        self._library_loading = False
        self._fill_gen = 0
        self._fill_library = False
        self._fill_dates = False
        self._fill_meta = False
        self._focus_kuid = ""
        self._detail_from_picks = False
        self._dep_cache: dict[str, tuple[str, list]] = {}
        self._detail_cap_noted = False
        self._jobs: dict[str, InstallJob] = {}
        self._source_paths: dict[str, Path] = {}
        self._encrypting = False
        self._view: list[tuple[str, tuple[str, ...]]] = []
        self._selected = ""
        self._job_pct: dict[str, int] = {}
        self._job_status: dict[str, str] = {}
        self._data_dir: Path | None = None
        self._data_ready = False
        self._data_gen = 0
        self._cover_gen = 0
        self._archive_index: dict[str, Path] | None = None
        self._editing_index: dict[str, Path] | None = None
        self._archive_root: Path | None = None
        self._task_gen = 0
        self._task_busy = False
        self._batch_rows: list[dict[str, object]] = []
        self._install_rows: dict[str, dict[str, object]] = {}
        self._install_order: list[str] = []
        self._progress_summary = "Open, submit, or validate an asset"
        self._progress_percent = 0
        from ..util.preload import boot_log

        boot_log("TrainzUtil · TrainzUtilBridge")
        self._bridge = TrainzUtilBridge(self)
        self._bridge.set_dark(self._theme != "light")
        boot_log("TrainzUtil · install queue")
        self.queue = _Queue()
        self.queue.jobDone.connect(self._on_job_done)
        self.queue.jobProgress.connect(self._on_job_progress)
        self.queue.launcherLost.connect(self._on_launcher_lost)
        self.probeDone.connect(self._on_probe)
        self.scanDone.connect(self._scan_done)
        self.encryptDone.connect(self._on_encrypt)
        self.scanFailed.connect(self._scan_failed)
        self.statusDone.connect(self._bridge.set_status_text)
        self.libraryDone.connect(self._on_library)
        self.creditsDone.connect(self._on_credits)
        self.reportDone.connect(self._on_report)
        self.reportView.connect(self._bridge.show_report)
        self.detailReady.connect(self._on_detail)
        self.sizesDone.connect(self._on_sizes)
        self.datesDone.connect(self._on_dates)
        self.dataDirDone.connect(self._on_data_dir)
        self.taskStep.connect(self._on_task_step)
        self.coverReady.connect(self._on_cover)
        self.packagesReady.connect(self._on_packages_ready)
        self.metaDone.connect(self._on_meta)
        self.fillEvent.connect(self._on_fill_event)
        self.queue.start()
        self._shell = shell
        self._surface_ready = False
        self._ok = False
        self._view_quick = None
        if shell:
            return
        self._mount_surface(start_probe)

    def finish_surface(self) -> None:
        """QML page and the library probe, once. The bridge and queue already exist."""
        if self._surface_ready:
            return
        self._shell = False
        self._mount_surface(self._auto_library)

    def _mount_surface(self, start_probe: bool) -> None:
        from ..util.preload import boot_log
        from .assets.sidebar import _logo_pixmap

        boot_log("TrainzUtil · TrainzUtilPage.qml")
        self._view_quick = _quick(
            _QML, self._bridge, logo=lambda mode: _logo_pixmap(160, mode=mode)
        )
        from PySide6.QtQuick import QQuickWindow

        window = self._view_quick.quickWindow()
        if window is not None:
            window.setTextRenderType(QQuickWindow.TextRenderType.NativeTextRendering)
        lay = self.layout()
        if lay is None:
            lay = QVBoxLayout(self)
            lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view_quick)
        self._ok = _qml_ok(self._view_quick)
        self._surface_ready = True
        boot_log("TrainzUtil · find TrainzUtil.exe")
        saved = str(QSettings(*_SETTINGS).value(_KEY, "") or "")
        found = find_trainzutil(saved)
        if found is not None:
            boot_log("TrainzUtil · library cache")
            self._show_cached_library(found)
        if found is not None and start_probe:
            self.use_exe(found, save=False)
        elif found is not None:
            self.queue.exe = found
            self._bridge.set_util_path(str(found))
            self._bridge.set_launcher(False, "Open the Trainz Launcher first")
            self._begin_data_lookup()
        else:
            self._data_ready = True
            self._bridge.set_util_path("TrainzUtil.exe not found — press Browse")
            self._bridge.set_launcher(False, "Not found — press Browse")
        if start_probe:
            boot_log("TrainzUtil · probe launcher")
            QTimer.singleShot(0, self.refresh_launcher)

    @property
    def ok(self) -> bool:
        return self._ok

    def go_home(self) -> None:
        self._on_home()

    def open_studio(self, name: str) -> None:
        if self._on_studio is not None:
            self._on_studio(name)

    def open_packages(self) -> None:
        """Open Packages now, then fill the finder once the asset folder is known.

        The page switch waits one turn so this click can finish before the
        TrainzUtil page is swapped out.
        """
        kuid = (self._focus_kuid or self._bridge._detail_kuid).strip()
        QTimer.singleShot(0, lambda: self._open_packages_soon(kuid))

    def _open_packages_soon(self, kuid: str) -> None:
        if self._on_studio is not None:
            self._on_studio("packages")
        data = self.data_folder()
        if not kuid or data is None:
            self.packagesReady.emit("")
            return
        archives = self._archive_index if self._archive_root == data else None

        def work() -> None:
            path = None
            try:
                index = archives if archives is not None else archive_index(data)
                if archives is None:
                    self._archive_index = index
                    self._archive_root = data
                path = asset_browse_dir(data, kuid, index)
            except (OSError, ValueError):
                path = None
            self.packagesReady.emit("" if path is None else str(path))

        threading.Thread(target=work, daemon=True, name="trainzutil-packages").start()

    def _on_packages_ready(self, folder: str) -> None:
        if not folder:
            self._bridge.set_status_text("No files for this asset")

    def set_theme(self, mode: str) -> None:
        mode = mode if mode in ("dark", "light") else "dark"
        self._theme = mode
        self._bridge.set_dark(mode != "light")
        self._view_quick.setClearColor(QColor("#12161c" if mode != "light" else "#eef1f6"))

    def browse_start(self) -> str:
        exe = self.queue.exe
        if exe is not None and exe.is_file():
            return str(exe.parent)
        return str(Path.home())

    def data_folder(self) -> Path | None:
        if self._data_dir is not None and self._data_dir.is_dir():
            return self._data_dir
        if self._data_ready:
            return trainz_data_dir()
        return None

    @property
    def data_ready(self) -> bool:
        return self._data_ready

    def _on_data_dir(self, gen: int, path: str) -> None:
        if gen != self._data_gen:
            return
        folder = Path(path) if path else None
        self._data_dir = folder if folder is not None and folder.is_dir() else None
        self._data_ready = True
        self._archive_index = None
        self._editing_index = None
        self._archive_root = None
        if self._focus_kuid:
            self._load_cover(self._focus_kuid)
        if self._bridge._page == "backups":
            self._bridge._publish_backups(self._bridge._backup_query)

    def _begin_data_lookup(self) -> None:
        exe = self.queue.exe
        gen = self._data_gen

        def work() -> None:
            root = _installation_folder(exe)
            self.dataDirDone.emit(gen, "" if root is None else str(root))

        threading.Thread(target=work, daemon=True, name="trainzutil-datapath").start()

    def use_exe(self, path: Path, *, save: bool = True) -> None:
        path = Path(path)
        if not path.is_file():
            self._bridge.note(f"Not a file: {path}")
            return
        self.queue.exe = path
        self._data_gen += 1
        self._data_dir = None
        self._data_ready = False
        self._bridge.set_util_path(str(path))
        if save:
            QSettings(*_SETTINGS).setValue(_KEY, str(path))
        self._show_cached_library(path)
        self._scan_dates()
        self.refresh_launcher()

    def _show_cached_library(self, exe: Path) -> None:
        rows = read_library_cache(exe)
        if not rows:
            return
        self._bridge._library.set_assets(rows)
        if not self._bridge._library_user and self._bridge._page != "install":
            self._bridge.set_page("library")
        faulty = sum(1 for row in rows if row.faulty)
        self._bridge.note(f"{len(rows)} installed · {faulty} faulty · cached")

    def _on_probe(self, ok: bool, text: str) -> None:
        self._bridge.set_launcher(ok, text)
        if ok and self._auto_library:
            self.load_library(quiet=self._bridge._library.rowCount() > 0)

    def refresh_launcher(self) -> None:
        exe = self.queue.exe
        if exe is None or not exe.is_file():
            self._bridge.set_launcher(False, "Not found — press Browse")
            return
        self._bridge.set_launcher(False, "Checking Launcher…")

        def work() -> None:
            ok, text = probe_launcher(exe)
            self.probeDone.emit(ok, text)

        threading.Thread(target=work, daemon=True, name="trainzutil-probe").start()

    def add_script_paths(self, paths: list[Path]) -> None:
        found = collect_script_files(paths)
        if not found:
            self._bridge.note("No .gs files in that drop")
            return
        rows = list(self._bridge._scripts)
        for path in found:
            script_id = str(path)
            if any(row["scriptId"] == script_id for row in rows):
                continue
            rows.append(
                {
                    "scriptId": script_id,
                    "name": path.name,
                    "folder": str(path.parent),
                    "status": "Ready",
                    "tone": "wait",
                }
            )
        self._bridge.publish_scripts(rows)
        self._bridge._library_user = True
        self._bridge.set_page("encrypt")

    def encrypt_queued(self) -> None:
        if self._encrypting:
            return
        exe = self.queue.exe
        if exe is None or not exe.is_file():
            self._bridge.note("Pick TrainzUtil.exe with Browse")
            return
        rows = [dict(row) for row in self._bridge._scripts]
        if not rows:
            self._bridge.note("Drop .gs files first")
            return
        self._encrypting = True
        for row in rows:
            row["status"] = "Encrypting…"
            row["tone"] = "run"
        self._bridge.publish_scripts(rows)
        sources = [Path(row["scriptId"]) for row in rows]

        def work() -> None:
            try:
                results = encrypt_scripts(exe, sources)
            except Exception as exc:
                results = [(src, False, str(exc)) for src in sources]
            self.encryptDone.emit(results)

        threading.Thread(target=work, daemon=True, name="trainzutil-encrypt").start()

    def _on_encrypt(self, results: list) -> None:
        by = {str(path): (ok, msg) for path, ok, msg in results}
        rows: list[dict[str, str]] = []
        done = 0
        for row in self._bridge._scripts:
            copied = dict(row)
            hit = by.get(copied["scriptId"])
            if hit is not None:
                ok, msg = hit
                copied["tone"] = "ok" if ok else "bad"
                copied["status"] = msg
                if ok:
                    done += 1
            rows.append(copied)
        self._encrypting = False
        self._bridge.publish_scripts(rows)
        failed = sum(1 for _path, ok, _msg in results if not ok)
        if failed:
            self._bridge.note(f"{done} encrypted · {failed} failed")
        else:
            self._bridge.note(f"{done} encrypted beside the .gs files")

    def add_paths(self, paths: list[Path]) -> None:
        rows = list(self._bridge._sources)
        fresh: list[tuple[str, Path]] = []
        for path in paths:
            path = Path(path)
            if not path.is_file():
                continue
            if path.suffix.lower() not in (".zip", ".cdp"):
                self._bridge.note(f"Skipped {path.name}")
                continue
            source_id = path.resolve().as_posix()
            if any(row["sourceId"] == source_id for row in rows):
                continue
            self._source_paths[source_id] = path
            row = source_row(path, path.suffix.lower().lstrip("."), source_id)
            row["status"] = "Reading…"
            rows.append(row)
            fresh.append((source_id, path))
        if not fresh:
            return
        self._bridge.replace_sources(rows)
        self._bridge._library_user = True
        self._bridge.set_page("install")
        for source_id, path in fresh:
            threading.Thread(
                target=self._scan_source,
                args=(source_id, path),
                daemon=True,
                name="trainzutil-scan",
            ).start()

    def _scan_source(self, source_id: str, path: Path) -> None:
        try:
            scanned = scan_path(path)
        except Exception as exc:
            self.scanFailed.emit(source_id, str(exc))
            return
        self.scanDone.emit(source_id, scanned)

    def _scan_failed(self, source_id: str, message: str) -> None:
        self._bridge.patch_source(source_id, "Unreadable")
        self._bridge.note(message)

    def _scan_done(self, source_id: str, scanned) -> None:
        if source_id not in self._source_paths:
            return
        for job in scanned.jobs:
            self._jobs[job.id] = job
        n = sum(1 for job in scanned.jobs if job.can_install)
        self._bridge.patch_source(source_id, f"{n} to install")
        if self._selected in ("", source_id):
            self.show_source(source_id)

    def show_source(self, source_id: str) -> None:
        path = self._source_paths.get(source_id)
        if path is None:
            return
        self._selected = source_id
        self._view = [(source_id, ())]
        jobs = [job for job in self._jobs.values() if job.source == path and not job.chain]
        # Jobs scanned from the root have an empty chain. Nested opens add chain.
        if path.suffix.lower() == ".cdp":
            jobs = [job for job in self._jobs.values() if job.source == path]
        self._bridge.show_contents(path.name, jobs)

    def open_entry(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job is None or job.kind != "zip-nested":
            return
        try:
            found = scan_nested_zip(job.source, job.chain, job.member)
        except Exception as exc:
            self._bridge.note(str(exc))
            return
        for item in found:
            self._jobs[item.id] = item
        chain = job.chain + (job.member,)
        self._view.append((job.source.as_posix(), chain))
        self._bridge.show_contents(job.label, found)

    def back_contents(self) -> None:
        if len(self._view) <= 1:
            if self._selected:
                self.show_source(self._selected)
            return
        self._view.pop()
        source_id, chain = self._view[-1]
        path = self._source_paths.get(source_id) or self._source_paths.get(self._selected)
        if path is None:
            return
        if not chain:
            self.show_source(self._selected or source_id)
            return
        jobs = [
            job
            for job in self._jobs.values()
            if job.source == path and job.chain == chain
        ]
        label = Path(chain[-1]).name
        self._bridge.show_contents(label, jobs)

    def remove_source(self, source_id: str) -> None:
        path = self._source_paths.pop(source_id, None)
        self._jobs = {
            key: job
            for key, job in self._jobs.items()
            if path is None or job.source != path
        }
        rows = [row for row in self._bridge._sources if row["sourceId"] != source_id]
        self._bridge.replace_sources(rows)
        if self._selected == source_id:
            self._selected = ""
            self._view = []
            self._bridge.show_contents("Drop a zip or CDP", [])

    def clear_sources(self) -> None:
        self._jobs.clear()
        self._source_paths.clear()
        self._selected = ""
        self._view = []
        self._bridge.replace_sources([])
        self._bridge.show_contents("Drop a zip or CDP", [])

    def _package_jobs(self, path: Path) -> list[InstallJob]:
        """What one dropped file installs. A CDP is one package, not each asset inside it."""
        jobs = [job for job in self._jobs.values() if job.source == path and not job.chain]
        if path.suffix.lower() == ".cdp":
            return [job for job in jobs if job.kind == "cdp"]
        return [job for job in jobs if job.can_install and job.kind in ("zip-cdp", "zip-folder")]

    def install_sources(self, ids: list[str]) -> None:
        if not self._bridge._launcher_ok or self.queue.exe is None:
            self._bridge.note(self._bridge._launcher_text or "Open the Trainz Launcher first")
            return
        jobs: list[InstallJob] = []
        for source_id in ids:
            path = self._source_paths.get(source_id)
            if path is None:
                continue
            picked = self._package_jobs(path)
            if not picked:
                self._bridge.patch_source(source_id, "Nothing to install", 0)
                continue
            for job in picked:
                self._job_pct[job.id] = 0
                self._job_status[job.id] = "Queued"
                self._note_install(job, "Queued", 0, "Queued")
            jobs.extend(picked)
            self._bridge.patch_source(source_id, "Queued", 0)
        if not jobs:
            self._bridge.note("Nothing ready to install")
            return
        self._bridge.note(f"Queued {len(jobs)}")
        self.queue.enqueue(jobs)

    def _rollup(self, path: Path) -> None:
        source_id = path.resolve().as_posix()
        jobs = self._package_jobs(path)
        if not jobs:
            return
        avg = int(round(sum(self._job_pct.get(job.id, 0) for job in jobs) / len(jobs)))
        done = [job for job in jobs if self._job_status.get(job.id) == "Installed"]
        failed = [job for job in jobs if str(self._job_status.get(job.id, "")).startswith("Failed") or self._job_status.get(job.id) == "Paused"]
        rest = [job for job in jobs if job not in done and job not in failed]
        active = next((job for job in rest if self._job_pct.get(job.id, 0) > 0), None)
        if active is None and rest:
            active = rest[0]
        if active is not None:
            status = self._job_status.get(active.id, "Installing")
            if len(jobs) > 1:
                status = f"{len(done) + (0 if active in done else 1)}/{len(jobs)}  {status}"
        elif failed:
            status = "Failed" if len(failed) == len(jobs) else f"Failed {len(failed)} of {len(jobs)}"
        else:
            status = "Installed"
            avg = 100
        self._bridge.patch_source(source_id, status, max(0, min(100, avg)))

    def _on_job_progress(self, job_id: str, pct: int, status: str) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        self._job_pct[job_id] = max(0, min(100, int(pct)))
        self._job_status[job_id] = status
        self._note_install(job, "Running" if int(pct) < 100 else "Installed", int(pct), status)
        self._rollup(job.source)

    def install_ids(self, ids: list[str]) -> None:
        if not self._bridge._launcher_ok or self.queue.exe is None:
            self._bridge.note(self._bridge._launcher_text or "Open the Trainz Launcher first")
            return
        jobs = [self._jobs[i] for i in ids if i in self._jobs and self._jobs[i].can_install]
        if not jobs:
            self._bridge.note("Select something to install")
            return
        for job in jobs:
            self._job_pct[job.id] = 0
            self._job_status[job.id] = "Queued"
            self._note_install(job, "Queued", 0, "Queued")
            self._bridge.jobState.emit(job.id, "Queued")
        self._bridge.note(f"Queued {len(jobs)}")
        self.queue.enqueue(jobs)

    def load_library(self, *, quiet: bool = False) -> None:
        exe = self.queue.exe
        if exe is None or not exe.is_file():
            self._bridge.note("Pick TrainzUtil.exe with Browse")
            return
        if not self._bridge.launcherOk:
            self._bridge.note(self._bridge.launcherText or "Open the Trainz Launcher first")
            return
        if self._library_loading:
            return
        self._library_loading = True
        self._fill_library = True
        if quiet:
            self._publish_load(
                "Refreshing the installed list from Content Manager. "
                "The table already shows the last copy. Dates, sizes, and author names are still loading."
            )
        else:
            self._publish_load(
                "Asking Content Manager for the installed asset list. "
                "The table stays on the cached copy, or empty, until TrainzUtil answers."
            )

        def work() -> None:
            rows, err = load_installed_library(exe)
            if not err and rows:
                try:
                    write_library_cache(exe, rows)
                except OSError:
                    pass
            self.libraryDone.emit(rows, err)

        threading.Thread(target=work, daemon=True, name="trainzutil-library").start()
        self._scan_dates()

    def _publish_load(self, text: str) -> None:
        waiting = self._fill_library or self._fill_dates or self._fill_meta
        self._bridge.set_busy(waiting)
        self._bridge.show_load(text, on=waiting)
        if text:
            self._bridge.note(text)

    def _on_fill_event(self, gen: int, text: str, kind: str) -> None:
        if gen != self._fill_gen:
            return
        if kind == "dates":
            self._fill_dates = False
        elif kind == "meta":
            self._fill_meta = False
        elif kind == "fail":
            self._fill_dates = False
            self._fill_meta = False
        self._publish_load(text)

    def _scan_dates(self) -> None:
        exe = self.queue.exe
        gen = self._data_gen
        self._fill_gen += 1
        fill_gen = self._fill_gen
        self._fill_dates = True
        self._fill_meta = True
        if self._fill_library:
            self._publish_load(
                "Content Manager is still listing installed assets. "
                "This walk is also reading dates, file sizes, and author names from the content folders."
            )
        else:
            self._publish_load(
                "Looking up the Trainz content folder, then walking original and local for dates and file sizes."
            )

        def work() -> None:
            root = _installation_folder(exe)
            self.dataDirDone.emit(gen, "" if root is None else str(root))
            roots = [root] if root is not None else None
            self.fillEvent.emit(
                fill_gen,
                "Walking original and local archives for install time, modified time, and file size.",
                "note",
            )
            try:
                listing = index_content(roots)
                payload = read_asset_dates(roots, listing)
            except OSError as exc:
                self.reportDone.emit(str(exc))
                self.fillEvent.emit(fill_gen, str(exc), "fail")
                return
            stamped = dict(payload)
            stamped["gen"] = fill_gen
            self.datesDone.emit(stamped)
            try:
                scan_archive_meta(
                    roots,
                    on_status=lambda text, token=fill_gen: self.fillEvent.emit(token, text, "note"),
                    on_batch=lambda authors, builds, names, finished, token=fill_gen: self.metaDone.emit(
                        token, authors, builds, names, finished
                    ),
                    index=listing,
                )
            except Exception as exc:
                self.fillEvent.emit(fill_gen, str(exc), "fail")

        threading.Thread(target=work, daemon=True, name="trainzutil-dates").start()

    def _on_dates(self, payload: object) -> None:
        if not isinstance(payload, dict):
            return
        if int(payload.get("gen") or 0) != self._fill_gen:
            return
        self._fill_dates = False
        installed = payload.get("installed") or {}
        modified = payload.get("modified") or {}
        editing = payload.get("editing") or {}
        sizes = payload.get("sizes") or {}
        self._bridge._library.set_dates(
            {str(k): float(v) for k, v in installed.items()},
            {str(k): float(v) for k, v in modified.items()},
            {str(k): float(v) for k, v in editing.items()},
            {str(k): int(v) for k, v in sizes.items()},
        )
        extra = ""
        if self._fill_meta:
            extra = " Author names are still being read from each archive, so that column keeps filling."
        elif self._fill_library:
            extra = " The installed list from Content Manager has not arrived yet."
        self._publish_load(
            f"Dates and file sizes · {len(installed)} installed · {len(modified)} modified · {len(sizes)} sized · {len(editing)} open for edit.{extra}"
        )

    def _on_meta(self, gen: int, authors: object, builds: object, names: object, finished: bool) -> None:
        if gen != self._fill_gen:
            return
        author_map = authors if isinstance(authors, dict) else {}
        build_map = builds if isinstance(builds, dict) else {}
        name_map = names if isinstance(names, dict) else {}
        if author_map or build_map:
            self._bridge._library.merge_meta(
                {str(k): str(v) for k, v in author_map.items()},
                {str(k): str(v) for k, v in build_map.items()},
            )
        if name_map:
            cleaned = {str(k): str(v) for k, v in name_map.items() if v}
            self._bridge._library.merge_names(cleaned)
            title = cleaned.get(self._focus_kuid, "")
            if title:
                self._bridge.set_detail_title(self._focus_kuid, title)
        if finished:
            self._fill_meta = False
            count = len(self._bridge._library._authors)
            extra = ""
            if self._fill_library:
                extra = " Content Manager is still sending the installed list."
            self._publish_load(f"Author and build from archives · {count}.{extra}")

    def _on_library(self, rows: object, err: str) -> None:
        self._library_loading = False
        self._fill_library = False
        assets = list(rows) if isinstance(rows, list) else []
        if err:
            self._bridge.set_status_text(err)
            self._publish_load(err)
            return
        self._bridge._library.set_assets(assets)
        if assets and not self._bridge._library_user and self._bridge._page != "install":
            self._bridge.set_page("library")
        faulty = sum(1 for row in assets if row.faulty)
        extra = ""
        if self._fill_dates or self._fill_meta:
            extra = " Dates, sizes, and author names are still loading from the content folders."
        self._publish_load(f"{len(assets)} installed · {faulty} faulty.{extra}")

    def _on_credits(self, kuid: str, text: str) -> None:
        self._bridge._library.set_credits(kuid, text)

    def describe_asset(self, kuid: str) -> None:
        exe = self.queue.exe
        if not kuid:
            return
        if exe is None or not self._bridge._launcher_ok:
            self._bridge.set_status_text(self._bridge._launcher_text)
            return
        token = kuid if kuid.startswith("<") else f"<{kuid}>"

        def work() -> None:
            try:
                config = run_trainzutil(exe, ["printconfig", token], timeout=40)
                status = run_trainzutil(exe, ["status", token], timeout=40)
            except Exception as exc:
                self.statusDone.emit(str(exc))
                return
            if launcher_blocked(config) or launcher_blocked(status):
                self.statusDone.emit("Open the Trainz Launcher first")
                return
            credits = config_credits(config)
            self.creditsDone.emit(kuid, credits)
            state = decode_status(status)
            self.statusDone.emit(" · ".join(bit for bit in (credits, state) if bit))

        threading.Thread(target=work, daemon=True, name="trainzutil-credits").start()

    def _asset_card(self, kuid: str, note: str) -> dict[str, object]:
        lib = self._bridge._library
        row = next((item for item in lib._all if item.kuid == kuid), None)
        category = ""
        status: list[str] = []
        if row is not None:
            category = category_label(row.category) or row.category
            status = lib._bits(row)
        return {
            "kuid": kuid,
            "category": category,
            "status": status,
            "installed": _fmt_mtime(lib._installed_at(kuid)),
            "modified": _fmt_mtime(lib._modified_at(kuid)),
            "size": lib.packed_label(kuid),
            "author": lib._author(kuid),
            "build": lib._build(kuid),
            "note": note,
        }

    def _load_cover(self, kuid: str) -> None:
        self._cover_gen += 1
        gen = self._cover_gen
        self._bridge.set_cover("", True)
        data = self._data_dir

        def work() -> None:
            path = None
            if data is not None and data.is_dir():
                if self._archive_index is None or self._archive_root != data:
                    self._archive_index = archive_index(data)
                    self._editing_index = editing_index(data / "editing")
                    self._archive_root = data
                path = asset_cover_path(data, kuid, self._archive_index, self._editing_index)
            url = QUrl.fromLocalFile(str(path)).toString() if path is not None else ""
            self.coverReady.emit(gen, kuid, url)

        threading.Thread(target=work, daemon=True, name="trainzutil-cover").start()

    def _on_cover(self, gen: int, kuid: str, url: str) -> None:
        if gen != self._cover_gen or kuid != self._focus_kuid:
            return
        self._bridge.set_cover(url, False)

    def _can_query(self) -> bool:
        exe = self.queue.exe
        return exe is not None and exe.is_file() and self._bridge._launcher_ok

    def _view_row(self, kuid: str, note: str) -> dict[str, str]:
        lib = self._bridge._library
        row = next((item for item in lib._all if item.kuid == kuid), None)
        title = row.name if row is not None else lib.name_for(kuid)
        card = self._asset_card(kuid, note)
        status = card.get("status") or []
        return {
            "kuid": kuid,
            "title": title,
            "category": str(card.get("category") or ""),
            "statusText": " · ".join(str(bit) for bit in status),
            "build": str(card.get("build") or ""),
            "modified": str(card.get("modified") or ""),
            "size": str(card.get("size") or ""),
            "author": str(card.get("author") or ""),
            "note": note,
        }

    def sync_library_details(self) -> None:
        """Sidebar follows every ticked library row."""
        if self._bridge._page != "library":
            return
        kuids = self._bridge._library.selected_kuids()
        if not kuids:
            if self._detail_from_picks:
                self._detail_from_picks = False
                self._focus_kuid = ""
                self._bridge.clear_detail()
            return
        self._detail_from_picks = True
        focus = self._focus_kuid if self._focus_kuid in kuids else kuids[0]
        self._publish_cards(kuids, focus, fetch=focus not in self._dep_cache)

    def focus_asset(self, kuid: str) -> None:
        """Open one row, or focus it inside the ticked set."""
        picked = self._bridge._library.selected_kuids()
        if len(picked) > 1:
            if kuid not in picked:
                return
            self._detail_from_picks = True
            self._publish_cards(picked, kuid, fetch=kuid not in self._dep_cache)
            return
        self._detail_from_picks = kuid in picked
        self._publish_cards([kuid], kuid, fetch=kuid not in self._dep_cache)

    def _publish_cards(self, kuids: list[str], focus: str, fetch: bool) -> None:
        shown = kuids[:40]
        if len(kuids) > 40:
            if not self._detail_cap_noted:
                self._bridge.note("Showing the first 40")
                self._detail_cap_noted = True
        else:
            self._detail_cap_noted = False
        cards: list[dict[str, str]] = []
        for kuid in shown:
            if kuid == focus and fetch:
                note = (
                    "Reading dependencies…"
                    if self._can_query()
                    else "Open the Trainz Launcher to list dependencies"
                )
            else:
                cached = self._dep_cache.get(kuid)
                note = cached[0] if cached else ""
            cards.append(self._view_row(kuid, note))
        deps = [] if fetch or focus not in self._dep_cache else list(self._dep_cache[focus][1])
        if focus != self._focus_kuid:
            self._load_cover(focus)
        self._focus_kuid = focus
        self._bridge.set_details(cards, focus, deps)
        if fetch and self._can_query():
            self._fetch_deps(focus)

    def _fetch_deps(self, kuid: str) -> None:
        lib = self._bridge._library
        row = next((item for item in lib._all if item.kuid == kuid), None)
        title = row.name if row is not None else lib.name_for(kuid)
        exe = self.queue.exe
        assert exe is not None

        def work() -> None:
            try:
                raw = run_trainzutil(exe, ["list-dependencies", "direct", kuid], timeout=90)
                config = run_trainzutil(exe, ["printconfig", kuid], timeout=40)
            except Exception as exc:
                self.detailReady.emit(kuid, title, str(exc), [])
                return
            if launcher_blocked(raw) or launcher_blocked(config):
                self.detailReady.emit(kuid, title, "Open the Trainz Launcher first", [])
                return
            credits = config_credits(config)
            if credits:
                self.creditsDone.emit(kuid, credits)
            deps = []
            for dep in dependency_kuids(tidy_trainzutil(raw), skip=kuid):
                deps.append({"name": lib.name_for(dep), "kuid": dep})
            note = "" if deps else "No direct dependencies"
            self.detailReady.emit(kuid, title, note, deps)

        threading.Thread(target=work, daemon=True, name="trainzutil-detail").start()

    def _on_detail(self, kuid: str, title: str, body: str, deps: object) -> None:
        if kuid != self._focus_kuid:
            return
        rows = list(deps) if isinstance(deps, list) else []
        self._dep_cache[kuid] = (body, rows)
        if self._detail_from_picks:
            kuids = self._bridge._library.selected_kuids()
            if kuid not in kuids:
                kuids = [kuid, *kuids]
        else:
            kuids = [kuid]
        self._publish_cards(kuids or [kuid], kuid, fetch=False)

    def _append_log(self, row: dict[str, object], text: str) -> None:
        chunk = text.strip()
        if not chunk:
            return
        current = str(row.get("log") or "")
        if current.splitlines()[-1:] == [chunk]:
            return
        row["log"] = f"{current}\n{chunk}".strip() if current else chunk
        row["detail"] = chunk.splitlines()[-1][:180]

    def _show_progress(self, summary: str | None = None, percent: int | None = None) -> None:
        if summary is not None:
            self._progress_summary = summary
        if percent is not None:
            self._progress_percent = percent
        rows = list(self._batch_rows)
        rows.extend(self._install_rows[key] for key in self._install_order if key in self._install_rows)
        self._bridge.publish_tasks(rows, self._progress_summary, self._progress_percent, self._task_busy)

    def _note_install(self, job: InstallJob, state: str, percent: int, line: str) -> None:
        key = f"install:{job.id}"
        row = self._install_rows.get(key)
        if row is None:
            row = {
                "taskId": key,
                "name": job.label,
                "action": "Install",
                "state": state,
                "detail": "",
                "log": "",
                "percent": percent,
            }
            self._install_rows[key] = row
            self._install_order.append(key)
        row["state"] = state
        row["percent"] = max(0, min(100, int(percent)))
        self._append_log(row, line)
        if not self._task_busy:
            done = sum(1 for item in self._install_rows.values() if item["state"] in ("Installed", "Failed", "Paused"))
            total = len(self._install_rows)
            self._show_progress(f"Install · {done} of {total}", int((done / total) * 100) if total else 0)
        else:
            self._show_progress()

    def _on_task_step(self, gen: int, rows: object, summary: str, percent: int, busy: bool) -> None:
        if gen != self._task_gen:
            return
        self._task_busy = busy
        self._batch_rows = list(rows) if isinstance(rows, list) else []
        self._show_progress(summary, percent)

    def _action_kuids(self) -> list[str]:
        kuids = self._bridge._library.selected_kuids()
        if kuids:
            return kuids
        if self._bridge._detail_on and self._bridge._detail_kuid:
            return [self._bridge._detail_kuid]
        self._bridge.note("Select an asset")
        return []

    def run_asset_action(self, action: str) -> None:
        commands = {
            "edit": ("edit", "Open for editing"),
            "commit": ("commit", "Submit edit"),
            "validate": ("validate", "Validate"),
        }
        if action not in commands or self._task_busy or not self._ready():
            if self._task_busy:
                self._bridge.note("Wait for the current task")
            return
        kuids = self._action_kuids()
        if not kuids:
            return
        if len(kuids) > 40:
            kuids = kuids[:40]
            self._bridge.note("Running the first 40")
        exe = self.queue.exe
        assert exe is not None
        command, label = commands[action]
        self._task_gen += 1
        gen = self._task_gen
        self._task_busy = True
        rows = [
            {
                "taskId": f"{action}:{kuid}",
                "kuid": kuid,
                "name": self._bridge._library.name_for(kuid),
                "action": label,
                "state": "Queued",
                "detail": "Queued",
                "log": "Queued",
                "percent": 0,
            }
            for kuid in kuids
        ]
        self._batch_rows = rows
        self._task_busy = True
        self._show_progress(f"{label} · 0 of {len(rows)}", 0)

        def work() -> None:
            failed = 0
            finished = 0
            total = len(rows)
            for index, row in enumerate(rows):
                if gen != self._task_gen:
                    return
                row["state"] = "Running"
                row["percent"] = 40
                row["detail"] = "Running…"
                row["log"] = "Running…"
                done_pct = int(((finished + 0.4) / total) * 100)
                collected: list[str] = []

                def on_line(text: str, row: dict[str, object] = row) -> None:
                    if gen != self._task_gen:
                        return
                    collected.append(text)
                    _tone, shown = classify_trainz_line(text)
                    row["log"] = "\n".join(collected)
                    if shown:
                        row["detail"] = shown[:180]
                    row["percent"] = min(90, 45 + len(collected))
                    self.taskStep.emit(
                        gen,
                        [dict(item) for item in rows],
                        f"{label} · {index + 1} of {total}",
                        int(((finished + 0.4) / total) * 100),
                        True,
                    )

                self.taskStep.emit(
                    gen,
                    [dict(item) for item in rows],
                    f"{label} · {index + 1} of {total}",
                    done_pct,
                    True,
                )
                try:
                    raw = stream_trainzutil(exe, [command, str(row["kuid"])], on_line, timeout=180)
                except Exception as exc:
                    ok, detail = False, str(exc)
                    row["log"] = str(exc)
                else:
                    ok, detail = task_outcome(raw)
                    if raw:
                        row["log"] = raw
                row["state"] = "Done" if ok else "Failed"
                row["detail"] = detail
                row["percent"] = 100
                finished += 1
                if not ok:
                    failed += 1
                if not ok and detail == "Open the Trainz Launcher first":
                    for rest in rows[index + 1 :]:
                        rest["state"] = "Stopped"
                    self.taskStep.emit(
                        gen,
                        [dict(item) for item in rows],
                        detail,
                        int((finished / total) * 100),
                        False,
                    )
                    return
            summary = f"{label} · {total - failed} done"
            if failed:
                summary += f" · {failed} failed"
            self.taskStep.emit(gen, [dict(item) for item in rows], summary, 100, False)

        threading.Thread(target=work, daemon=True, name="trainzutil-task").start()

    def _selected_kuids(self) -> list[str]:
        kuids = self._bridge._library.selected_kuids()
        if not kuids:
            self._bridge.note("Select at least one asset")
        return kuids

    def _ready(self) -> bool:
        if self.queue.exe is None or not self.queue.exe.is_file():
            self._bridge.note("Pick TrainzUtil.exe with Browse")
            return False
        if not self._bridge._launcher_ok:
            self._bridge.note(self._bridge.launcherText or "Open the Trainz Launcher first")
            return False
        return True

    def inspect_library(self, kind: str) -> None:
        kuids = self._selected_kuids()
        if not kuids or not self._ready():
            return
        exe = self.queue.exe
        assert exe is not None
        if len(kuids) > 30:
            kuids = kuids[:30]
            self._bridge.note("Showing the first 30 selected")

        def work() -> None:
            chunks: list[str] = []
            for kuid in kuids:
                name = self._bridge._library.name_for(kuid)
                cmd = ["validate", kuid] if kind == "validate" else (
                    ["list-dependencies", "direct", kuid] if kind == "dependencies" else ["status", kuid]
                )
                try:
                    raw = run_trainzutil(exe, cmd, timeout=90)
                except Exception as exc:
                    chunks.append(f"{name}: {exc}")
                    continue
                if launcher_blocked(raw):
                    chunks.append("Open the Trainz Launcher first")
                    break
                body = tidy_trainzutil(raw)
                if kind == "status":
                    config = run_trainzutil(exe, ["printconfig", kuid], timeout=40)
                    credits = config_credits(config)
                    self.creditsDone.emit(kuid, credits)
                    validated = run_trainzutil(exe, ["validate", kuid], timeout=90)
                    errors = tidy_trainzutil(validated)
                    body = " · ".join(bit for bit in (credits, decode_status(raw)) if bit)
                    if errors:
                        body = f"{body}\n{errors}"
                chunks.append(f"{name}  {kuid}\n{body}")
            self.reportView.emit("\n\n".join(chunks))

        threading.Thread(target=work, daemon=True, name="trainzutil-inspect").start()

    def measure_selected(self) -> None:
        kuids = self._selected_kuids()
        if not kuids or not self._ready():
            return
        exe = self.queue.exe
        assert exe is not None
        each = len(kuids) <= 15

        def work() -> None:
            folder = Path(tempfile.mkdtemp(prefix="mstn-tu-size-"))
            try:
                if not each:
                    dest = folder / "selection.cdp"
                    raw = create_cdp(exe, dest, kuids)
                    size = dest.stat().st_size if dest.is_file() else 0
                    self.reportDone.emit(
                        tidy_trainzutil(raw) + f"\nPacked size of {len(kuids)} assets: {format_bytes(size)}"
                    )
                    return
                total = 0
                lines = []
                sizes: dict[str, str] = {}
                for kuid in kuids:
                    dest = folder / "one.cdp"
                    if dest.exists():
                        dest.unlink()
                    raw = create_cdp(exe, dest, [kuid])
                    if launcher_blocked(raw):
                        lines.append("Open the Trainz Launcher first")
                        break
                    size = dest.stat().st_size if dest.is_file() else 0
                    total += size
                    label = format_bytes(size)
                    sizes[kuid] = label
                    lines.append(f"{self._bridge._library.name_for(kuid)}  {label}")
                self.sizesDone.emit(sizes)
                lines.append(f"Total packed {format_bytes(total)}")
                self.reportDone.emit("\n".join(lines))
            except Exception as exc:
                self.reportDone.emit(str(exc))
            finally:
                shutil.rmtree(folder, ignore_errors=True)

        self._bridge.note("Measuring packed size…")
        threading.Thread(target=work, daemon=True, name="trainzutil-size").start()

    def export_selected(self, *, separate: bool) -> None:
        from PySide6.QtWidgets import QFileDialog

        kuids = self._selected_kuids()
        if not kuids or not self._ready():
            return
        exe = self.queue.exe
        assert exe is not None
        if separate:
            folder = QFileDialog.getExistingDirectory(self, "Folder for one CDP per asset", str(Path.home()))
            if not folder:
                return
            dest_dir = Path(folder)
        else:
            path, _ = QFileDialog.getSaveFileName(
                self, "Export CDP", str(Path.home() / "selection.cdp"), "Content package (*.cdp)"
            )
            if not path:
                return
            dest = Path(path)
            if dest.suffix.lower() != ".cdp":
                dest = dest.with_suffix(".cdp")

        def work() -> None:
            try:
                if separate:
                    wrote = 0
                    for kuid in kuids:
                        stem = _cdp_stem(self._bridge._library.name_for(kuid), kuid)
                        out = dest_dir / f"{stem}.cdp"
                        raw = create_cdp(exe, out, [kuid])
                        if launcher_blocked(raw):
                            self.reportDone.emit("Open the Trainz Launcher first")
                            return
                        wrote += 1
                    self.reportDone.emit(f"Exported {wrote} CDP files to {dest_dir}")
                    return
                raw = create_cdp(exe, dest, kuids)
                self.reportDone.emit(tidy_trainzutil(raw) + f"\nExported {dest}")
            except Exception as exc:
                self.reportDone.emit(str(exc))

        self._bridge.note("Exporting…")
        threading.Thread(target=work, daemon=True, name="trainzutil-export").start()

    def open_in_tuner(self, kuid: str) -> None:
        from ..lib.engine_tuner.config_io import looks_like_enginespec

        chosen = kuid.strip() or self._bridge._library.tuner_kuid()
        if not chosen:
            self._bridge.note("Select an engine spec")
            return
        if not self._ready():
            return
        exe = self.queue.exe
        assert exe is not None
        flags = self._bridge._library.flags_for(chosen)
        name = self._bridge._library.name_for(chosen)

        def work() -> None:
            text = ""
            if "E" in flags:
                editing = trainz_editing_dir(self._data_dir)
                path = config_in_editing(editing, chosen) if editing is not None else None
                if path is not None:
                    text = path.read_text(encoding="utf-8", errors="replace")
            if not looks_like_enginespec(text):
                try:
                    raw = run_trainzutil(exe, ["printconfig", chosen], timeout=60)
                except Exception as exc:
                    self.reportDone.emit(str(exc))
                    return
                if launcher_blocked(raw):
                    self.reportDone.emit("Open the Trainz Launcher first")
                    return
                text = tidy_trainzutil(raw)
            if not looks_like_enginespec(text):
                self.reportDone.emit(f"{name} is not an engine spec")
                return
            self.tunerReady.emit(chosen, text, name)

        self._bridge.note("Opening engine spec…")
        threading.Thread(target=work, daemon=True, name="trainzutil-tuner").start()

    def _on_report(self, text: str) -> None:
        for line in text.splitlines():
            if line.strip():
                self._bridge.note(line.strip())

    def _on_sizes(self, sizes: object) -> None:
        if not isinstance(sizes, dict):
            return
        for kuid, label in sizes.items():
            self._bridge._library.set_size(str(kuid), str(label))

    def lookup_kuid(self, kuid: str) -> None:
        exe = self.queue.exe
        if not kuid:
            return
        if exe is None or not self._bridge._launcher_ok:
            self._bridge.set_status_text(self._bridge._launcher_text)
            return
        token = kuid if kuid.startswith("<") else f"<{kuid}>"

        def work() -> None:
            try:
                raw = run_trainzutil(exe, ["status", token], timeout=40)
            except Exception as exc:
                text = str(exc)
            else:
                text = "Open the Trainz Launcher first" if launcher_blocked(raw) else decode_status(raw)
            self.statusDone.emit(text)

        threading.Thread(target=work, daemon=True, name="trainzutil-status").start()

    def _on_job_done(self, job_id: str, ok: bool, msg: str) -> None:
        job = self._jobs.get(job_id)
        label = job.label if job is not None else job_id
        if msg.startswith("Paused"):
            self._job_status[job_id] = "Paused"
            self._bridge.jobState.emit(job_id, "Paused")
            if job is not None:
                self._note_install(job, "Paused", self._job_pct.get(job_id, 0), msg)
                self._rollup(job.source)
            self._bridge.note(msg)
            return
        if ok:
            self._job_pct[job_id] = 100
            self._job_status[job_id] = "Installed"
        else:
            self._job_status[job_id] = "Failed"
        if job is not None:
            state = "Installed" if ok else "Failed"
            self._note_install(job, state, 100 if ok else self._job_pct.get(job_id, 0), tidy_trainzutil(msg) or state)
            self._rollup(job.source)
        self._bridge.jobState.emit(job_id, "Installed" if ok else "Failed")
        self._bridge.note(f"{'Installed' if ok else 'Failed'} {label}" + (f" — {msg}" if msg else ""))

    def _on_launcher_lost(self, text: str) -> None:
        self._bridge.set_launcher(False, text)
        self._bridge.note(text)

    def shutdown(self) -> None:
        self.queue.shutdown()
        self.queue.wait(1500)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._view_quick.setFocus(Qt.FocusReason.OtherFocusReason)
