from loguru import logger
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal

from boostx.core.services.monitor.system_monitor_service import SystemMonitorService
from boostx.core.services.monitor.system_snapshot import (
    FastSnapshot,
    GpuStats,
    PingStats,
    SlowSnapshot,
    SystemSnapshot,
)
from boostx.ui.controllers.monitor_worker import MonitorWorker

_DEFAULT_FAST_INTERVAL_MS = 500
_THREAD_WAIT_TIMEOUT_MS = 3000

_EMPTY_GPU = GpuStats(
    available=False,
    name=None,
    load_percent=None,
    memory_used_mb=None,
    memory_total_mb=None,
    temperature_c=None,
)
_EMPTY_PING = PingStats(target="8.8.8.8", latency_ms=None, reachable=False)


class MonitorController(QObject):
    snapshot_updated = Signal(object)

    pause_requested = Signal()
    resume_requested = Signal()
    stop_requested = Signal()

    def __init__(self, service: SystemMonitorService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._latest_slow: SlowSnapshot | None = None

        self._fast_timer = QTimer(self)
        self._fast_timer.setInterval(_DEFAULT_FAST_INTERVAL_MS)
        self._fast_timer.timeout.connect(self._on_fast_tick)

        self._thread = QThread(self)
        self._worker = MonitorWorker(service)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.start_polling)
        self._thread.finished.connect(self._worker.deleteLater)

        self.pause_requested.connect(self._worker.pause, Qt.ConnectionType.QueuedConnection)
        self.resume_requested.connect(self._worker.resume, Qt.ConnectionType.QueuedConnection)
        self.stop_requested.connect(self._worker.stop, Qt.ConnectionType.QueuedConnection)
        self._worker.slow_snapshot_ready.connect(self._on_slow_snapshot, Qt.ConnectionType.QueuedConnection)

    def start(self) -> None:
        self._thread.start()
        self._fast_timer.start()

    def pause(self) -> None:
        self._fast_timer.stop()
        self.pause_requested.emit()

    def resume(self) -> None:
        self._fast_timer.start()
        self.resume_requested.emit()

    def set_interval(self, interval_ms: int) -> None:
        self._fast_timer.setInterval(interval_ms)

    def shutdown(self) -> None:
        self._fast_timer.stop()
        self.stop_requested.emit()
        self._thread.quit()
        if not self._thread.wait(_THREAD_WAIT_TIMEOUT_MS):
            logger.warning("Monitor worker thread did not stop within timeout")

    def _on_fast_tick(self) -> None:
        fast = self._service.sample_fast()
        self.snapshot_updated.emit(self._build_snapshot(fast))

    def _on_slow_snapshot(self, slow: SlowSnapshot) -> None:
        self._latest_slow = slow

    def _build_snapshot(self, fast: FastSnapshot) -> SystemSnapshot:
        gpu = self._latest_slow.gpu if self._latest_slow is not None else _EMPTY_GPU
        ping = self._latest_slow.ping if self._latest_slow is not None else _EMPTY_PING
        return SystemSnapshot(
            timestamp=fast.timestamp,
            cpu=fast.cpu,
            ram=fast.ram,
            disk=fast.disk,
            network=fast.network,
            gpu=gpu,
            ping=ping,
        )
