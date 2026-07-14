"""UpstreamConnector that reaches the destination directly, with the
socket bound to the WireGuard tunnel interface so it — and only it —
travels through the encrypted tunnel to the VPS. No second SOCKS5 hop:
the tunnel itself carries the connection the rest of the way, same as
any real WireGuard peer.
"""
from __future__ import annotations

import socket
from dataclasses import dataclass

from loguru import logger

from boostx.core.services.net.tcp_keepalive import enable_tcp_keepalive
from boostx.core.services.vpn.interface_binding import bind_socket_to_interface
from boostx.core.services.vpn.tunnel_manager import is_tunnel_service_running

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
        try:
            sock.settimeout(_CONNECT_TIMEOUT_S)
            bind_socket_to_interface(sock, self.interface_index)
            sock.connect((dest_host, dest_port))
        except OSError:
            sock.close()
            # The tunnel manager already verifies readiness before handing
            # out an interface index, but the network can still degrade
            # after that point (another VPN toggled, adapter dropped,
            # etc.) — logging the tunnel's state at the exact moment of a
            # connect failure is what makes that distinguishable from an
            # unrelated destination-side problem when reading logs later.
            logger.warning(
                f"VPN bridge connect to {dest_host}:{dest_port} failed via interface "
                f"{self.interface_index}; tunnel_service_running={is_tunnel_service_running()}"
            )
            raise
        sock.settimeout(None)
        # Discord's gateway (and anything else long-lived/WebSocket-like)
        # is quiet between app-level heartbeats for tens of seconds — long
        # enough for a stateful middlebox on the real network path to drop
        # the idle mapping before either endpoint notices. Keepalive keeps
        # that state refreshed instead of waiting to find out the hard way.
        enable_tcp_keepalive(sock)
        return sock
