import pytest
from fakes import FakeEngineProcess

from boostx.core.services.api.exceptions import ApiConnectionError, ApiError
from boostx.core.services.tunnel.errors import ElevationDeclinedError, TunnelError
from boostx.core.services.tunnel.models import AppRule, RelayServer, RelaySession
from boostx.core.services.tunnel.tunnel_service import TunnelService

FRANKFURT = RelayServer("fra1", "Frankfurt", "EU", "203.0.113.10:4700", "key-fra")
STOCKHOLM = RelayServer("sto1", "Stockholm", "EU", "203.0.113.20:4700", "key-sto")
GAME = AppRule("counter_strike_2", exes=("cs2.exe",))
DISCORD = AppRule("discord", dirs=(r"C:\Users\me\AppData\Local\Discord",))


class Backend:
    def __init__(self, servers=(FRANKFURT, STOCKHOLM), expires_at=10_000) -> None:
        self.servers = servers
        self.expires_at = expires_at
        self.calls = 0
        self.error: Exception | None = None

    def __call__(self) -> RelaySession:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return RelaySession(token=f"token-{self.calls}", expires_at=self.expires_at, servers=tuple(self.servers))


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def make(backend=None, engine=None, clock=None):
    backend = backend or Backend()
    engine = engine or FakeEngineProcess()
    service = TunnelService(
        backend, engine=engine, clock=clock or Clock(), sleep=lambda _s: None, connect_timeout_s=0.5
    )
    return service, backend, engine, engine.fake_client


def test_first_app_starts_the_tunnel_on_the_fastest_reachable_relay():
    service, backend, engine, client = make()
    client.probe_results = [
        {"relay": STOCKHOLM.address, "ok": True, "rtt_ms": 18.0},
        {"relay": FRANKFURT.address, "ok": True, "rtt_ms": 41.0},
    ]

    service.enable(GAME)

    assert client.named("start") == [("start", STOCKHOLM.address, "key-sto", "token-1", ("counter_strike_2",))]
    assert engine.launches == 1
    snapshot = service.snapshot()
    assert snapshot.connected and snapshot.relay_name == "Stockholm"
    assert snapshot.active_apps == {"counter_strike_2"}
    assert snapshot.rtt_ms == 23.5


def test_unreachable_relays_are_skipped():
    service, _, _, client = make()
    client.probe_results = [
        {"relay": FRANKFURT.address, "ok": True, "rtt_ms": 60.0},
        {"relay": STOCKHOLM.address, "ok": False, "rtt_ms": 0},
    ]
    service.enable(GAME)
    assert client.named("start")[0][1] == FRANKFURT.address


def test_no_reachable_relay_is_reported_and_nothing_is_left_enabled():
    service, _, _, client = make()
    client.probe_results = [{"relay": FRANKFURT.address, "ok": False}, {"relay": STOCKHOLM.address, "ok": False}]

    with pytest.raises(TunnelError, match="No routing server could be reached"):
        service.enable(GAME)

    assert client.named("start") == []
    assert service.active_apps == frozenset()


def test_second_app_joins_the_running_tunnel_without_restarting_it():
    service, backend, engine, client = make()
    service.enable(GAME)
    service.enable(DISCORD)

    assert len(client.named("start")) == 1, "restarting would drop the first app's connections"
    assert client.named("rules") == [("rules", ("counter_strike_2", "discord"))]
    assert backend.calls == 1 and engine.launches == 1
    assert service.active_apps == {"counter_strike_2", "discord"}


def test_disabling_one_app_keeps_the_other_routed_and_the_last_one_stops_the_tunnel():
    service, _, engine, client = make()
    service.enable(GAME)
    service.enable(DISCORD)

    service.disable("counter_strike_2")
    assert client.named("rules")[-1] == ("rules", ("discord",))
    assert client.running and client.named("stop") == []

    service.disable("discord")
    assert client.named("stop") == [("stop",)]
    assert not client.running
    assert engine.alive and not engine.stopped, "the engine stays up so the next boost needs no new prompt"
    assert service.snapshot().active_apps == frozenset()

    service.enable(GAME)
    assert engine.launches == 1
    assert len(client.named("start")) == 2


def test_disable_of_an_app_that_is_not_enabled_does_nothing():
    service, _, engine, client = make()
    service.disable("discord")
    assert client.calls == [] and engine.launches == 0


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiConnectionError(), "Could not reach the Nexora server"),
        (ApiError("x", status_code=503), "not available right now"),
        (ApiError("x", status_code=403), "not allowed"),
        (ApiError("x", status_code=500), "Could not get routing access"),
    ],
)
def test_backend_failures_become_messages_for_the_user(error, expected):
    backend = Backend()
    backend.error = error
    service, _, _, client = make(backend=backend)

    with pytest.raises(TunnelError, match=expected):
        service.enable(GAME)
    assert client.named("start") == []
    assert service.active_apps == frozenset()


def test_backend_with_no_servers_is_reported():
    service, *_ = make(backend=Backend(servers=()))
    with pytest.raises(TunnelError, match="not available right now"):
        service.enable(GAME)


