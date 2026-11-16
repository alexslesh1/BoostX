import threading
from pathlib import Path

import pytest
from fakes import FakeEngineProcess

from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.catalog import DEMO_EXECUTABLE_SENTINEL
from boostx.core.services.tunnel.errors import TunnelError
from boostx.core.services.tunnel.models import AppRule, FlowInfo, RelayServer, RelaySession, TunnelSnapshot
from boostx.core.services.tunnel.tunnel_service import TunnelService
from boostx.ui.controllers import app_boost_controller as app_boost_module
from boostx.ui.controllers import app_tunnel_controller as app_tunnel_module
from boostx.ui.controllers.app_boost_controller import AppBoostController
from boostx.ui.controllers.app_tunnel_controller import AppTunnelController
from boostx.ui.controllers.boost_sequence_controller import BoostSequenceController
from boostx.ui.controllers.tunnel_controller import TunnelController

RELAY = RelayServer("fra1", "Frankfurt", "EU", "203.0.113.10:4700", "key")


class FakeTunnelService:
    """TunnelService's contract, with the outcome of each call scripted."""

    def __init__(self) -> None:
        self.rules: dict[str, AppRule] = {}
        self.enable_error: TunnelError | Exception | None = None
        self.gate: threading.Event | None = None
        self.disabled: list[str] = []
        self.shut_down = False
        self.next_snapshot: TunnelSnapshot | None = None

    def enable(self, rule: AppRule) -> None:
        if self.gate is not None:
            self.gate.wait(3)
        if self.enable_error is not None:
            raise self.enable_error
        self.rules[rule.name] = rule

    def disable(self, app_key: str) -> None:
        self.disabled.append(app_key)
        self.rules.pop(app_key, None)

    def snapshot(self) -> TunnelSnapshot:
        if self.next_snapshot is not None:
            return self.next_snapshot
        return TunnelSnapshot(active_apps=frozenset(self.rules), connected=bool(self.rules), relay_name="Frankfurt")

    def shutdown(self) -> None:
        self.shut_down = True


class Recorder:
    def __init__(self, **signals) -> None:
        self.events: list[tuple] = []
        for name, signal in signals.items():
            signal.connect(lambda *args, n=name: self.events.append((n, *args)))

    def names(self) -> list[str]:
        return [event[0] for event in self.events]


@pytest.fixture
def tunnel(qapp):
    service = FakeTunnelService()
    controller = TunnelController(service)
    controller._poll_timer.stop()  # tests drive polling themselves
    yield controller, service
    controller.shutdown()


RULE = AppRule("discord", exes=("Discord.exe",))


# --------------------------------------------------------------------------
# TunnelController
# --------------------------------------------------------------------------
def test_enable_reports_success_and_marks_the_app_routed(tunnel, wait_until):
    controller, service = tunnel
    events = Recorder(enabled=controller.app_enabled, failed=controller.app_failed)

    controller.enable("discord", RULE)
    assert controller.is_pending("discord") and not controller.is_enabled("discord")
    wait_until(lambda: events.events, message="enable result")

    assert events.events == [("enabled", "discord")]
    assert controller.is_enabled("discord") and not controller.is_pending("discord")
    assert service.rules == {"discord": RULE}


def test_enable_failure_carries_the_users_message_and_leaves_the_app_unrouted(tunnel, wait_until):
    controller, service = tunnel
    service.enable_error = TunnelError("No routing server could be reached from your network.")
    events = Recorder(enabled=controller.app_enabled, failed=controller.app_failed)

    controller.enable("discord", RULE)
    wait_until(lambda: events.events, message="enable result")

    assert events.events == [("failed", "discord", "No routing server could be reached from your network.")]
    assert not controller.is_enabled("discord") and not controller.is_pending("discord")


def test_unexpected_error_is_not_shown_raw_to_the_user(tunnel, wait_until):
    controller, service = tunnel
    service.enable_error = KeyError("servers")
    events = Recorder(failed=controller.app_failed)

    controller.enable("discord", RULE)
    wait_until(lambda: events.events, message="enable result")

    assert events.events == [("failed", "discord", "Routing could not be started. Please try again.")]


