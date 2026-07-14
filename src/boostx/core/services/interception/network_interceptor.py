"""Owns the single NETWORK-layer WinDivert handle that redirects a tracked
process's outbound TCP traffic to the local transparent relay (see
transparent_relay.py) instead of letting it go straight to its real
destination.

A single broad, static filter (`outbound and tcp`) is used rather than one
scoped to the currently-tracked ports: WinDivert filters can't be updated
on an open handle, and the tracked-port set changes on every new
connection a process opens — reopening per-change would mean a filter
rebuild (and a packet-loss window) on every single connection. For
traffic unrelated to a tracked app, that churn buys nothing. Instead,
every outbound TCP packet is checked against the (fast, in-memory)
tracked-port set, and anything that isn't a tracked flow is re-injected
completely unchanged — this is the same approach real WinDivert-based
routing tools use, and it's what keeps a live PID/port set (which changes
continuously) from ever requiring the WinDivert handle itself to change.

UDP is deliberately out of scope here (see the separate, later voice/UDP
stage) — this interceptor only ever sees TCP.
"""
from __future__ import annotations

import sys
import threading

from loguru import logger

import pydivert

from boostx.core.services.interception.packet_redirect import redirect_to_local_relay
from boostx.core.services.interception.redirect_table import RedirectTable

_FILTER = "outbound and tcp"
_IDLE_SWEEP_INTERVAL_S = 5.0
_IDLE_TIMEOUT_S = 300.0


class NetworkInterceptor:
    def __init__(self, redirect_table: RedirectTable, relay_port: int) -> None:
        self._redirect_table = redirect_table
        self._relay_port = relay_port
        self._tracked_ports: set[int] = set()
        self._tracked_lock = threading.Lock()
        self._handle: "pydivert.WinDivert | None" = None
        self._thread: threading.Thread | None = None
        self._sweep_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def update_tracked_ports(self, ports: set[int]) -> None:
        """`ports` are this app's currently-live local TCP ports, from
        FlowTracker — updated live, with no handle reopen needed."""
        with self._tracked_lock:
            self._tracked_ports = set(ports)

    def start(self) -> None:
        if sys.platform != "win32":  # pragma: no cover - Windows-only feature
            raise OSError("NetworkInterceptor is only available on Windows")
        self._stop_event.clear()
        handle = pydivert.WinDivert(_FILTER, layer=pydivert.Layer.NETWORK)
        handle.open()
        self._handle = handle
        self._thread = threading.Thread(target=self._run, args=(handle,), daemon=True)
        self._thread.start()
        self._sweep_thread = threading.Thread(target=self._sweep_loop, daemon=True)
        self._sweep_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._sweep_thread is not None:
            self._sweep_thread.join(timeout=_IDLE_SWEEP_INTERVAL_S + 1.0)
            self._sweep_thread = None

    def _run(self, handle: "pydivert.WinDivert") -> None:
        while not self._stop_event.is_set():
            try:
                packet = handle.recv()
            except OSError:
                return
            try:
                self._handle_packet(handle, packet)
            except Exception as exc:
                logger.warning(f"NetworkInterceptor: error handling a packet, passing it through unchanged: {exc}")
                try:
                    handle.send(packet)
                except OSError:
                    pass

    def _handle_packet(self, handle: "pydivert.WinDivert", packet: "pydivert.Packet") -> None:
        with self._tracked_lock:
            tracked = packet.src_port in self._tracked_ports
        if not tracked:
            handle.send(packet)
            return

        entry, created = self._redirect_table.get_or_create(
            protocol="tcp",
            client_ip=packet.src_addr,
            client_port=packet.src_port,
            real_dst_ip=packet.dst_addr,
            real_dst_port=packet.dst_port,
        )
        if created:
            # The concrete, one-line-per-flow confirmation that a
            # redirect actually happened — this is the log line to look
            # for when verifying the interceptor is doing anything at all.
            logger.info(
                f"NetworkInterceptor: redirect table hit — "
                f"{entry.client_ip}:{entry.client_port} -> {entry.real_dst_ip}:{entry.real_dst_port} "
                f"redirected to local relay port {self._relay_port}"
            )
        redirect_to_local_relay(packet, self._relay_port)
        handle.send(packet)

    def _sweep_loop(self) -> None:
        while not self._stop_event.wait(_IDLE_SWEEP_INTERVAL_S):
            expired = self._redirect_table.sweep_idle(_IDLE_TIMEOUT_S)
            if expired:
                logger.debug(f"NetworkInterceptor: reaped {len(expired)} idle redirect entries")
