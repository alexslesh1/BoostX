"""Data passed between the backend, the tunnel service and the UI."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RelayServer:
    id: str
    name: str
    region: str
    address: str  # host:port
    public_key: str


@dataclass(frozen=True)
class RelaySession:
    """What the backend hands a signed-in device: the relays that exist and
    a token they accept until `expires_at` (unix seconds)."""

    token: str
    expires_at: int
    servers: tuple[RelayServer, ...]


@dataclass(frozen=True)
class AppRule:
    """Which programs belong to one boosted application. `name` is the
    catalog key, so connections reported by the engine can be attributed
    back to the application they belong to."""

    name: str
    exes: tuple[str, ...] = ()
    dirs: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return {"name": self.name, "exes": list(self.exes), "dirs": list(self.dirs)}


@dataclass(frozen=True)
class FlowInfo:
    """One connection of a boosted application that goes through the relay."""

    app: str
    exe: str
    protocol: str
    remote: str
    bytes_out: int
    bytes_in: int


@dataclass(frozen=True)
class TunnelSnapshot:
    """Point-in-time state of the tunnel, for the Connection page."""

    active_apps: frozenset[str] = frozenset()
    connected: bool = False
    relay_name: str = ""
    rtt_ms: float | None = None
    loss_percent: float | None = None
    error: str = ""
    flows: tuple[FlowInfo, ...] = field(default_factory=tuple)

    def flows_for(self, app_key: str) -> tuple[FlowInfo, ...]:
        return tuple(flow for flow in self.flows if flow.app == app_key)
