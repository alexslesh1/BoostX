from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QWidget

_SIZE = 48
_LINE_WIDTH = 4
_INTERVAL_MS = 16
_DEGREES_PER_TICK = 6
_ARC_SPAN_16THS = 100 * 16


class SpinnerWidget(QWidget):
    """A rotating circular progress ring, drawn by hand since Qt has no
    built-in indeterminate circular indicator."""

    def __init__(self, parent: QWidget | None = None, color: str = "#D32F2F") -> None:
        super().__init__(parent)
        self.setFixedSize(_SIZE, _SIZE)
        self._color = QColor(color)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(_INTERVAL_MS)
        self._timer.timeout.connect(self._advance)
        self.hide()

    def start(self) -> None:
        self.show()
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        self.hide()

    def _advance(self) -> None:
        self._angle = (self._angle + _DEGREES_PER_TICK) % 360
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color)
        pen.setWidth(_LINE_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        rect = QRectF(_LINE_WIDTH, _LINE_WIDTH, _SIZE - 2 * _LINE_WIDTH, _SIZE - 2 * _LINE_WIDTH)
        painter.drawArc(rect, -self._angle * 16, _ARC_SPAN_16THS)
