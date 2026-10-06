"""VS Code-style plain-text editor: gutter line numbers, Trainz highlight, find/replace.

Syntax colours follow https://github.com/agmike/vscode-trainzscript
(trainzconfig.tmLanguage — tags, numbers, KUIDs, strings) plus texture.txt Key=value.
"""
from __future__ import annotations

import re
from typing import Literal

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QRect,
    QSize,
    Qt,
    QVariantAnimation,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeySequence,
    QPainter,
    QPalette,
    QShortcut,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .motion import fade_widget
from .smooth_scroll import enable_code_scroll

_FIND_ANIM_MS = 200
_CODE_FONT_PT_MIN = 9
_CODE_FONT_PT_MAX = 28
_CODE_FONT_PT_DEFAULT = 13
_code_font_pt = _CODE_FONT_PT_DEFAULT

SyntaxMode = Literal["trainzconfig", "trainzscript", "plain"]


def code_font_pt() -> int:
    return _code_font_pt


def _load_code_font_pt() -> int:
    try:
        from PySide6.QtCore import QSettings

        v = int(QSettings("MSTN", "TrainzStudio").value("code_edit/font_pt", _CODE_FONT_PT_DEFAULT))
        return max(_CODE_FONT_PT_MIN, min(_CODE_FONT_PT_MAX, v))
    except Exception:
        return _CODE_FONT_PT_DEFAULT


def set_code_font_pt(pt: int, *, persist: bool = True) -> int:
    """Set editor font size for every CodeEdit in the app. Returns clamped pt."""
    global _code_font_pt
    _code_font_pt = max(_CODE_FONT_PT_MIN, min(_CODE_FONT_PT_MAX, int(pt)))
    if persist:
        try:
            from PySide6.QtCore import QSettings

            QSettings("MSTN", "TrainzStudio").setValue("code_edit/font_pt", _code_font_pt)
        except Exception:
            pass
    app = QApplication.instance()
    if app is not None:
        for w in app.allWidgets():
            if isinstance(w, CodeEdit):
                w.apply_editor_font()
    return _code_font_pt


def bump_code_font_pt(delta: int) -> int:
    return set_code_font_pt(code_font_pt() + int(delta))


def make_code_font(point_size: int | None = None) -> QFont:
    pt = _code_font_pt if point_size is None else int(point_size)
    for family in ("Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo", "Monaco"):
        f = QFont(family, pt)
        if f.exactMatch() or family == "Consolas":
            f.setStyleHint(QFont.StyleHint.Monospace)
            f.setFixedPitch(True)
            return f
    f = QFont()
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setFixedPitch(True)
    f.setPointSize(pt)
    return f


# restore persisted size once at import
_code_font_pt = _load_code_font_pt()

# Scopes from agmike/vscode-trainzscript (trainzconfig + trainzscript tmLanguage)
_RE_COMMENT = re.compile(r"#.*$")
_RE_STRING = re.compile(r'"(?:\\.|[^"\\])*"')
_RE_KUID = re.compile(r"<kuid2?:\d+:\d+(?::\d+)?>", re.IGNORECASE)
_RE_NUMBER = re.compile(
    r"\b((0[xX][0-9a-fA-F]*)|(([0-9]+\.?[0-9]*)|(\.[0-9]+))([eE][+\-]?[0-9]+)?)([Ff])?\b"
)
# tag  value   OR   Key=value  (texture.txt / lm-ish)
_RE_TAG_EQ = re.compile(r"^(\s*)((?:\w|-|_)+)(\s*=\s*)(.*)$")
_RE_TAG_SPACE = re.compile(r"^(\s*)((?:\w|-|_)+)(\s+)(?=[^\n\"{]*$)(.*)$")
_RE_TAG_STR = re.compile(r'^(\s*)((?:\w|-|_)+)(\s+)(".*)$')

# trainzscript.tmLanguage — keywords / types / modifiers
_GS_CONTROL = frozenset(
    "return break case continue default while for switch if else wait on".split()
)
_GS_OPERATOR_KW = frozenset("isclass inherited new copy size cast and or".split())
_GS_STORAGE = frozenset(
    "static final game public define thread secured mandatory native obsolete class include".split()
)
_GS_TYPES = frozenset("bool int float object string void".split())
_GS_LITERALS = frozenset("true false null me".split())
_RE_GS_IDENT = re.compile(r"[A-Za-z_]\w*")


