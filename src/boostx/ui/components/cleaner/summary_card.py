from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.cleaner.models import CleanResult
from boostx.ui.components.card import Card
from boostx.ui.utils.formatting import format_bytes

_FADE_DURATION_MS = 300


class CleaningSummaryCard(Card):
    """Fades in once a cleaning cycle completes; hidden before that."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.hide()

        title = QLabel("Cleaning Complete", self)
        title.setObjectName("CleanerSectionTitle")

        self._freed_value = self._build_stat_column("Freed Space")
        self._memory_value = self._build_stat_column("Optimized Memory")
        self._duration_value = self._build_stat_column("Scan Duration")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(32)
        stats_row.addLayout(self._freed_value[0])
        stats_row.addLayout(self._memory_value[0])
        stats_row.addLayout(self._duration_value[0])
        stats_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addLayout(stats_row)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(_FADE_DURATION_MS)

    def _build_stat_column(self, label_text: str) -> tuple[QVBoxLayout, QLabel]:
        label = QLabel(label_text, self)
        label.setObjectName("MetricCardLabel")
        value = QLabel("—", self)
        value.setObjectName("MetricCardValue")
        column = QVBoxLayout()
        column.setSpacing(2)
        column.addWidget(label)
        column.addWidget(value)
        return column, value

    def show_summary(self, clean_result: CleanResult, memory_freed_bytes: int) -> None:
        self._freed_value[1].setText(format_bytes(clean_result.freed_bytes))
        self._memory_value[1].setText(format_bytes(memory_freed_bytes))
        self._duration_value[1].setText(f"{clean_result.duration_seconds:.0f} seconds")

        self.show()
        self._opacity_effect.setOpacity(0.0)
        self._fade_animation.stop()
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        self._fade_animation.start()
