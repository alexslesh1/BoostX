from pathlib import Path

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.icon_button import IconButton
from boostx.ui.components.monogram import render_monogram_pixmap

_ICON_SIZE = QSize(28, 28)
_NO_DATA = "—"  # em dash: honest placeholder, not a fabricated number

_COLUMN_STRETCH = (
    ("Application", 3),
    ("Nexora Server", 2),
    ("Game Server", 2),
    ("Protocol", 1),
    ("Sent", 1),
    ("Received", 1),
    ("Ping", 1),
)


class ConnectionTableHeader(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionTableHeader")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(12)
        for title, stretch in _COLUMN_STRETCH:
            label = QLabel(title, self)
            label.setObjectName("ConnectionTableHeaderLabel")
            layout.addWidget(label, stretch=stretch)
        layout.addSpacing(56)  # reserve space matching the eye + chevron buttons on each row


class ConnectionTableRow(QWidget):
    """One row of the upgraded connections table. Columns we don't have
    real per-flow telemetry for yet (Game Server / Protocol / Sent /
    Received) show an em-dash rather than a fabricated number -- only
    Application, routing, and ping are backed by real data."""

    expand_toggled = Signal(str, bool)  # app_key, expanded

    def __init__(
        self,
        entry: BoostCatalogEntry,
        icon_path: Path | None,
        routed_through_nexora: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ConnectionTableRow")
        self._app_key = entry.key
        self._expanded = False

        row_layout = QVBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        main_row = QWidget(self)
        main_layout = QHBoxLayout(main_row)
        main_layout.setContentsMargins(12, 10, 12, 10)
        main_layout.setSpacing(12)

        icon_label = QLabel(main_row)
        icon_label.setFixedSize(_ICON_SIZE)
        icon_label.setScaledContents(True)
        icon_label.setPixmap(self._load_icon(entry, icon_path))

        app_column = QHBoxLayout()
        app_column.setContentsMargins(0, 0, 0, 0)
        app_column.setSpacing(8)
        app_column.addWidget(icon_label)
        name_label = QLabel(entry.display_name, main_row)
        name_label.setObjectName("ConnectionRowName")
        app_column.addWidget(name_label, stretch=1)
        main_layout.addLayout(app_column, stretch=_COLUMN_STRETCH[0][1])

        server_text = "Nexora Network" if routed_through_nexora else _NO_DATA
        main_layout.addWidget(self._value_label(server_text, main_row), stretch=_COLUMN_STRETCH[1][1])
        main_layout.addWidget(self._value_label(_NO_DATA, main_row), stretch=_COLUMN_STRETCH[2][1])
        main_layout.addWidget(self._value_label(_NO_DATA, main_row), stretch=_COLUMN_STRETCH[3][1])
        main_layout.addWidget(self._value_label(_NO_DATA, main_row), stretch=_COLUMN_STRETCH[4][1])
        main_layout.addWidget(self._value_label(_NO_DATA, main_row), stretch=_COLUMN_STRETCH[5][1])

        self._ping_label = self._value_label(_NO_DATA, main_row)
        main_layout.addWidget(self._ping_label, stretch=_COLUMN_STRETCH[6][1])

        eye_button = IconButton(self._icon_path("eye"), QSize(16, 16), icon_color="#B3B3B3", parent=main_row)
        eye_button.setFixedSize(28, 28)
        eye_button.clicked.connect(self._toggle_expanded)

        self._chevron_button = IconButton(
            self._icon_path("chevron"), QSize(14, 14), icon_color="#B3B3B3", parent=main_row
        )
        self._chevron_button.setFixedSize(28, 28)
        self._chevron_button.clicked.connect(self._toggle_expanded)

        main_layout.addWidget(eye_button)
        main_layout.addWidget(self._chevron_button)

        self._detail_panel = QLabel(
            "Detailed per-connection metrics (protocol, game server, bytes sent/received) "
            "aren't tracked yet for this app.",
            self,
        )
        self._detail_panel.setObjectName("ConnectionRowDetail")
        self._detail_panel.setWordWrap(True)
        self._detail_panel.setContentsMargins(52, 0, 12, 10)
        self._detail_panel.setVisible(False)

        divider = QFrame(self)
        divider.setObjectName("ConnectionRowDivider")
        divider.setFrameShape(QFrame.Shape.HLine)

        row_layout.addWidget(main_row)
        row_layout.addWidget(self._detail_panel)
        row_layout.addWidget(divider)

    def set_ping(self, ping_ms: float | None) -> None:
        self._ping_label.setText(f"{ping_ms:.0f} ms" if ping_ms is not None else _NO_DATA)

    def _toggle_expanded(self) -> None:
        self._expanded = not self._expanded
        self._detail_panel.setVisible(self._expanded)
        self.expand_toggled.emit(self._app_key, self._expanded)

    @staticmethod
    def _value_label(text: str, parent: QWidget) -> QLabel:
        label = QLabel(text, parent)
        label.setObjectName("ConnectionRowDetail")
        return label

    @staticmethod
    def _icon_path(name: str) -> Path:
        from boostx.config.paths import AppPaths

        mapping = {"eye": "maximize.svg", "chevron": "restore.svg"}
        return AppPaths.window_icons_dir() / mapping[name]

    @staticmethod
    def _load_icon(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, _ICON_SIZE)
