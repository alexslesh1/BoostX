"""UpstreamConnector that hops through an authenticated SOCKS5 proxy (the
shared 3proxy relay) — the original Boost Discord/Telegram transport,
kept as-is and unaffected by the newer WireGuard-based VPN transport.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

from python_socks.sync import Proxy

_UPSTREAM_CONNECT_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Socks5UpstreamConnector:
    host: str
    port: int
    login: str
    password: str

    def __call__(self, dest_host: str, dest_port: int) -> socket.socket:
        url = f"socks5://{self.login}:{self.password}@{self.host}:{self.port}"
        return Proxy.from_url(url).connect(dest_host, dest_port, timeout=_UPSTREAM_CONNECT_TIMEOUT_S)
