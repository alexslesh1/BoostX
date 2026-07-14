"""Shared bidirectional TCP byte relay used by both the SOCKS5 bridge
(kept as a fallback path) and the WinDivert-based transparent relay that
replaces it as the primary path. Extracted so the half-close fix and its
regression tests live in exactly one place rather than being duplicated
(and potentially re-broken) across two relay implementations.

A clean EOF on one leg only half-closes the corresponding write side of
the other leg (SHUT_WR), rather than fully closing both sockets — an
unconditional SHUT_RDWR on any signal (clean EOF included) kills a peer
leg that may still be mid-response, which was the original bug here.
"""
from __future__ import annotations

import socket
import threading
from typing import Callable

from loguru import logger

_RELAY_CHUNK_SIZE = 8192


def extract_sni(data: bytes) -> str | None:
    """Best-effort SNI extraction from a plaintext TLS ClientHello. The SNI
    extension is sent unencrypted by design (the server needs it before any
    keys exist), so this needs no decryption — just enough of RFC 8446's
    record/handshake framing to walk to the extension. Returns None on any
    failure or on non-ClientHello traffic; this is purely a diagnostic aid
    for comparing a session's first bytes against a known-good client and
    must never affect the relay itself.
    """
    try:
        if len(data) < 5 or data[0] != 0x16:  # TLS record type: handshake
            return None
        pos = 5  # skip the 5-byte record header
        if data[pos] != 0x01:  # Handshake type: ClientHello
            return None
        pos += 4  # handshake type (1 byte) + length (3 bytes)
        pos += 2 + 32  # client_version (2) + random (32)
        session_id_len = data[pos]
        pos += 1 + session_id_len
        cipher_suites_len = int.from_bytes(data[pos:pos + 2], "big")
        pos += 2 + cipher_suites_len
        compression_len = data[pos]
        pos += 1 + compression_len
        extensions_len = int.from_bytes(data[pos:pos + 2], "big")
        pos += 2
        extensions_end = pos + extensions_len
        while pos < extensions_end:
            ext_type = int.from_bytes(data[pos:pos + 2], "big")
            ext_len = int.from_bytes(data[pos + 2:pos + 4], "big")
            ext_data_start = pos + 4
            if ext_type == 0x0000:  # server_name
                sni_pos = ext_data_start + 2  # skip server_name_list length
                if data[sni_pos] == 0x00:  # name_type: host_name
                    name_len = int.from_bytes(data[sni_pos + 1:sni_pos + 3], "big")
                    return data[sni_pos + 3:sni_pos + 3 + name_len].decode("ascii", errors="replace")
            pos = ext_data_start + ext_len
        return None
    except (IndexError, UnicodeDecodeError):
        return None


def pump(
    session_id: str,
    direction: str,
    source: socket.socket,
    destination: socket.socket,
    on_first_chunk: Callable[[bytes], None] | None = None,
) -> None:
    total_bytes = 0
    first_chunk = True
    try:
        while True:
            chunk = source.recv(_RELAY_CHUNK_SIZE)
            if not chunk:
                logger.info(f"[{session_id}] {direction}: clean EOF after {total_bytes} bytes")
                break
            if first_chunk:
                first_chunk = False
                if on_first_chunk is not None:
                    on_first_chunk(chunk)
            total_bytes += len(chunk)
            destination.sendall(chunk)
    except OSError as exc:
        logger.info(f"[{session_id}] {direction}: {exc} after {total_bytes} bytes")
        # A real error (as opposed to a clean EOF) means the connection
        # itself is broken — tear down both legs, not just this one.
        for sock in (source, destination):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        return

    # Clean EOF only means THIS direction is done (the peer finished
    # writing) — it says nothing about the other direction, which may
    # still be relaying an in-flight response. Half-closing just the
    # write side propagates that forward without killing a still-active
    # peer leg out from under it.
    try:
        destination.shutdown(socket.SHUT_WR)
    except OSError:
        pass


def relay_bidirectional(
    session_id: str,
    client_socket: socket.socket,
    upstream_socket: socket.socket,
    on_first_client_chunk: Callable[[bytes], None] | None = None,
) -> None:
    """Pumps both directions of a client<->upstream TCP pair until both
    sides are done. Blocks until the client->upstream direction finishes;
    the caller is responsible for closing both sockets afterward."""
    reverse_pump = threading.Thread(
        target=pump,
        args=(session_id, "upstream->client", upstream_socket, client_socket),
        daemon=True,
    )
    reverse_pump.start()
    try:
        pump(session_id, "client->upstream", client_socket, upstream_socket, on_first_chunk=on_first_client_chunk)
    finally:
        reverse_pump.join(timeout=2.0)
    logger.info(f"[{session_id}]: relay finished")
