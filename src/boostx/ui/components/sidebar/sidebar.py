from PySide6.QtCore import QAbstractAnimation, QEasingCurve, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QResizeEvent, QShowEvent
from PySide6.QtWidgets import QButtonGroup, QVBoxLayout, QWidget

from boostx.config.layout import LayoutConstants
from boostx.config.paths import AppPaths
from boostx.ui.components.sidebar.nav_item import NAV_ITEMS
from boostx.ui.components.sidebar.sidebar_button import SidebarButton
from boostx.ui.components.sidebar.sidebar_indicator import SidebarIndicator

_BUTTON_HEIGHT = 44
_BUTTON_SPACING = 4
_MARGINS = (8, 16, 8, 8)
_INDICATOR_ANIMATION_MS = 200


class Sidebar(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(LayoutConstants().SIDEBAR_WIDTH)

        self._buttons: list[SidebarButton] = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._animation: QPropertyAnimation | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*_MARGINS)
        layout.setSpacing(_BUTTON_SPACING)

        for item in NAV_ITEMS:
            icon_path = AppPaths.nav_icons_dir() / f"{item.key}.svg"
            button = SidebarButton(icon_path, item.label, self)
            button.setFixedHeight(_BUTTON_HEIGHT)
            self._button_group.addButton(button, item.page_index)
            button.clicked.connect(lambda _checked=False, idx=item.page_index: self._on_button_clicked(idx))
            layout.addWidget(button)
            self._buttons.append(button)
        layout.addStretch(1)

        self._indicator = SidebarIndicator(_BUTTON_HEIGHT, self)
        self._indicator.raise_()

        self._buttons[0].setChecked(True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._snap_indicator_to(self._checked_page_index())

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._snap_indicator_to(self._checked_page_index())

    def _checked_page_index(self) -> int:
        checked = self._button_group.checkedButton()
        return self._button_group.id(checked) if checked is not None else 0

    def _button_for_index(self, page_index: int) -> SidebarButton | None:
        for button in self._buttons:
            if self._button_group.id(button) == page_index:
                return button
        return None

    def _snap_indicator_to(self, page_index: int) -> None:
        button = self._button_for_index(page_index)
        if button is not None:
            self._indicator.move(0, button.y())

    def select_page(self, page_index: int) -> None:
        button = self._button_for_index(page_index)
        if button is None:
            return
        if not button.isChecked():
            button.setChecked(True)
        self._on_button_clicked(page_index)

    def _on_button_clicked(self, page_index: int) -> None:
        self._animate_indicator_to(page_index)
        self.page_changed.emit(page_index)

    def _animate_indicator_to(self, page_index: int) -> None:
        button = self._button_for_index(page_index)
        if button is None:
            return
        animation = QPropertyAnimation(self._indicator, b"pos", self)
        animation.setDuration(_INDICATOR_ANIMATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(self._indicator.pos())
        animation.setEndValue(QPoint(0, button.y()))
        animation.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation
