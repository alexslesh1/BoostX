from dataclasses import dataclass

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from boostx.config.palette import Palette
from boostx.ui.components.card import Card
from boostx.ui.components.charts.rolling_series_buffer import RollingSeriesBuffer

_MAX_POINTS = 60


@dataclass(frozen=True)
class SeriesSpec:
    name: str
    color: str
    y_axis_max: float | None = None


_MIN_CARD_HEIGHT = 240


class LineChartCard(Card):
    def __init__(self, title: str, series_specs: list[SeriesSpec], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        palette = Palette()
        self.setMinimumHeight(_MIN_CARD_HEIGHT)

        title_label = QLabel(title, self)
        title_label.setObjectName("ChartCardTitle")

        self._chart = QChart()
        self._chart.setBackgroundVisible(False)
        self._chart.legend().setVisible(len(series_specs) > 1)
        if len(series_specs) > 1:
            self._chart.legend().setLabelColor(QColor(palette.TEXT_SECONDARY))

        self._buffers: dict[str, RollingSeriesBuffer] = {
            spec.name: RollingSeriesBuffer(_MAX_POINTS) for spec in series_specs
        }
        self._series: dict[str, QLineSeries] = {}

        grid_pen = QPen(QColor(palette.BORDER))
        grid_pen.setWidth(1)

        self._x_axis = QValueAxis()
        self._x_axis.setRange(0, _MAX_POINTS - 1)
        self._x_axis.setVisible(False)
        self._chart.addAxis(self._x_axis, Qt.AlignmentFlag.AlignBottom)

        self._y_axis = QValueAxis()
        self._y_axis.setLabelsColor(QColor(palette.TEXT_SECONDARY))
        self._y_axis.setGridLinePen(grid_pen)
        self._y_axis.setLinePen(grid_pen)
        self._chart.addAxis(self._y_axis, Qt.AlignmentFlag.AlignLeft)

        fixed_max = next((spec.y_axis_max for spec in series_specs if spec.y_axis_max is not None), None)
        self._auto_scale = fixed_max is None
        self._y_axis.setRange(0, fixed_max or 1.0)

        for spec in series_specs:
            series = QLineSeries()
            series.setName(spec.name)
            pen = QPen(QColor(spec.color))
            pen.setWidth(2)
            series.setPen(pen)
            self._chart.addSeries(series)
            series.attachAxis(self._x_axis)
            series.attachAxis(self._y_axis)
            self._series[spec.name] = series

        self._chart_view = QChartView(self._chart, self)
        self._chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._empty_state_label = QLabel("", self)
        self._empty_state_label.setObjectName("ChartEmptyState")
        self._empty_state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_state_label.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        layout.addWidget(title_label)
        layout.addWidget(self._chart_view, stretch=1)
        layout.addWidget(self._empty_state_label, stretch=1)

    def update_series(self, name: str, value: float) -> None:
        buffer = self._buffers.get(name)
        series = self._series.get(name)
        if buffer is None or series is None:
            return
        buffer.push(value)
        series.replace([QPointF(i, y) for i, y in enumerate(buffer.values())])
        if self._auto_scale:
            observed_max = max((buf.max_value() for buf in self._buffers.values()), default=0.0)
            self._y_axis.setRange(0, max(1.0, observed_max * 1.15))

    def clear(self) -> None:
        for name, buffer in self._buffers.items():
            buffer.clear()
            self._series[name].clear()
        if self._auto_scale:
            self._y_axis.setRange(0, 1.0)

    def show_empty_state(self, message: str) -> None:
        self._chart_view.hide()
        self._empty_state_label.setText(message)
        self._empty_state_label.show()

    def hide_empty_state(self) -> None:
        self._empty_state_label.hide()
        self._chart_view.show()
