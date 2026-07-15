from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from boostx.config.paths import AppPaths
from boostx.core.services.boost.catalog import BOOST_CATALOG, BoostCatalogEntry
from boostx.core.services.boost.icon_resolver import build_icon_index, resolve_icon_path
from boostx.ui.components.monogram import render_monogram_pixmap

_ICON_SIZE = QSize(32, 32)


class AppPickerDialog(QDialog):
    """Reuses BOOST_CATALOG (the same catalog Boost's own grid draws from)
    to let the user pin an app to the Home/Connection toggle row."""

    def __init__(self, already_pinned: set[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add application")
        self.selected_key: str | None = None

        icon_index = build_icon_index(AppPaths.game_icons_dir())

        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(4)

        available = [entry for entry in BOOST_CATALOG if not entry.is_demo and entry.key not in already_pinned]
        for entry in available:
            icon_path = resolve_icon_path(entry.display_name, icon_index)
            container_layout.addWidget(self._build_row(entry, icon_path))
        container_layout.addStretch(1)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.addWidget(scroll_area)
        self.resize(360, 480)

    def _build_row(self, entry: BoostCatalogEntry, icon_path: Path | None) -> QWidget:
        row_button = QPushButton(self)
        row_button.setCursor(Qt.CursorShape.PointingHandCursor)
        row_button.setFlat(True)
        row_button.clicked.connect(lambda: self._on_selected(entry.key))

        icon_label = QLabel(row_button)
        icon_label.setFixedSize(_ICON_SIZE)
        icon_label.setScaledContents(True)
        icon_label.setPixmap(self._load_icon(entry, icon_path))

        name_label = QLabel(entry.display_name, row_button)

        row_layout = QHBoxLayout(row_button)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(12)
        row_layout.addWidget(icon_label)
        row_layout.addWidget(name_label, stretch=1)
        return row_button

    def _on_selected(self, app_key: str) -> None:
        self.selected_key = app_key
        self.accept()

    @staticmethod
    def _load_icon(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, _ICON_SIZE)
