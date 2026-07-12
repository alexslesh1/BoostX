from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.cleaner.models import ScanCategory
from boostx.ui.components.card import Card
from boostx.ui.utils.formatting import format_bytes


class ScanCategoryCard(Card):
    """One selectable row in the scan results list: a checkbox, the
    category name, and its measured size."""

    toggled = Signal(str, bool)

    def __init__(self, category: ScanCategory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = category.key

        self._checkbox = QCheckBox(self)
        self._checkbox.setChecked(category.selected)
        self._checkbox.toggled.connect(self._on_toggled)

        self._label = QLabel(category.label, self)
        self._label.setObjectName("MetricCardLabel")

        self._size_label = QLabel(format_bytes(category.size_bytes), self)
        self._size_label.setObjectName("MetricCardValue")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(self._label)
        text_layout.addWidget(self._size_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        layout.addWidget(self._checkbox)
        layout.addLayout(text_layout, stretch=1)

        self.set_enabled_state(category.size_bytes > 0)

    @property
    def key(self) -> str:
        return self._key

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def update_category(self, category: ScanCategory) -> None:
        self._size_label.setText(format_bytes(category.size_bytes))
        self.set_enabled_state(category.size_bytes > 0)

    def set_enabled_state(self, has_content: bool) -> None:
        self._checkbox.setEnabled(has_content)
        if not has_content:
            self._checkbox.setChecked(False)

    def _on_toggled(self, checked: bool) -> None:
        self.toggled.emit(self._key, checked)
