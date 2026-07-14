"""A local, unauthenticated SOCKS5 server that relays every connection
through a pluggable upstream connector.

Discord/Chromium's --proxy-server flag (and, for the local-bridge variant
used by the VPN feature, Telegram's tg://socks deep link) has no way to
carry credentials or route selection logic, so we bind a bridge on
127.0.0.1 that the app connects to with no credentials at all. What
happens to a connection once it reaches this bridge is entirely up to the
injected `UpstreamConnector` — today that's either an authenticated SOCKS5
hop to the shared 3proxy relay (see discord_boost/telegram proxy paths),
or a direct connect bound to the WireGuard tunnel interface (see
core/services/vpn) — the bridge itself doesn't know or care which.
"""
from __future__ import annotations

import socket
import socketserver
import threading
from typing import Callable

from loguru import logger

from boostx.core.services.net.tcp_pump import extract_sni, relay_bidirectional

# Given (dest_host, dest_port), returns a connected socket to that
# destination — however it gets there is the connector's business.
UpstreamConnector = Callable[[str, int], socket.socket]

_SOCKS_VERSION = 0x05
_METHOD_NO_AUTH = 0x00
_CMD_CONNECT = 0x01
_ATYP_IPV4 = 0x01
_ATYP_DOMAIN = 0x03
_ATYP_IPV6 = 0x04
_REPLY_SUCCEEDED = 0x00
_REPLY_GENERAL_FAILURE = 0x01
_REPLY_COMMAND_NOT_SUPPORTED = 0x07


class _BridgeRequestHandler(socketserver.BaseRequestHandler):
    server: "_BridgeServer"

    def handle(self) -> None:
        try:
            dest_host, dest_port = self._read_socks5_request()
        except (OSError, ValueError) as exc:
            logger.debug(f"SOCKS5 bridge: bad client request: {exc}")
            return

        session_id = f"{dest_host}:{dest_port}#{id(self.request):x}"

        try:
            upstream_socket = self.server.upstream_connector(dest_host, dest_port)
        except Exception as exc:
            logger.warning(f"SOCKS5 bridge [{session_id}]: upstream connect failed: {exc}")
            self._send_reply(_REPLY_GENERAL_FAILURE)
            return

        logger.info(f"SOCKS5 bridge [{session_id}]: connected, relaying")
        self._send_reply(_REPLY_SUCCEEDED)
        self._relay(session_id, self.request, upstream_socket)

    def _read_socks5_request(self) -> tuple[str, int]:
        client = self.request
        version, n_methods = self._recv_exact(client, 2)
        if version != _SOCKS_VERSION:
            raise ValueError(f"unsupported SOCKS version {version}")
        self._recv_exact(client, n_methods)  # offered auth methods — we only ever accept no-auth
        client.sendall(bytes([_SOCKS_VERSION, _METHOD_NO_AUTH]))

        version, cmd, _reserved, atyp = self._recv_exact(client, 4)
        if version != _SOCKS_VERSION or cmd != _CMD_CONNECT:
            self._send_reply(_REPLY_COMMAND_NOT_SUPPORTED)
            raise ValueError("unsupported SOCKS5 command")

        if atyp == _ATYP_IPV4:
            dest_host = socket.inet_ntoa(bytes(self._recv_exact(client, 4)))
        elif atyp == _ATYP_DOMAIN:
            (length,) = self._recv_exact(client, 1)
            dest_host = bytes(self._recv_exact(client, length)).decode("utf-8", errors="replace")
        elif atyp == _ATYP_IPV6:
            dest_host = socket.inet_ntop(socket.AF_INET6, bytes(self._recv_exact(client, 16)))
        else:
            raise ValueError(f"unsupported SOCKS5 address type {atyp}")

        port_bytes = self._recv_exact(client, 2)
        dest_port = int.from_bytes(bytes(port_bytes), "big")
        return dest_host, dest_port

    def _send_reply(self, reply_code: int) -> None:
        # BND.ADDR/BND.PORT are irrelevant to CONNECT-only clients like a browser
        # or Electron app; 0.0.0.0:0 is the conventional placeholder.
        self.request.sendall(bytes([_SOCKS_VERSION, reply_code, 0x00, _ATYP_IPV4, 0, 0, 0, 0, 0, 0]))

    def _relay(self, session_id: str, client_socket: socket.socket, upstream_socket: socket.socket) -> None:
        def log_first_chunk(chunk: bytes) -> None:
            # Only the client's very first outbound chunk carries a TLS
            # ClientHello worth inspecting — this is the exact byte
            # sequence a fingerprinting server (e.g. Cloudflare) would
            # judge, so it's logged unconditionally rather than only on
            # error, letting a failing session be compared against a
            # known-good one (e.g. curl) after the fact.
            sni = extract_sni(chunk)
            logger.info(
                f"SOCKS5 bridge [{session_id}] client->upstream: first chunk "
                f"{len(chunk)} bytes, sni={sni!r}, prefix={chunk[:16].hex()}"
            )

        try:
            relay_bidirectional(
                f"SOCKS5 bridge [{session_id}]", client_socket, upstream_socket, on_first_client_chunk=log_first_chunk
            )
        finally:
            # The framework closes the client-facing socket for us once
            # handle() returns; the upstream socket is ours to clean up —
            # shutdown() alone doesn't release the file descriptor.
            try:
                upstream_socket.close()
            except OSError:
                pass

    @staticmethod
    def _recv_exact(sock: socket.socket, count: int) -> bytes:
        data = b""
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise OSError("connection closed while reading SOCKS5 request")
            data += chunk
        return data


class _BridgeServer(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, upstream_connector: UpstreamConnector) -> None:
        self.upstream_connector = upstream_connector
        super().__init__(("127.0.0.1", 0), _BridgeRequestHandler)


class Socks5Bridge:
    def __init__(self, upstream_connector: UpstreamConnector) -> None:
        self._server = _BridgeServer(upstream_connector)
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
