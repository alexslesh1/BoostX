from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from boostx.ui.components.card import Card


class BasePage(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("BasePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        heading = QLabel(title, self)
        heading.setObjectName("PageHeading")

        subtitle_label = QLabel(subtitle, self)
        subtitle_label.setObjectName("PageSubtitle")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(4)
        layout.addWidget(heading)
        layout.addWidget(subtitle_label)
        layout.addSpacing(20)

        self._build_body(layout)

    def _build_body(self, layout: QVBoxLayout) -> None:
        placeholder_card = Card(self)
        placeholder_layout = QVBoxLayout(placeholder_card)
        placeholder_note = QLabel("Coming soon", placeholder_card)
        placeholder_note.setObjectName("CardPlaceholderLabel")
        placeholder_layout.addWidget(placeholder_note)
        layout.addWidget(placeholder_card, stretch=1)
