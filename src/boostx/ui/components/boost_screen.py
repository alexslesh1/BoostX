from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from boostx.config.palette import Palette
from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.boost_metrics import BoostMetricsProvider
from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.boost_active.average_fps_card import AverageFPSCard
from boostx.ui.components.boost_active.cpu_usage_card import CPUUsageCard
from boostx.ui.components.boost_active.packet_loss_card import PacketLossCard
from boostx.ui.components.boost_active.ping_widget import PingWidget
from boostx.ui.components.boost_active.power_plan_card import PowerPlanCard
from boostx.ui.components.boost_active.pulse_dot import PulseDot
from boostx.ui.components.boost_active.session_time_card import SessionTimeCard
from boostx.ui.components.card import Card
from boostx.ui.components.monogram import render_monogram_pixmap
from boostx.ui.components.status_chip import StatusChip

COVER_SIZE = QSize(168, 299)
_METRICS_INTERVAL_MS = 1000
_PREPARING_TEXT = "Preparing Boost..."
_LAUNCHING_TEXT = "Launching..."
_ACTIVE_TEXT = "Boost Active"
_STATS_COLUMNS = 2

_SEVERITY_PALETTE_ATTR = {
    "success": "SUCCESS",
    "error": "ERROR",
    "neutral": "TEXT_SECONDARY",
}


class BoostScreen(QWidget):
    back_requested = Signal()
    stop_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = Palette()
        self._metrics = BoostMetricsProvider()

        back_button = QPushButton("← Back", self)
        back_button.setObjectName("BoostScreenBackButton")
        back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        back_button.clicked.connect(self._on_back_clicked)
        back_row = QHBoxLayout()
        back_row.addWidget(back_button)
        back_row.addStretch(1)

        top_row = QHBoxLayout()
        top_row.setSpacing(28)
        top_row.addLayout(self._build_left_column(), stretch=0)
        top_row.addLayout(self._build_right_column(), stretch=1)

        card = Card(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.addLayout(top_row)

        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(10)
        outer_layout.addLayout(back_row)
        outer_layout.addWidget(card, stretch=1)

        self._timer = QTimer(self)
        self._timer.setInterval(_METRICS_INTERVAL_MS)
        self._timer.timeout.connect(self._on_metrics_tick)

    def _build_left_column(self) -> QVBoxLayout:
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
        left_column.setSpacing(8)
        left_column.addWidget(self._cover_label)
        left_column.addWidget(self._name_label)
        left_column.addWidget(self._installed_chip, alignment=Qt.AlignmentFlag.AlignLeft)
        left_column.addWidget(self._launcher_label)
        left_column.addStretch(1)
        return left_column

    def _build_right_column(self) -> QVBoxLayout:
        status_heading = QLabel("BOOST STATUS", self)
        status_heading.setObjectName("SecondaryPathLabel")

        self._status_dot = PulseDot(10, self)
        self._status_label = QLabel(_PREPARING_TEXT, self)
        self._status_label.setObjectName("BoostActiveStatusLabel")
        self._status_label.setWordWrap(True)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        status_row.addWidget(self._status_dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addWidget(self._status_label, alignment=Qt.AlignmentFlag.AlignVCenter)
        status_row.addStretch(1)

        stop_button = QPushButton("Stop Boost", self)
        stop_button.setObjectName("BoostStopButton")
        stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        stop_button.clicked.connect(self._on_stop_clicked)

        self._ping_widget = PingWidget(self)

        self._packet_loss_card = PacketLossCard(self)
        self._session_time_card = SessionTimeCard(self)
        self._power_plan_card = PowerPlanCard(self)
        self._average_fps_card = AverageFPSCard(self)
        self._cpu_usage_card = CPUUsageCard(self)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(10)
        stats_grid.setVerticalSpacing(10)
        for column in range(_STATS_COLUMNS):
            stats_grid.setColumnStretch(column, 1)
        stats_grid.addWidget(self._packet_loss_card, 0, 0)
        stats_grid.addWidget(self._session_time_card, 0, 1)
        stats_grid.addWidget(self._average_fps_card, 1, 0)
        stats_grid.addWidget(self._cpu_usage_card, 1, 1)
        stats_grid.addWidget(self._power_plan_card, 2, 0, 1, _STATS_COLUMNS)

        right_column = QVBoxLayout()
        right_column.setSpacing(4)
        right_column.addWidget(status_heading)
        right_column.addLayout(status_row)
        right_column.addSpacing(4)
        right_column.addWidget(stop_button, alignment=Qt.AlignmentFlag.AlignLeft)
        right_column.addSpacing(10)
        right_column.addWidget(self._ping_widget, stretch=1)
        right_column.addSpacing(10)
        right_column.addLayout(stats_grid)
        return right_column

    def start(self, entry: BoostCatalogEntry, status: BoostAppStatus, icon_path: Path | None) -> None:
        self._cover_label.setPixmap(self._load_cover(entry, icon_path))
        self._name_label.setText(entry.display_name)
        self._installed_chip.setText("Installed" if status.installed else "Not Installed")
        self._installed_chip.set_severity("success" if status.installed else "neutral")
        self._launcher_label.setText(f"Launcher: {(status.source or 'Manual').title()}")

        self._set_status(_PREPARING_TEXT, "neutral", pulsing=True)
        self._ping_widget.reset()
        for card in (
            self._packet_loss_card,
            self._session_time_card,
            self._power_plan_card,
            self._average_fps_card,
            self._cpu_usage_card,
        ):
            card.reset()

        self._metrics.start()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()

    def on_step_started(self, step_key: str) -> None:
        text = _LAUNCHING_TEXT if step_key == "launch" else _PREPARING_TEXT
        self._set_status(text, "neutral", pulsing=True)

    def on_sequence_failed(self, message: str) -> None:
        self._set_status(message or "Boost Failed", "error", pulsing=False)
        self._timer.stop()

    def on_sequence_finished(self, success: bool) -> None:
        if not success:
            return
        self._set_status(_ACTIVE_TEXT, "success", pulsing=True)

    def _set_status(self, text: str, severity: str, *, pulsing: bool) -> None:
        self._status_label.setText(text)
        self._status_label.setProperty("severity", severity)
        style = self._status_label.style()
        style.unpolish(self._status_label)
        style.polish(self._status_label)

        self._status_dot.set_color(getattr(self._palette, _SEVERITY_PALETTE_ATTR[severity]))
        self._status_dot.set_pulsing(pulsing)

    @staticmethod
    def _load_cover(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, COVER_SIZE)

    def _on_metrics_tick(self) -> None:
        snapshot = self._metrics.sample()
        self._ping_widget.update_ping(snapshot.ping_ms)
        self._packet_loss_card.update_percent(snapshot.packet_loss_percent)
        self._session_time_card.update_seconds(snapshot.session_seconds)
        self._power_plan_card.update_plan(snapshot.power_plan)
        self._average_fps_card.update_fps(snapshot.average_fps)
        self._cpu_usage_card.update_percent(snapshot.cpu_usage_percent)

    def _on_back_clicked(self) -> None:
        self.back_requested.emit()

    def _on_stop_clicked(self) -> None:
        self.stop_requested.emit()
