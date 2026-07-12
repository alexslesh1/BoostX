from PySide6.QtCore import QObject, QTimer, Signal, Slot

from boostx.core.services.monitor.system_monitor_service import SystemMonitorService

_SLOW_INTERVAL_MS = 3000


class MonitorWorker(QObject):
    slow_snapshot_ready = Signal(object)

    def __init__(self, service: SystemMonitorService) -> None:
        super().__init__()
        self._service = service
        self._timer: QTimer | None = None

    @Slot()
    def start_polling(self) -> None:
        self._timer = QTimer(self)
        self._timer.setInterval(_SLOW_INTERVAL_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    @Slot()
    def pause(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    @Slot()
    def resume(self) -> None:
        if self._timer is not None:
            self._timer.start()

    @Slot()
    def stop(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    def _tick(self) -> None:
        snapshot = self._service.sample_slow()
        self.slow_snapshot_ready.emit(snapshot)
