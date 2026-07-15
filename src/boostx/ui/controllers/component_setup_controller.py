"""Runs the one-time background setup step (installing the VPN routing
component if it isn't already present) at app startup — silently, with
no dialog and no mention of the underlying technology. In the common
case (already installed from a previous run) this does nothing at all,
not even briefly.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from boostx.core.services.api.api_worker import run_async
from boostx.core.services.vpn.wireguard_dependency import check_wireguard
from boostx.core.services.vpn.wireguard_installer import InstallProgress, install_wireguard

_PROGRESS_TEXT = {
    "downloading": "Preparing Nexora components...",
    "verifying": "Preparing Nexora components...",
    "installing": "Finishing setup...",
    "done": "Ready.",
}


class ComponentSetupController(QObject):
    progress = Signal(str)
    finished = Signal(bool)

    def run_if_needed(self) -> None:
        dependency = check_wireguard()
        if dependency.available:
            return
        self.progress.emit(_PROGRESS_TEXT["downloading"])
        run_async(self._install, self._on_success, self._on_error)

    def _install(self) -> None:
        install_wireguard(on_progress=self._on_progress)

    def _on_progress(self, progress: InstallProgress) -> None:
        text = _PROGRESS_TEXT.get(progress.stage)
        if text is not None:
            self.progress.emit(text)

    def _on_success(self, _result: object) -> None:
        self.finished.emit(True)

    def _on_error(self, _error: object) -> None:
        # Silent by design — a first-run setup hiccup (e.g. no internet
        # yet) shouldn't greet the user with an error for a feature they
        # haven't tried to use. If it's still missing later, enabling
        # Discord/Telegram VPN will quietly retry and surface a neutral
        # message then, contextually.
        self.finished.emit(False)
