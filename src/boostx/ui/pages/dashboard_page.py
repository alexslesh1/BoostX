from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from boostx.config.paths import AppPaths
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG
from boostx.core.services.boost.icon_resolver import build_icon_index, resolve_icon_path
from boostx.core.services.monitor.system_snapshot import SystemSnapshot
from boostx.ui.components.boost_discord_card import BoostDiscordCard
from boostx.ui.components.card import Card
from boostx.ui.components.connection_row import ConnectionRow
from boostx.ui.components.stat_card import StatCard, severity_for_percent
from boostx.ui.controllers.boost_discord_controller import BoostDiscordController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.pages.base_page import BasePage
from boostx.ui.utils.formatting import format_bytes_per_sec, format_percent

_CONNECTIONS_REFRESH_MS = 3000


class DashboardPage(BasePage):
    boost_requested = Signal()

    def __init__(
        self,
        monitor_controller: MonitorController,
        boost_service: BoostService,
        boost_discord_controller: BoostDiscordController,
        parent: QWidget | None = None,
    ) -> None:
        # Must be assigned before super().__init__(), since it triggers _build_body() synchronously.
        self._monitor_controller = monitor_controller
        self._boost_service = boost_service
        self._boost_discord_controller = boost_discord_controller
        self._stat_cards: dict[str, StatCard] = {}
        self._last_ping_ms: float | None = None
        self._icon_index = build_icon_index(AppPaths.game_icons_dir())

        super().__init__(
            title="Dashboard",
            subtitle="Overview of your system status",
            parent=parent,
        )
        self._monitor_controller.snapshot_updated.connect(self._on_snapshot)

        self._connections_timer = QTimer(self)
        self._connections_timer.setInterval(_CONNECTIONS_REFRESH_MS)
        self._connections_timer.timeout.connect(self._refresh_connections)
        self._connections_timer.start()
        self._refresh_connections()

    def _build_body(self, layout: QVBoxLayout) -> None:
        icons_dir = AppPaths.icons_dir() / "stats"

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        for key, title in (
            ("cpu", "CPU"),
            ("gpu", "GPU"),
            ("ram", "RAM"),
            ("disk", "Disk"),
            ("network", "Network"),
        ):
            card = StatCard(icons_dir / f"{key}.svg", title, self)
            self._stat_cards[key] = card
            cards_layout.addWidget(card)
        layout.addLayout(cards_layout)

        layout.addSpacing(16)

        connections_card = Card(self)
        connections_layout = QVBoxLayout(connections_card)
        connections_layout.setContentsMargins(20, 16, 20, 16)
        connections_layout.setSpacing(4)

        title = QLabel("Current Connections", connections_card)
        title.setObjectName("StatCardTitle")
        connections_layout.addWidget(title)
        connections_layout.addSpacing(6)

        self._connections_stack = QStackedLayout()
        self._connections_stack.addWidget(self._build_rows_view(connections_card))
        self._connections_stack.addWidget(self._build_empty_state_view(connections_card))
        connections_layout.addLayout(self._connections_stack, stretch=1)

        layout.addWidget(connections_card, stretch=1)

        layout.addSpacing(16)
        layout.addWidget(BoostDiscordCard(self._boost_discord_controller, self))

    def _build_rows_view(self, parent: QWidget) -> QWidget:
        self._rows_container = QWidget(parent)
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(0)

        scroll_area = QScrollArea(parent)
        scroll_area.setWidget(self._rows_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        return scroll_area

    def _build_empty_state_view(self, parent: QWidget) -> QWidget:
        empty_state = QWidget(parent)

        title_label = QLabel("No Active Connections", empty_state)
        title_label.setObjectName("EmptyStateTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle_label = QLabel(
            "Launch an application using Boost to see active connections here.", empty_state
        )
        subtitle_label.setObjectName("EmptyStateSubtitle")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle_label.setWordWrap(True)

        boost_button = QPushButton("Boost", empty_state)
        boost_button.setObjectName("BoostCtaButton")
        boost_button.clicked.connect(self.boost_requested.emit)

        content_layout = QVBoxLayout()
        content_layout.setSpacing(8)
        content_layout.addWidget(title_label)
        content_layout.addWidget(subtitle_label)
        content_layout.addSpacing(8)
        content_layout.addWidget(boost_button, alignment=Qt.AlignmentFlag.AlignHCenter)

        outer_layout = QVBoxLayout(empty_state)
        outer_layout.addStretch(1)
        row_layout = QHBoxLayout()
        row_layout.addStretch(1)
        row_layout.addLayout(content_layout)
        row_layout.addStretch(1)
        outer_layout.addLayout(row_layout)
        outer_layout.addStretch(1)
        return empty_state

    def _refresh_connections(self) -> None:
        running_keys = self._boost_service.get_running_app_keys()

        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        if not running_keys:
            self._connections_stack.setCurrentIndex(1)
            return

        self._connections_stack.setCurrentIndex(0)
        for entry in BOOST_CATALOG:
            if entry.key not in running_keys:
                continue
            icon_path = resolve_icon_path(entry.display_name, self._icon_index)
            row = ConnectionRow(entry, icon_path, self._rows_container)
            row.set_detail(self._last_ping_ms)
            self._rows_layout.addWidget(row)
        self._rows_layout.addStretch(1)

    def _on_snapshot(self, snapshot: SystemSnapshot) -> None:
        if snapshot.ping.reachable and snapshot.ping.latency_ms is not None:
            self._last_ping_ms = snapshot.ping.latency_ms

        cpu_severity, cpu_label = severity_for_percent(snapshot.cpu.percent)
        self._stat_cards["cpu"].update_value(
            format_percent(snapshot.cpu.percent), snapshot.cpu.percent, cpu_label, cpu_severity
        )

        if snapshot.gpu.available and snapshot.gpu.load_percent is not None:
            gpu_severity, gpu_label = severity_for_percent(snapshot.gpu.load_percent)
            self._stat_cards["gpu"].update_value(
                format_percent(snapshot.gpu.load_percent), snapshot.gpu.load_percent, gpu_label, gpu_severity
            )
        else:
            self._stat_cards["gpu"].set_unavailable()

        ram_severity, ram_label = severity_for_percent(snapshot.ram.percent)
        self._stat_cards["ram"].update_value(
            format_percent(snapshot.ram.percent), snapshot.ram.percent, ram_label, ram_severity
        )

        primary_disk = snapshot.disk.partitions[0] if snapshot.disk.partitions else None
        if primary_disk is not None:
            disk_severity, disk_label = severity_for_percent(primary_disk.percent)
            self._stat_cards["disk"].update_value(
                format_percent(primary_disk.percent), primary_disk.percent, disk_label, disk_severity
            )
        else:
            self._stat_cards["disk"].set_unavailable()

        if snapshot.network.local_ip is None:
            self._stat_cards["network"].update_value("Offline", None, "No connection", "error")
        else:
            if snapshot.ping.reachable and snapshot.ping.latency_ms is not None:
                status_text = f"{snapshot.ping.latency_ms:.0f} ms"
            else:
                status_text = "Connected"
            download_text = format_bytes_per_sec(snapshot.network.recv_bytes_per_sec)
            self._stat_cards["network"].update_value(f"{download_text} ↓", None, status_text, "success")
