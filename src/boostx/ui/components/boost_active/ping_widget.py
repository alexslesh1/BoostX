from PySide6.QtCharts import QAreaSeries, QChart, QChartView, QSplineSeries, QValueAxis
from PySide6.QtCore import QMargins, QPointF, QPropertyAnimation, Qt
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from boostx.config.palette import Palette
from boostx.ui.components.card import Card
from boostx.ui.components.charts.rolling_series_buffer import RollingSeriesBuffer

_HISTORY_POINTS = 60
_MIN_CHART_HEIGHT = 130
_MIN_WIDGET_HEIGHT = 300
_FADE_DURATION_MS = 250
_FADE_START_OPACITY = 0.35


class PingWidget(Card):
    """The dominant widget on the Boost Active screen: a large ping
    readout with a smooth animated latency graph filling the space
    beneath it."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(_MIN_WIDGET_HEIGHT)
        palette = Palette()

        title_label = QLabel("PING", self)
        title_label.setObjectName("PingTitleLabel")
        title_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._value_label = QLabel("— ms", self)
        self._value_label.setObjectName("PingValueLabel")
        self._value_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        self._opacity_effect = QGraphicsOpacityEffect(self._value_label)
        self._opacity_effect.setOpacity(1.0)
        self._value_label.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(_FADE_DURATION_MS)

        self._buffer = RollingSeriesBuffer(_HISTORY_POINTS)
        self._chart_view = self._build_chart(palette)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(2)
        layout.addWidget(title_label)
        layout.addWidget(self._value_label)
        layout.addSpacing(14)
        layout.addWidget(self._chart_view, stretch=1)

    def _build_chart(self, palette: Palette) -> QChartView:
        chart = QChart()
        chart.setBackgroundVisible(False)
        chart.legend().setVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        self._chart = chart

        line_color = QColor(palette.SUCCESS)
        pen = QPen(line_color)
        pen.setWidth(2)

        self._upper_series = QSplineSeries()
        self._lower_series = QSplineSeries()

        area = QAreaSeries(self._upper_series, self._lower_series)
        area.setPen(pen)
        gradient = QLinearGradient(0, 0, 0, 1)
        gradient.setCoordinateMode(QLinearGradient.CoordinateMode.ObjectBoundingMode)
        top_color = QColor(line_color)
        top_color.setAlphaF(0.35)
        bottom_color = QColor(line_color)
        bottom_color.setAlphaF(0.0)
        gradient.setColorAt(0.0, top_color)
        gradient.setColorAt(1.0, bottom_color)
        area.setBrush(QBrush(gradient))
        self._area_series = area
        chart.addSeries(area)

        self._x_axis = QValueAxis()
        self._x_axis.setRange(0, _HISTORY_POINTS - 1)
        self._x_axis.setVisible(False)
        chart.addAxis(self._x_axis, Qt.AlignmentFlag.AlignBottom)
        area.attachAxis(self._x_axis)

        self._y_axis = QValueAxis()
        self._y_axis.setVisible(False)
        self._y_axis.setRange(0, 100)
        chart.addAxis(self._y_axis, Qt.AlignmentFlag.AlignLeft)
        area.attachAxis(self._y_axis)

        chart_view = QChartView(chart, self)
        chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        chart_view.setMinimumHeight(_MIN_CHART_HEIGHT)
        chart_view.setStyleSheet("background: transparent; border: none;")
        return chart_view

    def reset(self) -> None:
        self._buffer.clear()
        self._upper_series.clear()
        self._lower_series.clear()
        self._value_label.setText("— ms")

    def update_ping(self, ping_ms: float) -> None:
        self._buffer.push(ping_ms)
        values = self._buffer.values()
        self._upper_series.replace([QPointF(i, y) for i, y in enumerate(values)])
        self._lower_series.replace([QPointF(i, 0.0) for i in range(len(values))])

        observed_max = max(values, default=10.0)
        self._y_axis.setRange(0, max(10.0, observed_max * 1.3))

        text = f"{ping_ms:.0f} ms"
        if self._value_label.text() != text:
            self._value_label.setText(text)
            self._fade_animation.stop()
            self._fade_animation.setStartValue(_FADE_START_OPACITY)
            self._fade_animation.setEndValue(1.0)
            self._fade_animation.start()
