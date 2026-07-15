from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from boostx.core.services.boost.boost_service import BoostService
from boostx.ui.components.app_toggles_row import AppTogglesRow
from boostx.ui.components.connections_table import ConnectionsTable
from boostx.ui.controllers.app_boost_controller import AppBoostController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.pages.base_page import BasePage


class ConnectionPage(BasePage):
    boost_requested = Signal()

    def __init__(
        self,
        monitor_controller: MonitorController,
        boost_service: BoostService,
        boost_controller: AppBoostController,
        parent: QWidget | None = None,
    ) -> None:
        self._monitor_controller = monitor_controller
        self._boost_service = boost_service
        self._boost_controller = boost_controller
        super().__init__(
            title="Connection",
            subtitle="Live status and network details for your boosted applications",
            parent=parent,
        )

    def _build_body(self, layout: QVBoxLayout) -> None:
        self._toggles_row = AppTogglesRow(self._boost_service, self._boost_controller, self)
        layout.addWidget(self._toggles_row)
        layout.addSpacing(16)

        self._connections_table = ConnectionsTable(self._boost_service, self._monitor_controller, self)
        self._connections_table.boost_requested.connect(self.boost_requested.emit)
        layout.addWidget(self._connections_table, stretch=1)

    def shutdown(self) -> None:
        self._connections_table.shutdown()
