from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.core.services.api.session_manager import SessionManager
from boostx.core.services.boost.boost_repository import BoostRepository
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.discord_boost.discord_launcher import (
    discord_install_dir,
    find_discord_executable,
    launch_discord_plain,
)
from boostx.core.services.monitor.system_monitor_service import SystemMonitorService
from boostx.core.services.telegram_boost.telegram_launcher import find_telegram_executable, launch_telegram
from boostx.core.services.tunnel.tunnel_service import TunnelService
from boostx.ui.components.sidebar.sidebar import Sidebar
from boostx.ui.components.title_bar.title_bar import TitleBar
from boostx.ui.controllers.app_boost_controller import AppBoostController
from boostx.ui.controllers.app_tunnel_controller import AppTunnelController
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.controllers.tunnel_controller import TunnelController
from boostx.ui.main_window.frameless_mixin import FramelessWindowMixin
from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget
from boostx.ui.navigation.page_router import PageRouter
from boostx.ui.components.sidebar.nav_item import NAV_ITEMS
from boostx.ui.pages.about_page import AboutPage
from boostx.ui.pages.account_page import AccountPage
from boostx.ui.pages.boost_page import BoostPage
from boostx.ui.pages.cleaner_page import CleanerPage
from boostx.ui.pages.connection_page import ConnectionPage
from boostx.ui.pages.dashboard_page import DashboardPage
from boostx.ui.pages.home_page import HomePage
from boostx.ui.pages.settings_page import SettingsPage
from boostx.ui.pages.tweaks_page import TweaksPage


