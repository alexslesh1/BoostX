"""Learns which local TCP/UDP ports currently belong to a set of tracked
PIDs, via WinDivert's SOCKET layer — the only layer whose filter language
supports a `processId` condition at all (WinDivert's filter reference
explicitly excludes the NETWORK/NETWORK_FORWARD layers from that field).
This is why flow discovery is a separate stage feeding the NETWORK-layer
interceptor rather than something the interceptor resolves on its own —
the interceptor's own layer has no way to see process identity.

This produces an up-to-date port list purely from the driver's own event
stream, not from polling — a connection opened and closed between two
poll ticks (the exact risk a psutil-only design would have) can't be
missed, because the driver reports SOCKET_BIND/SOCKET_CONNECT/SOCKET_CLOSE
as they happen.
"""
from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import Callable

from loguru import logger

import pydivert

# WINDIVERT_EVENT_* (windivert.h). Only BIND/CONNECT populate LocalPort
# meaningfully for our purposes; CLOSE is what tears an entry back down.
_EVENT_SOCKET_BIND = 3
_EVENT_SOCKET_CONNECT = 4
_EVENT_SOCKET_CLOSE = 7

_HANDLE_CLOSE_JOIN_TIMEOUT_S = 2.0


@dataclass(frozen=True)
class TrackedFlow:
    protocol: str  # "tcp" or "udp"
    local_port: int


def build_pid_filter(pids: set[int]) -> str:
    """`false` for the empty-set case: an app with no PIDs currently
    running should have the socket-layer handle intercept nothing, not
    fail to open — WinDivert requires some valid filter expression, it
    can't be left blank to mean "nothing"."""
    if not pids:
        return "false"
    return " or ".join(f"processId == {pid}" for pid in sorted(pids))


def _flow_from_packet(packet: "pydivert.Packet") -> TrackedFlow | None:
    socket_data = packet.socket
    if socket_data is None:
        return None
    if socket_data.Protocol == int(pydivert.Protocol.TCP):
        protocol = "tcp"
    elif socket_data.Protocol == int(pydivert.Protocol.UDP):
        protocol = "udp"
    else:
        return None
    return TrackedFlow(protocol=protocol, local_port=socket_data.LocalPort)


class SocketLayerMonitor:
    """Owns a single WinDivert SOCKET-layer handle, reopened with a new
    filter whenever the tracked PID set changes — WinDivert filters are
    fixed for the lifetime of a handle, there is no in-place update.
    `on_flows_changed` is called with the full current flow set every time
    it changes (added or removed)."""

    def __init__(self, on_flows_changed: Callable[[set[TrackedFlow]], None]) -> None:
        self._on_flows_changed = on_flows_changed
        self._pids: set[int] = set()
        self._flows: set[TrackedFlow] = set()
        self._handle: "pydivert.WinDivert | None" = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def flows(self) -> set[TrackedFlow]:
        with self._lock:
            return set(self._flows)

    def update_pids(self, pids: set[int]) -> None:
        if sys.platform != "win32":  # pragma: no cover - Windows-only feature
            raise OSError("SocketLayerMonitor is only available on Windows")
        if pids == self._pids:
            return
        self._pids = set(pids)
        self._reopen()

    def stop(self) -> None:
        self._pids = set()
        self._close_handle()
        with self._lock:
            self._flows = set()

    def _reopen(self) -> None:
        self._close_handle()
        with self._lock:
            self._flows = set()
        if not self._pids:
            return
        handle = pydivert.WinDivert(build_pid_filter(self._pids), layer=pydivert.Layer.SOCKET)
        handle.open()
        self._handle = handle
        thread = threading.Thread(target=self._run, args=(handle,), daemon=True)
        self._thread = thread
        thread.start()

    def _close_handle(self) -> None:
        handle, self._handle = self._handle, None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=_HANDLE_CLOSE_JOIN_TIMEOUT_S)

    def _run(self, handle: "pydivert.WinDivert") -> None:
        while True:
            try:
                packet = handle.recv()
            except OSError:
                # Expected once _close_handle() closes this same handle
                # from another thread — recv() unblocks with an error.
                return
            self._handle_packet(packet)

    def _handle_packet(self, packet: "pydivert.Packet") -> None:
        flow = _flow_from_packet(packet)
        if flow is None:
            return
        with self._lock:
            if packet.event == _EVENT_SOCKET_CLOSE:
                if flow not in self._flows:
                    return
                self._flows = self._flows - {flow}
            elif packet.event in (_EVENT_SOCKET_BIND, _EVENT_SOCKET_CONNECT):
                if flow in self._flows:
                    return
                self._flows = self._flows | {flow}
            else:
                return
            changed = set(self._flows)
        logger.debug(f"Socket layer monitor: {flow} (event={packet.event}) -> {changed}")
        self._on_flows_changed(changed)
