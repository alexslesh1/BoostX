from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from boostx.core.services.api.api_worker import run_async
from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.models import ProxyCredentials
from boostx.core.services.api.session_manager import SessionManager
from boostx.core.services.telegram_boost.telegram_boost_service import (
    TelegramBoostResult,
    TelegramBoostService,
)

_GENERIC_FAILURE_MESSAGE = "Unable to reach the server. Please try again."


class TelegramBoostController(QObject):
    started = Signal()
    failed = Signal(str)
    stopped = Signal()

    def __init__(self, session_manager: SessionManager, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        self._service = TelegramBoostService()
        self._busy = False

    @property
    def is_active(self) -> bool:
        return self._service.is_active

    def start(self) -> None:
        if self._busy or self._service.is_active:
            return
        self._busy = True
        self._session_manager.get_proxy_credentials(self._on_credentials, self._on_error)

    def stop(self) -> None:
        self._service.stop()
        self.stopped.emit()

    def shutdown(self) -> None:
        self._service.stop()

    def _on_credentials(self, credentials: ProxyCredentials) -> None:
        run_async(lambda: self._service.start(credentials), self._on_start_result, self._on_error)

    def _on_start_result(self, result: TelegramBoostResult) -> None:
        self._busy = False
        if result.success:
            self.started.emit()
        else:
            self.failed.emit(result.error or _GENERIC_FAILURE_MESSAGE)

    def _on_error(self, _error: ApiError) -> None:
        self._busy = False
        self.failed.emit(_GENERIC_FAILURE_MESSAGE)
