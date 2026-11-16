from collections.abc import Callable
from pathlib import Path

from loguru import logger
from PySide6.QtCore import QObject, QThread, Qt, Signal

from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG, DEMO_EXECUTABLE_SENTINEL
from boostx.core.services.optimizer.game_mode import enable_game_mode
from boostx.core.services.optimizer.memory_cleanup import memory_cleanup
from boostx.core.services.optimizer.optimizer_result import OptimizerResult
from boostx.core.services.optimizer.power_plan import set_high_performance_power_plan
from boostx.core.services.optimizer.temp_cleanup import temp_cleanup
from boostx.core.services.tunnel.rules import build_rule
from boostx.ui.controllers.boost_script_worker import BoostScriptWorker
from boostx.ui.controllers.tunnel_controller import TunnelController

_SCRIPT_FILENAME = "general (ALT11).bat"
_SCRIPT_TIMEOUT_S = 30.0
_THREAD_WAIT_TIMEOUT_MS = 5000
_FAILURE_MESSAGE = (
    "Unable to execute the startup script. Please try again later. "
    "We're already working on fixing this issue."
)

# Temporarily disabled per product request while the cross-platform launch path is being
# fixed — the script step was hard-blocking every boost sequence when no script folder is
# configured. Flip back to True to re-enable locate/run-script once launching is solid.
_STARTUP_SCRIPT_ENABLED = False


class BoostSequenceController(QObject):
    step_started = Signal(str)
    step_completed = Signal(str, bool)
    sequence_failed = Signal(str)
    sequence_finished = Signal(bool)
    # Routing through the Nexora network could not be set up; the game is
    # launched on its normal connection instead. Carries the reason.
    routing_unavailable = Signal(str)

    _run_script_requested = Signal(str, float)

    def __init__(
        self,
        service: BoostService,
        tunnel_controller: TunnelController | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._tunnel = tunnel_controller
        self._busy = False
        self._current_app_key: str | None = None
        self._awaiting_route = False
        if self._tunnel is not None:
            self._tunnel.app_enabled.connect(self._on_route_ready)
            self._tunnel.app_failed.connect(self._on_route_failed)

        self._thread = QThread(self)
        self._worker = BoostScriptWorker()
        self._worker.moveToThread(self._thread)
        self._run_script_requested.connect(self._worker.run_script, Qt.ConnectionType.QueuedConnection)
        self._worker.script_finished.connect(self._on_script_finished, Qt.ConnectionType.QueuedConnection)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.start()

    def run(self, app_key: str) -> bool:
        if self._busy:
            return False
        self._busy = True
        self._current_app_key = app_key

        status = self._service.get_status(app_key)

        self.step_started.emit("verify_install")
        if status is None or not status.installed:
            self.step_completed.emit("verify_install", False)
            self._fail("This application is not installed.")
            return True
        self.step_completed.emit("verify_install", True)

        self.step_started.emit("verify_executable")
        if not status.executable_path:
            self.step_completed.emit("verify_executable", False)
            self._fail("No launch executable is known for this application.")
            return True
        self.step_completed.emit("verify_executable", True)

        if not _STARTUP_SCRIPT_ENABLED:
            # Script step is bypassed (see _STARTUP_SCRIPT_ENABLED), but still report it as an
            # instantly-completed step so the overlay checklist doesn't show a permanently
            # pending row for it.
            self.step_started.emit("run_script")
            self.step_completed.emit("run_script", True)
            self._continue_after_script()
            return True

        self.step_started.emit("locate_script")
        script_folder = self._service.get_setting("startup_script_folder")
        if not script_folder:
            self.step_completed.emit("locate_script", False)
            self._fail(_FAILURE_MESSAGE)
            return True
        script_path = Path(script_folder) / _SCRIPT_FILENAME
        self.step_completed.emit("locate_script", True)

        self.step_started.emit("run_script")
        self._run_script_requested.emit(str(script_path), _SCRIPT_TIMEOUT_S)
        return True

    def _on_script_finished(self, result: OptimizerResult) -> None:
        self.step_completed.emit("run_script", result.success)
        if not result.success:
            logger.error(f"Startup script failed: {result.error}")
            self._fail(_FAILURE_MESSAGE)
            return
        self._continue_after_script()

    def _continue_after_script(self) -> None:
        self._run_optional_step("memory_cleanup", memory_cleanup)
        self._run_optional_step("game_mode", enable_game_mode)
        self._run_optional_step("power_plan", set_high_performance_power_plan)

        if self._service.get_setting("temp_cleanup_enabled") == "1":
            self._run_optional_step("temp_cleanup", temp_cleanup)

        if not self._start_routing():
            self._launch()

    def _start_routing(self) -> bool:
        """Routes the game through the Nexora network before it starts, so
        even its first connection takes that path. Returns False if there
        is nothing to wait for."""
        status = self._service.get_status(self._current_app_key)
        if (
            self._tunnel is None
            or status is None
            or not status.executable_path
            or status.executable_path == DEMO_EXECUTABLE_SENTINEL
        ):
            return False
        entry = next(entry for entry in BOOST_CATALOG if entry.key == self._current_app_key)
        rule = build_rule(
            entry.key, status.executable_path, install_dir=status.install_dir, extra_exes=entry.network_exes
        )
        self.step_started.emit("route")
        self._awaiting_route = True
        self._tunnel.enable(entry.key, rule)
        return True

    def _on_route_ready(self, app_key: str) -> None:
        if not self._awaiting_route or app_key != self._current_app_key:
            return
        self._awaiting_route = False
        self.step_completed.emit("route", True)
        self._launch()

    def _on_route_failed(self, app_key: str, message: str) -> None:
        if not self._awaiting_route or app_key != self._current_app_key:
            return
        # Not fatal: the game still gets every local optimisation and
        # starts on its normal connection. The user is told which.
        self._awaiting_route = False
        logger.warning(f"Routing unavailable for {app_key}: {message}")
        self.step_completed.emit("route", False)
        self.routing_unavailable.emit(message)
        self._launch()

    def _launch(self) -> None:
        self.step_started.emit("launch")
        launched = self._service.launch_app(self._current_app_key)
        self.step_completed.emit("launch", launched)

        self._busy = False
        self.sequence_finished.emit(True)

    def _run_optional_step(self, step_name: str, action: Callable[[], OptimizerResult]) -> None:
        self.step_started.emit(step_name)
        result = action()
        if not result.success:
            logger.warning(f"{step_name} failed: {result.error}")
        self.step_completed.emit(step_name, result.success)

    def _fail(self, message: str) -> None:
        self._busy = False
        self.sequence_failed.emit(message)
        self.sequence_finished.emit(False)

    def shutdown(self) -> None:
        self._awaiting_route = False
        self._thread.quit()
        if not self._thread.wait(_THREAD_WAIT_TIMEOUT_MS):
            logger.warning("Boost script worker thread did not stop within timeout")