class MainWindow(FramelessWindowMixin, QWidget):
    def __init__(self, session_manager: SessionManager) -> None:
        super().__init__()
        self._session_manager = session_manager
        self.setObjectName("MainWindowRoot")
        self.setWindowTitle("Nexora")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        layout_constants = LayoutConstants()
        self.setMinimumSize(layout_constants.MIN_WIDTH, layout_constants.MIN_HEIGHT)
        self.init_frameless()

        self._monitor_controller = MonitorController(SystemMonitorService(), parent=self)
        self._boost_repository = BoostRepository(AppPaths.data_dir() / "boost.db")
        self._boost_service = BoostService(self._boost_repository)
        # One tunnel carries every boosted application; the engine behind
        # it is only started (one administrator prompt) the first time a
        # boost actually needs it.
        self._tunnel_controller = TunnelController(
            TunnelService(self._session_manager.fetch_relay_session), parent=self
        )
        self._boost_sequence_controller = BoostSequenceController(
            self._boost_service, self._tunnel_controller, parent=self
        )
        self._communication_controllers = {
            "discord": AppTunnelController(
                "discord",
                "Discord",
                find_discord_executable,
                launch_discord_plain,
                discord_install_dir,
                self._tunnel_controller,
                parent=self,
            ),
            "telegram": AppTunnelController(
                "telegram",
                "Telegram",
                find_telegram_executable,
                launch_telegram,
                lambda executable: executable.parent,
                self._tunnel_controller,
                parent=self,
            ),
        }
        self._app_boost_controller = AppBoostController(
            self._boost_service,
            self._boost_sequence_controller,
            self._communication_controllers,
            self._tunnel_controller,
            parent=self,
        )

        self._title_bar = TitleBar("Nexora", self)
        self._offline_banner = QLabel(
            "Offline — showing cached data. Changes will sync when reconnected.", self
        )
        self._offline_banner.setObjectName("OfflineBanner")
        self._offline_banner.setVisible(self._session_manager.is_offline)
        self._session_manager.offline_changed.connect(self._offline_banner.setVisible)

        self._sidebar = Sidebar(self)
        self._stack = FadeStackedWidget(self)
        self._router = PageRouter(self._stack)

        self._register_pages()
        self._build_layout()
        self._connect_signals()

        self._monitor_controller.start()

    def _register_pages(self) -> None:
        boost_page_index = next(item.page_index for item in NAV_ITEMS if item.key == "boost")
        connection_page_index = next(item.page_index for item in NAV_ITEMS if item.key == "connection")

        self._home_page = HomePage(self._stack)
        self._dashboard_page = DashboardPage(self._monitor_controller, self._stack)

        self._boost_page = BoostPage(
            self._boost_service,
            self._boost_sequence_controller,
            self._communication_controllers,
            self._tunnel_controller,
            self._stack,
        )
        self._boost_page.stop_requested.connect(self._app_boost_controller.stop)
        # Once the user actually starts a boost from the Boost page, jump to
        # Connection so they immediately see its live status there.
        self._boost_sequence_controller.sequence_finished.connect(
            lambda success: self._sidebar.select_page(connection_page_index) if success else None
        )
        for controller in self._communication_controllers.values():
            controller.started.connect(lambda: self._sidebar.select_page(connection_page_index))

        self._connection_page = ConnectionPage(
            self._monitor_controller,
            self._boost_service,
            self._app_boost_controller,
            self._tunnel_controller,
            self._stack,
        )
        self._connection_page.boost_requested.connect(lambda: self._sidebar.select_page(boost_page_index))

        self._cleaner_page = CleanerPage(self._stack)
        self._tweaks_page = TweaksPage(self._stack)

        pages = {
            0: self._home_page,
            1: self._connection_page,
            2: self._boost_page,
            3: self._dashboard_page,
            4: self._tweaks_page,
            5: self._cleaner_page,
            6: AccountPage(self._session_manager, self._stack),
            7: SettingsPage(self._boost_service, self._stack),
            8: AboutPage(self._stack),
        }
        for index, page in pages.items():
            self._router.register_page(index, page)

    def _build_layout(self) -> None:
        margin = self._resize_margin
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(margin, margin, margin, margin)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(self._title_bar)
        outer_layout.addWidget(self._offline_banner)

        content_layout = QHBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._sidebar)
        content_layout.addWidget(self._stack, stretch=1)
        outer_layout.addLayout(content_layout, stretch=1)

    def _connect_signals(self) -> None:
        self._title_bar.drag_delta_requested.connect(self._on_drag_delta)
        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.maximize_toggle_requested.connect(self._toggle_maximize)
        self._title_bar.close_requested.connect(self.close)
        self._sidebar.page_changed.connect(self._router.navigate_to)

    def _on_drag_delta(self, delta: QPoint) -> None:
        if not self.isMaximized():
            self.move(self.pos() + delta)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._title_bar.set_maximized(self.isMaximized())

    def closeEvent(self, event: QCloseEvent) -> None:
        # All background pollers that touch _boost_repository (directly or
        # via _boost_service) must be stopped before it's closed below —
        # otherwise a still-running timer keeps hitting a closed sqlite3
        # connection on every tick with no way to stop itself.
        #
        # Each step runs independently: a failure in one must never skip
        # the rest. In particular the tunnel controller's shutdown is what
        # stops the routing engine, and _boost_repository.close() is what
        # releases the database.
        self._safe_shutdown("connection page", self._connection_page.shutdown)
        self._safe_shutdown("app boost controller", self._app_boost_controller.shutdown)
        self._safe_shutdown("monitor controller", self._monitor_controller.shutdown)
        self._safe_shutdown("boost sequence controller", self._boost_sequence_controller.shutdown)
        for name, controller in self._communication_controllers.items():
            self._safe_shutdown(f"{name} routing controller", controller.shutdown)
        self._safe_shutdown("tunnel controller (stops the routing engine)", self._tunnel_controller.shutdown)
        self._safe_shutdown("cleaner page", self._cleaner_page.shutdown)
        self._safe_shutdown("tweaks page", self._tweaks_page.shutdown)
        self._safe_shutdown("boost repository", self._boost_repository.close)
        super().closeEvent(event)

    @staticmethod
    def _safe_shutdown(name: str, shutdown: Callable[[], None]) -> None:
        try:
            shutdown()
        except Exception:
            logger.exception(f"Error shutting down {name} -- continuing with the rest of app teardown")
