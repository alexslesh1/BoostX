from loguru import logger
from PySide6.QtCore import QObject, Qt, QThread, Signal

from boostx.core.services.cleaner.models import StartupEntry
from boostx.ui.controllers.cleaner_worker import CleanerWorker

_THREAD_WAIT_TIMEOUT_MS = 5000


class CleanerController(QObject):
    scan_finished = Signal(object)
    clean_progress = Signal(str)
    clean_finished = Signal(object)
    memory_snapshot_ready = Signal(object)
    memory_optimize_finished = Signal(object)
    startup_entries_ready = Signal(object)
    startup_toggle_finished = Signal(str, bool, bool)
    large_files_ready = Signal(object)
    restore_points_ready = Signal(object)
    restore_point_created = Signal(object)

    _scan_requested = Signal()
    _clean_requested = Signal(object)
    _memory_snapshot_requested = Signal()
    _memory_optimize_requested = Signal()
    _startup_entries_requested = Signal()
    _startup_toggle_requested = Signal(object, bool)
    _large_files_requested = Signal()
    _restore_points_requested = Signal()
    _restore_point_create_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        self._thread = QThread(self)
        self._worker = CleanerWorker()
        self._worker.moveToThread(self._thread)

        connection = Qt.ConnectionType.QueuedConnection
        self._scan_requested.connect(self._worker.scan, connection)
        self._clean_requested.connect(self._worker.clean, connection)
        self._memory_snapshot_requested.connect(self._worker.load_memory_snapshot, connection)
        self._memory_optimize_requested.connect(self._worker.optimize_memory, connection)
        self._startup_entries_requested.connect(self._worker.load_startup_entries, connection)
        self._startup_toggle_requested.connect(self._worker.toggle_startup, connection)
        self._large_files_requested.connect(self._worker.load_large_files, connection)
        self._restore_points_requested.connect(self._worker.load_restore_points, connection)
        self._restore_point_create_requested.connect(self._worker.create_restore_point, connection)

        self._worker.scan_finished.connect(self.scan_finished, connection)
        self._worker.clean_progress.connect(self.clean_progress, connection)
        self._worker.clean_finished.connect(self.clean_finished, connection)
        self._worker.memory_snapshot_ready.connect(self.memory_snapshot_ready, connection)
        self._worker.memory_optimize_finished.connect(self.memory_optimize_finished, connection)
        self._worker.startup_entries_ready.connect(self.startup_entries_ready, connection)
        self._worker.startup_toggle_finished.connect(self.startup_toggle_finished, connection)
        self._worker.large_files_ready.connect(self.large_files_ready, connection)
        self._worker.restore_points_ready.connect(self.restore_points_ready, connection)
        self._worker.restore_point_created.connect(self.restore_point_created, connection)

        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def scan(self) -> None:
        self._scan_requested.emit()

    def clean(self, selected_keys: set[str]) -> None:
        self._clean_requested.emit(selected_keys)

    def load_memory_snapshot(self) -> None:
        self._memory_snapshot_requested.emit()

    def optimize_memory(self) -> None:
        self._memory_optimize_requested.emit()

    def load_startup_entries(self) -> None:
        self._startup_entries_requested.emit()

    def toggle_startup(self, entry: StartupEntry, enabled: bool) -> None:
        self._startup_toggle_requested.emit(entry, enabled)

    def load_large_files(self) -> None:
        self._large_files_requested.emit()

    def load_restore_points(self) -> None:
        self._restore_points_requested.emit()

    def create_restore_point(self) -> None:
        self._restore_point_create_requested.emit()

    def shutdown(self) -> None:
        self._thread.quit()
        if not self._thread.wait(_THREAD_WAIT_TIMEOUT_MS):
            logger.warning("Cleaner worker thread did not stop within timeout")
