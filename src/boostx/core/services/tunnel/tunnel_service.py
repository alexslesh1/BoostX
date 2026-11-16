"""Routes boosted applications through a Nexora relay.

One tunnel is shared by every boosted application: enabling the first
one brings it up, enabling more only adds them to it (without disturbing
the connections already going through), and disabling the last one takes
it down. All methods block and are meant to be called off the UI thread.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable

from loguru import logger

from boostx.core.services.api.exceptions import ApiConnectionError, ApiError
from boostx.core.services.tunnel.engine_client import EngineClient
from boostx.core.services.tunnel.engine_process import EngineProcess
from boostx.core.services.tunnel.errors import EngineError, TunnelError
from boostx.core.services.tunnel.models import (
    AppRule,
    FlowInfo,
    RelayServer,
    RelaySession,
    TunnelSnapshot,
)

SessionProvider = Callable[[], RelaySession]

_CONNECT_TIMEOUT_S = 8.0
_CONNECT_POLL_S = 0.2
# A new token is fetched this long before the current one runs out, so a
# reconnect after a network blip never presents an expired token.
_TOKEN_REFRESH_MARGIN_S = 15 * 60
_TOKEN_REFRESH_RETRY_S = 60
_SHUTDOWN_LOCK_TIMEOUT_S = 2.0
_HTTP_SERVICE_UNAVAILABLE = 503
_HTTP_FORBIDDEN = 403


class TunnelService:
    def __init__(
        self,
        session_provider: SessionProvider,
        engine: EngineProcess | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        connect_timeout_s: float = _CONNECT_TIMEOUT_S,
    ) -> None:
        self._session_provider = session_provider
        self._engine = engine or EngineProcess()
        self._clock = clock
        self._sleep = sleep
        self._connect_timeout_s = connect_timeout_s

        self._lock = threading.RLock()
        self._rules: dict[str, AppRule] = {}
        self._session: RelaySession | None = None
        self._relay: RelayServer | None = None
        self._tunnel_up = False
        self._next_token_refresh_attempt = 0.0
        self._last_snapshot = TunnelSnapshot()

    # -- public API -------------------------------------------------------
    @property
    def active_apps(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._rules)

    def enable(self, rule: AppRule) -> None:
        """Routes `rule`'s programs through the relay. Raises TunnelError
        (with a message for the user) and leaves everything as it was if
        that is not possible."""
        with self._lock:
            previous = dict(self._rules)
            self._rules[rule.name] = rule
            try:
                self._apply()
            except Exception:
                self._rules = previous
                raise

    def disable(self, app_key: str) -> None:
        """Stops routing new connections of the application. Never raises:
        switching boost off must always work from the user's side."""
        with self._lock:
            if self._rules.pop(app_key, None) is None:
                return
            client = self._engine.client
            if client is None:
                # The engine is gone, so nothing is being routed any more.
                self._mark_tunnel_down()
                return
            try:
                if self._rules:
                    client.set_rules(list(self._rules.values()))
                else:
                    self._mark_tunnel_down()
                    # The engine process itself is kept: starting it again
                    # would mean another administrator prompt the next time
                    # boost is switched on.
                    client.stop()
            except EngineError as exc:
                logger.warning(f"Could not update routing after disabling {app_key}: {exc}")

    def snapshot(self) -> TunnelSnapshot:
        """Current tunnel state. Returns the previous snapshot rather than
        waiting if an enable/disable is in progress."""
        if not self._lock.acquire(blocking=False):
            return self._last_snapshot
        try:
            self._last_snapshot = self._read_snapshot()
            return self._last_snapshot
        finally:
            self._lock.release()

    def shutdown(self) -> None:
        # Called while the app is closing, so it must not wait behind an
        # enable that is stuck (say, on an unanswered administrator prompt).
        # Stopping the engine without the lock is safe: it is the last thing
        # that happens, and the engine also exits by itself with the app.
        locked = self._lock.acquire(timeout=_SHUTDOWN_LOCK_TIMEOUT_S)
        try:
            self._rules.clear()
            self._mark_tunnel_down()
            self._engine.stop()
        finally:
            if locked:
                self._lock.release()

    # -- internals --------------------------------------------------------
    def _apply(self) -> None:
        client = self._engine.ensure_running()
        rules = list(self._rules.values())
        if self._tunnel_up:
            try:
                if client.status().get("running"):
                    client.set_rules(rules)
                    return
            except EngineError as exc:
                logger.warning(f"Engine lost its tunnel ({exc}); starting it again")
            self._tunnel_up = False
        self._start_tunnel(client, rules)

    def _start_tunnel(self, client: EngineClient, rules: list[AppRule]) -> None:
        session = self._fetch_session()
        relay = self._pick_relay(client, session.servers)
        try:
            client.start(relay.address, relay.public_key, session.token, rules)
            self._wait_connected(client)
        except EngineError as exc:
            logger.error(f"Engine could not start routing via {relay.name}: {exc}")
            self._stop_quietly(client)
            raise TunnelError(_describe_engine_error(str(exc))) from exc
        except TunnelError:
            self._stop_quietly(client)
            raise
        self._session, self._relay, self._tunnel_up = session, relay, True
        self._next_token_refresh_attempt = 0.0
        logger.info(f"Routing {[rule.name for rule in rules]} via {relay.name} ({relay.address})")

    def _fetch_session(self) -> RelaySession:
        try:
            session = self._session_provider()
        except ApiConnectionError as exc:
            raise TunnelError("Could not reach the Nexora server. Check your internet connection.") from exc
        except ApiError as exc:
            if exc.status_code == _HTTP_SERVICE_UNAVAILABLE:
                raise TunnelError("Routing servers are not available right now.") from exc
            if exc.status_code == _HTTP_FORBIDDEN:
                raise TunnelError("This device is not allowed to use routing. Please sign in again.") from exc
            raise TunnelError("Could not get routing access from the Nexora server.") from exc
        if not session.servers:
            raise TunnelError("Routing servers are not available right now.")
        return session

    @staticmethod
    def _pick_relay(client: EngineClient, servers: tuple[RelayServer, ...]) -> RelayServer:
        """The reachable relay with the lowest round-trip time from here."""
        by_address = {server.address: server for server in servers}
        try:
            results = client.probe(list(by_address))
        except EngineError as exc:
            raise TunnelError("Could not measure the routing servers.") from exc
        for result in results:  # the engine sorts fastest first
            server = by_address.get(result.get("relay", ""))
            if server is not None and result.get("ok"):
                logger.info(f"Best relay: {server.name} at {result.get('rtt_ms')} ms")
                return server
        raise TunnelError("No routing server could be reached from your network.")

    def _wait_connected(self, client: EngineClient) -> None:
        deadline = time.monotonic() + self._connect_timeout_s
        error = ""
        while True:
            status = client.status()
            tunnel = status.get("tunnel") or {}
            if tunnel.get("connected"):
                return
            error = tunnel.get("error") or status.get("error") or error
            if not status.get("running"):
                raise TunnelError(_describe_engine_error(error))
            if time.monotonic() >= deadline:
                logger.error(f"Relay did not accept the session in time: {error or 'no answer'}")
                raise TunnelError("The routing server did not respond. Please try again.")
            self._sleep(_CONNECT_POLL_S)

    def _mark_tunnel_down(self) -> None:
        self._tunnel_up = False
        self._session = None
        self._relay = None

    @staticmethod
    def _stop_quietly(client: EngineClient) -> None:
        try:
            client.stop()
        except EngineError:
            pass

    def _read_snapshot(self) -> TunnelSnapshot:
        if not self._tunnel_up or not self._rules:
            return TunnelSnapshot(active_apps=frozenset(self._rules))
        client = self._engine.client
        try:
            status = client.status() if client is not None else {}
        except EngineError as exc:
            return TunnelSnapshot(active_apps=frozenset(self._rules), error=str(exc))
        if client is None or not status.get("running"):
            # The engine went away (closed from Task Manager, crashed). The
            # applications are on their normal connection again; say so
            # instead of showing them as routed.
            self._rules.clear()
            self._mark_tunnel_down()
            return TunnelSnapshot(error=status.get("error") or "Routing stopped unexpectedly.")

        tunnel = status.get("tunnel") or {}
        self._refresh_token_if_due(client, tunnel)
        connected = bool(tunnel.get("connected"))
        return TunnelSnapshot(
            active_apps=frozenset(self._rules),
            connected=connected,
            relay_name=self._relay.name if self._relay is not None else "",
            rtt_ms=tunnel.get("rtt_ms") if connected else None,
            loss_percent=tunnel.get("loss_percent") if connected else None,
            error=tunnel.get("error") or "",
            flows=tuple(
                FlowInfo(
                    app=flow.get("app", ""),
                    exe=flow.get("exe", ""),
                    protocol=flow.get("protocol", ""),
                    remote=flow.get("remote", ""),
                    bytes_out=int(flow.get("bytes_out", 0)),
                    bytes_in=int(flow.get("bytes_in", 0)),
                )
                for flow in status.get("flows") or ()
            ),
        )

    def _refresh_token_if_due(self, client: EngineClient, tunnel: dict) -> None:
        if self._session is None:
            return
        now = self._clock()
        refused = not tunnel.get("connected") and "token" in (tunnel.get("error") or "")
        due = self._session.expires_at - now <= _TOKEN_REFRESH_MARGIN_S
        if not (due or refused) or now < self._next_token_refresh_attempt:
            return
        self._next_token_refresh_attempt = now + _TOKEN_REFRESH_RETRY_S
        try:
            session = self._fetch_session()
            client.set_token(session.token)
        except (TunnelError, EngineError) as exc:
            logger.warning(f"Could not renew the routing token: {exc}")
            return
        self._session = session
        logger.info("Routing token renewed")


def _describe_engine_error(raw: str) -> str:
    """Maps the engine's technical errors to something a user can act on."""
    lowered = raw.lower()
    if "administrator" in lowered or "access denied" in lowered:
        return "Administrator permission is needed to route traffic."
    if "signature" in lowered or "blocked from loading" in lowered:
        return "Windows blocked the routing driver. Security software may be preventing it."
    if "marked for removal" in lowered:
        return "Please restart your computer to finish updating the routing driver."
    if "token" in lowered:
        return "The routing server did not accept this session. Please sign in again."
    return "Routing could not be started. Please try again."
