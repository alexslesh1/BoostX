from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from boostx.ui.components.card import Card

_FADE_DURATION_MS = 250
_FADE_START_OPACITY = 0.35


class MetricCard(Card):
    """Shared layout for a small label + large value stat card, with a
    smooth cross-fade whenever the value changes."""

    def __init__(self, label_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        label = QLabel(label_text, self)
        label.setObjectName("MetricCardLabel")

        self._value_label = QLabel("—", self)
        self._value_label.setObjectName("MetricCardValue")

        self._opacity_effect = QGraphicsOpacityEffect(self._value_label)
        self._opacity_effect.setOpacity(1.0)
        self._value_label.setGraphicsEffect(self._opacity_effect)

        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(_FADE_DURATION_MS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(4)
        layout.addWidget(label)
        layout.addWidget(self._value_label)

    def set_severity(self, severity: str) -> None:
        self._value_label.setProperty("severity", severity)
        style = self._value_label.style()
        style.unpolish(self._value_label)
        style.polish(self._value_label)

    def reset(self) -> None:
        self._value_label.setText("—")

    def _set_value(self, text: str) -> None:
        if self._value_label.text() == text:
            return
        self._value_label.setText(text)
        self._fade_animation.stop()
        self._fade_animation.setStartValue(_FADE_START_OPACITY)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