def test_declined_administrator_prompt_is_reported_and_leaves_nothing_enabled():
    engine = FakeEngineProcess(start_error=ElevationDeclinedError())
    service, backend, _, _ = make(engine=engine)

    with pytest.raises(TunnelError, match="Administrator permission"):
        service.enable(GAME)
    assert service.active_apps == frozenset()
    assert backend.calls == 0


def test_engine_refusing_to_start_is_explained_and_stopped():
    service, _, _, client = make()
    client.fail_start = "WinDivertOpen: the driver was blocked from loading (security software, or a non-local folder)"

    with pytest.raises(TunnelError, match="Windows blocked the routing driver"):
        service.enable(GAME)
    assert service.active_apps == frozenset()
    assert client.named("stop") == [("stop",)]


def test_relay_that_never_accepts_the_session_fails_and_stops_capturing():
    service, _, _, client = make()
    client.connected_after_polls = 10**9

    with pytest.raises(TunnelError, match="did not respond"):
        service.enable(GAME)
    assert not client.running, "an engine left running would keep capturing with no relay"
    assert service.active_apps == frozenset()


def test_failed_enable_of_a_second_app_leaves_the_first_one_routed():
    service, _, _, client = make()
    service.enable(GAME)

    def broken_set_rules(_rules):
        raise TunnelError("boom")

    client.set_rules = broken_set_rules
    with pytest.raises(TunnelError):
        service.enable(DISCORD)
    assert service.active_apps == {"counter_strike_2"}
    assert client.running


def test_token_is_renewed_before_it_expires_without_restarting():
    clock = Clock(0)
    service, backend, _, client = make(backend=Backend(expires_at=10_000), clock=clock)
    service.enable(GAME)

    clock.now = 10_000 - 16 * 60
    service.snapshot()
    assert client.named("token") == [], "too early"

    clock.now = 10_000 - 14 * 60
    backend.expires_at = 20_000
    service.snapshot()
    assert client.named("token") == [("token", "token-2")]
    assert len(client.named("start")) == 1

    service.snapshot()
    assert len(client.named("token")) == 1, "the renewed token is not due again"


def test_failed_token_renewal_is_retried_later_not_on_every_poll():
    clock = Clock(10_000 - 60)
    service, backend, _, client = make(backend=Backend(expires_at=10_000), clock=clock)
    service.enable(GAME)
    backend.error = ApiConnectionError()

    for _ in range(5):
        service.snapshot()
    assert backend.calls == 2, "one start, one failed renewal"

    clock.now += 61
    backend.error = None
    backend.expires_at = 20_000
    service.snapshot()
    assert client.named("token") == [("token", "token-3")]


def test_relay_rejecting_an_expired_token_triggers_renewal_at_once():
    service, backend, _, client = make(backend=Backend(expires_at=10**9))
    service.enable(GAME)
    client.tunnel_error = "relay rejected the session token"

    snapshot = service.snapshot()
    assert client.named("token") == [("token", "token-2")]
    assert not snapshot.connected and snapshot.rtt_ms is None


def test_engine_dying_is_reported_and_never_restarted_just_to_read_status():
    service, _, engine, client = make()
    service.enable(GAME)
    engine.die()

    snapshot = service.snapshot()
    assert snapshot.active_apps == frozenset()
    assert "stopped" in snapshot.error.lower()
    assert engine.launches == 1, "reading status must never raise an administrator prompt"

    service.disable("counter_strike_2")
    assert engine.launches == 1

    service.enable(GAME)
    assert engine.launches == 2
    assert len(client.named("start")) == 2


def test_snapshot_reports_each_apps_connections():
    service, _, _, client = make()
    service.enable(GAME)
    service.enable(DISCORD)
    client.flows = [
        {"app": "counter_strike_2", "exe": "cs2.exe", "protocol": "UDP", "remote": "155.133.248.34:27015",
         "bytes_out": 1000, "bytes_in": 9000},
        {"app": "discord", "exe": "Discord.exe", "protocol": "TCP", "remote": "162.159.130.234:443",
         "bytes_out": 50, "bytes_in": 70},
    ]  # fmt: skip

    snapshot = service.snapshot()
    game_flows = snapshot.flows_for("counter_strike_2")
    assert [(f.exe, f.protocol, f.remote, f.bytes_out, f.bytes_in) for f in game_flows] == [
        ("cs2.exe", "UDP", "155.133.248.34:27015", 1000, 9000)
    ]
    assert len(snapshot.flows_for("discord")) == 1
    assert snapshot.flows_for("telegram") == ()


def test_shutdown_stops_the_engine_process():
    service, _, engine, _ = make()
    service.enable(GAME)
    service.shutdown()
    assert engine.stopped
    assert service.active_apps == frozenset()


def test_boost_metrics_use_the_measured_route_when_there_is_one():
    from boostx.core.services.boost.boost_metrics import BoostMetricsProvider

    provider = BoostMetricsProvider()
    provider.start()
    measured: list[tuple[float, float] | None] = [(31.4, 0.0)]
    provider.set_network_source(lambda: measured[0])

    sample = provider.sample()
    assert (sample.ping_ms, sample.packet_loss_percent) == (31.4, 0.0), "0% loss is a measurement, not 'missing'"

    measured[0] = None  # the application is not routed
    assert provider.sample().ping_ms >= 15
