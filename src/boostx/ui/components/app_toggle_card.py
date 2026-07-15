from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.card import Card
from boostx.ui.components.icon_button import IconButton
from boostx.ui.components.monogram import render_monogram_pixmap
from boostx.ui.components.toggle_switch import ToggleSwitch

CARD_SIZE = QSize(220, 96)
_ICON_SIZE = QSize(40, 40)


class AppToggleCard(Card):
    """Small pinned-app tile: icon + name + mode label + on/off switch +
    close button. Purely a view -- it reports the user's intent via
    signals and waits to be told the real resulting state via
    set_checked()/set_mode(), since a regular game has no real "stop" and
    the switch must reflect actual state, not an optimistic guess."""

    toggle_requested = Signal(str, bool)  # app_key, desired checked state
    remove_requested = Signal(str)  # app_key

    def __init__(
        self,
        entry: BoostCatalogEntry,
        icon_path: Path | None,
        mode_label: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("AppToggleCard")
        self._app_key = entry.key
        self.setFixedSize(CARD_SIZE)

        icon_label = QLabel(self)
        icon_label.setFixedSize(_ICON_SIZE)
        icon_label.setScaledContents(True)
        icon_label.setPixmap(self._load_icon(entry, icon_path))

        name_label = QLabel(entry.display_name, self)
        name_label.setObjectName("AppToggleCardName")
        mode_label_widget = QLabel(mode_label, self)
        mode_label_widget.setObjectName("AppToggleCardMode")

        text_column = QVBoxLayout()
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(2)
        text_column.addWidget(name_label)
        text_column.addWidget(mode_label_widget)

        self._close_button = IconButton(
            self._close_icon_path(), QSize(14, 14), icon_color="#B3B3B3", parent=self
        )
        self._close_button.setFixedSize(24, 24)
        self._close_button.clicked.connect(lambda: self.remove_requested.emit(self._app_key))

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(10)
        top_row.addWidget(icon_label)
        top_row.addLayout(text_column, stretch=1)
        top_row.addWidget(self._close_button, alignment=Qt.AlignmentFlag.AlignTop)

        self._switch = ToggleSwitch(self)
        self._switch.toggled.connect(lambda checked: self.toggle_requested.emit(self._app_key, checked))

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.addWidget(self._switch)
        bottom_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 10, 12)
        layout.setSpacing(10)
        layout.addLayout(top_row)
        layout.addStretch(1)
        layout.addLayout(bottom_row)

    @property
    def app_key(self) -> str:
        return self._app_key

    def set_checked(self, checked: bool) -> None:
        self._switch.blockSignals(True)
        self._switch.setChecked(checked)
        self._switch.blockSignals(False)

    @staticmethod
    def _close_icon_path() -> Path:
        from boostx.config.paths import AppPaths

        return AppPaths.window_icons_dir() / "close.svg"

    @staticmethod
    def _load_icon(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, _ICON_SIZE)
