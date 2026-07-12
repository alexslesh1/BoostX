from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.ui.components.card import Card
from boostx.ui.utils.formatting import format_bytes

_WARNING_THRESHOLD = 60
_ERROR_THRESHOLD = 35


class SystemHealthCard(Card):
    scan_requested = Signal()
    clean_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._has_results = False

        title = QLabel("System Health", self)
        title.setObjectName("CleanerSectionTitle")

        self._health_label = QLabel("—", self)
        self._health_label.setObjectName("HealthPercentLabel")

        recoverable_title = QLabel("Estimated Recoverable Space", self)
        recoverable_title.setObjectName("MetricCardLabel")

        self._recoverable_label = QLabel("—", self)
        self._recoverable_label.setObjectName("MetricCardValue")

        self._scan_button = QPushButton("Scan", self)
        self._scan_button.setObjectName("CleanerPrimaryButton")
        self._scan_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._scan_button.clicked.connect(self.scan_requested.emit)

        self._clean_button = QPushButton("Clean Selected", self)
        self._clean_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clean_button.setEnabled(False)
        self._clean_button.clicked.connect(self.clean_requested.emit)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self._scan_button)
        button_row.addWidget(self._clean_button)
        button_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(4)
        layout.addWidget(title)
        layout.addWidget(self._health_label)
        layout.addSpacing(8)
        layout.addWidget(recoverable_title)
        layout.addWidget(self._recoverable_label)
        layout.addSpacing(14)
        layout.addLayout(button_row)

    def set_health_percent(self, percent: int) -> None:
        self._health_label.setText(f"{percent}%")
        if percent < _ERROR_THRESHOLD:
            severity = "error"
        elif percent < _WARNING_THRESHOLD:
            severity = "warning"
        else:
            severity = "success"
        self._health_label.setProperty("severity", severity)
        style = self._health_label.style()
        style.unpolish(self._health_label)
        style.polish(self._health_label)

    def set_recoverable_bytes(self, size_bytes: int) -> None:
        self._recoverable_label.setText(format_bytes(size_bytes))

    def set_has_results(self, has_results: bool) -> None:
        self._has_results = has_results
        self._clean_button.setEnabled(has_results)

    def set_busy(self, busy: bool, label: str = "Scan") -> None:
        self._scan_button.setEnabled(not busy)
        self._scan_button.setText("Scanning..." if busy else label)
        self._clean_button.setEnabled(not busy and self._has_results)
