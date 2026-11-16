from __future__ import annotations

import time

from PySide6.QtCore import QObject, QTimer, Signal

from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG, BoostCatalogEntry
from boostx.ui.controllers.app_tunnel_controller import AppTunnelController
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.tunnel_controller import TunnelController

_RUNNING_POLL_MS = 3000
# A routed game that has not shown up as a running process this long after
# its boost was started is taken to have failed to launch.
_LAUNCH_GRACE_S = 180.0


class AppBoostController(QObject):
    """The one place that knows how to start/stop/check any BOOST_CATALOG
    entry, whether it's a regular game (BoostSequenceController.run --
    optimise, route, launch) or a communication app (AppTunnelController,
    which only routes and makes sure the app is open). Shared by the
    AppTogglesRow tiles so that branching isn't duplicated there.

    BoostPage keeps its own wiring to these same underlying controller
    instances for its full-screen boost overlay -- this class only tags
    their signals with the app_key for the smaller tile UI.

    It also ends a game's routing once the game has exited, so the tunnel
    is not kept up for a program that is no longer there.
    """

    step_started = Signal(str, str)  # app_key, step_key
    sequence_failed = Signal(str, str)  # app_key, message
    sequence_finished = Signal(str, bool)  # app_key, success
    communication_started = Signal(str)  # app_key
    communication_failed = Signal(str, str)  # app_key, message
    communication_progress = Signal(str, str)  # app_key, message
    running_keys_changed = Signal(object)  # set[str]

    def __init__(
        self,
        service: BoostService,
        sequence_controller: BoostSequenceController,
        communication_controllers: dict[str, AppTunnelController],
        tunnel_controller: TunnelController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._sequence_controller = sequence_controller
        self._communication_controllers = dict(communication_controllers)
        self._tunnel = tunnel_controller
        self._pending_game_key: str | None = None
        # Routed games: app_key -> (seen running, when routing was noticed).
        self._routed_games: dict[str, tuple[bool, float]] = {}

        self._sequence_controller.step_started.connect(self._on_step_started)
        self._sequence_controller.sequence_failed.connect(self._on_sequence_failed)
        self._sequence_controller.sequence_finished.connect(self._on_sequence_finished)

        for key, controller in self._communication_controllers.items():
            controller.started.connect(lambda k=key: self.communication_started.emit(k))
            controller.failed.connect(lambda message, k=key: self.communication_failed.emit(k, message))
            controller.progress.connect(lambda message, k=key: self.communication_progress.emit(k, message))

        self._running_poll_timer = QTimer(self)
        self._running_poll_timer.setInterval(_RUNNING_POLL_MS)
        self._running_poll_timer.timeout.connect(self._poll_running_keys)
        self._running_poll_timer.start()

    def shutdown(self) -> None:
        self._running_poll_timer.stop()

    @staticmethod
    def entry_for_key(app_key: str) -> BoostCatalogEntry:
        return next(entry for entry in BOOST_CATALOG if entry.key == app_key)

    def is_running(self, app_key: str) -> bool:
        entry = self.entry_for_key(app_key)
        if entry.is_communication_app:
            return self._communication_controllers[app_key].is_active
        return app_key in self._service.get_running_app_keys()

    def start(self, app_key: str) -> None:
        entry = self.entry_for_key(app_key)
        if entry.is_communication_app:
            self._communication_controllers[app_key].start()
            return
        self._pending_game_key = app_key
        self._sequence_controller.run(app_key)

    def stop(self, app_key: str) -> None:
        # A game itself is never closed from here -- launching one is a
        # fire-and-forget process spawn. What stops is its routing: from
        # now on the connections it opens go out directly.
        entry = self.entry_for_key(app_key)
        if entry.is_communication_app:
            self._communication_controllers[app_key].stop()
        else:
            self._routed_games.pop(app_key, None)
            self._tunnel.disable(app_key)

    def is_routed(self, app_key: str) -> bool:
        return self._tunnel.is_enabled(app_key)

    def poll_running_keys_now(self) -> None:
        self._poll_running_keys()

    def _poll_running_keys(self) -> None:
        running_keys = self._service.get_running_app_keys()
        self._release_exited_games(running_keys)
        self.running_keys_changed.emit(running_keys)

    def _release_exited_games(self, running_keys: set[str]) -> None:
        now = time.monotonic()
        for entry in BOOST_CATALOG:
            key = entry.key
            if entry.is_communication_app or not self._tunnel.is_enabled(key):
                self._routed_games.pop(key, None)
                continue
            seen_running, since = self._routed_games.get(key, (False, now))
            if key in running_keys:
                self._routed_games[key] = (True, since)
            elif seen_running or now - since > _LAUNCH_GRACE_S:
                self._routed_games.pop(key, None)
                self._tunnel.disable(key)
            else:
                self._routed_games[key] = (False, since)

    def _on_step_started(self, step_key: str) -> None:
        if self._pending_game_key is not None:
            self.step_started.emit(self._pending_game_key, step_key)

    def _on_sequence_failed(self, message: str) -> None:
        if self._pending_game_key is not None:
            self.sequence_failed.emit(self._pending_game_key, message)

    def _on_sequence_finished(self, success: bool) -> None:
        if self._pending_game_key is not None:
            self.sequence_finished.emit(self._pending_game_key, success)
            self._pending_game_key = None
