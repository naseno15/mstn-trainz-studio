"""App-wide i18n — English keys, QSettings persistence, change signal."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject, QSettings, Signal

from . import catalog_en, catalog_id, catalog_ja, catalog_th

LANG_EN = "en"
LANG_TH = "th"
LANG_JA = "ja"
LANG_ID = "id"

LANG_ORDER: tuple[str, ...] = (LANG_EN, LANG_TH, LANG_JA, LANG_ID)

# Native labels shown in the Lang menu (always in that language).
LANG_NATIVE: dict[str, str] = {
    LANG_EN: "English",
    LANG_TH: "ไทย",
    LANG_JA: "日本語",
    LANG_ID: "Bahasa Indonesia",
}

_CATALOGS: dict[str, tuple[dict[str, str], dict[str, str]]] = {
    LANG_EN: (catalog_en.STRINGS, catalog_en.GLOSSARY),
    LANG_TH: (catalog_th.STRINGS, catalog_th.GLOSSARY),
    LANG_JA: (catalog_ja.STRINGS, catalog_ja.GLOSSARY),
    LANG_ID: (catalog_id.STRINGS, catalog_id.GLOSSARY),
}

_SETTINGS_ORG = "MSTN"
_SETTINGS_APP = "TrainzStudio"
_SETTINGS_KEY = "ui/language"


class I18n(QObject):
    """Singleton translator. English source string is the lookup key."""

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._lang = LANG_EN
        self._strings, self._glossary = _CATALOGS[LANG_EN]
        self._listeners: list[Callable[[str], None]] = []

    @property
    def language(self) -> str:
        return self._lang

    def t(self, key: str, **kwargs: object) -> str:
        if not key:
            return key
        text = self._strings.get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError, IndexError):
                return text
        return text

    def g(self, glossary_id: str, **kwargs: object) -> str:
        """Translate a stable glossary id (e.g. ve39.tip)."""
        if not glossary_id:
            return glossary_id
        # Prefer locale glossary; fall back to English glossary value as key into STRINGS.
        text = self._glossary.get(glossary_id)
        if text is None:
            text = catalog_en.GLOSSARY.get(glossary_id, glossary_id)
            text = self._strings.get(text, text)
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError, IndexError):
                return text
        return text

    def set_language(self, lang: str, *, persist: bool = True) -> bool:
        lang = (lang or LANG_EN).lower()
        if lang not in _CATALOGS:
            return False
        if lang == self._lang:
            return False
        self._lang = lang
        self._strings, self._glossary = _CATALOGS[lang]
        if persist:
            QSettings(_SETTINGS_ORG, _SETTINGS_APP).setValue(_SETTINGS_KEY, lang)
        self.language_changed.emit(lang)
        for fn in list(self._listeners):
            try:
                fn(lang)
            except Exception:
                pass
        return True

    def load_persisted(self) -> str:
        raw = QSettings(_SETTINGS_ORG, _SETTINGS_APP).value(_SETTINGS_KEY, LANG_EN)
        lang = str(raw or LANG_EN).lower()
        if lang not in _CATALOGS:
            lang = LANG_EN
        self._lang = lang
        self._strings, self._glossary = _CATALOGS[lang]
        return lang

    def on_change(self, fn: Callable[[str], None]) -> None:
        self._listeners.append(fn)


_I18N: I18n | None = None


def i18n() -> I18n:
    global _I18N
    if _I18N is None:
        _I18N = I18n()
        _I18N.load_persisted()
    return _I18N


def t(key: str, **kwargs: object) -> str:
    return i18n().t(key, **kwargs)


def g(glossary_id: str, **kwargs: object) -> str:
    return i18n().g(glossary_id, **kwargs)


def current_language() -> str:
    return i18n().language


def set_language(lang: str, *, persist: bool = True) -> bool:
    return i18n().set_language(lang, persist=persist)
