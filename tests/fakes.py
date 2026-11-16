"""In-memory stand-ins for the engine process and its control API."""
from __future__ import annotations

from boostx.core.services.tunnel.errors import EngineError, TunnelError


class FakeEngineClient:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.running = False
        self.connected_after_polls = 0
        self.tunnel_error = ""
        self.rules: list[str] = []
        self.token = ""
        self.relay = ""
        self.probe_results: list[dict] | None = None
        self.fail_start: str | None = None
        self.flows: list[dict] = []
        self._polls = 0

    def status(self) -> dict:
        if not self.running:
            return {"running": False}
        self._polls += 1
        connected = self._polls > self.connected_after_polls and not self.tunnel_error
        return {
            "running": True,
            "tunnel": {
                "connected": connected,
                "relay": self.relay,
                "rtt_ms": 23.5,
                "loss_percent": 0.5,
                "error": self.tunnel_error,
            },
            "flows": self.flows,
        }

    def probe(self, addresses: list[str]) -> list[dict]:
        self.calls.append(("probe", tuple(addresses)))
        if self.probe_results is not None:
            return self.probe_results
        return [{"relay": address, "ok": True, "rtt_ms": 10.0 + i} for i, address in enumerate(addresses)]

    def start(self, relay_address, relay_public_key, token, rules) -> dict:
        self.calls.append(("start", relay_address, relay_public_key, token, tuple(r.name for r in rules)))
        if self.fail_start:
            raise EngineError(self.fail_start, 500)
        self.running, self.relay, self.token = True, relay_address, token
        self.rules = [r.name for r in rules]
        self._polls = 0
        return {"running": True}

    def set_rules(self, rules) -> dict:
        self.calls.append(("rules", tuple(r.name for r in rules)))
        if not self.running:
            raise EngineError("engine is not running", 409)
        self.rules = [r.name for r in rules]
        return {"running": True}

    def set_token(self, token: str) -> dict:
        self.calls.append(("token", token))
        self.token = token
        return {"running": True}

    def stop(self) -> dict:
        self.calls.append(("stop",))
        self.running = False
        return {"running": False}

    def named(self, name: str) -> list[tuple]:
        return [call for call in self.calls if call[0] == name]


class FakeEngineProcess:
    """An engine that 'starts' instantly. `launches` counts how many times
    one had to be started — each of those is an administrator prompt."""

    def __init__(self, client: FakeEngineClient | None = None, start_error: TunnelError | None = None) -> None:
        self.fake_client = client or FakeEngineClient()
        self.start_error = start_error
        self.launches = 0
        self.alive = False
        self.stopped = False

    @property
    def is_running(self) -> bool:
        return self.alive

    @property
    def client(self):
        return self.fake_client if self.alive else None

    def ensure_running(self):
        if not self.alive:
            if self.start_error is not None:
                raise self.start_error
            self.launches += 1
            self.alive = True
        return self.fake_client

    def stop(self) -> None:
        self.stopped = True
        self.alive = False
        self.fake_client.running = False

    def die(self) -> None:
        self.alive = False
        self.fake_client.running = False
