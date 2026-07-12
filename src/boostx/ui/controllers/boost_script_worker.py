from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from boostx.core.services.optimizer.startup_script_runner import run_startup_script


class BoostScriptWorker(QObject):
    script_finished = Signal(object)

    @Slot(str, float)
    def run_script(self, script_path: str, timeout_s: float) -> None:
        result = run_startup_script(Path(script_path), timeout_s)
        self.script_finished.emit(result)
