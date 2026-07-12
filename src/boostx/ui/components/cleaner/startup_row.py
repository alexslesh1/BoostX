from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QWidget

from boostx.core.services.cleaner.models import StartupEntry
from boostx.ui.components.status_chip import StatusChip


class StartupRow(QWidget):
    toggled = Signal(object, bool)

    def __init__(self, entry: StartupEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry

        name_label = QLabel(entry.name, self)
        name_label.setObjectName("ConnectionRowName")

        self._status_chip = StatusChip(
            "Enabled" if entry.enabled else "Disabled",
            "success" if entry.enabled else "neutral",
            self,
        )

        self._checkbox = QCheckBox(self)
        self._checkbox.setChecked(entry.enabled)
        self._checkbox.toggled.connect(self._on_toggled)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        layout.addWidget(name_label, stretch=1)
        layout.addWidget(self._status_chip, alignment=Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._checkbox, alignment=Qt.AlignmentFlag.AlignVCenter)

    def set_pending(self, pending: bool) -> None:
        self._checkbox.setEnabled(not pending)

    def apply_result(self, enabled: bool, success: bool) -> None:
        self._checkbox.setEnabled(True)
        if not success:
            self._checkbox.blockSignals(True)
            self._checkbox.setChecked(not enabled)
            self._checkbox.blockSignals(False)
            return
        self._status_chip.setText("Enabled" if enabled else "Disabled")
        self._status_chip.set_severity("success" if enabled else "neutral")

    def _on_toggled(self, checked: bool) -> None:
        self.set_pending(True)
        self.toggled.emit(self._entry, checked)
