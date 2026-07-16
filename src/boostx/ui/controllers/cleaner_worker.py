from PySide6.QtCore import QObject, Signal, Slot

from boostx.core.services.cleaner import restore_point_service
from boostx.core.services.cleaner.cleaner_service import CleanerService
from boostx.core.services.cleaner.large_file_scanner import LargeFileScanner
from boostx.core.services.cleaner.memory_optimizer import MemoryOptimizer
from boostx.core.services.cleaner.models import StartupEntry
from boostx.core.services.cleaner.startup_manager import StartupManager


class CleanerWorker(QObject):
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

    def __init__(self) -> None:
        super().__init__()
        self._cleaner_service = CleanerService()
        self._memory_optimizer = MemoryOptimizer()
        self._startup_manager = StartupManager()
        self._large_file_scanner = LargeFileScanner()

    @Slot()
    def scan(self) -> None:
        self.scan_finished.emit(self._cleaner_service.scan())

    @Slot(object)
    def clean(self, selected_keys: set) -> None:
        result = self._cleaner_service.clean(selected_keys, on_progress=self.clean_progress.emit)
        self.clean_finished.emit(result)

    @Slot()
    def load_memory_snapshot(self) -> None:
        self.memory_snapshot_ready.emit(self._memory_optimizer.snapshot())

    @Slot()
    def optimize_memory(self) -> None:
        self.memory_optimize_finished.emit(self._memory_optimizer.optimize())

    @Slot()
    def load_startup_entries(self) -> None:
        self.startup_entries_ready.emit(self._startup_manager.list_entries())

    @Slot(object, bool)
    def toggle_startup(self, entry: StartupEntry, enabled: bool) -> None:
        success = self._startup_manager.set_enabled(entry, enabled)
        self.startup_toggle_finished.emit(entry.name, enabled, success)

    @Slot()
    def load_large_files(self) -> None:
        self.large_files_ready.emit(self._large_file_scanner.scan())

    @Slot()
    def load_restore_points(self) -> None:
        self.restore_points_ready.emit(restore_point_service.list_restore_points())

    @Slot()
    def create_restore_point(self) -> None:
        self.restore_point_created.emit(restore_point_service.create_restore_point())
