from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from boostx.core.services.api.api_worker import run_async
from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.core.services.vpn.models import VpnResult
from boostx.core.services.vpn.telegram_vpn_service import TelegramVpnService
from boostx.core.services.vpn.vpn_coordinator import VpnCoordinator
from boostx.core.services.vpn.wireguard_dependency import check_wireguard
from boostx.core.services.vpn.wireguard_installer import InstallProgress, install_wireguard

_GENERIC_FAILURE_MESSAGE = "Unable to reach the server. Please try again."
_INSTALL_CONSENT_TITLE = "Install WireGuard for Windows"
_INSTALL_CONSENT_TEXT = (
    "Telegram VPN requires WireGuard for Windows, which isn't installed.\n\n"
    "BoostX will download the official installer and run it automatically. "
    "Windows will show a permission (UAC) prompt during installation — "
    "please approve it to continue."
)
_PROGRESS_TEXT = {
    "downloading": "Downloading WireGuard...",
    "verifying": "Verifying WireGuard installer...",
    "installing": "Installing WireGuard (approve the permission prompt)...",
    "done": "WireGuard installed.",
}


class TelegramVpnController(QObject):
    started = Signal()
    failed = Signal(str)
    stopped = Signal()
    progress = Signal(str)

    def __init__(
        self, session_manager: SessionManager, vpn_coordinator: VpnCoordinator, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._service = TelegramVpnService(vpn_coordinator)
        self._busy = False

    @property
    def is_active(self) -> bool:
        return self._service.is_active

    def start(self) -> None:
        if self._busy or self._service.is_active:
            return

        dependency = check_wireguard()
        if not dependency.available:
            if not self._confirm_install():
                return
            self._busy = True
            self.progress.emit(_PROGRESS_TEXT["downloading"])
            run_async(self._install_wireguard, self._on_installed, self._on_install_error)
            return

        self._fetch_config()

    def stop(self) -> None:
        self._service.stop()
        self.stopped.emit()

    def shutdown(self) -> None:
        self._service.stop()

    @staticmethod
    def _confirm_install() -> bool:
        box = QMessageBox()
        box.setWindowTitle(_INSTALL_CONSENT_TITLE)
        box.setText(_INSTALL_CONSENT_TEXT)
        install_button = box.addButton("Install", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        return box.clickedButton() is install_button

    def _install_wireguard(self) -> None:
        install_wireguard(on_progress=self._on_install_progress)

    def _on_install_progress(self, progress: InstallProgress) -> None:
        self.progress.emit(_PROGRESS_TEXT.get(progress.stage, progress.stage))

    def _on_installed(self, _result: None) -> None:
        self._busy = False
        self._fetch_config()

    def _on_install_error(self, error: ApiError) -> None:
        self._busy = False
        self.failed.emit(str(error) or "Failed to install WireGuard for Windows.")

    def _fetch_config(self) -> None:
        self._busy = True
        self._session_manager.get_vpn_config(self._on_config, self._on_error)

    def _on_config(self, conf_text: str) -> None:
        run_async(lambda: self._service.start(conf_text), self._on_start_result, self._on_error)

    def _on_start_result(self, result: VpnResult) -> None:
        self._busy = False
        if result.success:
            self.started.emit()
        else:
            self.failed.emit(result.error or _GENERIC_FAILURE_MESSAGE)

    def _on_error(self, _error: ApiError) -> None:
        self._busy = False
        self.failed.emit(_GENERIC_FAILURE_MESSAGE)
