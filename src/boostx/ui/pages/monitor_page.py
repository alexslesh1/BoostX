from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from boostx.config.palette import Palette
from boostx.core.services.monitor.system_snapshot import SystemSnapshot
from boostx.ui.components.charts.line_chart_card import LineChartCard, SeriesSpec
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.pages.base_page import BasePage

_INTERVAL_OPTIONS_MS = (250, 500, 1000, 2000)
_DEFAULT_INTERVAL_MS = 500


class MonitorPage(BasePage):
    def __init__(self, monitor_controller: MonitorController, parent: QWidget | None = None) -> None:
        # Must be assigned before super().__init__(), since it triggers _build_body() synchronously.
        self._monitor_controller = monitor_controller
        self._is_paused = False
        super().__init__(
            title="Monitor",
            subtitle="Full CPU, GPU, RAM, disk and network monitoring",
            parent=parent,
        )
        self._monitor_controller.snapshot_updated.connect(self._on_snapshot)

    def _build_body(self, layout: QVBoxLayout) -> None:
        palette = Palette()

        toolbar = QHBoxLayout()
        self._pause_button = QPushButton("Pause", self)
        self._pause_button.clicked.connect(self._toggle_pause)
        toolbar.addWidget(self._pause_button)

        reset_button = QPushButton("Reset", self)
        reset_button.clicked.connect(self._reset_charts)
        toolbar.addWidget(reset_button)

        toolbar.addSpacing(12)
        toolbar.addWidget(QLabel("Interval:", self))
        self._interval_combo = QComboBox(self)
        for ms in _INTERVAL_OPTIONS_MS:
            self._interval_combo.addItem(f"{ms} ms", ms)
        self._interval_combo.setCurrentIndex(_INTERVAL_OPTIONS_MS.index(_DEFAULT_INTERVAL_MS))
        self._interval_combo.currentIndexChanged.connect(self._on_interval_changed)
        toolbar.addWidget(self._interval_combo)
        toolbar.addStretch(1)

        layout.addLayout(toolbar)
        layout.addSpacing(12)

        self._cpu_chart = LineChartCard("CPU %", [SeriesSpec("CPU", palette.PRIMARY, y_axis_max=100.0)], self)
        self._ram_chart = LineChartCard("RAM %", [SeriesSpec("RAM", palette.SUCCESS, y_axis_max=100.0)], self)
        self._gpu_chart = LineChartCard("GPU %", [SeriesSpec("GPU", palette.WARNING, y_axis_max=100.0)], self)
        self._disk_chart = LineChartCard(
            "Disk I/O",
            [SeriesSpec("Read", palette.CHART_SERIES_A), SeriesSpec("Write", palette.CHART_SERIES_B)],
            self,
        )
        self._network_chart = LineChartCard(
            "Network",
            [SeriesSpec("Download", palette.CHART_SERIES_A), SeriesSpec("Upload", palette.CHART_SERIES_B)],
            self,
        )

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.addWidget(self._cpu_chart, 0, 0)
        grid.addWidget(self._ram_chart, 0, 1)
        grid.addWidget(self._gpu_chart, 1, 0)
        grid.addWidget(self._disk_chart, 1, 1)
        grid.addWidget(self._network_chart, 2, 0, 1, 2)

        grid_container = QWidget(self)
        grid_container.setLayout(grid)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(grid_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        layout.addWidget(scroll_area, stretch=1)

        self._gpu_chart.show_empty_state("GPU not detected")

    def _toggle_pause(self) -> None:
        if self._is_paused:
            self._monitor_controller.resume()
            self._pause_button.setText("Pause")
        else:
            self._monitor_controller.pause()
            self._pause_button.setText("Resume")
        self._is_paused = not self._is_paused

    def _reset_charts(self) -> None:
        for chart in (self._cpu_chart, self._ram_chart, self._gpu_chart, self._disk_chart, self._network_chart):
            chart.clear()

    def _on_interval_changed(self, index: int) -> None:
        self._monitor_controller.set_interval(self._interval_combo.itemData(index))

    def _on_snapshot(self, snapshot: SystemSnapshot) -> None:
        self._cpu_chart.update_series("CPU", snapshot.cpu.percent)
        self._ram_chart.update_series("RAM", snapshot.ram.percent)

        if snapshot.gpu.available and snapshot.gpu.load_percent is not None:
            self._gpu_chart.hide_empty_state()
            self._gpu_chart.update_series("GPU", snapshot.gpu.load_percent)
        else:
            self._gpu_chart.show_empty_state("GPU not detected")

        if snapshot.disk.read_bytes_per_sec is not None:
            self._disk_chart.update_series("Read", snapshot.disk.read_bytes_per_sec)
        if snapshot.disk.write_bytes_per_sec is not None:
            self._disk_chart.update_series("Write", snapshot.disk.write_bytes_per_sec)

        if snapshot.network.recv_bytes_per_sec is not None:
            self._network_chart.update_series("Download", snapshot.network.recv_bytes_per_sec)
        if snapshot.network.sent_bytes_per_sec is not None:
            self._network_chart.update_series("Upload", snapshot.network.sent_bytes_per_sec)