def test_switching_off_while_switching_on_ends_up_off(tunnel, wait_until, settle):
    controller, service = tunnel
    service.gate = threading.Event()
    events = Recorder(enabled=controller.app_enabled, disabled=controller.app_disabled)

    controller.enable("discord", RULE)
    controller.disable("discord")  # the user changed their mind mid-connect
    service.gate.set()
    wait_until(lambda: "discord" in service.disabled, message="the cancelled enable to be undone")
    settle()

    assert not controller.is_enabled("discord")
    assert events.names() == ["disabled"], "must never announce it as enabled"
    assert service.rules == {}


def test_disable_updates_state_immediately_and_tells_the_service(tunnel, wait_until):
    controller, service = tunnel
    controller.enable("discord", RULE)
    wait_until(lambda: controller.is_enabled("discord"))
    events = Recorder(disabled=controller.app_disabled)

    controller.disable("discord")
    assert not controller.is_enabled("discord")
    assert events.events == [("disabled", "discord")]
    wait_until(lambda: service.disabled == ["discord"])

    controller.disable("discord")
    assert events.events == [("disabled", "discord")], "disabling twice is not announced twice"


def test_routing_that_ends_on_its_own_is_reflected(tunnel, wait_until):
    controller, service = tunnel
    controller.enable("discord", RULE)
    wait_until(lambda: controller.is_enabled("discord"))
    wait_until(lambda: not controller._poll_in_flight)
    events = Recorder(disabled=controller.app_disabled, snapshot=controller.snapshot_updated)

    # The engine was closed from Task Manager: nothing is routed any more.
    service.next_snapshot = TunnelSnapshot(error="Routing stopped unexpectedly.")
    controller._poll()
    wait_until(lambda: "snapshot" in events.names(), message="snapshot")

    assert ("disabled", "discord") in events.events
    assert not controller.is_enabled("discord")
    assert controller.snapshot.error == "Routing stopped unexpectedly."


def test_status_read_before_an_enable_finished_cannot_undo_it(tunnel, wait_until, settle):
    controller, service = tunnel
    controller.enable("discord", RULE)
    wait_until(lambda: controller.is_enabled("discord"))
    wait_until(lambda: not controller._poll_in_flight)

    # A status read starts while only Discord is routed...
    gate = threading.Event()
    original = service.snapshot

    def slow_snapshot():
        result = original()
        gate.wait(3)
        return result

    service.snapshot = slow_snapshot
    controller._poll()
    # ...and a game is enabled before that read comes back.
    controller.enable("cs2", AppRule("cs2", exes=("cs2.exe",)))
    wait_until(lambda: controller.is_enabled("cs2"))
    gate.set()
    settle()

    assert controller.is_enabled("cs2"), "a stale status read switched the game off"


def test_shutdown_stops_the_service(qapp):
    service = FakeTunnelService()
    controller = TunnelController(service)
    controller.shutdown()
    assert service.shut_down and not controller._poll_timer.isActive()


# --------------------------------------------------------------------------
# AppTunnelController (Discord / Telegram)
# --------------------------------------------------------------------------
def make_app_controller(tunnel_controller, monkeypatch, *, executable, running=False, launch_ok=True):
    launched: list[Path] = []
    monkeypatch.setattr(app_tunnel_module, "is_process_running", lambda _path: running)

    def launch(path: Path) -> bool:
        launched.append(path)
        return launch_ok

    controller = AppTunnelController(
        "discord",
        "Discord",
        lambda: executable,
        launch,
        lambda exe: exe.parent.parent,
        tunnel_controller,
    )
    events = Recorder(
        started=controller.started, failed=controller.failed, stopped=controller.stopped, progress=controller.progress
    )
    return controller, events, launched


DISCORD_EXE = Path(r"C:\Users\me\AppData\Local\Discord\app-1.0.9163\Discord.exe")


