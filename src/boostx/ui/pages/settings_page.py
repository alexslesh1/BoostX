from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.core.services.boost.boost_service import BoostService
from boostx.ui.components.card import Card
from boostx.ui.pages.base_page import BasePage

_SCRIPT_FOLDER_SETTING_KEY = "startup_script_folder"


class SettingsPage(BasePage):
    def __init__(self, service: BoostService, parent: QWidget | None = None) -> None:
        # Must be assigned before super().__init__(), since it triggers _build_body() synchronously.
        self._service = service
        super().__init__(
            title="Settings",
            subtitle="General, interface, performance and notification settings",
            parent=parent,
        )

    def _build_body(self, layout: QVBoxLayout) -> None:
        card = Card(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 18)
        card_layout.setSpacing(10)

        title = QLabel("Startup Script Folder", card)
        title.setObjectName("StatCardTitle")
        description = QLabel(
            'Folder containing "general (ALT11).bat", run before applying optimizations and launching a game.',
            card,
        )
        description.setObjectName("CardPlaceholderLabel")
        description.setWordWrap(True)

        self._path_label = QLabel(self._current_folder_text(), card)
        self._path_label.setObjectName("SecondaryPathLabel")
        self._path_label.setWordWrap(True)

        change_button = QPushButton("Change...", card)
        change_button.clicked.connect(self._on_change_folder)

        card_layout.addWidget(title)
        card_layout.addWidget(description)
        card_layout.addWidget(self._path_label)
        card_layout.addWidget(change_button, alignment=Qt.AlignmentFlag.AlignLeft)

        layout.addWidget(card)
        layout.addStretch(1)

    def _current_folder_text(self) -> str:
        folder = self._service.get_setting(_SCRIPT_FOLDER_SETTING_KEY)
        return folder if folder else "Not configured"

    def _on_change_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Startup Script Folder")
        if not folder:
            return
        self._service.set_setting(_SCRIPT_FOLDER_SETTING_KEY, folder)
        self._path_label.setText(self._current_folder_text())
