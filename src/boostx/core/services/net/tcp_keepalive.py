"""Enables aggressive TCP keepalive on a socket that will carry a
long-lived, mostly-idle connection (e.g. a WebSocket like Discord's
gateway, whose only traffic between app-level heartbeats — roughly every
41s — is silence) through an external network hop. A stateful middlebox
anywhere on that path (the relay VPS's own connection tracking, a NAT
device, a load balancer) can silently drop an idle mapping faster than
the app-level heartbeat interval tolerates; neither endpoint finds out
until they next try to send/receive, which surfaces as an abrupt
connection abort with no prior warning.

Windows' default keepalive idle time is ~2 hours — far too loose to
matter here. This tightens it to well under Discord's own heartbeat gap
so the idle mapping gets refreshed proactively instead of silently
expiring.
"""
from __future__ import annotations

import socket
import sys

from loguru import logger

_KEEPALIVE_IDLE_S = 20
_KEEPALIVE_INTERVAL_S = 10
_KEEPALIVE_COUNT = 3


def enable_tcp_keepalive(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        if sys.platform == "win32":  # pragma: no cover - Windows-only ioctl
            sock.ioctl(
                socket.SIO_KEEPALIVE_VALS,
                (1, _KEEPALIVE_IDLE_S * 1000, _KEEPALIVE_INTERVAL_S * 1000),
            )
        else:
            # Best-effort elsewhere (this app ships for Windows only; this
            # branch just keeps the logic exercisable in non-Windows tests).
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, _KEEPALIVE_IDLE_S)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, _KEEPALIVE_INTERVAL_S)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, _KEEPALIVE_COUNT)
    except OSError as exc:
        logger.debug(f"Failed to enable TCP keepalive tuning: {exc}")
