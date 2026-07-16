from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.config.palette import Palette
from boostx.core.services.cleaner.models import CreateRestorePointResult, RestorePointStatus
from boostx.ui.components.boost_active.pulse_dot import PulseDot
from boostx.ui.components.card import Card


def _format_relative(creation_time: datetime) -> str:
    total_seconds = (datetime.now(timezone.utc) - creation_time).total_seconds()
    if total_seconds < 60:
        return "just now"
    minutes = int(total_seconds // 60)
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


class RestorePointCard(Card):
    create_requested = Signal()
    apply_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = Palette()

        title = QLabel("System Restore Points", self)
        title.setObjectName("CleanerSectionTitle")

        description = QLabel(
            "Create a Windows System Restore Point before making changes, or open the "
            "built-in restore wizard to roll back to a previous point.",
            self,
        )
        description.setObjectName("CardPlaceholderLabel")
        description.setWordWrap(True)

        self._last_created_label = QLabel("Checking for existing restore points...", self)
        self._last_created_label.setObjectName("MetricCardLabel")
        self._last_created_label.setWordWrap(True)

        self._create_button = QPushButton("Create Restore Point", self)
        self._create_button.setObjectName("CleanerPrimaryButton")
        self._create_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_button.clicked.connect(self.create_requested.emit)

        self._apply_button = QPushButton("Apply Restore Point", self)
        self._apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_button.clicked.connect(self.apply_requested.emit)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(10)
        buttons_row.addWidget(self._create_button)
        buttons_row.addWidget(self._apply_button)
        buttons_row.addStretch(1)

        self._status_dot = PulseDot(8, self)
        self._status_dot.hide()
        self._status_label = QLabel("", self)
        self._status_label.setObjectName("CleanerResultLabel")
        self._status_label.setWordWrap(True)
        self._status_label.hide()

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self._status_dot, alignment=Qt.AlignmentFlag.AlignTop)
        status_row.addWidget(self._status_label, stretch=1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(description)
        layout.addSpacing(6)
        layout.addWidget(self._last_created_label)
        layout.addSpacing(10)
        layout.addLayout(buttons_row)
        layout.addLayout(status_row)

    def update_status(self, status: RestorePointStatus) -> None:
        latest = status.latest
        if latest is None:
            self._last_created_label.setText("No restore points found yet.")
            return
        self._last_created_label.setText(
            f'Last created: {_format_relative(latest.creation_time)} — "{latest.description}"'
        )

    def set_busy(self, busy: bool) -> None:
        self._create_button.setEnabled(not busy)
        self._create_button.setText("Creating..." if busy else "Create Restore Point")
        self._status_dot.setVisible(busy)
        self._status_dot.set_color(self._palette.TEXT_SECONDARY)
        self._status_dot.set_pulsing(busy)
        if busy:
            self._status_label.setText("Creating restore point — this can take up to a minute...")
            self._status_label.show()

    def show_result(self, result: CreateRestorePointResult) -> None:
        self._status_dot.hide()
        self._status_dot.set_pulsing(False)
        self._status_label.setText(result.message)
        self._status_label.show()
