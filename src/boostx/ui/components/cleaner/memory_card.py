from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.config.palette import Palette
from boostx.core.services.cleaner.models import MemoryOptimizationResult, MemorySnapshot
from boostx.ui.components.boost_active.pulse_dot import PulseDot
from boostx.ui.components.card import Card
from boostx.ui.components.progress_bar import ProgressBar
from boostx.ui.utils.formatting import format_bytes


class MemoryOptimizationCard(Card):
    optimize_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = Palette()

        title = QLabel("Memory Optimization", self)
        title.setObjectName("CleanerSectionTitle")

        self._usage_label = QLabel("— / — GB", self)
        self._usage_label.setObjectName("MetricCardValue")
        self._usage_bar = ProgressBar(self)

        self._available_title = QLabel("Available Memory", self)
        self._available_title.setObjectName("MetricCardLabel")
        self._available_value = QLabel("—", self)
        self._available_value.setObjectName("MetricCardValue")

        self._standby_title = QLabel("Standby Cache", self)
        self._standby_title.setObjectName("MetricCardLabel")
        self._standby_value = QLabel("—", self)
        self._standby_value.setObjectName("MetricCardValue")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)
        available_column = QVBoxLayout()
        available_column.setSpacing(2)
        available_column.addWidget(self._available_title)
        available_column.addWidget(self._available_value)
        standby_column = QVBoxLayout()
        standby_column.setSpacing(2)
        standby_column.addWidget(self._standby_title)
        standby_column.addWidget(self._standby_value)
        stats_row.addLayout(available_column)
        stats_row.addLayout(standby_column)
        stats_row.addStretch(1)

        self._optimize_button = QPushButton("Optimize Memory", self)
        self._optimize_button.setObjectName("CleanerPrimaryButton")
        self._optimize_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._optimize_button.clicked.connect(self.optimize_requested.emit)

        self._status_dot = PulseDot(8, self)
        self._status_dot.hide()
        self._status_label = QLabel("", self)
        self._status_label.setObjectName("CleanerResultLabel")
        self._status_label.hide()

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self._status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self._status_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self._usage_label)
        layout.addWidget(self._usage_bar)
        layout.addSpacing(10)
        layout.addLayout(stats_row)
        layout.addSpacing(14)
        layout.addWidget(self._optimize_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addLayout(status_row)

    def update_snapshot(self, snapshot: MemorySnapshot) -> None:
        used_gb = snapshot.used_bytes / (1024**3)
        total_gb = snapshot.total_bytes / (1024**3)
        self._usage_label.setText(f"{used_gb:.1f} / {total_gb:.0f} GB")
        percent = round((snapshot.used_bytes / snapshot.total_bytes) * 100) if snapshot.total_bytes else 0
        self._usage_bar.setValue(max(0, min(100, percent)))
        self._usage_bar.set_severity("warning" if percent >= 85 else "success")
        self._available_value.setText(format_bytes(snapshot.available_bytes))
        self._standby_value.setText(
            format_bytes(snapshot.standby_bytes) if snapshot.standby_bytes is not None else "—"
        )

    def set_busy(self, busy: bool) -> None:
        self._optimize_button.setEnabled(not busy)
        self._optimize_button.setText("Optimizing..." if busy else "Optimize Memory")
        self._status_dot.setVisible(busy)
        self._status_dot.set_color(self._palette.TEXT_SECONDARY)
        self._status_dot.set_pulsing(busy)
        if busy:
            self._status_label.setText("Analyzing memory usage...")
            self._status_label.show()

    def show_result(self, result: MemoryOptimizationResult) -> None:
        self._status_dot.hide()
        self._status_dot.set_pulsing(False)
        if result.already_optimized:
            self._status_label.setText("Memory is already optimized.")
        else:
            self._status_label.setText(f"Memory Optimized — Freed: {format_bytes(result.freed_bytes)}")
        self._status_label.show()
