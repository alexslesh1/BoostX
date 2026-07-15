from PySide6.QtWidgets import QComboBox, QWidget

from boostx.i18n import SUPPORTED_LANGUAGES, i18n

_NATIVE_NAMES = {"en": "English", "ru": "Русский"}


class LanguageSwitcher(QComboBox):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("LanguageSwitcher")
        for code in SUPPORTED_LANGUAGES:
            self.addItem(f"\U0001F310 {_NATIVE_NAMES.get(code, code.upper())}", code)
        self._sync_from_language(i18n.language)
        self.currentIndexChanged.connect(self._on_index_changed)
        i18n.language_changed.connect(self._sync_from_language)

    def _sync_from_language(self, language: str) -> None:
        index = self.findData(language)
        if index >= 0 and index != self.currentIndex():
            self.blockSignals(True)
            self.setCurrentIndex(index)
            self.blockSignals(False)

    def _on_index_changed(self, index: int) -> None:
        code = self.itemData(index)
        if code:
            i18n.set_language(code)
