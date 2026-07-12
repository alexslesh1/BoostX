from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from boostx.core.services.tweaks.models import DeviceOption
from boostx.ui.components.card import Card


class DeviceOptionCard(Card):
    """A single selectable CPU/GPU entry in a tweak's device list."""

    clicked = Signal(str)

    def __init__(self, device: DeviceOption, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = device.key
        self.setObjectName("TweakProviderCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        label = QLabel(device.label, self)
        label.setObjectName("MetricCardValue")

        arrow_label = QLabel("›", self)
        arrow_label.setObjectName("TweakCardArrow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.addWidget(label, stretch=1)
        layout.addWidget(arrow_label, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)
