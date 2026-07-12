from PySide6.QtWidgets import QWidget

from boostx.ui.pages.base_page import BasePage


class AboutPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="About",
            subtitle="Version, developer, license and changelog",
            parent=parent,
        )
