"""Ties an app's PID membership (process_monitor.py) to its live socket
flows (socket_layer_monitor.py) so the NETWORK-layer interceptor has a
single up-to-date port list to match packets against for one registered
app — this is the object a VPN toggle controller starts/stops per app.
"""
from __future__ import annotations

from typing import Callable

from boostx.core.services.interception.app_registry import InterceptedApp
from boostx.core.services.interception.process_monitor import ProcessMonitor
from boostx.core.services.interception.socket_layer_monitor import SocketLayerMonitor, TrackedFlow


class FlowTracker:
    def __init__(self, app: InterceptedApp, on_flows_changed: Callable[[set[TrackedFlow]], None]) -> None:
        self._on_flows_changed = on_flows_changed
        self._socket_monitor = SocketLayerMonitor(on_flows_changed=self._on_flows_changed)
        self._process_monitor = ProcessMonitor(app, on_pids_changed=self._socket_monitor.update_pids)

    @property
    def flows(self) -> set[TrackedFlow]:
        return self._socket_monitor.flows

    def start(self) -> None:
        self._process_monitor.start()

    def stop(self) -> None:
        self._process_monitor.stop()
        self._socket_monitor.stop()
