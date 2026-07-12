from PySide6.QtWidgets import QProgressBar, QWidget


class ProgressBar(QProgressBar):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setTextVisible(False)
        self.setRange(0, 100)
        self.setFixedHeight(6)

    def set_severity(self, severity: str) -> None:
        self.setProperty("severity", severity)
        style = self.style()
        style.unpolish(self)
        style.polish(self)
