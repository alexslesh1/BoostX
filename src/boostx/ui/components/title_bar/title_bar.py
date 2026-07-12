from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.ui.components.title_bar.window_control_button import WindowControlButton


class TitleBar(QWidget):
    drag_delta_requested = Signal(QPoint)
    minimize_requested = Signal()
    maximize_toggle_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(LayoutConstants().TITLEBAR_HEIGHT)

        self._drag_last_pos: QPoint | None = None

        self._title_label = QLabel(title, self)
        self._title_label.setObjectName("TitleBarLabel")

        icons_dir = AppPaths.window_icons_dir()
        self._minimize_button = WindowControlButton(icons_dir / "minimize.svg", self)
        self._maximize_button = WindowControlButton(icons_dir / "maximize.svg", self)
        self._close_button = WindowControlButton(icons_dir / "close.svg", self)
        self._close_button.setObjectName("CloseButton")

        self._minimize_button.clicked.connect(self.minimize_requested.emit)
        self._maximize_button.clicked.connect(self.maximize_toggle_requested.emit)
        self._close_button.clicked.connect(self.close_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._title_label)
        layout.addStretch(1)
        layout.addWidget(self._minimize_button)
        layout.addWidget(self._maximize_button)
        layout.addWidget(self._close_button)

    def set_maximized(self, is_maximized: bool) -> None:
        icon_name = "restore.svg" if is_maximized else "maximize.svg"
        self._maximize_button.set_icon_path(AppPaths.window_icons_dir() / icon_name)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_last_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_last_pos is not None:
            current_pos = event.globalPosition().toPoint()
            self.drag_delta_requested.emit(current_pos - self._drag_last_pos)
            self._drag_last_pos = current_pos
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_last_pos = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.maximize_toggle_requested.emit()
        super().mouseDoubleClickEvent(event)