def _syntax_palette(dark: bool) -> dict[str, QColor]:
    """VS Code Dark+ / Light+ tones matching vscode-trainzscript scopes."""
    if dark:
        return {
            "tag": QColor("#569CD6"),
            "keyword": QColor("#569CD6"),
            "type": QColor("#569CD6"),
            "class": QColor("#4EC9B0"),
            "function": QColor("#DCDCAA"),
            "macro": QColor("#4FC1FF"),
            "constant": QColor("#569CD6"),
            "number": QColor("#B5CEA8"),
            "kuid": QColor("#4EC9B0"),
            "string": QColor("#CE9178"),
            "comment": QColor("#6A9955"),
            "punct": QColor("#D4D4D4"),
            "gutter_fg": QColor("#858585"),
            "gutter_fg_active": QColor("#C6C6C6"),
            "gutter_bg": QColor("#1E1E1E"),
            "current_line": QColor(255, 255, 255, 10),
            "find": QColor(234, 92, 0, 90),
            "find_current": QColor(234, 92, 0, 160),
        }
    return {
        "tag": QColor("#0000FF"),
        "keyword": QColor("#0000FF"),
        "type": QColor("#267F99"),
        "class": QColor("#267F99"),
        "function": QColor("#795E26"),
        "macro": QColor("#0070C1"),
        "constant": QColor("#0000FF"),
        "number": QColor("#098658"),
        "kuid": QColor("#267F99"),
        "string": QColor("#A31515"),
        "comment": QColor("#008000"),
        "punct": QColor("#000000"),
        "gutter_fg": QColor("#237893"),
        "gutter_fg_active": QColor("#0B216F"),
        "gutter_bg": QColor("#F0F0F0"),
        "current_line": QColor(0, 0, 0, 8),
        "find": QColor(255, 180, 0, 100),
        "find_current": QColor(255, 140, 0, 160),
    }


