"""Records, per (protocol, client_ip, client_port), the true destination a
tracked process's connection was headed to before the NETWORK-layer
interceptor rewrote it to point at the local transparent relay instead.

This exists because WinDivert can't redirect an *outbound* packet to a
different real network interface on send (its own docs say the
IfIdx/SubIfIdx fields are ignored for outbound injection — only inbound
injection honors them), so getting a tracked app's traffic onto the
WireGuard tunnel can't be done by rewriting the source address and
re-injecting. What *does* work (and is WinDivert's own documented
`streamdump`-style pattern) is redirecting the packet's destination to a
local relay, which then opens a brand-new real connection to the true
destination bound to the tunnel interface via IP_UNICAST_IF. This table
is the memory of "where did that redirected connection actually want to
go" that the relay consults once it accepts it.

Entry lifecycle is owned by the relay, not by FIN/RST-sniffing here: once
a TCP session is genuinely established end-to-end (process <-> real
server, tunnelled via the relay's own outbound leg), the OS's two real
TCP stacks handle all of the connection's actual state machine — this
table only needs to know "is this still a live redirect" for as long as
the relay's own connection handler is running, and the handler already
knows exactly when that is. `sweep_idle` exists purely as a fallback for
a relay handler that crashes without cleaning up after itself.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class RedirectEntry:
    protocol: str
    client_ip: str
    client_port: int
    real_dst_ip: str
    real_dst_port: int
    last_seen: float


class RedirectTable:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple[str, str, int], RedirectEntry] = {}

    def get_or_create(
        self, protocol: str, client_ip: str, client_port: int, real_dst_ip: str, real_dst_port: int
    ) -> tuple[RedirectEntry, bool]:
        """Returns (entry, created) — `created` is True only the first
        time this exact flow is seen, so a caller can log a "redirect
        happened" line exactly once per flow instead of once per packet."""
        key = (protocol, client_ip, client_port)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                entry.last_seen = time.monotonic()
                return entry, False
            entry = RedirectEntry(
                protocol=protocol,
                client_ip=client_ip,
                client_port=client_port,
                real_dst_ip=real_dst_ip,
                real_dst_port=real_dst_port,
                last_seen=time.monotonic(),
            )
            self._entries[key] = entry
            return entry, True

    def lookup(self, protocol: str, client_ip: str, client_port: int) -> RedirectEntry | None:
        with self._lock:
            entry = self._entries.get((protocol, client_ip, client_port))
            if entry is not None:
                entry.last_seen = time.monotonic()
            return entry

    def remove(self, entry: RedirectEntry) -> None:
        with self._lock:
            self._entries.pop((entry.protocol, entry.client_ip, entry.client_port), None)

    def sweep_idle(self, idle_timeout_s: float) -> list[RedirectEntry]:
        deadline = time.monotonic() - idle_timeout_s
        with self._lock:
            expired = [e for e in self._entries.values() if e.last_seen < deadline]
            for entry in expired:
                self._entries.pop((entry.protocol, entry.client_ip, entry.client_port), None)
        return expired

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)
