from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedLayout, QVBoxLayout, QWidget

from boostx.config.paths import AppPaths
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG
from boostx.core.services.boost.icon_resolver import build_icon_index, resolve_icon_path
from boostx.core.services.monitor.system_snapshot import SystemSnapshot
from boostx.ui.components.card import Card
from boostx.ui.components.connection_table_row import ConnectionTableHeader, ConnectionTableRow
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.controllers.tunnel_controller import TunnelController

_REFRESH_MS = 3000


class ConnectionsTable(QWidget):
    """Applications that are running or routed, with live figures from the
    routing engine for the ones that go through Nexora."""

    boost_requested = Signal()

    def __init__(
        self,
        service: BoostService,
        monitor_controller: MonitorController,
        tunnel_controller: TunnelController,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._monitor_controller = monitor_controller
        self._tunnel = tunnel_controller
        self._icon_index = build_icon_index(AppPaths.game_icons_dir())
        self._last_ping_ms: float | None = None
        self._rows: dict[str, ConnectionTableRow] = {}

        card = Card(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(0, 16, 0, 16)
        card_layout.setSpacing(4)

        title = QLabel("Current Connections", card)
        title.setObjectName("StatCardTitle")
        title.setContentsMargins(20, 0, 20, 0)
        card_layout.addWidget(title)
        card_layout.addSpacing(6)
        card_layout.addWidget(ConnectionTableHeader(card))

        self._stack = QStackedLayout()
        self._stack.addWidget(self._build_rows_view(card))
        self._stack.addWidget(self._build_empty_state_view(card))
        card_layout.addLayout(self._stack, stretch=1)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(card)

        self._monitor_controller.snapshot_updated.connect(self._on_snapshot)
        self._tunnel.snapshot_updated.connect(lambda _snapshot: self._update_rows())
        self._tunnel.app_enabled.connect(lambda _key: self.refresh())
        self._tunnel.app_disabled.connect(lambda _key: self.refresh())
        self._timer = QTimer(self)
        self._timer.setInterval(_REFRESH_MS)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def shutdown(self) -> None:
        self._timer.stop()

    def refresh(self) -> None:
        shown_keys = self._service.get_running_app_keys() | {
            entry.key for entry in BOOST_CATALOG if self._tunnel.is_enabled(entry.key)
        }
        if shown_keys != set(self._rows):
            self._rebuild_rows(shown_keys)
        self._stack.setCurrentIndex(0 if self._rows else 1)
        self._update_rows()

    def _rebuild_rows(self, shown_keys: set[str]) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

        for entry in BOOST_CATALOG:
            if entry.key not in shown_keys:
                continue
            icon_path = resolve_icon_path(entry.display_name, self._icon_index)
            row = ConnectionTableRow(entry, icon_path, self._rows_container)
            self._rows_layout.addWidget(row)
            self._rows[entry.key] = row
        self._rows_layout.addStretch(1)

    def _update_rows(self) -> None:
        snapshot = self._tunnel.snapshot
        for app_key, row in self._rows.items():
            if self._tunnel.is_enabled(app_key):
                row.set_routed(snapshot.relay_name, snapshot.connected, snapshot.flows_for(app_key))
                # For a routed application the figure that matters is the
                # round trip to the relay it actually goes through.
                row.set_ping(snapshot.rtt_ms if snapshot.connected else None)
            else:
                row.set_direct()
                row.set_ping(self._last_ping_ms)

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

    def _on_snapshot(self, snapshot: SystemSnapshot) -> None:
        if snapshot.ping.reachable and snapshot.ping.latency_ms is not None:
            self._last_ping_ms = snapshot.ping.latency_ms
            for app_key, row in self._rows.items():
                if not self._tunnel.is_enabled(app_key):
                    row.set_ping(self._last_ping_ms)
