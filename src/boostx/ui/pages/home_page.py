from PySide6.QtWidgets import QWidget

from boostx.ui.pages.base_page import BasePage


class HomePage(BasePage):
    """Placeholder -- uses BasePage's default "Coming soon" body until this
    page's actual content is designed."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(
            title="Home",
            subtitle="Coming soon",
            parent=parent,
        )
