from loguru import logger
from PySide6.QtCore import QObject, Qt, QThread, Signal

from boostx.ui.controllers.tweaks_worker import TweaksWorker

_THREAD_WAIT_TIMEOUT_MS = 5000


class TweaksController(QObject):
    dependency_checked = Signal(str, object)
    devices_ready = Signal(str, object)
    tweak_finished = Signal(str, object)

    _dependency_check_requested = Signal(str)
    _devices_requested = Signal(str)
    _apply_requested = Signal(str, object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._thread = QThread(self)
        self._worker = TweaksWorker()
        self._worker.moveToThread(self._thread)

        connection = Qt.ConnectionType.QueuedConnection
        self._dependency_check_requested.connect(self._worker.check_dependency, connection)
        self._devices_requested.connect(self._worker.load_devices, connection)
        self._apply_requested.connect(self._worker.apply_tweak, connection)

        self._worker.dependency_checked.connect(self.dependency_checked, connection)
        self._worker.devices_ready.connect(self.devices_ready, connection)
        self._worker.tweak_finished.connect(self.tweak_finished, connection)

        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def check_dependency(self, provider_key: str) -> None:
        self._dependency_check_requested.emit(provider_key)

    def load_devices(self, provider_key: str) -> None:
        self._devices_requested.emit(provider_key)

    def apply_tweak(self, provider_key: str, device_key: str | None) -> None:
        self._apply_requested.emit(provider_key, device_key)

    def shutdown(self) -> None:
        self._thread.quit()
        if not self._thread.wait(_THREAD_WAIT_TIMEOUT_MS):
            logger.warning("Tweaks worker thread did not stop within timeout")
