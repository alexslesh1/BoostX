"""Tracks which OS PIDs currently belong to a registered app's process
name(s), on a continuous poll rather than a one-off lookup at launch time
— an Electron app like Discord spawns and kills renderer/GPU helper
processes throughout its life, so the matching PID set is not static.

This module answers only "which PIDs are this app right now" — it does
not enumerate sockets/ports. That is deliberately left to the WinDivert
SOCKET-layer stage (see socket_layer_monitor.py), which learns new
5-tuples as an event stream from the driver itself the instant a socket is
created, rather than by polling for them — polling for ports specifically
would reopen the exact race window (a connection created and torn down
between two poll ticks) this architecture is meant to avoid.
"""
from __future__ import annotations

import threading
from typing import Callable

import psutil
from loguru import logger

from boostx.core.services.interception.app_registry import InterceptedApp

_POLL_INTERVAL_S = 0.3


def find_matching_pids(app: InterceptedApp) -> set[int]:
    matching: set[int] = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if proc.info["name"] in app.process_names:
                matching.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return matching


class ProcessMonitor:
    """Polls for PIDs matching an app's process name(s) and reports the
    full current set via a callback whenever it changes, so a caller never
    has to re-derive membership itself."""

    def __init__(self, app: InterceptedApp, on_pids_changed: Callable[[set[int]], None]) -> None:
        self._app = app
        self._on_pids_changed = on_pids_changed
        self._known_pids: set[int] = set()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def known_pids(self) -> set[int]:
        return set(self._known_pids)

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=_POLL_INTERVAL_S * 2)
            self._thread = None

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                current = find_matching_pids(self._app)
            except Exception as exc:  # psutil can raise a variety of OS-level errors
                logger.warning(f"Process monitor for {self._app.key} failed to enumerate processes: {exc}")
                current = set(self._known_pids)
            if current != self._known_pids:
                logger.debug(f"Process monitor for {self._app.key}: pids {self._known_pids} -> {current}")
                self._known_pids = current
                self._on_pids_changed(set(current))
            self._stop_event.wait(_POLL_INTERVAL_S)
