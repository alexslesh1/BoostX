from __future__ import annotations

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

from boostx.core.services.api.api_worker import run_async
from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.tunnel.errors import TunnelError
from boostx.core.services.tunnel.models import AppRule, TunnelSnapshot
from boostx.core.services.tunnel.tunnel_service import TunnelService

_POLL_MS = 2000
_UNEXPECTED_FAILURE_MESSAGE = "Routing could not be started. Please try again."


class TunnelController(QObject):
    """Qt-side owner of the one shared tunnel. Runs the blocking
    TunnelService calls off the UI thread and reports back with signals
    tagged by application key, so every screen that shows routing state
    (Boost, the Connection toggles, the connections table) agrees."""

    app_enabled = Signal(str)  # app_key
    app_failed = Signal(str, str)  # app_key, message for the user
    app_disabled = Signal(str)  # app_key
    snapshot_updated = Signal(object)  # TunnelSnapshot

    def __init__(self, service: TunnelService, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._enabled: set[str] = set()
        self._pending: set[str] = set()
        # Switched off again before the switch-on had finished.
        self._cancelled: set[str] = set()
        self._snapshot = TunnelSnapshot()
        # Bumped whenever the set of routed applications changes, so a
        # status read that started before the change is not mistaken for
        # the state after it.
        self._generation = 0
        self._poll_in_flight = False

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(_POLL_MS)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start()

    @property
    def snapshot(self) -> TunnelSnapshot:
        return self._snapshot

    def is_enabled(self, app_key: str) -> bool:
        return app_key in self._enabled

    def is_pending(self, app_key: str) -> bool:
        return app_key in self._pending

    def enable(self, app_key: str, rule: AppRule) -> None:
        if app_key in self._pending:
            self._cancelled.discard(app_key)
            return
        if app_key in self._enabled:
            self.app_enabled.emit(app_key)
            return
        self._pending.add(app_key)

        def work() -> None:
            try:
                self._service.enable(rule)
            except TunnelError:
                raise
            except Exception as exc:
                logger.exception(f"Unexpected error while enabling routing for {app_key}")
                raise TunnelError(_UNEXPECTED_FAILURE_MESSAGE) from exc

        run_async(
            work,
            lambda _result: self._on_enabled(app_key),
            lambda error: self._on_enable_failed(app_key, error),
        )

    def disable(self, app_key: str) -> None:
        if app_key in self._pending:
            self._cancelled.add(app_key)
            return
        if app_key not in self._enabled:
            return
        self._enabled.discard(app_key)
        self._generation += 1
        run_async(lambda: self._service.disable(app_key))
        self.app_disabled.emit(app_key)

    def shutdown(self) -> None:
        self._poll_timer.stop()
        self._enabled.clear()
        self._service.shutdown()

    def _on_enabled(self, app_key: str) -> None:
        self._pending.discard(app_key)
        self._enabled.add(app_key)
        self._generation += 1
        if app_key in self._cancelled:
            self._cancelled.discard(app_key)
            self.disable(app_key)
            return
        self.app_enabled.emit(app_key)
        self._poll()

    def _on_enable_failed(self, app_key: str, error: ApiError) -> None:
        self._pending.discard(app_key)
        self._cancelled.discard(app_key)
        self.app_failed.emit(app_key, str(error) or _UNEXPECTED_FAILURE_MESSAGE)

    def _poll(self) -> None:
        if self._poll_in_flight or (not self._enabled and not self._snapshot.active_apps):
            return
        self._poll_in_flight = True
        generation = self._generation
        run_async(
            self._service.snapshot,
            lambda snapshot: self._on_snapshot(generation, snapshot),
            lambda _error: self._on_snapshot(generation, None),
        )

    def _on_snapshot(self, generation: int, snapshot: TunnelSnapshot | None) -> None:
        self._poll_in_flight = False
        if snapshot is None or generation != self._generation:
            return
        self._snapshot = snapshot
        # Routing can end without anyone asking for it (the engine was
        # closed from Task Manager): reflect that instead of showing
        # applications as routed when they no longer are.
        for app_key in sorted(self._enabled - snapshot.active_apps):
            self._enabled.discard(app_key)
            self._generation += 1
            self.app_disabled.emit(app_key)
        self.snapshot_updated.emit(snapshot)
