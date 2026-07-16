from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from boostx.config.paths import AppPaths
from boostx.core.services.monitor.system_snapshot import SystemSnapshot
from boostx.ui.components.monitor_charts_panel import MonitorChartsPanel
from boostx.ui.components.stat_card import StatCard, severity_for_percent
from boostx.ui.controllers.monitor_controller import MonitorController
from boostx.ui.pages.base_page import BasePage
from boostx.ui.utils.formatting import format_bytes_per_sec, format_percent


class DashboardPage(BasePage):
    """StatCard row (CPU/GPU/RAM/Disk/Network) on top -- restored per
    product decision, this is the original Dashboard's top block -- and
    Monitor's chart grid below (folded in here since Monitor is no longer
    a separate nav destination). No app toggles, no connections table --
    those live only on Connection."""

    def __init__(self, monitor_controller: MonitorController, parent: QWidget | None = None) -> None:
        # Must be assigned before super().__init__(), since it triggers _build_body() synchronously.
        self._monitor_controller = monitor_controller
        self._stat_cards: dict[str, StatCard] = {}
        super().__init__(
            title="Dashboard",
            subtitle="Overview of your system status",
            parent=parent,
        )
        self._monitor_controller.snapshot_updated.connect(self._on_snapshot)

    def _build_body(self, layout: QVBoxLayout) -> None:
        icons_dir = AppPaths.icons_dir() / "stats"

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(16)
        for key, title in (
            ("cpu", "CPU"),
            ("gpu", "GPU"),
            ("ram", "RAM"),
            ("disk", "Disk"),
            ("network", "Network"),
        ):
            card = StatCard(icons_dir / f"{key}.svg", title, self)
            self._stat_cards[key] = card
            cards_layout.addWidget(card)
        layout.addLayout(cards_layout)

        layout.addSpacing(16)

        self._monitor_panel = MonitorChartsPanel(self._monitor_controller, self)
        layout.addWidget(self._monitor_panel, stretch=1)

    def _on_snapshot(self, snapshot: SystemSnapshot) -> None:
        cpu_severity, cpu_label = severity_for_percent(snapshot.cpu.percent)
        self._stat_cards["cpu"].update_value(
            format_percent(snapshot.cpu.percent), snapshot.cpu.percent, cpu_label, cpu_severity
        )

        if snapshot.gpu.available and snapshot.gpu.load_percent is not None:
            gpu_severity, gpu_label = severity_for_percent(snapshot.gpu.load_percent)
            self._stat_cards["gpu"].update_value(
                format_percent(snapshot.gpu.load_percent), snapshot.gpu.load_percent, gpu_label, gpu_severity
            )
        else:
            self._stat_cards["gpu"].set_unavailable()

        ram_severity, ram_label = severity_for_percent(snapshot.ram.percent)
        self._stat_cards["ram"].update_value(
            format_percent(snapshot.ram.percent), snapshot.ram.percent, ram_label, ram_severity
        )

        primary_disk = snapshot.disk.partitions[0] if snapshot.disk.partitions else None
        if primary_disk is not None:
            disk_severity, disk_label = severity_for_percent(primary_disk.percent)
            self._stat_cards["disk"].update_value(
                format_percent(primary_disk.percent), primary_disk.percent, disk_label, disk_severity
            )
        else:
            self._stat_cards["disk"].set_unavailable()

        if snapshot.network.local_ip is None:
            self._stat_cards["network"].update_value("Offline", None, "No connection", "error")
        else:
            if snapshot.ping.reachable and snapshot.ping.latency_ms is not None:
                status_text = f"{snapshot.ping.latency_ms:.0f} ms"
            else:
                status_text = "Connected"
            download_text = format_bytes_per_sec(snapshot.network.recv_bytes_per_sec)
            self._stat_cards["network"].update_value(f"{download_text} ↓", None, status_text, "success")
