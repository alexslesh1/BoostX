from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.tweaks.provider import TweakProviderHandler
from boostx.ui.components.card import Card
from boostx.ui.components.monogram import render_monogram_pixmap

_BADGE_SIZE = QSize(48, 48)


class TweakProviderCard(Card):
    """One row on the Tweaks home screen: icon, title, short description,
    and an arrow indicating it opens another page."""

    clicked = Signal(str)

    def __init__(self, provider: TweakProviderHandler, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = provider.key
        self.setObjectName("TweakProviderCard")
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        icon_label = QLabel(self)
        icon_label.setFixedSize(_BADGE_SIZE)
        icon_label.setScaledContents(True)
        icon_label.setPixmap(render_monogram_pixmap(provider.title, provider.icon_key, _BADGE_SIZE))

        title_label = QLabel(provider.title, self)
        title_label.setObjectName("MetricCardValue")

        description_label = QLabel(provider.description, self)
        description_label.setObjectName("CardPlaceholderLabel")
        description_label.setWordWrap(True)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        arrow_label = QLabel("›", self)
        arrow_label.setObjectName("TweakCardArrow")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)
        layout.addWidget(icon_label)
        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(arrow_label, alignment=Qt.AlignmentFlag.AlignVCenter)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)
