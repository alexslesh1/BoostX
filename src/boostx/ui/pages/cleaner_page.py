from PySide6.QtWidgets import QWidget

from boostx.ui.pages.base_page import BasePage


class CleanerPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Cleaner",
            subtitle="Scan and clean temporary files, caches and logs",
            parent=parent,
        )
