from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.core.services.api.session_manager import SessionManager
from boostx.core.services.boost.boost_repository import BoostRepository
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.monitor.system_monitor_service import SystemMonitorService
from boostx.core.services.vpn.vpn_coordinator import VpnCoordinator
from boostx.ui.components.sidebar.sidebar import Sidebar
from boostx.ui.components.title_bar.title_bar import TitleBar
from boostx.ui.controllers.app_boost_controller import AppBoostController
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.component_setup_controller import ComponentSetupController
from boostx.ui.controllers.discord_vpn_controller import DiscordVpnController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.controllers.telegram_vpn_controller import TelegramVpnController
from boostx.ui.main_window.frameless_mixin import FramelessWindowMixin
from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget
from boostx.ui.navigation.page_router import PageRouter
from boostx.ui.components.sidebar.nav_item import NAV_ITEMS
from boostx.ui.pages.about_page import AboutPage
from boostx.ui.pages.account_page import AccountPage
from boostx.ui.pages.boost_page import BoostPage
from boostx.ui.pages.cleaner_page import CleanerPage
from boostx.ui.pages.connection_page import ConnectionPage
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
        self._boost_sequence_controller = BoostSequenceController(self._boost_service, parent=self)
        self._vpn_coordinator = VpnCoordinator()
        self._discord_vpn_controller = DiscordVpnController(
            self._session_manager, self._vpn_coordinator, parent=self
        )
        self._telegram_vpn_controller = TelegramVpnController(
            self._session_manager, self._vpn_coordinator, parent=self
        )
        self._app_boost_controller = AppBoostController(
            self._boost_service,
            self._boost_sequence_controller,
            self._discord_vpn_controller,
            self._telegram_vpn_controller,
            parent=self,
        )

        self._title_bar = TitleBar("Nexora", self)
        self._offline_banner = QLabel(
            "Offline — showing cached data. Changes will sync when reconnected.", self
        )
        self._offline_banner.setObjectName("OfflineBanner")
        self._offline_banner.setVisible(self._session_manager.is_offline)
        self._session_manager.offline_changed.connect(self._offline_banner.setVisible)

        self._setup_banner = QLabel("", self)
        self._setup_banner.setObjectName("OfflineBanner")
        self._setup_banner.setVisible(False)
        self._component_setup_controller = ComponentSetupController(parent=self)
        self._component_setup_controller.progress.connect(self._on_setup_progress)
        self._component_setup_controller.finished.connect(self._on_setup_finished)

        self._sidebar = Sidebar(self)
        self._stack = FadeStackedWidget(self)
        self._router = PageRouter(self._stack)

        self._register_pages()
        self._build_layout()
        self._connect_signals()

        self._monitor_controller.start()
        self._component_setup_controller.run_if_needed()

    def _register_pages(self) -> None:
        boost_page_index = next(item.page_index for item in NAV_ITEMS if item.key == "boost")
        connection_page_index = next(item.page_index for item in NAV_ITEMS if item.key == "connection")

        self._home_page = HomePage(
            self._monitor_controller, self._boost_service, self._app_boost_controller, self._stack
        )

        self._boost_page = BoostPage(
            self._boost_service,
            self._boost_sequence_controller,
            self._discord_vpn_controller,
            self._telegram_vpn_controller,
            self._stack,
        )
        # Once the user actually starts a boost from the Boost page, jump to
        # Connection so they immediately see its live status there.
        self._boost_sequence_controller.sequence_finished.connect(
            lambda success: self._sidebar.select_page(connection_page_index) if success else None
        )
        self._discord_vpn_controller.started.connect(lambda: self._sidebar.select_page(connection_page_index))
        self._telegram_vpn_controller.started.connect(lambda: self._sidebar.select_page(connection_page_index))

        self._connection_page = ConnectionPage(
            self._monitor_controller, self._boost_service, self._app_boost_controller, self._stack
        )
        self._connection_page.boost_requested.connect(lambda: self._sidebar.select_page(boost_page_index))

        self._cleaner_page = CleanerPage(self._stack)
        self._tweaks_page = TweaksPage(self._stack)

        pages = {
            0: self._home_page,
            1: self._boost_page,
            2: self._connection_page,
            3: self._cleaner_page,
            4: self._tweaks_page,
            5: SettingsPage(self._boost_service, self._stack),
            6: AccountPage(self._session_manager, self._stack),
            7: AboutPage(self._stack),
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
        outer_layout.addWidget(self._setup_banner)

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

    def _on_setup_progress(self, message: str) -> None:
        self._setup_banner.setText(message)
        self._setup_banner.setVisible(True)

    def _on_setup_finished(self, _success: bool) -> None:
        self._setup_banner.setVisible(False)

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
        self._connection_page.shutdown()
        self._app_boost_controller.shutdown()
        self._monitor_controller.shutdown()
        self._boost_sequence_controller.shutdown()
        self._discord_vpn_controller.shutdown()
        self._telegram_vpn_controller.shutdown()
        self._vpn_coordinator.shutdown()
        self._cleaner_page.shutdown()
        self._tweaks_page.shutdown()
        self._boost_repository.close()
        super().closeEvent(event)
