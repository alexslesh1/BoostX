from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_stack import AuthStack
from boostx.ui.components.title_bar.title_bar import TitleBar
from boostx.ui.main_window.frameless_mixin import FramelessWindowMixin

_MIN_WIDTH = 480
_MIN_HEIGHT = 640


class AuthWindow(FramelessWindowMixin, QWidget):
    authenticated = Signal()

    def __init__(self, session_manager: SessionManager) -> None:
        super().__init__()
        self.setObjectName("AuthWindowRoot")
        self.setWindowTitle("Nexora")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumSize(_MIN_WIDTH, _MIN_HEIGHT)
        self.resize(_MIN_WIDTH, _MIN_HEIGHT)
        self.init_frameless()

        self._title_bar = TitleBar("Nexora", self)
        self._auth_stack = AuthStack(session_manager, self)
        self._auth_stack.authenticated.connect(self.authenticated.emit)

        margin = self._resize_margin
        layout = QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        layout.setSpacing(0)
        layout.addWidget(self._title_bar)
        layout.addWidget(self._auth_stack, stretch=1)

        self._title_bar.drag_delta_requested.connect(self._on_drag_delta)
        self._title_bar.minimize_requested.connect(self.showMinimized)
        self._title_bar.maximize_toggle_requested.connect(self._toggle_maximize)
        self._title_bar.close_requested.connect(self.close)

    def reset_to_login(self) -> None:
        self._auth_stack.reset_to_login()

    def _on_drag_delta(self, delta: QPoint) -> None:
        if not self.isMaximized():
            self.move(self.pos() + delta)

    def _toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self._title_bar.set_maximized(self.isMaximized())
