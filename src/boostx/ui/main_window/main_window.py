from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.core.services.api.session_manager import SessionManager
from boostx.core.services.boost.boost_repository import BoostRepository
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.monitor.system_monitor_service import SystemMonitorService
from boostx.ui.components.sidebar.sidebar import Sidebar
from boostx.ui.components.title_bar.title_bar import TitleBar
from boostx.ui.controllers.boost_discord_controller import BoostDiscordController
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.controllers.telegram_boost_controller import TelegramBoostController
from boostx.ui.main_window.frameless_mixin import FramelessWindowMixin
from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget
from boostx.ui.navigation.page_router import PageRouter
from boostx.ui.components.sidebar.nav_item import NAV_ITEMS
from boostx.ui.pages.about_page import AboutPage
from boostx.ui.pages.account_page import AccountPage
from boostx.ui.pages.boost_page import BoostPage
from boostx.ui.pages.cleaner_page import CleanerPage
from boostx.ui.pages.dashboard_page import DashboardPage
from boostx.ui.pages.monitor_page import MonitorPage
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
        self._boost_discord_controller = BoostDiscordController(self._session_manager, parent=self)
        self._telegram_boost_controller = TelegramBoostController(self._session_manager, parent=self)

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
        dashboard_page = DashboardPage(self._monitor_controller, self._boost_service, self._stack)
        boost_page_index = next(item.page_index for item in NAV_ITEMS if item.key == "boost")
        dashboard_page.boost_requested.connect(lambda: self._sidebar.select_page(boost_page_index))

        self._cleaner_page = CleanerPage(self._stack)
        self._tweaks_page = TweaksPage(self._stack)

        pages = {
            0: dashboard_page,
            1: MonitorPage(self._monitor_controller, self._stack),
            2: BoostPage(
                self._boost_service,
                self._boost_sequence_controller,
                self._boost_discord_controller,
                self._telegram_boost_controller,
                self._stack,
            ),
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
        self._monitor_controller.shutdown()
        self._boost_sequence_controller.shutdown()
        self._boost_discord_controller.shutdown()
        self._telegram_boost_controller.shutdown()
        self._cleaner_page.shutdown()
        self._tweaks_page.shutdown()
        self._boost_repository.close()
        super().closeEvent(event)
