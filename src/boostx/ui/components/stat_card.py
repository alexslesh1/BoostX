from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.ui.components.card import Card
from boostx.ui.components.icon_label import IconLabel
from boostx.ui.components.progress_bar import ProgressBar
from boostx.ui.components.status_chip import StatusChip

_ICON_SIZE = QSize(22, 22)


def severity_for_percent(percent: float) -> tuple[str, str]:
    if percent >= 85:
        return "error", "Critical"
    if percent >= 60:
        return "warning", "High"
    return "success", "Normal"


class StatCard(Card):
    def __init__(self, icon_path: Path, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        icon = IconLabel(icon_path, icon_size=_ICON_SIZE, icon_color="#B3B3B3", parent=self)
        title_label = QLabel(title, self)
        title_label.setObjectName("StatCardTitle")

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)
        header_layout.addWidget(icon)
        header_layout.addWidget(title_label)
        header_layout.addStretch(1)

        self._value_label = QLabel("—", self)
        self._value_label.setObjectName("StatCardValue")

        self._progress_bar = ProgressBar(self)
        self._status_chip = StatusChip("Unavailable", "neutral", self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addLayout(header_layout)
        layout.addWidget(self._value_label)
        layout.addWidget(self._progress_bar)
        layout.addWidget(self._status_chip)
        layout.addStretch(1)

    def update_value(
        self,
        value_text: str,
        percent: float | None,
        status_text: str,
        severity: str,
    ) -> None:
        self._value_label.setText(value_text)
        if percent is None:
            self._progress_bar.setVisible(False)
        else:
            self._progress_bar.setVisible(True)
            self._progress_bar.setValue(max(0, min(100, round(percent))))
            self._progress_bar.set_severity(severity)
        self._status_chip.setText(status_text)
        self._status_chip.set_severity(severity)

    def set_unavailable(self) -> None:
        self.update_value("N/A", None, "Unavailable", "neutral")
