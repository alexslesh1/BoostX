from PySide6.QtWidgets import QWidget

_INDICATOR_WIDTH = 4


class SidebarIndicator(QWidget):
    def __init__(self, height: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarIndicator")
        self.resize(_INDICATOR_WIDTH, height)