def _fmt(color: QColor, *, bold: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(color)
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    return f


def classify_trainzconfig_spans(line: str) -> list[tuple[int, int, str]]:
    """Return (start, length, scope) spans — pure helper for checks / highlighter."""
    spans: list[tuple[int, int, str]] = []
    cm = _RE_COMMENT.search(line)
    code = line if cm is None else line[: cm.start()]
    if cm is not None:
        spans.append((cm.start(), cm.end() - cm.start(), "comment"))

    # tag line first (so Key= / tag value get tag colour)
    m = _RE_TAG_EQ.match(code) or _RE_TAG_STR.match(code) or _RE_TAG_SPACE.match(code)
    if m is not None:
        spans.append((m.start(2), m.end(2) - m.start(2), "tag"))
        rest_i = m.start(4) if m.lastindex and m.lastindex >= 4 else m.end(3)
        rest = code[rest_i:]
        offset = rest_i
    else:
        rest = code
        offset = 0

    occupied = [(s, s + n) for s, n, _ in spans]

    def _free(a: int, b: int) -> bool:
        for x, y in occupied:
            if a < y and b > x:
                return False
        return True

    for rx, scope in ((_RE_STRING, "string"), (_RE_KUID, "kuid"), (_RE_NUMBER, "number")):
        for m in rx.finditer(rest):
            a, b = offset + m.start(), offset + m.end()
            if _free(a, b):
                spans.append((a, b - a, scope))
                occupied.append((a, b))
    spans.sort(key=lambda t: t[0])
    return spans


def _gs_word_scope(word: str, line: str, end: int) -> str | None:
    """Map identifier → vscode-trainzscript-ish scope (None = leave default ink)."""
    if word in _GS_CONTROL or word in _GS_OPERATOR_KW or word in _GS_STORAGE:
        return "keyword"
    if word in _GS_TYPES:
        return "type"
    if word in _GS_LITERALS:
        return "constant"
    # ALL_CAPS defines (STOP_NONE) — not single-letter (avoids X → macro)
    if len(word) >= 2 and word == word.upper() and any(c.isalpha() for c in word):
        return "macro"
    rest = line[end:].lstrip()
    if rest.startswith("("):
        return "function"
    # PascalCase / Trainz class names (GSObject, KIHA_DriveLogic, …)
    if word[0].isupper():
        return "class"
    return None


def classify_trainzscript_spans(
    line: str, *, in_block_comment: bool = False
) -> tuple[list[tuple[int, int, str]], bool]:
    """Return (spans, ends_in_block_comment) for one .gs line."""
    spans: list[tuple[int, int, str]] = []
    i = 0
    n = len(line)
    if in_block_comment:
        end = line.find("*/")
        if end < 0:
            if n:
                spans.append((0, n, "comment"))
            return spans, True
        spans.append((0, end + 2, "comment"))
        i = end + 2

    while i < n:
        ch = line[i]
        if ch == "/" and i + 1 < n and line[i + 1] == "*":
            end = line.find("*/", i + 2)
            if end < 0:
                spans.append((i, n - i, "comment"))
                return spans, True
            spans.append((i, end + 2 - i, "comment"))
            i = end + 2
            continue
        if ch == "/" and i + 1 < n and line[i + 1] == "/":
            spans.append((i, n - i, "comment"))
            break
        if ch in "\"'":
            j = i + 1
            while j < n:
                if line[j] == "\\":
                    j += 2
                    continue
                if line[j] == ch:
                    j += 1
                    break
                j += 1
            spans.append((i, j - i, "string"))
            i = j
            continue
        if ch.isdigit() or (ch == "." and i + 1 < n and line[i + 1].isdigit()):
            m = _RE_NUMBER.match(line, i)
            if m is not None:
                spans.append((m.start(), m.end() - m.start(), "number"))
                i = m.end()
                continue
        if ch.isalpha() or ch == "_":
            m = _RE_GS_IDENT.match(line, i)
            if m is not None:
                word = m.group(0)
                scope = _gs_word_scope(word, line, m.end())
                if scope is not None:
                    spans.append((m.start(), m.end() - m.start(), scope))
                i = m.end()
                continue
        i += 1
    return spans, False


def syntax_for_filename(name: str) -> SyntaxMode:
    """Pick highlighter from file name (Viewer / Editor)."""
    low = (name or "").lower().replace("\\", "/")
    base = low.rsplit("/", 1)[-1]
    if base.endswith(".gs") or base.endswith(".gse"):
        return "trainzscript"
    if (
        base == "config.txt"
        or base.endswith(".texture.txt")
        or base.endswith(".lm.txt")
        or base.endswith(".txt")
        or base.endswith(".chump")
    ):
        return "trainzconfig"
    return "plain"


class _BaseHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._dark = True
        self._formats: dict[str, QTextCharFormat] = {}
        self.set_dark(True)

    def set_dark(self, dark: bool) -> None:
        self._dark = bool(dark)
        pal = _syntax_palette(self._dark)
        self._formats = {k: _fmt(v) for k, v in pal.items() if k not in (
            "gutter_fg", "gutter_fg_active", "gutter_bg",
            "current_line", "find", "find_current", "punct",
        )}
        # tag stands out a bit in config
        if "tag" in self._formats:
            self._formats["tag"] = _fmt(pal["tag"], bold=True)
        self.rehighlight()


class TrainzConfigHighlighter(_BaseHighlighter):
    """Highlight rules from vscode-trainzscript trainzconfig grammar."""

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for start, length, scope in classify_trainzconfig_spans(text):
            fmt = self._formats.get(scope)
            if fmt is not None:
                self.setFormat(start, length, fmt)


class TrainzScriptHighlighter(_BaseHighlighter):
    """Highlight rules from vscode-trainzscript trainzscript grammar (.gs)."""

    _STATE_BLOCK = 1

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        in_block = self.previousBlockState() == self._STATE_BLOCK
        spans, ends_block = classify_trainzscript_spans(text, in_block_comment=in_block)
        self.setCurrentBlockState(self._STATE_BLOCK if ends_block else 0)
        for start, length, scope in spans:
            fmt = self._formats.get(scope)
            if fmt is not None:
                self.setFormat(start, length, fmt)


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEdit) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor.paint_line_number_area(event)


