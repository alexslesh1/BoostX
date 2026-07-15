from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QScrollArea, QWidget

from boostx.config.paths import AppPaths
from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG
from boostx.core.services.boost.icon_resolver import build_icon_index, resolve_icon_path
from boostx.ui.components.app_picker_dialog import AppPickerDialog
from boostx.ui.components.app_toggle_card import CARD_SIZE, AppToggleCard
from boostx.ui.controllers.app_boost_controller import AppBoostController

_PINNED_APPS_SETTING_KEY = "pinned_apps"
_ROW_MARGIN = 24


class AppTogglesRow(QWidget):
    """Row of pinned-app toggle cards + an add button, shown identically
    on both Home and Connection -- both pages construct their own instance
    of this widget but share the same AppBoostController and BoostService,
    so pinned apps and running state stay consistent across pages."""

    def __init__(
        self, service: BoostService, boost_controller: AppBoostController, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._controller = boost_controller
        self._icon_index = build_icon_index(AppPaths.game_icons_dir())
        self._cards: dict[str, AppToggleCard] = {}

        self._cards_container = QWidget(self)
        self._cards_layout = QHBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(12)

        self._add_button = QPushButton("+", self._cards_container)
        self._add_button.setObjectName("AppTogglesAddButton")
        self._add_button.setFixedSize(CARD_SIZE)
        self._add_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._add_button.clicked.connect(self._on_add_clicked)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(self._cards_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setFixedHeight(CARD_SIZE.height() + _ROW_MARGIN)

        outer_layout = QHBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll_area)

        self._controller.communication_started.connect(self._on_started)
        self._controller.sequence_finished.connect(self._on_sequence_finished)
        self._controller.communication_failed.connect(self._on_failed)
        self._controller.running_keys_changed.connect(self._on_running_keys_changed)

        for app_key in self._load_pinned_keys():
            self._add_card(app_key)
        self._reflow()
        self._refresh_all_states()

    def _load_pinned_keys(self) -> list[str]:
        raw = self._service.get_setting(_PINNED_APPS_SETTING_KEY)
        if not raw:
            return []
        catalog_keys = {entry.key for entry in BOOST_CATALOG}
        return [key for key in raw.split(",") if key in catalog_keys]

    def _save_pinned_keys(self) -> None:
        self._service.set_setting(_PINNED_APPS_SETTING_KEY, ",".join(self._cards.keys()))

    def _add_card(self, app_key: str) -> None:
        entry = self._controller.entry_for_key(app_key)
        icon_path = resolve_icon_path(entry.display_name, self._icon_index)
        mode_label = "Manual" if entry.is_communication_app else "Automatic"
        card = AppToggleCard(entry, icon_path, mode_label, self._cards_container)
        card.toggle_requested.connect(self._on_toggle_requested)
        card.remove_requested.connect(self._on_remove_requested)
        self._cards[app_key] = card

    def _reflow(self) -> None:
        while self._cards_layout.count():
            self._cards_layout.takeAt(0)
        for card in self._cards.values():
            self._cards_layout.addWidget(card)
        self._cards_layout.addWidget(self._add_button)
        self._cards_layout.addStretch(1)

    def _on_add_clicked(self) -> None:
        dialog = AppPickerDialog(set(self._cards.keys()), self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_key:
            self._add_card(dialog.selected_key)
            self._reflow()
            self._save_pinned_keys()
            self._refresh_card_state(dialog.selected_key)

    def _on_remove_requested(self, app_key: str) -> None:
        card = self._cards.pop(app_key, None)
        if card is not None:
            self._controller.stop(app_key)
            card.setParent(None)
            card.deleteLater()
        self._reflow()
        self._save_pinned_keys()

    def _on_toggle_requested(self, app_key: str, checked: bool) -> None:
        if checked:
            self._controller.start(app_key)
        else:
            self._controller.stop(app_key)
            # Regular games have no real stop -- if it's still actually
            # running, snap the switch back on instead of lying about state.
            QTimer.singleShot(50, lambda: self._refresh_card_state(app_key))

    def _on_started(self, app_key: str) -> None:
        self._refresh_card_state(app_key)

    def _on_sequence_finished(self, app_key: str, success: bool) -> None:
        del success
        self._refresh_card_state(app_key)

    def _on_failed(self, app_key: str, _message: str) -> None:
        self._refresh_card_state(app_key)

    def _on_running_keys_changed(self, running_keys: set) -> None:
        for app_key, card in self._cards.items():
            entry = self._controller.entry_for_key(app_key)
            if not entry.is_communication_app:
                card.set_checked(app_key in running_keys)

    def _refresh_card_state(self, app_key: str) -> None:
        card = self._cards.get(app_key)
        if card is not None:
            card.set_checked(self._controller.is_running(app_key))

    def _refresh_all_states(self) -> None:
        for app_key in list(self._cards.keys()):
            self._refresh_card_state(app_key)
