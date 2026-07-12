from PySide6.QtWidgets import QLabel, QWidget


class StatusChip(QLabel):
    def __init__(self, text: str = "", severity: str = "neutral", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.set_severity(severity)

    def set_severity(self, severity: str) -> None:
        self.setProperty("severity", severity)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
