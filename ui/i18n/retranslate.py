"""Snapshot English UI strings once, then re-apply translations on language change."""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTextEdit,
    QTreeWidget,
    QWidget,
)

from .core import LANG_EN, current_language, i18n, t
from . import catalog_en

_SRC = "mstn_i18n_src"
_SRC_TIP = "mstn_i18n_tip"
_SRC_STATUS = "mstn_i18n_status"
_SRC_PLACE = "mstn_i18n_place"
_SRC_ITEMS = "mstn_i18n_items"
_SRC_TABS = "mstn_i18n_tabs"
_SRC_HEADERS = "mstn_i18n_headers"
_SKIP = "mstn_i18n_skip"  # Material icon glyphs, etc.


def mark_skip(obj: QWidget | QAction) -> None:
    obj.setProperty(_SKIP, True)


def _skipped(obj: object) -> bool:
    try:
        return bool(obj.property(_SKIP))  # type: ignore[attr-defined]
    except Exception:
        return False


def _to_english_key(text: str) -> str:
    """Map a visible string back to the English catalog key when possible."""
    if not text:
        return text
    if text in catalog_en.STRINGS:
        return text
    # Reverse lookup in the active locale (and English) so a late first-snapshot
    # after a language change still freezes the English source, not Thai/JA/ID.
    for mapping in (i18n()._strings, catalog_en.STRINGS):
        for key, val in mapping.items():
            if val == text:
                return key
    return text


def _capture_str(obj: object, prop: str, current: str) -> str:
    if not current:
        return ""
    existing = obj.property(prop)  # type: ignore[attr-defined]
    if isinstance(existing, str) and existing:
        # Repair bad captures from older sessions (translated text stored as src).
        if existing not in catalog_en.STRINGS and current_language() != LANG_EN:
            fixed = _to_english_key(existing)
            if fixed != existing:
                obj.setProperty(prop, fixed)  # type: ignore[attr-defined]
                return fixed
        return existing
    key = _to_english_key(current)
    obj.setProperty(prop, key)  # type: ignore[attr-defined]
    return key


def _apply_str(obj: object, prop: str, current: str, setter) -> None:
    if _skipped(obj):
        return
    src = _capture_str(obj, prop, current)
    if not src:
        return
    translated = t(src)
    if translated != current:
        setter(translated)


