from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPaintEvent, QPainter
from PySide6.QtWidgets import QWidget

_PULSE_DURATION_MS = 1400
_MIN_OPACITY = 0.35


class PulseDot(QWidget):
    """A small filled circle with an optional subtle breathing pulse."""

    def __init__(self, diameter: int = 10, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(diameter, diameter)
        self._color = QColor("#FFFFFF")
        self._opacity = 1.0

        self._animation = QPropertyAnimation(self, b"dotOpacity", self)
        self._animation.setDuration(_PULSE_DURATION_MS)
        self._animation.setStartValue(1.0)
        self._animation.setKeyValueAt(0.5, _MIN_OPACITY)
        self._animation.setEndValue(1.0)
        self._animation.setLoopCount(-1)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutSine)

    def set_color(self, hex_color: str) -> None:
        self._color = QColor(hex_color)
        self.update()

    def set_pulsing(self, pulsing: bool) -> None:
        if pulsing:
            if self._animation.state() != QPropertyAnimation.State.Running:
                self._animation.start()
        else:
            self._animation.stop()
            self._set_dot_opacity(1.0)

    def _get_dot_opacity(self) -> float:
        return self._opacity

    def _set_dot_opacity(self, value: float) -> None:
        self._opacity = value
        self.update()

    dotOpacity = Property(float, _get_dot_opacity, _set_dot_opacity)

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._color)
        color.setAlphaF(self._opacity)
        painter.setBrush(color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(self.rect())
