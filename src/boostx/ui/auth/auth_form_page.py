from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.ui.components.card import Card

_CARD_WIDTH = 380


class AuthFormPage(QWidget):
    def __init__(self, title: str, subtitle: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AuthPage")

        card = Card(self)
        card.setFixedWidth(_CARD_WIDTH)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(32, 32, 32, 32)
        card_layout.setSpacing(10)

        self._title_label = QLabel(title, card)
        self._title_label.setObjectName("AuthTitle")
        self._subtitle_label = QLabel(subtitle, card)
        self._subtitle_label.setObjectName("AuthSubtitle")
        self._subtitle_label.setWordWrap(True)

        card_layout.addWidget(self._title_label)
        card_layout.addWidget(self._subtitle_label)
        card_layout.addSpacing(6)

        self._build_form(card_layout)

        self.error_label = QLabel("", card)
        self.error_label.setObjectName("AuthErrorLabel")
        self.error_label.setWordWrap(True)
        self.error_label.hide()
        card_layout.addWidget(self.error_label)

        self.status_label = QLabel("", card)
        self.status_label.setObjectName("AuthStatusLabel")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        card_layout.addWidget(self.status_label)

        outer_layout = QVBoxLayout(self)
        outer_layout.addStretch(1)
        row_layout = QHBoxLayout()
        row_layout.addStretch(1)
        row_layout.addWidget(card)
        row_layout.addStretch(1)
        outer_layout.addLayout(row_layout)
        outer_layout.addStretch(1)

    def _build_form(self, layout: QVBoxLayout) -> None:
        raise NotImplementedError

    def set_title(self, text: str) -> None:
        self._title_label.setText(text)

    def set_subtitle(self, text: str) -> None:
        self._subtitle_label.setText(text)

    def show_error(self, message: str) -> None:
        self.status_label.hide()
        self.error_label.setText(message)
        self.error_label.show()

    def show_status(self, message: str) -> None:
        self.error_label.hide()
        self.status_label.setText(message)
        self.status_label.show()

    def clear_messages(self) -> None:
        self.error_label.hide()
        self.status_label.hide()
