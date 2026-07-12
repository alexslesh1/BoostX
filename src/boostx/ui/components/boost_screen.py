import random
import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.card import Card
from boostx.ui.components.monogram import render_monogram_pixmap
from boostx.ui.components.status_chip import StatusChip

COVER_SIZE = QSize(220, 391)
_UPDATE_INTERVAL_MS = 1000
_PREPARING_TEXT = "Preparing Boost..."
_LAUNCHING_TEXT = "Launching..."
_ACTIVE_TEXT = "Boost Active"


def _divider() -> QFrame:
    line = QFrame()
    line.setObjectName("BoostScreenDivider")
    line.setFixedHeight(1)
    return line


class BoostScreen(QWidget):
    back_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._start_time = 0.0

        back_button = QPushButton("← Back", self)
        back_button.setObjectName("BoostScreenBackButton")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self._on_back_clicked)
        back_row = QHBoxLayout()
        back_row.addWidget(back_button)
        back_row.addStretch(1)

        self._cover_label = QLabel(self)
        self._cover_label.setFixedSize(COVER_SIZE)
        self._cover_label.setScaledContents(True)

        self._name_label = QLabel("", self)
        self._name_label.setObjectName("PageHeading")
        self._name_label.setWordWrap(True)

        self._installed_chip = StatusChip("Installed", "success", self)
        self._launcher_label = QLabel("", self)
        self._launcher_label.setObjectName("SecondaryPathLabel")

        left_column = QVBoxLayout()
        left_column.setSpacing(10)
        left_column.addWidget(self._cover_label)
        left_column.addWidget(self._name_label)
        left_column.addWidget(self._installed_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        left_column.addWidget(self._launcher_label)
        left_column.addStretch(1)

        status_heading = QLabel("BOOST STATUS", self)
        status_heading.setObjectName("SecondaryPathLabel")
        self._status_label = QLabel(_PREPARING_TEXT, self)
        self._status_label.setObjectName("BoostScreenStatusLabel")
        self._status_label.setWordWrap(True)

        right_column = QVBoxLayout()
        right_column.setSpacing(6)
        right_column.addWidget(status_heading)
        right_column.addWidget(self._status_label)
        right_column.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(32)
        top_row.addLayout(left_column, stretch=0)
        top_row.addLayout(right_column, stretch=1)

        self._stat_labels: dict[str, QLabel] = {}
        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(24)
        stats_grid.setVerticalSpacing(10)
        for row, (key, title) in enumerate(
            (
                ("ping", "Current Ping"),
                ("fps", "Average FPS"),
                ("cpu", "CPU Usage"),
                ("gpu", "GPU Usage"),
                ("ram", "RAM Usage"),
                ("cpu_temp", "CPU Temperature"),
                ("gpu_temp", "GPU Temperature"),
                ("session", "Session Time"),
                ("power_plan", "Current Power Plan"),
            )
        ):
            label = QLabel(title, self)
            label.setObjectName("BoostScreenStatRow")
            value = QLabel("—", self)
            value.setObjectName("StatCardValue")
            self._stat_labels[key] = value
            stats_grid.addWidget(label, row, 0)
            stats_grid.addWidget(value, row, 1)

        boost_status_row_label = QLabel("Boost Status", self)
        boost_status_row_label.setObjectName("BoostScreenStatRow")
        self._boost_status_chip = StatusChip("Preparing", "neutral", self)
        stats_grid.addWidget(boost_status_row_label, stats_grid.rowCount(), 0)
        stats_grid.addWidget(self._boost_status_chip, stats_grid.rowCount() - 1, 1)

        stop_button = QPushButton("Stop Boost", self)
        stop_button.setObjectName("BoostStopButton")
        stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_button.clicked.connect(self._on_stop_clicked)
        stop_row = QHBoxLayout()
        stop_row.addStretch(1)
        stop_row.addWidget(stop_button)

        card = Card(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.setSpacing(20)
        card_layout.addLayout(top_row)
        card_layout.addWidget(_divider())
        card_layout.addLayout(stats_grid)
        card_layout.addWidget(_divider())
        card_layout.addLayout(stop_row)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(card)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(16)
        outer_layout.addLayout(back_row)
        outer_layout.addWidget(scroll_area, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(_UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self._update_values)

    def start(self, entry: BoostCatalogEntry, status: BoostAppStatus, icon_path: Path | None) -> None:
        self._cover_label.setPixmap(self._load_cover(entry, icon_path))
        self._name_label.setText(entry.display_name)
        self._installed_chip.setText("Installed" if status.installed else "Not Installed")
        self._installed_chip.set_severity("success" if status.installed else "neutral")
        self._launcher_label.setText(f"Launcher: {(status.source or 'Manual').title()}")

        self._status_label.setText(_PREPARING_TEXT)
        self._boost_status_chip.setText("Preparing")
        self._boost_status_chip.set_severity("neutral")
        for label in self._stat_labels.values():
            label.setText("—")

        self._start_time = time.monotonic()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def on_step_started(self, step_key: str) -> None:
        self._status_label.setText(_LAUNCHING_TEXT if step_key == "launch" else _PREPARING_TEXT)

    def on_sequence_failed(self, message: str) -> None:
        self._status_label.setText(message or "Boost Failed")
        self._boost_status_chip.setText("Failed")
        self._boost_status_chip.set_severity("error")
        self._timer.stop()

    def on_sequence_finished(self, success: bool) -> None:
        if not success:
            return
        self._status_label.setText(_ACTIVE_TEXT)
        self._boost_status_chip.setText("Active")
        self._boost_status_chip.set_severity("success")

    @staticmethod
    def _load_cover(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, COVER_SIZE)

    def _update_values(self) -> None:
        elapsed = int(time.monotonic() - self._start_time)
        minutes, seconds = divmod(elapsed, 60)
        self._stat_labels["ping"].setText(f"{random.randint(12, 45)} ms")
        self._stat_labels["fps"].setText(f"{random.randint(90, 240)} FPS")
        self._stat_labels["cpu"].setText(f"{random.randint(20, 70)}%")
        self._stat_labels["gpu"].setText(f"{random.randint(40, 95)}%")
        self._stat_labels["ram"].setText(f"{random.randint(30, 80)}%")
        self._stat_labels["cpu_temp"].setText(f"{random.randint(45, 75)}°C")
        self._stat_labels["gpu_temp"].setText(f"{random.randint(55, 85)}°C")
        self._stat_labels["session"].setText(f"{minutes:02d}:{seconds:02d}")
        self._stat_labels["power_plan"].setText("High Performance")

    def _on_back_clicked(self) -> None:
        self.back_requested.emit()

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()
