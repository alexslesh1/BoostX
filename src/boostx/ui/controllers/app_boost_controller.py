from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from boostx.core.services.boost.boost_service import BoostService
from boostx.core.services.boost.catalog import BOOST_CATALOG, BoostCatalogEntry
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.discord_vpn_controller import DiscordVpnController
from boostx.ui.controllers.telegram_vpn_controller import TelegramVpnController

_RUNNING_POLL_MS = 3000


class AppBoostController(QObject):
    """The one place that knows how to start/stop/check any BOOST_CATALOG
    entry, whether it's a regular game (BoostSequenceController.run --
    a fire-and-forget process launch with no real "stop") or a
    communication app (Discord/TelegramVpnController, which has a real
    start()/stop() tunnel session). Shared by the AppTogglesRow tiles on
    Home and Connection so that branching isn't duplicated between them.

    BoostPage keeps its own existing wiring to these same underlying
    controller instances for its full-screen boost overlay -- this class
    only tags their signals with the app_key for the smaller tile UI.
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
        discord_vpn_controller: DiscordVpnController,
        telegram_vpn_controller: TelegramVpnController,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._sequence_controller = sequence_controller
        self._communication_controllers = {
            "discord": discord_vpn_controller,
            "telegram": telegram_vpn_controller,
        }
        self._pending_game_key: str | None = None

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
        # Regular games have no real "stop" from our side -- launching one
        # is a fire-and-forget process spawn, not a session we hold open --
        # only communication apps have a real tunnel to tear down.
        entry = self.entry_for_key(app_key)
        if entry.is_communication_app:
            self._communication_controllers[app_key].stop()

    def poll_running_keys_now(self) -> None:
        self._poll_running_keys()

    def _poll_running_keys(self) -> None:
        self.running_keys_changed.emit(self._service.get_running_app_keys())

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