def test_discord_is_routed_first_and_only_then_launched(tunnel, monkeypatch, wait_until):
    tunnel_controller, service = tunnel
    service.gate = threading.Event()
    controller, events, launched = make_app_controller(tunnel_controller, monkeypatch, executable=DISCORD_EXE)

    controller.start()
    assert events.names() == ["progress"]
    assert launched == [], "launching before routing is up would leak its first connections"
    service.gate.set()
    wait_until(lambda: "started" in events.names(), message="started")

    assert launched == [DISCORD_EXE]
    assert controller.is_active
    assert service.rules["discord"].exes == ("Discord.exe",)


def test_already_running_discord_is_not_launched_again(tunnel, monkeypatch, wait_until):
    tunnel_controller, _ = tunnel
    controller, events, launched = make_app_controller(
        tunnel_controller, monkeypatch, executable=DISCORD_EXE, running=True
    )
    controller.start()
    wait_until(lambda: "started" in events.names(), message="started")
    assert launched == []


def test_missing_discord_is_reported_without_touching_the_tunnel(tunnel, monkeypatch, settle):
    tunnel_controller, service = tunnel
    controller, events, _ = make_app_controller(tunnel_controller, monkeypatch, executable=None)
    controller.start()
    settle()
    assert events.events == [("failed", "Discord installation not found.")]
    assert service.rules == {} and not controller.is_active


def test_routing_failure_reaches_the_boost_screen_and_nothing_is_launched(tunnel, monkeypatch, wait_until):
    tunnel_controller, service = tunnel
    service.enable_error = TunnelError("Routing servers are not available right now.")
    controller, events, launched = make_app_controller(tunnel_controller, monkeypatch, executable=DISCORD_EXE)

    controller.start()
    wait_until(lambda: "failed" in events.names(), message="failure")

    assert ("failed", "Routing servers are not available right now.") in events.events
    assert launched == [] and not controller.is_active
    controller.start()  # and it can be tried again
    wait_until(lambda: events.names().count("failed") == 2, message="second failure")


def test_launch_failure_undoes_the_routing(tunnel, monkeypatch, wait_until):
    tunnel_controller, service = tunnel
    controller, events, _ = make_app_controller(
        tunnel_controller, monkeypatch, executable=DISCORD_EXE, launch_ok=False
    )
    controller.start()
    wait_until(lambda: "failed" in events.names(), message="failure")
    wait_until(lambda: service.disabled == ["discord"], message="routing to be undone")

    assert ("failed", "Unable to launch Discord.") in events.events
    assert not controller.is_active


def test_stop_ends_routing_and_announces_it(tunnel, monkeypatch, wait_until):
    tunnel_controller, service = tunnel
    controller, events, _ = make_app_controller(tunnel_controller, monkeypatch, executable=DISCORD_EXE)
    controller.start()
    wait_until(lambda: controller.is_active)

    controller.stop()
    assert not controller.is_active
    assert "stopped" in events.names()


def test_one_apps_events_do_not_leak_into_the_other(tunnel, monkeypatch, wait_until, settle):
    tunnel_controller, service = tunnel
    discord, discord_events, _ = make_app_controller(tunnel_controller, monkeypatch, executable=DISCORD_EXE)
    telegram = AppTunnelController(
        "telegram", "Telegram", lambda: Path(r"C:\T\Telegram.exe"), lambda _p: True, lambda e: e.parent, tunnel_controller
    )
    telegram_events = Recorder(started=telegram.started, failed=telegram.failed, stopped=telegram.stopped)

    discord.start()
    wait_until(lambda: "started" in discord_events.names())
    settle()
    assert telegram_events.events == []


# --------------------------------------------------------------------------
# BoostSequenceController (games)
# --------------------------------------------------------------------------
class FakeBoostService:
    def __init__(self, executable_path: str | None = r"D:\Games\CS2\game\bin\win64\cs2.exe") -> None:
        self.status = BoostAppStatus(
            app_key="counter_strike_2",
            installed=True,
            executable_path=executable_path,
            install_dir=r"D:\Games\CS2",
            source="steam",
            launch_count=0,
            last_launch_at=None,
            custom_settings=None,
        )
        self.launched: list[str] = []
        self.running: set[str] = set()

    def get_status(self, app_key: str):
        return self.status

    def get_setting(self, key: str):
        return None

    def launch_app(self, app_key: str) -> bool:
        self.launched.append(app_key)
        return True

    def get_running_app_keys(self) -> set[str]:
        return set(self.running)