def snapshot_and_apply(root: QWidget | None) -> None:
    """Walk the widget tree: freeze English sources on first pass, then set t()."""
    if root is None:
        return

    # Actions owned by the window / menus
    for act in root.findChildren(QAction):
        if _skipped(act):
            continue
        _apply_str(act, _SRC, act.text(), act.setText)
        tip = act.toolTip() or ""
        if tip:
            _apply_str(act, _SRC_TIP, tip, act.setToolTip)
        st = act.statusTip() or ""
        if st:
            _apply_str(act, _SRC_STATUS, st, act.setStatusTip)

    for menu in root.findChildren(QMenu):
        if _skipped(menu):
            continue
        title = menu.title()
        if title:
            _apply_str(menu, _SRC, title, menu.setTitle)

    # Menu bar top-level menus (children of menuBar, may already be in findChildren)
    mb = getattr(root, "menuBar", None)
    if callable(mb):
        bar = mb()
        if bar is not None:
            for act in bar.actions():
                menu = act.menu()
                if menu is not None and not _skipped(menu):
                    title = menu.title()
                    if title:
                        _apply_str(menu, _SRC, title, menu.setTitle)
                elif not _skipped(act):
                    _apply_str(act, _SRC, act.text(), act.setText)

    for lab in root.findChildren(QLabel):
        if _skipped(lab):
            continue
        # Rich HTML labels: translate only if no tags (simple text)
        text = lab.text()
        if text and "<" not in text:
            _apply_str(lab, _SRC, text, lab.setText)
        tip = lab.toolTip() or ""
        if tip:
            _apply_str(lab, _SRC_TIP, tip, lab.setToolTip)

    for btn in root.findChildren(QAbstractButton):
        if _skipped(btn):
            continue
        text = btn.text()
        # Material Icons use private-use glyphs — skip those
        if text and not (len(text) <= 2 and ord(text[0]) >= 0xE000):
            _apply_str(btn, _SRC, text, btn.setText)
        tip = btn.toolTip() or ""
        if tip:
            _apply_str(btn, _SRC_TIP, tip, btn.setToolTip)

    for box in root.findChildren(QGroupBox):
        if _skipped(box):
            continue
        title = box.title()
        if title:
            _apply_str(box, _SRC, title, box.setTitle)

    for edit in root.findChildren(QLineEdit):
        if _skipped(edit):
            continue
        ph = edit.placeholderText() or ""
        if ph:
            _apply_str(edit, _SRC_PLACE, ph, edit.setPlaceholderText)
        tip = edit.toolTip() or ""
        if tip:
            _apply_str(edit, _SRC_TIP, tip, edit.setToolTip)

    for edit in root.findChildren(QPlainTextEdit):
        if _skipped(edit):
            continue
        tip = edit.toolTip() or ""
        if tip:
            _apply_str(edit, _SRC_TIP, tip, edit.setToolTip)
        # placeholderText exists on QPlainTextEdit in Qt6
        ph = getattr(edit, "placeholderText", lambda: "")()
        if ph:
            _apply_str(edit, _SRC_PLACE, ph, edit.setPlaceholderText)

    for edit in root.findChildren(QTextEdit):
        if _skipped(edit):
            continue
        tip = edit.toolTip() or ""
        if tip:
            _apply_str(edit, _SRC_TIP, tip, edit.setToolTip)

    for tabs in root.findChildren(QTabWidget):
        if _skipped(tabs):
            continue
        stored = tabs.property(_SRC_TABS)
        if not isinstance(stored, list) or len(stored) != tabs.count():
            stored = [_to_english_key(tabs.tabText(i)) for i in range(tabs.count())]
            tabs.setProperty(_SRC_TABS, stored)
        else:
            stored = [_to_english_key(s) if s else s for s in stored]
            tabs.setProperty(_SRC_TABS, stored)
        for i, src in enumerate(stored):
            if src:
                tabs.setTabText(i, t(src))

    for combo in root.findChildren(QComboBox):
        if _skipped(combo):
            continue
        stored = combo.property(_SRC_ITEMS)
        if not isinstance(stored, list) or len(stored) != combo.count():
            stored = [_to_english_key(combo.itemText(i)) for i in range(combo.count())]
            combo.setProperty(_SRC_ITEMS, stored)
        else:
            stored = [_to_english_key(s) if s else s for s in stored]
            combo.setProperty(_SRC_ITEMS, stored)
        for i, src in enumerate(stored):
            if src:
                combo.setItemText(i, t(src))

    for table in root.findChildren(QTableWidget):
        if _skipped(table):
            continue
        cols = table.columnCount()
        stored = table.property(_SRC_HEADERS)
        if not isinstance(stored, list) or len(stored) != cols:
            stored = []
            for i in range(cols):
                item = table.horizontalHeaderItem(i)
                stored.append(_to_english_key(item.text()) if item is not None else "")
            table.setProperty(_SRC_HEADERS, stored)
        else:
            stored = [_to_english_key(s) if s else s for s in stored]
            table.setProperty(_SRC_HEADERS, stored)
        for i, src in enumerate(stored):
            if not src:
                continue
            item = table.horizontalHeaderItem(i)
            if item is not None:
                item.setText(t(src))

    for tree in root.findChildren(QTreeWidget):
        if _skipped(tree):
            continue
        cols = tree.columnCount()
        stored = tree.property(_SRC_HEADERS)
        if not isinstance(stored, list) or len(stored) != cols:
            stored = []
            for i in range(cols):
                item = tree.headerItem()
                stored.append(_to_english_key(item.text(i)) if item is not None else "")
            tree.setProperty(_SRC_HEADERS, stored)
        else:
            stored = [_to_english_key(s) if s else s for s in stored]
            tree.setProperty(_SRC_HEADERS, stored)
        item = tree.headerItem()
        if item is not None:
            for i, src in enumerate(stored):
                if src:
                    item.setText(i, t(src))

    for bar in root.findChildren(QStatusBar):
        if _skipped(bar):
            continue
        msg = bar.currentMessage() or ""
        if msg:
            src = _capture_str(bar, _SRC, msg)
            if src:
                bar.showMessage(t(src))

    # Window title
    title = root.windowTitle()
    if title:
        src = _capture_str(root, _SRC, title)
        if src:
            root.setWindowTitle(t(src))


def translate_tip(english: str) -> str:
    """Translate a tooltip / glass-tip string (stores nothing)."""
    return t(english) if english else english
