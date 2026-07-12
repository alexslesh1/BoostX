from PySide6.QtWidgets import QWidget

from boostx.ui.pages.base_page import BasePage


class AccountPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Account",
            subtitle="Manage your BoostX account",
            parent=parent,
        )
