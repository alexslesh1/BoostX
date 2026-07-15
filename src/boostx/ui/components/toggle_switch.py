from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

_WIDTH = 40
_HEIGHT = 22
_KNOB_MARGIN = 3
_ANIMATION_MS = 150


class ToggleSwitch(QAbstractButton):
    """A small pill-shaped on/off switch (there's no Qt built-in for this)."""

    def __init__(self, parent: QWidget | None = None, on_color: str = "#4CAF50", off_color: str = "#2F2F2F") -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(_WIDTH, _HEIGHT)
        self._on_color = QColor(on_color)
        self._off_color = QColor(off_color)
        self._knob_position = 1.0 if self.isChecked() else 0.0
        self._animation = QPropertyAnimation(self, b"knob_position", self)
        self._animation.setDuration(_ANIMATION_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate_to_checked_state)

    def _get_knob_position(self) -> float:
        return self._knob_position

    def _set_knob_position(self, value: float) -> None:
        self._knob_position = value
        self.update()

    knob_position = Property(float, _get_knob_position, _set_knob_position)

    def _animate_to_checked_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._knob_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._knob_position = 1.0 if checked else 0.0
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        track_color = self._blend(self._off_color, self._on_color, self._knob_position)
        painter.setBrush(track_color)
        track_rect = QRectF(0, 0, self.width(), self.height())
        painter.drawRoundedRect(track_rect, self.height() / 2, self.height() / 2)

        knob_diameter = self.height() - 2 * _KNOB_MARGIN
        travel = self.width() - self.height()
        knob_x = _KNOB_MARGIN + travel * self._knob_position
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(knob_x, _KNOB_MARGIN, knob_diameter, knob_diameter))

    @staticmethod
    def _blend(start: QColor, end: QColor, fraction: float) -> QColor:
        return QColor(
            int(start.red() + (end.red() - start.red()) * fraction),
            int(start.green() + (end.green() - start.green()) * fraction),
            int(start.blue() + (end.blue() - start.blue()) * fraction),
        )
