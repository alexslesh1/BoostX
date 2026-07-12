from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.monogram import render_monogram_pixmap

_ICON_SIZE = QSize(32, 32)
_UNKNOWN_SERVER = "Unknown Server"


class ConnectionRow(QWidget):
    def __init__(self, entry: BoostCatalogEntry, icon_path: Path | None, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        icon_label = QLabel(self)
        icon_label.setFixedSize(_ICON_SIZE)
        icon_label.setScaledContents(True)
        icon_label.setPixmap(self._load_icon(entry, icon_path))

        name_label = QLabel(entry.display_name, self)
        name_label.setObjectName("ConnectionRowName")

        self._detail_label = QLabel("Connected", self)
        self._detail_label.setObjectName("ConnectionRowDetail")

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(2)
        text_layout.addWidget(name_label)
        text_layout.addWidget(self._detail_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        layout.addWidget(icon_label)
        layout.addLayout(text_layout, stretch=1)

    @staticmethod
    def _load_icon(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, _ICON_SIZE)

    def set_detail(self, ping_ms: float | None, server_label: str = _UNKNOWN_SERVER) -> None:
        if ping_ms is not None:
            self._detail_label.setText(f"{ping_ms:.0f} ms • {server_label}")
        else:
            self._detail_label.setText("Connected")
