"""UpstreamConnector that reaches the destination directly, with the
socket bound to the WireGuard tunnel interface so it — and only it —
travels through the encrypted tunnel to the VPS. No second SOCKS5 hop:
the tunnel itself carries the connection the rest of the way, same as
any real WireGuard peer.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

from boostx.core.services.vpn.interface_binding import bind_socket_to_interface

_CONNECT_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class WireguardUpstreamConnector:
    interface_index: int

    def __call__(self, dest_host: str, dest_port: int) -> socket.socket:
        # dest_host is resolved locally (via the normal, untunneled DNS
        # path) before the TCP connect — unlike the SOCKS5 transport,
        # which resolves domain names remotely at the relay. Only the
        # actual data connection travels through the tunnel.
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(_CONNECT_TIMEOUT_S)
        bind_socket_to_interface(sock, self.interface_index)
        sock.connect((dest_host, dest_port))
        sock.settimeout(None)
        return sock
