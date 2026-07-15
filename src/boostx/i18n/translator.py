from __future__ import annotations

import json
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, Signal

from boostx.config.paths import AppPaths

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ru")

_PREFS_FILENAME = "language.json"


def _strings_dir() -> Path:
    return AppPaths.resources_dir() / "i18n"


def _load_strings(language: str) -> dict[str, str]:
    path = _strings_dir() / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _prefs_path() -> Path:
    return AppPaths.data_dir() / _PREFS_FILENAME


def _load_saved_language() -> str:
    path = _prefs_path()
    if not path.is_file():
        return DEFAULT_LANGUAGE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return DEFAULT_LANGUAGE
    language = data.get("language")
    return language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def _save_language(language: str) -> None:
    try:
        _prefs_path().write_text(json.dumps({"language": language}), encoding="utf-8")
    except OSError as error:
        logger.warning(f"Could not persist language preference: {error}")


class Translator(QObject):
    """Looks up user-facing strings by key in the active language, with an
    English fallback for missing keys. Storage is plain JSON resource files
    (resources/i18n/<lang>.json) rather than Qt Linguist .ts/QTranslator,
    since the codebase has no tr()-wrapped strings to extract from and JSON
    keeps translation editing decoupled from Python source.
    """

    language_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._strings = {language: _load_strings(language) for language in SUPPORTED_LANGUAGES}
        self._language = _load_saved_language()

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language not in SUPPORTED_LANGUAGES or language == self._language:
            return
        self._language = language
        _save_language(language)
        self.language_changed.emit(language)

    def tr(self, key: str, **kwargs: object) -> str:
        value = self._strings[self._language].get(key)
        if value is None:
            value = self._strings[DEFAULT_LANGUAGE].get(key, key)
        return value.format(**kwargs) if kwargs else value


i18n = Translator()
