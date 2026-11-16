from pathlib import Path

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.core.services.tunnel.models import FlowInfo
from boostx.ui.components.icon_button import IconButton
from boostx.ui.components.monogram import render_monogram_pixmap

_ICON_SIZE = QSize(28, 28)
_NO_DATA = "—"  # em dash: honest placeholder, not a fabricated number
_DIRECT_TEXT = "Direct"
_CONNECTING_TEXT = "Connecting…"
_NOT_ROUTED_DETAIL = "This application is using its normal connection. Start it from Boost to route it through Nexora."
_NO_CONNECTIONS_DETAIL = "Routed through Nexora. No connections are open right now."
_MAX_DETAIL_LINES = 8

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


def format_bytes(count: int) -> str:
    value = float(count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


class ConnectionTableRow(QWidget):
    """One row of the connections table. Every value comes from the
    routing engine's own counters for this application; where there is
    nothing to report (the app is running on its normal connection) the
    cell shows an em-dash rather than a made-up number."""

    expand_toggled = Signal(str, bool)  # app_key, expanded

    def __init__(
        self,
        entry: BoostCatalogEntry,
        icon_path: Path | None,
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

        self._server_label = self._value_label(_NO_DATA, main_row)
        self._game_server_label = self._value_label(_NO_DATA, main_row)
        self._protocol_label = self._value_label(_NO_DATA, main_row)
        self._sent_label = self._value_label(_NO_DATA, main_row)
        self._received_label = self._value_label(_NO_DATA, main_row)
        self._ping_label = self._value_label(_NO_DATA, main_row)
        for index, label in enumerate(
            (
                self._server_label,
                self._game_server_label,
                self._protocol_label,
                self._sent_label,
                self._received_label,
                self._ping_label,
            ),
            start=1,
        ):
            main_layout.addWidget(label, stretch=_COLUMN_STRETCH[index][1])

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

        self._detail_panel = QLabel(_NOT_ROUTED_DETAIL, self)
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

    def set_direct(self) -> None:
        """The app is running but not routed through Nexora."""
        self._server_label.setText(_DIRECT_TEXT)
        for label in (self._game_server_label, self._protocol_label, self._sent_label, self._received_label):
            label.setText(_NO_DATA)
        self._detail_panel.setText(_NOT_ROUTED_DETAIL)

    def set_routed(self, server_name: str, connected: bool, flows: tuple[FlowInfo, ...]) -> None:
        self._server_label.setText((server_name or "Nexora Network") if connected else _CONNECTING_TEXT)
        if not flows:
            for label in (self._game_server_label, self._protocol_label, self._sent_label, self._received_label):
                label.setText(_NO_DATA)
            self._detail_panel.setText(_NO_CONNECTIONS_DETAIL)
            return

        busiest = max(flows, key=lambda flow: flow.bytes_out + flow.bytes_in)
        others = len({flow.remote for flow in flows}) - 1
        self._game_server_label.setText(busiest.remote + (f"  +{others}" if others > 0 else ""))
        self._protocol_label.setText("/".join(sorted({flow.protocol for flow in flows})))
        self._sent_label.setText(format_bytes(sum(flow.bytes_out for flow in flows)))
        self._received_label.setText(format_bytes(sum(flow.bytes_in for flow in flows)))

        ordered = sorted(flows, key=lambda flow: flow.bytes_out + flow.bytes_in, reverse=True)
        lines = [
            f"{flow.exe}   {flow.protocol}   {flow.remote}   "
            f"sent {format_bytes(flow.bytes_out)}   received {format_bytes(flow.bytes_in)}"
            for flow in ordered[:_MAX_DETAIL_LINES]
        ]
        if len(ordered) > _MAX_DETAIL_LINES:
            lines.append(f"… and {len(ordered) - _MAX_DETAIL_LINES} more")
        self._detail_panel.setText("\n".join(lines))

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
