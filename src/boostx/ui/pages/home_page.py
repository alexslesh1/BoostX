from PySide6.QtWidgets import QVBoxLayout, QWidget

from boostx.core.services.boost.boost_service import BoostService
from boostx.ui.components.app_toggles_row import AppTogglesRow
from boostx.ui.components.monitor_charts_panel import MonitorChartsPanel
from boostx.ui.controllers.app_boost_controller import AppBoostController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.pages.base_page import BasePage


class HomePage(BasePage):
    """Former DashboardPage, renamed, with Monitor's chart grid folded in
    below the pinned-app toggle row (Monitor is no longer a separate nav
    destination) and the connections table moved out to ConnectionPage."""

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
        super().__init__(title="Home", subtitle="Overview of your system status", parent=parent)

    def _build_body(self, layout: QVBoxLayout) -> None:
        self._toggles_row = AppTogglesRow(self._boost_service, self._boost_controller, self)
        layout.addWidget(self._toggles_row)
        layout.addSpacing(16)

        self._monitor_panel = MonitorChartsPanel(self._monitor_controller, self)
        layout.addWidget(self._monitor_panel, stretch=1)
