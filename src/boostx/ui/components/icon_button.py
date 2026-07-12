from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton, QWidget

from boostx.ui.components.tinted_svg import render_tinted_pixmap


class IconButton(QPushButton):
    def __init__(
        self,
        icon_path: Path,
        icon_size: QSize | None = None,
        icon_color: str = "#FFFFFF",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._icon_path = icon_path
        self._icon_size = icon_size or QSize(20, 20)
        self._icon_color = icon_color
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(self._icon_size)
        self._refresh_icon()

    def set_icon_color(self, color: str) -> None:
        self._icon_color = color
        self._refresh_icon()

    def set_icon_path(self, icon_path: Path) -> None:
        self._icon_path = icon_path
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        self.setIcon(QIcon(render_tinted_pixmap(self._icon_path, self._icon_color, self._icon_size)))
