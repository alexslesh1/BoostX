from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from boostx.config.paths import AppPaths
from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG, BoostCatalogEntry
from boostx.core.services.boost.icon_resolver import build_icon_index, resolve_icon_path
from boostx.core.services.discord_boost.discord_launcher import find_discord_executable
from boostx.core.services.telegram_boost.telegram_launcher import find_telegram_executable
from boostx.ui.components.boost_app_card import SLOT_SIZE, BoostAppCard
from boostx.ui.components.boost_screen import BoostScreen
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.discord_vpn_controller import DiscordVpnController
from boostx.ui.controllers.telegram_vpn_controller import TelegramVpnController
from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget
from boostx.ui.pages.base_page import BasePage

_COLUMNS = 4
_SEARCH_FIELD_HEIGHT = 36


class BoostPage(BasePage):
    def __init__(
        self,
        service: BoostService,
        sequence_controller: BoostSequenceController,
        discord_vpn_controller: DiscordVpnController,
        telegram_vpn_controller: TelegramVpnController,
        parent: QWidget | None = None,
    ) -> None:
        # Must be assigned before super().__init__(), since it triggers _build_body() synchronously.
        self._service = service
        self._sequence_controller = sequence_controller
        self._communication_controllers = {
            "discord": discord_vpn_controller,
            "telegram": telegram_vpn_controller,
        }
        self._communication_finders = {
            "discord": find_discord_executable,
            "telegram": find_telegram_executable,
        }
        self._cards: dict[str, BoostAppCard] = {}
        self._slots: dict[str, QWidget] = {}
        self._current_app_key: str | None = None
        self._last_failure_message = ""
        self._icon_index: dict[str, Path] = {}
        self._catalog_index = {entry.key: index for index, entry in enumerate(BOOST_CATALOG)}

        super().__init__(
            title="Boost",
            subtitle="Your one-click game launcher",
            parent=parent,
        )

        self._sequence_controller.step_started.connect(self._on_step_started)
        self._sequence_controller.sequence_failed.connect(self._on_sequence_failed)
        self._sequence_controller.sequence_finished.connect(self._on_sequence_finished)

        for controller in self._communication_controllers.values():
            controller.started.connect(self._on_communication_started)
            controller.failed.connect(self._on_communication_failed)

    def _build_body(self, layout: QVBoxLayout) -> None:
        toolbar = QHBoxLayout()
        self._search_field = QLineEdit(self)
        self._search_field.setPlaceholderText("Search games...")
        self._search_field.setFixedHeight(_SEARCH_FIELD_HEIGHT)
        self._search_field.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self._search_field, stretch=1)

        scan_button = QPushButton("Scan", self)
        scan_button.clicked.connect(self._on_scan_clicked)
        toolbar.addWidget(scan_button)

        self._scan_status_label = QLabel("", self)
        self._scan_status_label.setObjectName("GamesStatusLabel")
        toolbar.addWidget(self._scan_status_label)

        layout.addLayout(toolbar)
        layout.addSpacing(12)

        grid_container = QWidget()
        self._grid = QGridLayout(grid_container)
        self._grid.setSpacing(16)

        self._icon_index = build_icon_index(AppPaths.game_icons_dir())
        statuses = self._service.get_all_statuses()
        for entry in BOOST_CATALOG:
            slot = QWidget(grid_container)
            slot.setFixedSize(SLOT_SIZE)
            icon_path = resolve_icon_path(entry.display_name, self._icon_index)
            card = BoostAppCard(entry, statuses[entry.key], icon_path, slot)
            card.clicked.connect(self._on_card_clicked)
            self._slots[entry.key] = slot
            self._cards[entry.key] = card

        self._reflow_grid()

        scroll_area = QScrollArea()
        scroll_area.setWidget(grid_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(scroll_area)

        self._boost_screen = BoostScreen(self)
        self._boost_screen.back_requested.connect(self._on_back_requested)
        self._boost_screen.stop_requested.connect(self._on_stop_requested)

        self._stack = FadeStackedWidget(self)
        self._stack.addWidget(content_container)
        self._stack.addWidget(self._boost_screen)

        layout.addWidget(self._stack, stretch=1)

    def _sorted_keys(self) -> list[str]:
        statuses = self._service.get_all_statuses()
        return sorted(
            (entry.key for entry in BOOST_CATALOG),
            key=lambda key: (not statuses[key].installed, self._catalog_index[key]),
        )

    def _reflow_grid(self) -> None:
        for slot in self._slots.values():
            self._grid.removeWidget(slot)
        for index, key in enumerate(self._sorted_keys()):
            row, column = divmod(index, _COLUMNS)
            self._grid.addWidget(self._slots[key], row, column)

    def _on_search_changed(self, text: str) -> None:
        query = text.strip().lower()
        for entry in BOOST_CATALOG:
            self._slots[entry.key].setVisible(query in entry.display_name.lower())

    def _on_scan_clicked(self) -> None:
        self._scan_status_label.setText("Scanning...")
        result = self._service.scan()
        self._scan_status_label.setText(f"Found {result.detected}, matched {result.matched}")
        self._refresh_cards()

    def _refresh_cards(self) -> None:
        statuses = self._service.get_all_statuses()
        for entry in BOOST_CATALOG:
            self._cards[entry.key].update_status(statuses[entry.key])
        self._reflow_grid()

    def _on_card_clicked(self, app_key: str) -> None:
        entry = self._entry_for_key(app_key)
        if entry.is_communication_app:
            self._start_communication_boost(entry)
            return
        status = self._service.get_status(app_key)
        if status is not None and status.installed and status.executable_path:
            self._current_app_key = app_key
            self._last_failure_message = ""
            icon_path = resolve_icon_path(entry.display_name, self._icon_index)
            self._boost_screen.start(entry, status, icon_path)
            self._stack.setCurrentIndex(1)
            self._sequence_controller.run(app_key)
        else:
            self._show_locate_prompt(entry, status)

    def _start_communication_boost(self, entry: BoostCatalogEntry) -> None:
        executable_path = self._communication_finders[entry.key]()
        if executable_path is None:
            box = QMessageBox(self)
            box.setWindowTitle(f"{entry.display_name} not found")
            box.setText(f"{entry.display_name} installation not found. Please install it first.")
            box.exec()
            return

        status = BoostAppStatus(
            app_key=entry.key,
            installed=True,
            executable_path=str(executable_path),
            install_dir=str(executable_path.parent),
            source="detected",
            launch_count=0,
            last_launch_at=None,
            custom_settings=None,
        )

        self._current_app_key = entry.key
        self._last_failure_message = ""
        icon_path = resolve_icon_path(entry.display_name, self._icon_index)
        self._boost_screen.start(entry, status, icon_path)
        self._stack.setCurrentIndex(1)

        controller = self._communication_controllers[entry.key]
        if controller.is_active:
            self._boost_screen.on_sequence_finished(True)
        else:
            self._boost_screen.on_step_started("launch")
            controller.start()

    def _on_communication_started(self) -> None:
        self._boost_screen.on_sequence_finished(True)

    def _on_communication_failed(self, message: str) -> None:
        self._last_failure_message = message
        self._boost_screen.on_sequence_failed(message)

    def _show_locate_prompt(self, entry: BoostCatalogEntry, status: BoostAppStatus | None) -> None:
        if status is not None and status.installed and not status.executable_path:
            message = (
                f"We found {entry.display_name} installed via {status.source} but couldn't "
                "determine its executable — please locate it manually."
            )
        else:
            message = f"{entry.display_name} not found."

        box = QMessageBox(self)
        box.setWindowTitle("Game not found")
        box.setText(message)
        locate_button = box.addButton("Locate", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is not locate_button:
            return

        file_path, _ = QFileDialog.getOpenFileName(self, f"Locate {entry.display_name}")
        if not file_path:
            return
        self._service.locate_app(entry.key, file_path)
        self._refresh_cards()

    def _on_step_started(self, step_key: str) -> None:
        self._boost_screen.on_step_started(step_key)

    def _on_sequence_failed(self, message: str) -> None:
        self._last_failure_message = message
        self._boost_screen.on_sequence_failed(message)

    def _on_sequence_finished(self, success: bool) -> None:
        self._boost_screen.on_sequence_finished(success)
        if self._current_app_key:
            self._cards[self._current_app_key].update_status(self._service.get_status(self._current_app_key))

    def _on_back_requested(self) -> None:
        self._boost_screen.stop()
        self._stack.setCurrentIndex(0)

    def _on_stop_requested(self) -> None:
        controller = self._communication_controllers.get(self._current_app_key or "")
        if controller is not None:
            controller.stop()
        self._boost_screen.stop()
        self._stack.setCurrentIndex(0)
        self._refresh_cards()

    @staticmethod
    def _entry_for_key(app_key: str) -> BoostCatalogEntry:
        return next(entry for entry in BOOST_CATALOG if entry.key == app_key)
