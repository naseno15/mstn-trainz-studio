"""MSTN Trainz Studio internationalization."""
from __future__ import annotations

from .core import (
    LANG_EN,
    LANG_ID,
    LANG_JA,
    LANG_NATIVE,
    LANG_ORDER,
    LANG_TH,
    current_language,
    g,
    i18n,
    set_language,
    t,
)
from .fonts import apply_language_font, ensure_ui_fonts, family_for, ui_font
from .retranslate import mark_skip, snapshot_and_apply, translate_tip

__all__ = [
    "LANG_EN",
    "LANG_ID",
    "LANG_JA",
    "LANG_NATIVE",
    "LANG_ORDER",
    "LANG_TH",
    "apply_language_font",
    "current_language",
    "ensure_ui_fonts",
    "family_for",
    "g",
    "i18n",
    "mark_skip",
    "set_language",
    "snapshot_and_apply",
    "t",
    "translate_tip",
    "ui_font",
]
