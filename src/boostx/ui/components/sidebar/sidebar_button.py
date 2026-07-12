from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QWidget

from boostx.config.palette import Palette
from boostx.ui.components.icon_button import IconButton

_ICON_SIZE = QSize(18, 18)


class SidebarButton(IconButton):
    def __init__(self, icon_path: Path, label: str, parent: QWidget | None = None) -> None:
        palette = Palette()
        super().__init__(icon_path, icon_size=_ICON_SIZE, icon_color=palette.TEXT_SECONDARY, parent=parent)
        self._palette = palette
        self.setText(f"  {label}")
        self.setCheckable(True)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.setProperty("active", checked)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
        self.set_icon_color(self._palette.TEXT if checked else self._palette.TEXT_SECONDARY)
