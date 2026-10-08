"""Sounds Studio — library · waveform · QC · Fix · Save As · Play · Track→Track."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import Property, QObject, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...audio.decode import DST_RATE, find_ffmpeg, load_mono_pcm16
from ...audio.export_wav import write_mono_pcm16
from ...audio.ffmpeg_cfg import ffmpeg_status, set_ffmpeg_path
from ...audio.loop_fix import fix_loop
from ...audio.loop_qc import Finding, analyze_mono, worst_severity
from ..smooth_scroll import enable_smooth_scroll
from ..theme import app_font
from .player import ClipPlayer
from .track_sim import PHASE_A, PHASE_B, PHASE_IDLE, PHASE_SEAM, TrackPair
from .waveform import WaveformWidget

EXPORT_DIR = Path.home() / ".cache" / "trainz_studio" / "export"


@dataclass
class SoundClip:
    name: str
    source: Path
    mono: np.ndarray
    sample_rate: int
    findings: list[Finding] = field(default_factory=list)
    fix_report: dict | None = None


class _BindLabel:
    def __init__(self, setter) -> None:  # noqa: ANN001
        self._setter = setter

    def setText(self, text: str) -> None:
        self._setter(str(text))

    def setPlainText(self, text: str) -> None:
        self._setter(str(text))


class _ClipRow:
    def __init__(self, host: SoundsStudioHost, index: int) -> None:
        self._host = host
        self._index = index

    def setText(self, text: str) -> None:
        labels = list(self._host._bridge.clip_labels())
        if 0 <= self._index < len(labels):
            labels[self._index] = str(text)
            self._host._bridge.set_clips(labels)


class _ClipList:
    """Stand-in for QListWidget so clip logic can stay put under the QML list."""

    def __init__(self, host: SoundsStudioHost) -> None:
        self._host = host
        self._blocked = False

    def blockSignals(self, on: bool) -> None:
        self._blocked = bool(on)

    def addItem(self, item) -> None:  # noqa: ANN001
        labels = list(self._host._bridge.clip_labels())
        labels.append(item.text())
        self._host._bridge.set_clips(labels)

    def setCurrentRow(self, row: int) -> None:
        self._host._bridge.set_current(int(row))
        if not self._blocked:
            self._host._on_select(int(row))

    def item(self, index: int) -> _ClipRow:
        return _ClipRow(self._host, int(index))


class SoundsBridge(QObject):
    changed = Signal()

    def __init__(self, host: SoundsStudioHost) -> None:
        super().__init__()
        self._host = host
        self._dark = True
        self._syncing = False
        self._ffmpeg = ""
        self._meta = "No clip"
        self._amp = "Peak —   RMS —"
        self._qc = ""
        self._slots = ""
        self._phase = ""
        self._play = "Play"
        self._loop = "Loop: Off"
        self._clips: list[str] = []
        self._current = -1
        self._title = "Sounds Studio"
        self._clips_title = "Clips"
        self._qc_title = "Loop QC"
        self._ffmpeg_btn = "ffmpeg…"
        self._drop = "Drop WAV / audio / video here"
        self._set_a = "Set A"
        self._set_b = "Set B"
        self._play_ab = "Play A→B"
        self._stop = "Stop"
        self._fix = "Fix"
        self._tip = "Save As only · A→B = Trainz seam (no runtime overlap)"
        self._home = "Home"
        self._icon_font = ""
        self._open_glyph = "📂"
        self._save_glyph = "💾"

    def _flag(self, name: str):  # noqa: ANN202
        return lambda: getattr(self, name)

    dark = Property(bool, lambda self: self._dark, notify=changed)
    ffmpeg = Property(str, lambda self: self._ffmpeg, notify=changed)
    meta = Property(str, lambda self: self._meta, notify=changed)
    amp = Property(str, lambda self: self._amp, notify=changed)
    qc = Property(str, lambda self: self._qc, notify=changed)
    slots = Property(str, lambda self: self._slots, notify=changed)
    phase = Property(str, lambda self: self._phase, notify=changed)
    playLabel = Property(str, lambda self: self._play, notify=changed)
    loopLabel = Property(str, lambda self: self._loop, notify=changed)
    title = Property(str, lambda self: self._title, notify=changed)
    clipsTitle = Property(str, lambda self: self._clips_title, notify=changed)
    qcTitle = Property(str, lambda self: self._qc_title, notify=changed)
    ffmpegBtn = Property(str, lambda self: self._ffmpeg_btn, notify=changed)
    dropHint = Property(str, lambda self: self._drop, notify=changed)
    setA = Property(str, lambda self: self._set_a, notify=changed)
    setB = Property(str, lambda self: self._set_b, notify=changed)
    playAB = Property(str, lambda self: self._play_ab, notify=changed)
    stopLabel = Property(str, lambda self: self._stop, notify=changed)
    fixLabel = Property(str, lambda self: self._fix, notify=changed)
    barTip = Property(str, lambda self: self._tip, notify=changed)
    homeLabel = Property(str, lambda self: self._home, notify=changed)
    iconFont = Property(str, lambda self: self._icon_font, notify=changed)
    openGlyph = Property(str, lambda self: self._open_glyph, notify=changed)
    saveGlyph = Property(str, lambda self: self._save_glyph, notify=changed)
    current = Property(int, lambda self: self._current, notify=changed)
    clips = Property("QVariantList", lambda self: self._clips, notify=changed)

    def clip_labels(self) -> list[str]:
        return self._clips

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        self.changed.emit()

    def set_ffmpeg(self, text: str) -> None:
        self._ffmpeg = text
        self.changed.emit()

    def set_meta(self, text: str) -> None:
        self._meta = text
        self.changed.emit()

    def set_amp(self, text: str) -> None:
        self._amp = text
        self.changed.emit()

    def set_qc(self, text: str) -> None:
        self._qc = text
        self.changed.emit()

    def set_slots(self, text: str) -> None:
        self._slots = text
        self.changed.emit()

    def set_phase(self, text: str) -> None:
        self._phase = text
        self.changed.emit()

    def set_play(self, text: str) -> None:
        self._play = text
        self.changed.emit()

    def set_loop(self, text: str) -> None:
        self._loop = text
        self.changed.emit()

    def set_clips(self, labels: list[str]) -> None:
        self._clips = list(labels)
        self.changed.emit()

    def set_current(self, row: int) -> None:
        self._current = int(row)
        self.changed.emit()

    def apply_chrome(self, **text: str) -> None:
        for key, value in text.items():
            setattr(self, key, value)
        self.changed.emit()

    @Slot(int)
    def selectClip(self, row: int) -> None:
        if self._syncing:
            return
        self._host._on_select(int(row))

    @Slot()
    def browse(self) -> None:
        self._host._browse()

    @Slot()
    def pickFfmpeg(self) -> None:
        self._host._pick_ffmpeg()

    @Slot()
    def setSlotA(self) -> None:
        self._host._set_slot("a")

    @Slot()
    def setSlotB(self) -> None:
        self._host._set_slot("b")

    @Slot()
    def playAB(self) -> None:
        self._host._play_ab()

    @Slot()
    def togglePlay(self) -> None:
        self._host._toggle_play()

    @Slot()
    def stop(self) -> None:
        self._host._stop()

    @Slot()
    def toggleLoop(self) -> None:
        self._host._on_loop_toggled(not self._host._loop_on)

    @Slot()
    def fix(self) -> None:
        self._host._fix_current()

    @Slot()
    def saveAs(self) -> None:
        self._host._save_as()

    @Slot()
    def goHome(self) -> None:
        self._host._on_home()

    @Slot(list)
    def dropUrls(self, urls: list) -> None:
        from PySide6.QtCore import QUrl

        paths: list[Path] = []
        for raw in urls:
            text = str(raw)
            local = QUrl(text).toLocalFile() if text.startswith("file:") else text
            if local:
                paths.append(Path(local))
        if paths:
            self._host.import_paths(paths)

    @Slot(float, float, float, float)
    def waveRect(self, x: float, y: float, w: float, h: float) -> None:
        wave = getattr(self._host, "wave", None)
        if wave is None:
            return
        wave.setGeometry(int(x), int(y), max(1, int(w)), max(1, int(h)))
        wave.show()
        wave.raise_()


class SoundsStudioHost(QWidget):
    """Sounds editor — Phase B editor + Phase C Track→Track / ffmpeg path."""

    status = Signal(str)

    def __init__(
        self,
        *,
        on_home: Callable[[], None],
        on_theme: Callable[[], None] | None = None,
        theme_mode: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_home = on_home
        self._on_theme = on_theme
        self._theme = theme_mode
        self._clips: list[SoundClip] = []
        self._current: int = -1
        self._slot_a: int | None = None
        self._slot_b: int | None = None
        self._track_phase = PHASE_IDLE
        self._player = ClipPlayer()
        self._loop_on = False
        self._build()
        self._tick = QTimer(self)
        self._tick.setInterval(40)
        self._tick.timeout.connect(self._on_play_tick)
        self._refresh_ffmpeg_tip()

    def set_theme(self, mode: str) -> None:
        from ..theme import qpalette_for

        self._theme = mode
        self.setPalette(qpalette_for(mode if mode in ("dark", "light") else "dark"))
        self.wave.set_theme(mode)
        bridge = getattr(self, "_bridge", None)
        if bridge is not None:
            bridge.set_dark(mode != "light")
        if getattr(self, "_chrome", None) is not None:
            self._chrome.set_theme(mode)

    def retranslate(self) -> None:
        """Refresh QML chrome strings after a language change."""
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return
        from ..i18n import t
        from ..icons import ensure_material_icons, glyph, icon_font

        ensure_material_icons()
        font = icon_font(18)
        bridge.apply_chrome(
            _title=t("Sounds Studio"),
            _clips_title=t("Clips"),
            _qc_title=t("Loop QC"),
            _ffmpeg_btn=t("ffmpeg…"),
            _drop=t("Drop WAV / audio / video here"),
            _set_a=t("Set A"),
            _set_b=t("Set B"),
            _play_ab=t("Play A→B"),
            _stop=t("Stop"),
            _fix=t("Fix"),
            _tip=t("Save As only · A→B = Trainz seam (no runtime overlap)"),
            _home=t("Home"),
            _icon_font=font.family() if font is not None else "",
            _open_glyph=glyph("folder_open") or "●",
            _save_glyph=glyph("save_as") or "●",
        )

    def _try_qml(self) -> bool:
        from pathlib import Path as _Path

        from PySide6.QtWidgets import QVBoxLayout

        from ..qml_host import _qml_ok, _quick

        self._bridge = SoundsBridge(self)
        self._bridge.set_dark(self._theme != "light")
        self.library = _ClipList(self)
        self.meta = _BindLabel(self._bridge.set_meta)
        self.amp = _BindLabel(self._bridge.set_amp)
        self.qc = _BindLabel(self._bridge.set_qc)
        self.ff_lab = _BindLabel(self._bridge.set_ffmpeg)
        self.slots_lab = _BindLabel(self._bridge.set_slots)
        self.phase_lab = _BindLabel(self._bridge.set_phase)
        self.btn_play = _BindLabel(self._bridge.set_play)
        self.btn_loop = _BindLabel(self._bridge.set_loop)
        self.wave = WaveformWidget(self)
        self.wave.set_theme(self._theme)
        self.wave.hide()
        qml = _Path(__file__).resolve().parents[1] / "qml" / "SoundsPage.qml"
        self._view = _quick(qml, self._bridge)
        if not _qml_ok(self._view):
            self.wave.deleteLater()
            self._view.deleteLater()
            self._bridge = None
            return False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)
        self.retranslate()
        self._refresh_slots_label()
        return True

    def _build(self) -> None:
        if self._try_qml():
            return
        self._build_widgets()

    def import_paths(self, paths: list[Path]) -> None:
        errors: list[str] = []
        for path in paths:
            try:
                mono, sr, _used = load_mono_pcm16(Path(path), sample_rate=DST_RATE)
                clip = SoundClip(
                    name=Path(path).name,
                    source=Path(path),
                    mono=mono,
                    sample_rate=sr,
                )
                clip.findings = analyze_mono(
                    clip.mono, clip.sample_rate, key=clip.name, path=str(clip.source)
                )
                self._clips.append(clip)
                item = QListWidgetItem(self._badge(clip) + "  " + clip.name)
                item.setData(Qt.ItemDataRole.UserRole, len(self._clips) - 1)
                self.library.addItem(item)
            except Exception as e:
                errors.append(f"{Path(path).name}: {e}")
        if self._clips:
            self.library.setCurrentRow(len(self._clips) - 1)
        if errors:
            missing_ff = any("ffmpeg" in e.lower() for e in errors)
            msg = "\n".join(errors[:8])
            if missing_ff:
                msg += "\n\nUse “ffmpeg…” to set the binary path, then retry."
            QMessageBox.warning(self, "Import", msg)
        self.status.emit(f"Sounds — {len(self._clips)} clip(s)")
        self._refresh_ffmpeg_tip()

    def _badge(self, clip: SoundClip) -> str:
        sev = worst_severity(clip.findings)
        return {"ok": "[OK]", "warn": "[!]", "fail": "[X]"}.get(sev, "[?]")

    def _clip_name(self, idx: int | None) -> str:
        if idx is None or not (0 <= idx < len(self._clips)):
            return "—"
        return self._clips[idx].name

    def _refresh_slots_label(self) -> None:
        self.slots_lab.setText(
            f"A (trans): {self._clip_name(self._slot_a)}   →   "
            f"B (steady): {self._clip_name(self._slot_b)}"
        )

    def _refresh_ffmpeg_tip(self) -> None:
        self.ff_lab.setText(ffmpeg_status())

    def _build_widgets(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        title = QLabel("Sounds Studio")
        title.setObjectName("welcomeTitle")
        title.setFont(app_font(18, QFont.Weight.Bold))
        top.addWidget(title)
        top.addStretch(1)
        ff_btn = QPushButton("ffmpeg…")
        ff_btn.setToolTip("Set ffmpeg.exe for mp3 / video import")
        ff_btn.clicked.connect(self._pick_ffmpeg)
        top.addWidget(ff_btn)
        root.addLayout(top)

        self.ff_lab = QLabel("")
        self.ff_lab.setObjectName("mutedTip")
        root.addWidget(self.ff_lab)

        split = QSplitter(Qt.Orientation.Horizontal)
        left = QFrame()
        left.setObjectName("glassPanel")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(8, 8, 8, 8)
        ll.addWidget(QLabel("Clips"))
        self.library = QListWidget()
        enable_smooth_scroll(self.library)
        self.library.currentRowChanged.connect(self._on_select)
        ll.addWidget(self.library, 1)
        from ..icons import apply_icon

        open_btn = QPushButton()
        apply_icon(
            open_btn,
            "folder_open",
            tip="Open audio / video…",
            kind="accent",
            size=22,
            square=40,
        )
        open_btn.clicked.connect(self._browse)
        ll.addWidget(open_btn)
        tip = QLabel("Drop WAV / audio / video here")
        tip.setObjectName("mutedTip")
        tip.setWordWrap(True)
        ll.addWidget(tip)
        split.addWidget(left)

        mid = QFrame()
        mid.setObjectName("glassPanel")
        ml = QVBoxLayout(mid)
        ml.setContentsMargins(8, 8, 8, 8)
        self.meta = QLabel("No clip")
        self.meta.setObjectName("mutedTip")
        ml.addWidget(self.meta)
        self.wave = WaveformWidget()
        self.wave.set_theme(self._theme)
        ml.addWidget(self.wave, 1)
        self.amp = QLabel("Peak —   RMS —")
        self.amp.setObjectName("mutedTip")
        ml.addWidget(self.amp)
        split.addWidget(mid)

        right = QFrame()
        right.setObjectName("glassPanel")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.addWidget(QLabel("Loop QC"))
        self.qc = QTextEdit()
        self.qc.setReadOnly(True)
        self.qc.setObjectName("codeView")
        rl.addWidget(self.qc, 1)
        split.addWidget(right)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setStretchFactor(2, 2)
        root.addWidget(split, 1)

        # Track→Track strip
        track = QFrame()
        track.setObjectName("glassPanel")
        tl = QHBoxLayout(track)
        tl.setContentsMargins(10, 8, 10, 8)
        self.btn_set_a = QPushButton("Set A")
        self.btn_set_a.setToolTip("Selected clip = transition one-shot")
        self.btn_set_a.clicked.connect(lambda: self._set_slot("a"))
        self.btn_set_b = QPushButton("Set B")
        self.btn_set_b.setToolTip("Selected clip = steady loop")
        self.btn_set_b.clicked.connect(lambda: self._set_slot("b"))
        self.btn_ab = QPushButton("Play A→B")
        self.btn_ab.setObjectName("accentBtn")
        self.btn_ab.setToolTip("Trainz: play A to end → stop → loop B")
        self.btn_ab.clicked.connect(self._play_ab)
        self.slots_lab = QLabel("")
        self.slots_lab.setObjectName("mutedTip")
        self.phase_lab = QLabel("")
        self.phase_lab.setObjectName("mutedTip")
        for w in (
            self.btn_set_a,
            self.btn_set_b,
            self.btn_ab,
            self.slots_lab,
            self.phase_lab,
        ):
            tl.addWidget(w)
        tl.addStretch(1)
        root.addWidget(track)
        self._refresh_slots_label()

        bar = QFrame()
        bar.setObjectName("glassPanel")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 10, 8)
        from ..icons import apply_icon

        # Play/Stop stay text — labels flip to Playing… / Looping B… / A→B…
        self.btn_play = QPushButton("Play")
        self.btn_play.clicked.connect(self._toggle_play)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.clicked.connect(self._stop)
        self.btn_loop = QPushButton("Loop: Off")
        self.btn_loop.setCheckable(True)
        self.btn_loop.toggled.connect(self._on_loop_toggled)
        self.btn_fix = QPushButton("Fix")
        self.btn_fix.setObjectName("accentBtn")
        self.btn_fix.clicked.connect(self._fix_current)
        self.btn_save = QPushButton()
        apply_icon(self.btn_save, "save_as", tip="Save As…", kind="accent", size=20, square=36)
        self.btn_save.clicked.connect(self._save_as)
        for b in (
            self.btn_play,
            self.btn_stop,
            self.btn_loop,
            self.btn_fix,
            self.btn_save,
        ):
            bl.addWidget(b)
        bl.addStretch(1)
        self.bar_tip = QLabel("Save As only · A→B = Trainz seam (no runtime overlap)")
        self.bar_tip.setObjectName("mutedTip")
        bl.addWidget(self.bar_tip)
        root.addWidget(bar)

        from ..float_chrome import FloatActionBar

        chrome_row = QHBoxLayout()
        chrome_row.addStretch(1)
        self._chrome = FloatActionBar(mode=self._theme)
        self._chrome.home_clicked.connect(self._on_home)
        chrome_row.addWidget(self._chrome)
        chrome_row.addStretch(1)
        root.addLayout(chrome_row)

    def _pick_ffmpeg(self) -> None:
        cur = find_ffmpeg() or ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ffmpeg executable",
            str(Path(cur).parent if cur else Path.home()),
            "Executable (ffmpeg.exe ffmpeg);;All (*.*)",
        )
        if not path:
            return
        set_ffmpeg_path(path)
        self._refresh_ffmpeg_tip()
        self.status.emit(f"ffmpeg set → {path}")

    def _browse(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open audio / video",
            str(Path.home()),
            "Audio/Video (*.wav *.mp3 *.flac *.ogg *.m4a *.mp4 *.mkv *.mov);;All (*.*)",
        )
        if paths:
            self.import_paths([Path(p) for p in paths])

    def _current_clip(self) -> SoundClip | None:
        if 0 <= self._current < len(self._clips):
            return self._clips[self._current]
        return None

    def _show_clip(self, idx: int) -> None:
        """Update waveform/QC for idx without stopping an active A→B wait incorrectly."""
        if not (0 <= idx < len(self._clips)):
            return
        clip = self._clips[idx]
        self._current = idx
        self.library.blockSignals(True)
        self.library.setCurrentRow(idx)
        self.library.blockSignals(False)
        self.wave.set_audio(clip.mono, clip.sample_rate)
        self._refresh_qc(clip)
        dur = clip.mono.size / float(clip.sample_rate)
        peak = int(np.max(np.abs(clip.mono))) if clip.mono.size else 0
        rms = float(np.sqrt(np.mean(np.square(clip.mono.astype(np.float64))))) / 32768.0
        self.meta.setText(
            f"{clip.name}  ·  {dur:.3f}s  ·  {clip.sample_rate} Hz mono  ·  src {clip.source}"
        )
        self.amp.setText(f"Peak {peak}   RMS {rms:.4f}")

    def _on_select(self, row: int) -> None:
        if self._track_phase not in (PHASE_IDLE,):
            # Allow browsing during A→B but don't kill transport mid-seam unless idle play
            pass
        else:
            self._stop()
        self._current = row
        clip = self._current_clip()
        if clip is None:
            self.wave.set_audio(None, DST_RATE)
            self.qc.setPlainText("")
            self.meta.setText("No clip")
            self.amp.setText("Peak —   RMS —")
            return
        self.wave.set_audio(clip.mono, clip.sample_rate)
        if self._track_phase == PHASE_IDLE:
            self._player.load(clip.mono, clip.sample_rate)
        self._refresh_qc(clip)
        dur = clip.mono.size / float(clip.sample_rate)
        peak = int(np.max(np.abs(clip.mono))) if clip.mono.size else 0
        rms = float(np.sqrt(np.mean(np.square(clip.mono.astype(np.float64))))) / 32768.0
        self.meta.setText(
            f"{clip.name}  ·  {dur:.3f}s  ·  {clip.sample_rate} Hz mono  ·  src {clip.source}"
        )
        self.amp.setText(f"Peak {peak}   RMS {rms:.4f}")

    def _refresh_qc(self, clip: SoundClip) -> None:
        lines = []
        for f in clip.findings:
            lines.append(f"[{f.severity.upper()}] {f.kind}: {f.message}")
        if clip.fix_report:
            lines.append("")
            lines.append("Last Fix:")
            for step in clip.fix_report.get("steps", []):
                lines.append(f"  · {step}")
            lines.append(
                f"  → {clip.fix_report.get('duration_out', 0):.3f}s "
                f"({clip.fix_report.get('samples_out')} samples)"
            )
        self.qc.setPlainText("\n".join(lines) if lines else "(no findings)")

    def _set_slot(self, which: str) -> None:
        if self._current < 0 or self._current >= len(self._clips):
            self.status.emit("Select a clip first")
            return
        if which == "a":
            self._slot_a = self._current
        else:
            self._slot_b = self._current
        self._refresh_slots_label()
        self.status.emit(
            f"Slot {which.upper()} = {self._clips[self._current].name}"
        )

    def _play_ab(self) -> None:
        pair = TrackPair(
            a_idx=self._slot_a if self._slot_a is not None else -1,
            b_idx=self._slot_b if self._slot_b is not None else -1,
        )
        if not pair.valid(len(self._clips)):
            QMessageBox.information(
                self,
                "Track→Track",
                "Set A (transition) and B (steady) to different clips first.",
            )
            return
        self._stop_transport_only()
        a = self._clips[pair.a_idx]
        self._track_phase = PHASE_A
        self.phase_lab.setText("Playing A…")
        self._show_clip(pair.a_idx)
        self._player.load(a.mono, a.sample_rate)
        self._player.play(loop=False)
        self.btn_play.setText("A→B…")
        self._tick.start()
        self.status.emit(f"A→B: {a.name} → {self._clips[pair.b_idx].name}")

    def _advance_ab_to_b(self) -> None:
        if self._slot_b is None or not (0 <= self._slot_b < len(self._clips)):
            self._track_phase = PHASE_IDLE
            self.phase_lab.setText("")
            return
        self._track_phase = PHASE_SEAM
        self.phase_lab.setText("Seam → B")
        b = self._clips[self._slot_b]
        self._show_clip(self._slot_b)
        self._player.load(b.mono, b.sample_rate)
        self._track_phase = PHASE_B
        self.phase_lab.setText("Looping B")
        self._player.play(loop=True)
        self.btn_play.setText("Looping B…")
        self._tick.start()

    def _on_loop_toggled(self, on: bool) -> None:
        self._loop_on = on
        self._player.set_loop(on)
        self.btn_loop.setText("Loop: On" if on else "Loop: Off")

    def _toggle_play(self) -> None:
        if self._track_phase != PHASE_IDLE:
            self._stop()
            return
        clip = self._current_clip()
        if clip is None:
            return
        if self._player.playing:
            self._stop()
            return
        self._player.load(clip.mono, clip.sample_rate)
        sel = self.wave.selection()
        if sel is not None:
            self._player.play(start_s=sel[0], end_s=sel[1], loop=self._loop_on)
        else:
            self._player.play(loop=self._loop_on)
        self.btn_play.setText("Playing…")
        self._tick.start()

    def _stop_transport_only(self) -> None:
        self._player.stop()
        self._tick.stop()
        self.btn_play.setText("Play")
        self.wave.set_playhead(0.0)

    def _stop(self) -> None:
        self._stop_transport_only()
        self._track_phase = PHASE_IDLE
        self.phase_lab.setText("")

    def _on_play_tick(self) -> None:
        if self._track_phase == PHASE_A and self._player.oneshot_done:
            self._player.clear_oneshot_done()
            self._advance_ab_to_b()
            return
        if self._track_phase == PHASE_IDLE and not self._player.playing:
            self._tick.stop()
            self.btn_play.setText("Play")
            return
        if self._player.playing:
            self.wave.set_playhead(self._player.playhead_s())
        elif self._track_phase == PHASE_B:
            # looping B should keep playing; if stopped externally, idle
            self._track_phase = PHASE_IDLE
            self.phase_lab.setText("")
            self.btn_play.setText("Play")
            self._tick.stop()

    def _fix_current(self) -> None:
        clip = self._current_clip()
        if clip is None:
            return
        match_ref = None
        note = ""
        # If fixing A and B is set, level-match A tail → B head
        if (
            self._slot_a is not None
            and self._current == self._slot_a
            and self._slot_b is not None
            and 0 <= self._slot_b < len(self._clips)
        ):
            match_ref = self._clips[self._slot_b].mono
            note = f"\nAlso level-match tail → B head ({self._clips[self._slot_b].name})."
        reply = QMessageBox.question(
            self,
            "Fix loop",
            "Run Fix on this clip?\n\n"
            "trim silence · heal short holes · seamless wrap · head/tail level"
            f"{note}\n\n"
            "Result stays in memory — use Save As to write a file.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            out, report = fix_loop(
                clip.mono, clip.sample_rate, match_ref=match_ref
            )
        except Exception as e:
            QMessageBox.critical(self, "Fix failed", str(e))
            return
        clip.mono = out
        clip.fix_report = report
        clip.findings = analyze_mono(
            clip.mono, clip.sample_rate, key=clip.name, path=str(clip.source)
        )
        item = self.library.item(self._current)
        if item is not None:
            item.setText(self._badge(clip) + "  " + clip.name)
        self._on_select(self._current)
        self.status.emit(f"Fixed {clip.name} → {report.get('duration_out', 0):.3f}s")

    def _save_as(self) -> None:
        clip = self._current_clip()
        if clip is None:
            return
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        suggested = EXPORT_DIR / f"{Path(clip.name).stem}_fixed.wav"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save As (WAV mono 44.1 kHz)",
            str(suggested),
            "WAV (*.wav)",
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != ".wav":
            out = out.with_suffix(".wav")
        try:
            write_mono_pcm16(out, clip.mono, clip.sample_rate)
        except Exception as e:
            QMessageBox.critical(self, "Save failed", str(e))
            return
        self.status.emit(f"Saved {out}")
        QMessageBox.information(self, "Saved", f"Wrote:\n{out}")


def build_sounds_studio(
    *,
    on_home: Callable[[], None],
    on_theme: Callable[[], None] | None = None,
    theme_mode: str = "dark",
) -> SoundsStudioHost:
    return SoundsStudioHost(
        on_home=on_home, on_theme=on_theme, theme_mode=theme_mode
    )


def build_sounds_placeholder(*, on_home: Callable[[], None]) -> QWidget:
    return build_sounds_studio(on_home=on_home)
