from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from boostx.core.services.cleaner.models import LargeFileGroup
from boostx.ui.utils.formatting import format_bytes


class LargeFileRow(QWidget):
    """Displays a large-content folder/group with an "Open Folder" action.
    Never deletes anything - opening the folder is the only action offered."""

    def __init__(self, group: LargeFileGroup, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path = group.path

        name_label = QLabel(group.label, self)
        name_label.setObjectName("ConnectionRowName")

        self._size_label = QLabel(format_bytes(group.size_bytes), self)
        self._size_label.setObjectName("ConnectionRowDetail")

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        text_layout.addWidget(name_label)
        text_layout.addWidget(self._size_label)

        open_button = QPushButton("Open Folder", self)
        open_button.setCursor(Qt.CursorShape.PointingHandCursor)
        open_button.setEnabled(group.path.exists())
        open_button.clicked.connect(self._on_open_clicked)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(12)
        layout.addLayout(text_layout, stretch=1)
        layout.addWidget(open_button)

    def _on_open_clicked(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))