class _FindBar(QFrame):
    """Compact VS Code-like find / replace strip."""

    closed = Signal()

    def __init__(self, parent: CodeEdit) -> None:
        super().__init__(parent)
        self._editor = parent
        self.setObjectName("codeFindBar")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("Find")
        self.find_edit.setClearButtonEnabled(True)
        self.find_edit.textChanged.connect(self._on_find_changed)
        self.find_edit.returnPressed.connect(lambda: self._editor.find_next())
        row1.addWidget(self.find_edit, 1)

        self.case_btn = QToolButton()
        self.case_btn.setText("Aa")
        self.case_btn.setCheckable(True)
        self.case_btn.setToolTip("Match case")
        self.case_btn.toggled.connect(self._on_find_changed)
        row1.addWidget(self.case_btn)

        prev = QToolButton()
        prev.setText("↑")
        prev.setToolTip("Previous (Shift+F3)")
        prev.clicked.connect(self._editor.find_prev)
        row1.addWidget(prev)
        nxt = QToolButton()
        nxt.setText("↓")
        nxt.setToolTip("Next (F3 / Enter)")
        nxt.clicked.connect(self._editor.find_next)
        row1.addWidget(nxt)

        self.count_lab = QLabel("")
        self.count_lab.setObjectName("mutedTip")
        self.count_lab.setMinimumWidth(64)
        row1.addWidget(self.count_lab)

        close = QToolButton()
        close.setText("×")
        close.setToolTip("Close (Esc)")
        close.clicked.connect(self._close)
        row1.addWidget(close)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(4)
        self.replace_edit = QLineEdit()
        self.replace_edit.setPlaceholderText("Replace")
        self.replace_edit.returnPressed.connect(self._editor.replace_one)
        row2.addWidget(self.replace_edit, 1)
        one = QPushButton("Replace")
        one.clicked.connect(self._editor.replace_one)
        row2.addWidget(one)
        all_btn = QPushButton("All")
        all_btn.clicked.connect(self._editor.replace_all)
        row2.addWidget(all_btn)
        lay.addLayout(row2)
        self._replace_row = row2
        self._replace_widgets = (self.replace_edit, one, all_btn)
        self.set_replace_visible(False)

        for seq, slot in (
            (QKeySequence(Qt.Key.Key_Escape), self._close),
            (QKeySequence(Qt.Key.Key_F3), self._editor.find_next),
            (QKeySequence("Shift+F3"), self._editor.find_prev),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

    def set_replace_visible(self, on: bool) -> None:
        for w in self._replace_widgets:
            w.setVisible(on)
        self.updateGeometry()

    def _on_find_changed(self, *_args) -> None:
        self._editor.refresh_find_highlights()

    def _close(self) -> None:
        self._editor.close_find()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self._close()
            return
        if event.key() == Qt.Key.Key_F3:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._editor.find_prev()
            else:
                self._editor.find_next()
            return
        super().keyPressEvent(event)


class CodeEdit(QPlainTextEdit):
    """QPlainTextEdit with VS Code gutter, Trainz colours, Ctrl+F / Ctrl+H."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        syntax: SyntaxMode = "trainzconfig",
    ) -> None:
        super().__init__(parent)
        self.setObjectName("codeView")
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        self._syntax: SyntaxMode = "plain"
        self._highlighter: _BaseHighlighter | None = None
        self._syntax_dark = True
        self._find_margin = 0
        self._find_target_h = 0
        self._find_anim: QVariantAnimation | None = None
        self._find_opening = False
        self._match_ranges: list[tuple[int, int]] = []
        self._match_index = -1

        self._line_area = _LineNumberArea(self)
        self._find_bar = _FindBar(self)
        self._find_bar.hide()

        self.apply_editor_font()
        self.set_syntax(syntax)

        self.blockCountChanged.connect(self._sync_viewport_margins)
        self.updateRequest.connect(self._update_line_number_area)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._sync_viewport_margins()
        self._highlight_current_line()
        self._apply_dark_from_app()
        enable_code_scroll(self)

        for seq, slot in (
            (QKeySequence.StandardKey.Find, lambda: self.open_find(replace=False)),
            (QKeySequence("Ctrl+H"), lambda: self.open_find(replace=True)),
            (QKeySequence(Qt.Key.Key_F3), self.find_next),
            (QKeySequence("Shift+F3"), self.find_prev),
            (QKeySequence("Ctrl+="), lambda: bump_code_font_pt(1)),
            (QKeySequence("Ctrl++"), lambda: bump_code_font_pt(1)),
            (QKeySequence("Ctrl+-"), lambda: bump_code_font_pt(-1)),
            (QKeySequence("Ctrl+0"), lambda: set_code_font_pt(_CODE_FONT_PT_DEFAULT)),
        ):
            sc = QShortcut(seq, self)
            sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            sc.activated.connect(slot)

        # Escape closes find when focus is in the editor
        esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        esc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        esc.activated.connect(self._esc_find)

    def apply_editor_font(self) -> None:
        """Apply global monospace point size (Viewer / Config / all CodeEdit)."""
        self.setFont(make_code_font())
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * 4)
        self._sync_viewport_margins()
        if hasattr(self, "_line_area"):
            self._line_area.update()

    # —— theme / syntax ——
    def set_syntax(self, syntax: SyntaxMode) -> None:
        """Switch trainzconfig / trainzscript / plain highlighter."""
        if syntax not in ("trainzconfig", "trainzscript", "plain"):
            syntax = "plain"
        if syntax == self._syntax and (
            (syntax == "plain" and self._highlighter is None)
            or (syntax != "plain" and self._highlighter is not None)
        ):
            return
        if self._highlighter is not None:
            self._highlighter.setDocument(None)
            self._highlighter = None
        self._syntax = syntax
        if syntax == "trainzconfig":
            self._highlighter = TrainzConfigHighlighter(self.document())
        elif syntax == "trainzscript":
            self._highlighter = TrainzScriptHighlighter(self.document())
        if self._highlighter is not None:
            self._highlighter.set_dark(self._syntax_dark)

    def set_syntax_dark(self, dark: bool) -> None:
        self._syntax_dark = bool(dark)
        if self._highlighter is not None:
            self._highlighter.set_dark(self._syntax_dark)
        self._line_area.update()
        self._highlight_current_line()
        self.refresh_find_highlights()

    def _apply_dark_from_app(self) -> None:
        app = QApplication.instance()
        if app is None:
            dark = True
        else:
            ink = app.palette().color(QPalette.ColorRole.WindowText)
            dark = ink.lightness() > 140
        self.set_syntax_dark(dark)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._apply_dark_from_app()

    # —— gutter ——
    def line_number_area_width(self) -> int:
        digits = max(2, len(str(max(1, self.blockCount()))))
        return 12 + self.fontMetrics().horizontalAdvance("9") * digits + 8

    def _find_full_height(self) -> int:
        hint = self._find_bar.sizeHint().height()
        return max(40, hint)

    def _sync_viewport_margins(self, *_args) -> None:
        self.setViewportMargins(
            self.line_number_area_width(), int(self._find_margin), 0, 0
        )
        self._layout_chrome()

    def _layout_chrome(self) -> None:
        if not hasattr(self, "_line_area") or not hasattr(self, "_find_bar"):
            return
        cr = self.contentsRect()
        gw = self.line_number_area_width()
        fh = int(self._find_margin)
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top() + fh, gw, max(0, cr.height() - fh))
        )
        if not self._find_bar.isHidden() or fh > 0:
            full = max(self._find_target_h, fh, 1)
            # slide down: bar sits above the text until margin catches up
            y = cr.top() + fh - full
            self._find_bar.setGeometry(cr.left(), y, cr.width(), full)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._layout_chrome()

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(), self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._sync_viewport_margins()

    def paint_line_number_area(self, event) -> None:
        pal = _syntax_palette(self._syntax_dark)
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(), pal["gutter_bg"])
        # VS Code-style right edge hairline
        painter.setPen(QColor(128, 128, 128, 60))
        painter.drawLine(
            event.rect().right(), event.rect().top(),
            event.rect().right(), event.rect().bottom(),
        )

        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(
            self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
        )
        bottom = top + int(self.blockBoundingRect(block).height())
        cur = self.textCursor().blockNumber()
        height = self.fontMetrics().height()

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(
                    pal["gutter_fg_active"] if block_number == cur else pal["gutter_fg"]
                )
                painter.drawText(
                    0,
                    top,
                    self._line_area.width() - 8,
                    height,
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1
        painter.end()

    def _highlight_current_line(self) -> None:
        pal = _syntax_palette(self._syntax_dark)
        sel = QTextEdit.ExtraSelection()
        sel.format.setBackground(pal["current_line"])
        sel.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        sel.cursor = self.textCursor()
        sel.cursor.clearSelection()
        # keep find extras on top of current-line
        extras = [sel]
        extras.extend(self._find_extra_selections())
        self.setExtraSelections(extras)
        self._line_area.update()

    # —— find / replace ——
    def open_find(self, *, replace: bool = False) -> None:
        cur = self.textCursor()
        if cur.hasSelection():
            sel = cur.selectedText().replace("\u2029", "\n")
            if "\n" not in sel:
                self._find_bar.find_edit.setText(sel)
        self._find_bar.set_replace_visible(replace)
        target = self._find_full_height()
        already = self._find_margin >= target - 1 and not self._find_bar.isHidden()
        if already:
            self._focus_find_field()
            self.refresh_find_highlights()
            return
        self._animate_find(True, target)
        self._focus_find_field()
        self.refresh_find_highlights()

    def close_find(self) -> None:
        if self._find_margin <= 0 and self._find_bar.isHidden():
            return
        self._animate_find(False, 0)

    def _focus_find_field(self) -> None:
        self._find_bar.find_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._find_bar.find_edit.selectAll()

    def _animate_find(self, opening: bool, target: int) -> None:
        prev = self._find_anim
        if prev is not None:
            # stop() still emits finished — disconnect first
            try:
                prev.finished.disconnect(self._on_find_anim_done)
            except (RuntimeError, TypeError):
                pass
            prev.stop()
            self._find_anim = None

        self._find_opening = opening
        self._find_target_h = (
            target if opening else max(self._find_target_h, int(self._find_margin), 1)
        )
        start = int(self._find_margin)

        if opening:
            self._find_bar.show()
            if start <= 0:
                fade_widget(self._find_bar, 0.0, 1.0, _FIND_ANIM_MS)
            else:
                # height tweak (find ↔ replace) — keep solid
                if self._find_bar.graphicsEffect() is not None:
                    self._find_bar.setGraphicsEffect(None)
        else:
            fade_widget(self._find_bar, 1.0, 0.0, _FIND_ANIM_MS)

        if start == target:
            self._on_find_margin_tick(target)
            self._on_find_anim_done()
            return

        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(int(target))
        anim.setDuration(_FIND_ANIM_MS)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(self._on_find_margin_tick)
        anim.finished.connect(self._on_find_anim_done)
        self._find_anim = anim
        anim.start(QVariantAnimation.DeletionPolicy.DeleteWhenStopped)

    def _on_find_margin_tick(self, value: object) -> None:
        self._find_margin = int(value)  # type: ignore[arg-type]
        self.setViewportMargins(
            self.line_number_area_width(), self._find_margin, 0, 0
        )
        self._layout_chrome()

    def _on_find_anim_done(self) -> None:
        self._find_anim = None
        if self._find_opening:
            self._find_margin = self._find_target_h
            self._sync_viewport_margins()
            return
        self._find_margin = 0
        self._find_target_h = 0
        self._find_bar.hide()
        self._find_bar.setGraphicsEffect(None)
        self._sync_viewport_margins()
        self.clear_find_highlights()
        self.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self._find_bar.closed.emit()

    def _esc_find(self) -> None:
        if self._find_margin > 0 or not self._find_bar.isHidden():
            self.close_find()

    def _needle(self) -> str:
        return self._find_bar.find_edit.text()

    def _doc_find(self, start: QTextCursor) -> QTextCursor:
        needle = self._needle()
        if self._find_bar.case_btn.isChecked():
            return self.document().find(
                needle, start, QTextDocument.FindFlag.FindCaseSensitively
            )
        return self.document().find(needle, start)

    def refresh_find_highlights(self) -> None:
        needle = self._needle()
        self._match_ranges = []
        self._match_index = -1
        if needle:
            c = QTextCursor(self.document())
            while True:
                c = self._doc_find(c)
                if c.isNull():
                    break
                self._match_ranges.append((c.selectionStart(), c.selectionEnd()))
            # keep index near caret
            pos = self.textCursor().position()
            for i, (a, b) in enumerate(self._match_ranges):
                if a <= pos <= b:
                    self._match_index = i
                    break
            if self._match_ranges and self._match_index < 0:
                self._match_index = 0
        n = len(self._match_ranges)
        if not needle:
            self._find_bar.count_lab.setText("")
        elif n == 0:
            self._find_bar.count_lab.setText("No results")
        else:
            self._find_bar.count_lab.setText(f"{self._match_index + 1}/{n}")
        self._highlight_current_line()

    def _find_extra_selections(self) -> list:
        pal = _syntax_palette(self._syntax_dark)
        out = []
        for i, (a, b) in enumerate(self._match_ranges):
            sel = QTextEdit.ExtraSelection()
            sel.format.setBackground(
                pal["find_current"] if i == self._match_index else pal["find"]
            )
            cur = self.textCursor()
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            sel.cursor = cur
            out.append(sel)
        return out

    def clear_find_highlights(self) -> None:
        self._match_ranges = []
        self._match_index = -1
        self._find_bar.count_lab.setText("")
        self._highlight_current_line()

    def find_next(self) -> None:
        self._step_find(+1)

    def find_prev(self) -> None:
        self._step_find(-1)

    def _step_find(self, delta: int) -> None:
        if not self._needle():
            self.open_find(replace=self._find_bar.replace_edit.isVisible())
            return
        if not self._match_ranges:
            self.refresh_find_highlights()
        if not self._match_ranges:
            return
        self._match_index = (self._match_index + delta) % len(self._match_ranges)
        a, b = self._match_ranges[self._match_index]
        cur = self.textCursor()
        cur.setPosition(a)
        cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cur)
        self.centerCursor()
        self._find_bar.count_lab.setText(
            f"{self._match_index + 1}/{len(self._match_ranges)}"
        )
        self._highlight_current_line()

    def replace_one(self) -> None:
        if self.isReadOnly():
            return
        needle = self._needle()
        repl = self._find_bar.replace_edit.text()
        if not needle:
            return
        cur = self.textCursor()
        selected = cur.selectedText().replace("\u2029", "\n")
        ok = (
            selected == needle
            if self._find_bar.case_btn.isChecked()
            else selected.lower() == needle.lower()
        )
        if ok:
            cur.insertText(repl)
        self.refresh_find_highlights()
        self.find_next()

    def replace_all(self) -> None:
        if self.isReadOnly():
            return
        needle = self._needle()
        repl = self._find_bar.replace_edit.text()
        if not needle:
            return
        text = self.toPlainText()
        if self._find_bar.case_btn.isChecked():
            new = text.replace(needle, repl)
        else:
            # case-insensitive replace keeping non-overlapping matches
            parts: list[str] = []
            i = 0
            lower = text.lower()
            nlow = needle.lower()
            nlen = len(needle)
            while True:
                j = lower.find(nlow, i)
                if j < 0:
                    parts.append(text[i:])
                    break
                parts.append(text[i:j])
                parts.append(repl)
                i = j + nlen
            new = "".join(parts)
        if new != text:
            self.setPlainText(new)
        self.refresh_find_highlights()


def apply_code_edit_theme(root: QWidget, mode: str) -> None:
    """Retint every CodeEdit under *root* after light/dark toggle."""
    dark = mode == "dark"
    for w in root.findChildren(CodeEdit):
        w.set_syntax_dark(dark)
        w.apply_editor_font()
