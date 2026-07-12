from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.ui.components.boost_active.pulse_dot import PulseDot
from boostx.ui.components.card import Card
from boostx.ui.controllers.boost_discord_controller import BoostDiscordController

_IDLE_BUTTON_TEXT = "Launch Discord"
_STARTING_BUTTON_TEXT = "Starting..."
_STOP_BUTTON_TEXT = "Stop"
_DEFAULT_SUBTITLE = "One-click optimized routing for Discord voice and chat."


class BoostDiscordCard(Card):
    def __init__(self, controller: BoostDiscordController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(16)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(4)
        title = QLabel("Boost Discord", self)
        title.setObjectName("StatCardTitle")
        self._subtitle = QLabel(_DEFAULT_SUBTITLE, self)
        self._subtitle.setObjectName("EmptyStateSubtitle")
        self._subtitle.setWordWrap(True)
        text_layout.addWidget(title)
        text_layout.addWidget(self._subtitle)
        layout.addLayout(text_layout, stretch=1)

        action_layout = QVBoxLayout()
        action_layout.setSpacing(6)
        action_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(6)
        self._pulse_dot = PulseDot(8, self)
        self._pulse_dot.set_color("#3DD68C")
        self._status_label = QLabel("Boost active", self)
        self._status_label.setObjectName("BoostActiveStatusLabel")
        status_row.addWidget(self._pulse_dot)
        status_row.addWidget(self._status_label)
        self._status_widget = QWidget(self)
        self._status_widget.setLayout(status_row)
        self._status_widget.setVisible(False)
        action_layout.addWidget(self._status_widget, alignment=Qt.AlignmentFlag.AlignRight)

        self._action_button = QPushButton(_IDLE_BUTTON_TEXT, self)
        self._action_button.setObjectName("BoostCtaButton")
        self._action_button.clicked.connect(self._on_button_clicked)
        action_layout.addWidget(self._action_button)

        layout.addLayout(action_layout)

        self._controller.started.connect(self._on_started)
        self._controller.failed.connect(self._on_failed)
        self._controller.stopped.connect(self._on_stopped)

    def _on_button_clicked(self) -> None:
        if self._controller.is_active:
            self._controller.stop()
            return
        self._subtitle.setText(_DEFAULT_SUBTITLE)
        self._action_button.setEnabled(False)
        self._action_button.setText(_STARTING_BUTTON_TEXT)
        self._controller.start()

    def _on_started(self) -> None:
        self._action_button.setEnabled(True)
        self._action_button.setText(_STOP_BUTTON_TEXT)
        self._status_widget.setVisible(True)
        self._pulse_dot.set_pulsing(True)

    def _on_stopped(self) -> None:
        self._action_button.setEnabled(True)
        self._action_button.setText(_IDLE_BUTTON_TEXT)
        self._status_widget.setVisible(False)
        self._pulse_dot.set_pulsing(False)

    def _on_failed(self, message: str) -> None:
        self._action_button.setEnabled(True)
        self._action_button.setText(_IDLE_BUTTON_TEXT)
        self._subtitle.setText(message)