@pytest.fixture
def no_optimizers(monkeypatch):
    from boostx.core.services.optimizer.optimizer_result import OptimizerResult
    from boostx.ui.controllers import boost_sequence_controller as module

    ok = lambda: OptimizerResult(step="test", success=True)  # noqa: E731
    for name in ("memory_cleanup", "enable_game_mode", "set_high_performance_power_plan", "temp_cleanup"):
        monkeypatch.setattr(module, name, ok)


def make_sequence(tunnel_controller, boost_service):
    controller = BoostSequenceController(boost_service, tunnel_controller)
    events = Recorder(
        step=controller.step_started,
        done=controller.step_completed,
        unrouted=controller.routing_unavailable,
        finished=controller.sequence_finished,
        failed=controller.sequence_failed,
    )
    return controller, events


def test_game_is_routed_before_it_is_launched(tunnel, no_optimizers, wait_until):
    tunnel_controller, service = tunnel
    service.gate = threading.Event()
    boost = FakeBoostService()
    controller, events = make_sequence(tunnel_controller, boost)
    try:
        controller.run("counter_strike_2")
        assert ("step", "route") in events.events
        assert boost.launched == [], "the game must not start before its routing is up"
        service.gate.set()
        wait_until(lambda: ("finished", True) in events.events, message="sequence to finish")

        assert boost.launched == ["counter_strike_2"]
        assert ("done", "route", True) in events.events
        assert "unrouted" not in events.names()
        rule = service.rules["counter_strike_2"]
        assert rule.exes == ("cs2.exe",) and rule.dirs == (r"D:\Games\CS2",)
    finally:
        controller.shutdown()


def test_game_still_launches_when_routing_is_unavailable_and_says_so(tunnel, no_optimizers, wait_until):
    tunnel_controller, service = tunnel
    service.enable_error = TunnelError("Routing servers are not available right now.")
    boost = FakeBoostService()
    controller, events = make_sequence(tunnel_controller, boost)
    try:
        controller.run("counter_strike_2")
        wait_until(lambda: ("finished", True) in events.events, message="sequence to finish")

        assert boost.launched == ["counter_strike_2"], "a routing problem must not stop the game from starting"
        assert ("unrouted", "Routing servers are not available right now.") in events.events
        assert ("done", "route", False) in events.events
        assert "failed" not in events.names()
        assert not tunnel_controller.is_enabled("counter_strike_2")

        # The controller is free for the next boost.
        service.enable_error = None
        assert controller.run("counter_strike_2") is True
        wait_until(lambda: events.events.count(("finished", True)) == 2, message="second run")
    finally:
        controller.shutdown()


def test_demo_entry_is_not_routed(tunnel, no_optimizers, wait_until, settle):
    tunnel_controller, service = tunnel
    boost = FakeBoostService(executable_path=DEMO_EXECUTABLE_SENTINEL)
    controller, events = make_sequence(tunnel_controller, boost)
    try:
        controller.run("test")
        wait_until(lambda: ("finished", True) in events.events, message="sequence to finish")
        settle()
        assert ("step", "route") not in events.events
        assert service.rules == {}
    finally:
        controller.shutdown()


def test_another_apps_routing_result_does_not_launch_a_waiting_game(tunnel, no_optimizers, wait_until, settle):
    tunnel_controller, service = tunnel
    boost = FakeBoostService()
    controller, events = make_sequence(tunnel_controller, boost)
    try:
        tunnel_controller.enable("discord", RULE)
        wait_until(lambda: tunnel_controller.is_enabled("discord"))
        service.gate = threading.Event()
        controller.run("counter_strike_2")
        # Discord being (re)announced must not count as the game's result.
        tunnel_controller.enable("discord", RULE)
        settle()
        assert boost.launched == []
        service.gate.set()
        wait_until(lambda: boost.launched == ["counter_strike_2"], message="launch")
    finally:
        controller.shutdown()


