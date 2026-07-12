from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from boostx.ui.components.icon_button import IconButton

_BUTTON_SIZE = QSize(46, 32)
_ICON_SIZE = QSize(10, 10)


class WindowControlButton(IconButton):
    def __init__(self, icon_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(icon_path, icon_size=_ICON_SIZE, parent=parent)
        self.setFixedSize(_BUTTON_SIZE)
