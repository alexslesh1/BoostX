"""Local TCP listener that accepts WinDivert-redirected connections (see
network_interceptor.py) and forwards them to the real destination via a
brand-new outbound connection bound to the tunnel interface with
IP_UNICAST_IF — the same interface-binding mechanism the SOCKS5-based
architecture already used and proved working. The redirected process
never sees any of this: from its own TCP stack's perspective it just
connected directly to its real destination — WinDivert quietly changed
where the SYN actually landed, and this relay quietly recovers where it
was actually headed.
"""
from __future__ import annotations

import socket
import socketserver
import threading

from loguru import logger

from boostx.core.services.interception.redirect_table import RedirectTable
from boostx.core.services.net.tcp_pump import extract_sni, relay_bidirectional
from boostx.core.services.vpn.interface_binding import bind_socket_to_interface

_CONNECT_TIMEOUT_S = 10.0


class _RelayRequestHandler(socketserver.BaseRequestHandler):
    server: "_RelayServer"

    def handle(self) -> None:
        client_ip, client_port = self.request.getpeername()
        entry = self.server.redirect_table.lookup("tcp", client_ip, client_port)
        if entry is None:
            # Shouldn't happen: the interceptor only ever redirects a
            # packet after recording its true destination. Defensive only.
            logger.warning(f"Transparent relay: no redirect entry for {client_ip}:{client_port}, closing")
            return

        session_id = f"{entry.real_dst_ip}:{entry.real_dst_port}#{id(self.request):x}"
        try:
            upstream_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            upstream_socket.settimeout(_CONNECT_TIMEOUT_S)
            bind_socket_to_interface(upstream_socket, self.server.tunnel_interface_index)
            upstream_socket.connect((entry.real_dst_ip, entry.real_dst_port))
            upstream_socket.settimeout(None)
        except OSError as exc:
            logger.warning(f"Transparent relay [{session_id}]: upstream connect failed: {exc}")
            self.server.redirect_table.remove(entry)
            return

        logger.info(f"Transparent relay [{session_id}]: connected, relaying")

        def log_first_chunk(chunk: bytes) -> None:
            # Same diagnostic purpose as the SOCKS5 bridge's equivalent
            # logging: compare a session's first bytes/SNI against a
            # known-good client when something goes wrong for one app but
            # not another.
            sni = extract_sni(chunk)
            logger.info(
                f"Transparent relay [{session_id}] client->upstream: first chunk "
                f"{len(chunk)} bytes, sni={sni!r}, prefix={chunk[:16].hex()}"
            )

        try:
            relay_bidirectional(
                f"Transparent relay [{session_id}]",
                self.request,
                upstream_socket,
                on_first_client_chunk=log_first_chunk,
            )
        finally:
            try:
                upstream_socket.close()
            except OSError:
                pass
            self.server.redirect_table.remove(entry)


class _RelayServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, redirect_table: RedirectTable, tunnel_interface_index: int) -> None:
        self.redirect_table = redirect_table
        self.tunnel_interface_index = tunnel_interface_index
        super().__init__(("127.0.0.1", 0), _RelayRequestHandler)


class TransparentRelay:
    def __init__(self, redirect_table: RedirectTable, tunnel_interface_index: int) -> None:
        self._server = _RelayServer(redirect_table, tunnel_interface_index)
        self._thread: threading.Thread | None = None

    @property
    def local_port(self) -> int:
        return self._server.server_address[1]

    def start(self) -> None:
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
