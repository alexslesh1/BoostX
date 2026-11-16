from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from boostx.core.services.api.api_worker import run_async
from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.boost.running_detector import is_process_running
from boostx.core.services.tunnel.rules import build_rule
from boostx.ui.controllers.tunnel_controller import TunnelController

_CONNECTING_TEXT = "Connecting to Nexora Network..."


class AppTunnelController(QObject):
    """Boost for a communication app (Discord, Telegram): route it through
    the Nexora network, then make sure it is running. The app itself is
    started normally — it is never given a proxy setting or any other hint
    that its traffic takes a different path."""

    started = Signal()
    failed = Signal(str)
    stopped = Signal()
    progress = Signal(str)

    def __init__(
        self,
        app_key: str,
        display_name: str,
        find_executable: Callable[[], Path | None],
        launch: Callable[[Path], bool],
        install_dir_for: Callable[[Path], Path],
        tunnel_controller: TunnelController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._app_key = app_key
        self._display_name = display_name
        self._find_executable = find_executable
        self._launch = launch
        self._install_dir_for = install_dir_for
        self._tunnel = tunnel_controller
        self._busy = False
        self._executable: Path | None = None

        self._tunnel.app_enabled.connect(self._on_tunnel_enabled)
        self._tunnel.app_failed.connect(self._on_tunnel_failed)
        self._tunnel.app_disabled.connect(self._on_tunnel_disabled)

    @property
    def is_active(self) -> bool:
        return self._tunnel.is_enabled(self._app_key)

    def start(self) -> None:
        if self._busy or self.is_active:
            return
        executable = self._find_executable()
        if executable is None:
            self.failed.emit(f"{self._display_name} installation not found.")
            return
        self._busy = True
        self._executable = executable
        self.progress.emit(_CONNECTING_TEXT)
        rule = build_rule(self._app_key, str(executable), install_dir=str(self._install_dir_for(executable)))
        self._tunnel.enable(self._app_key, rule)

    def stop(self) -> None:
        self._tunnel.disable(self._app_key)

    def shutdown(self) -> None:
        self._busy = False

    def _on_tunnel_enabled(self, app_key: str) -> None:
        if app_key != self._app_key or not self._busy:
            return
        executable = self._executable

        def ensure_running() -> bool:
            return is_process_running(str(executable)) or self._launch(executable)

        run_async(ensure_running, self._on_launched, self._on_launch_error)

    def _on_launched(self, running: bool) -> None:
        self._busy = False
        if running:
            self.started.emit()
            return
        self._tunnel.disable(self._app_key)
        self.failed.emit(f"Unable to launch {self._display_name}.")

    def _on_launch_error(self, _error: ApiError) -> None:
        self._on_launched(False)

    def _on_tunnel_failed(self, app_key: str, message: str) -> None:
        if app_key != self._app_key or not self._busy:
            return
        self._busy = False
        self.failed.emit(message)

    def _on_tunnel_disabled(self, app_key: str) -> None:
        if app_key == self._app_key:
            self.stopped.emit()
