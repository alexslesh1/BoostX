from PySide6.QtWidgets import QWidget

from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget


class PageRouter:
    def __init__(self, stack: FadeStackedWidget) -> None:
        self._stack = stack

    def register_page(self, page_index: int, widget: QWidget) -> None:
        self._stack.insertWidget(page_index, widget)

    def navigate_to(self, page_index: int) -> None:
        self._stack.setCurrentIndex(page_index)