# --------------------------------------------------------------------------
# AppBoostController
# --------------------------------------------------------------------------
def make_app_boost(tunnel_controller, boost):
    sequence = BoostSequenceController(boost, tunnel_controller)
    controller = AppBoostController(boost, sequence, {}, tunnel_controller)
    controller._running_poll_timer.stop()
    return controller, sequence


def test_routing_ends_when_the_game_exits(tunnel, no_optimizers, wait_until, monkeypatch):
    tunnel_controller, service = tunnel
    boost = FakeBoostService()
    controller, sequence = make_app_boost(tunnel_controller, boost)
    try:
        controller.start("counter_strike_2")
        wait_until(lambda: tunnel_controller.is_enabled("counter_strike_2"))

        controller.poll_running_keys_now()  # still starting up: not seen yet
        assert tunnel_controller.is_enabled("counter_strike_2")

        boost.running = {"counter_strike_2"}
        controller.poll_running_keys_now()
        assert tunnel_controller.is_enabled("counter_strike_2")

        boost.running = set()  # the player closed the game
        controller.poll_running_keys_now()
        assert not tunnel_controller.is_enabled("counter_strike_2")
        wait_until(lambda: service.disabled == ["counter_strike_2"])
    finally:
        sequence.shutdown()
        controller.shutdown()


def test_game_that_never_appears_is_released_after_the_grace_period(tunnel, no_optimizers, wait_until, monkeypatch):
    tunnel_controller, _ = tunnel
    boost = FakeBoostService()
    controller, sequence = make_app_boost(tunnel_controller, boost)
    now = [1000.0]
    monkeypatch.setattr(app_boost_module.time, "monotonic", lambda: now[0])
    try:
        controller.start("counter_strike_2")
        wait_until(lambda: tunnel_controller.is_enabled("counter_strike_2"))
        controller.poll_running_keys_now()
        now[0] += app_boost_module._LAUNCH_GRACE_S - 1
        controller.poll_running_keys_now()
        assert tunnel_controller.is_enabled("counter_strike_2")
        now[0] += 2
        controller.poll_running_keys_now()
        assert not tunnel_controller.is_enabled("counter_strike_2")
    finally:
        sequence.shutdown()
        controller.shutdown()


def test_stopping_a_game_boost_ends_its_routing_only(tunnel, no_optimizers, wait_until):
    tunnel_controller, _ = tunnel
    boost = FakeBoostService()
    controller, sequence = make_app_boost(tunnel_controller, boost)
    try:
        tunnel_controller.enable("discord", RULE)
        controller.start("counter_strike_2")
        wait_until(lambda: tunnel_controller.is_enabled("counter_strike_2") and tunnel_controller.is_enabled("discord"))
        assert controller.is_routed("counter_strike_2")

        controller.stop("counter_strike_2")
        assert not controller.is_routed("counter_strike_2")
        assert tunnel_controller.is_enabled("discord")
    finally:
        sequence.shutdown()
        controller.shutdown()


# --------------------------------------------------------------------------
# Real TunnelService behind the Qt controller
# --------------------------------------------------------------------------
def test_controller_with_the_real_service_and_a_fake_engine(qapp, wait_until):
    engine = FakeEngineProcess()
    service = TunnelService(
        lambda: RelaySession("tok", 10**10, (RELAY,)), engine=engine, sleep=lambda _s: None, connect_timeout_s=0.5
    )
    controller = TunnelController(service)
    controller._poll_timer.stop()
    snapshots: list[TunnelSnapshot] = []
    controller.snapshot_updated.connect(snapshots.append)
    try:
        engine.fake_client.flows = [
            {"app": "discord", "exe": "Discord.exe", "protocol": "UDP", "remote": "66.22.200.1:50001",
             "bytes_out": 10, "bytes_in": 20}
        ]  # fmt: skip
        controller.enable("discord", RULE)
        wait_until(lambda: snapshots, message="first snapshot")

        assert controller.is_enabled("discord")
        assert snapshots[-1].connected and snapshots[-1].relay_name == "Frankfurt"
        assert snapshots[-1].flows_for("discord") == (
            FlowInfo("discord", "Discord.exe", "UDP", "66.22.200.1:50001", 10, 20),
        )
    finally:
        controller.shutdown()
    assert engine.stopped
