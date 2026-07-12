from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QMouseEvent, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.catalog import BoostCatalogEntry
from boostx.ui.components.card import Card
from boostx.ui.components.monogram import render_monogram_pixmap
from boostx.ui.components.status_chip import StatusChip

COVER_SIZE = QSize(160, 284)
SLOT_SIZE = QSize(200, 380)
REST_SIZE = QSize(184, 360)
_HOVER_GROWTH = 1.04
_ANIMATION_MS = 120


class BoostAppCard(Card):
    clicked = Signal(str)

    def __init__(
        self,
        entry: BoostCatalogEntry,
        status: BoostAppStatus,
        icon_path: Path | None,
        parent: QWidget,
    ) -> None:
        super().__init__(parent)
        self._app_key = entry.key
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        cover_label = QLabel(self)
        cover_label.setFixedSize(COVER_SIZE)
        cover_label.setScaledContents(True)
        cover_label.setPixmap(self._load_cover(entry, icon_path))

        name_label = QLabel(entry.display_name, self)
        name_label.setObjectName("BoostAppCardTitle")
        name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        name_label.setWordWrap(True)

        self._badge = StatusChip("", "neutral", self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        layout.addWidget(cover_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addWidget(name_label)
        layout.addWidget(self._badge, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addStretch(1)

        self._apply_status(status)
        self.setGeometry(self._rest_geometry())
        self._animation: QPropertyAnimation | None = None

    @staticmethod
    def _load_cover(entry: BoostCatalogEntry, icon_path: Path | None) -> QPixmap:
        if icon_path is not None:
            pixmap = QPixmap(str(icon_path))
            if not pixmap.isNull():
                return pixmap
        return render_monogram_pixmap(entry.display_name, entry.key, COVER_SIZE)

    def update_status(self, status: BoostAppStatus) -> None:
        self._apply_status(status)

    def _apply_status(self, status: BoostAppStatus) -> None:
        if status.installed:
            self._badge.setText("Installed")
            self._badge.set_severity("success")
        else:
            self._badge.setText("Not Installed")
            self._badge.set_severity("neutral")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._app_key)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self._animate_to(self._hover_geometry())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate_to(self._rest_geometry())
        super().leaveEvent(event)

    def _rest_geometry(self) -> QRect:
        return self._centered_geometry(REST_SIZE)

    def _hover_geometry(self) -> QRect:
        hover_size = QSize(int(REST_SIZE.width() * _HOVER_GROWTH), int(REST_SIZE.height() * _HOVER_GROWTH))
        return self._centered_geometry(hover_size)

    @staticmethod
    def _centered_geometry(size: QSize) -> QRect:
        x = (SLOT_SIZE.width() - size.width()) // 2
        y = (SLOT_SIZE.height() - size.height()) // 2
        return QRect(x, y, size.width(), size.height())

    def _animate_to(self, target: QRect) -> None:
        animation = QPropertyAnimation(self, b"geometry", self)
        animation.setDuration(_ANIMATION_MS)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.setStartValue(self.geometry())
        animation.setEndValue(target)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._animation = animation
