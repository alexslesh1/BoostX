from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QPixmap, QResizeEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_stack import AuthStack
from boostx.ui.auth.marketing_panel import MarketingPanel
from boostx.ui.components.title_bar.title_bar import TitleBar
from boostx.ui.main_window.frameless_mixin import FramelessWindowMixin

_AUTH_STACK_WIDTH = 460
_BACKGROUND_IMAGE_NAME = "auth_background.png"


class AuthWindow(FramelessWindowMixin, QWidget):
    authenticated = Signal()

    def __init__(self, session_manager: SessionManager) -> None:
        super().__init__()
        layout_constants = LayoutConstants()
        self.setObjectName("AuthWindowRoot")
        self.setWindowTitle("Nexora")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(layout_constants.MIN_WIDTH, layout_constants.MIN_HEIGHT)
        self.resize(layout_constants.MIN_WIDTH, layout_constants.MIN_HEIGHT)
        self.init_frameless()

        self._background_pixmap: QPixmap | None = None
        self._background_label = self._build_background_label()

        self._title_bar = TitleBar("Nexora", self)
        self._marketing_panel = MarketingPanel(self)
        self._auth_stack = AuthStack(session_manager, self)
        self._auth_stack.setFixedWidth(_AUTH_STACK_WIDTH)
        self._auth_stack.authenticated.connect(self.authenticated.emit)

        content_row = QHBoxLayout()
        content_row.setContentsMargins(0, 0, 0, 0)
        content_row.setSpacing(0)
        content_row.addWidget(self._marketing_panel, stretch=1)
        content_row.addWidget(self._auth_stack, stretch=0)

        margin = self._resize_margin
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(0)
        layout.addWidget(self._title_bar)
        layout.addLayout(content_row, stretch=1)

        self._title_bar.drag_delta_requested.connect(self._on_drag_delta)
        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.maximize_toggle_requested.connect(self._toggle_maximize)
        self._title_bar.close_requested.connect(self.close)

    def _build_background_label(self) -> QLabel | None:
        # No image at this path yet -- the QSS gradient on AuthWindowRoot is
        # the fallback. Drop the real 1300x900 reference photo in as
        # resources/images/auth_background.png for exact visual fidelity;
        # this label will then cover-crop and repaint it on every resize.
        image_path = AppPaths.images_dir() / _BACKGROUND_IMAGE_NAME
        if not image_path.is_file():
            return None
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            return None
        self._background_pixmap = pixmap
        label = QLabel(self)
        label.setObjectName("AuthBackgroundLabel")
        label.lower()
        return label

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._background_label is not None and self._background_pixmap is not None:
            self._background_label.setGeometry(self.rect())
            scaled = self._background_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x = max(0, (scaled.width() - self.width()) // 2)
            y = max(0, (scaled.height() - self.height()) // 2)
            self._background_label.setPixmap(scaled.copy(x, y, self.width(), self.height()))

    def reset_to_login(self) -> None:
        self._auth_stack.reset_to_login()

    def show_login(self) -> None:
        self._auth_stack.show_login()

    def _on_drag_delta(self, delta: QPoint) -> None:
        if not self.isMaximized():
            self.move(self.pos() + delta)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._title_bar.set_maximized(self.isMaximized())
