from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QWidget

from boostx.ui.components.tinted_svg import render_tinted_pixmap


class IconLabel(QLabel):
    def __init__(
        self,
        icon_path: Path,
        icon_size: QSize | None = None,
        icon_color: str = "#FFFFFF",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_size = icon_size or QSize(20, 20)
        self.setFixedSize(self._icon_size)
        self.setPixmap(render_tinted_pixmap(icon_path, icon_color, self._icon_size))
