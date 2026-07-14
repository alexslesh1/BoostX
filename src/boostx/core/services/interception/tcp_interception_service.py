"""Ties FlowTracker (which local TCP ports currently belong to a
registered app), NetworkInterceptor (the WinDivert redirect), and
TransparentRelay (the actual outbound leg via the tunnel interface)
together for one app — this is what a VPN controller starts/stops per
app, replacing Socks5Bridge + WireguardUpstreamConnector for that app.

UDP/voice support is a separate, later addition (see the dedicated UDP
NAT stage) — this service only ever handles TCP, by design, so Discord's
text/API/gateway traffic can be verified working end-to-end through this
architecture before voice is touched at all.
"""
from __future__ import annotations

from boostx.core.services.interception.app_registry import InterceptedApp
from boostx.core.services.interception.flow_tracker import FlowTracker
from boostx.core.services.interception.network_interceptor import NetworkInterceptor
from boostx.core.services.interception.redirect_table import RedirectTable
from boostx.core.services.interception.socket_layer_monitor import TrackedFlow
from boostx.core.services.interception.transparent_relay import TransparentRelay


class TcpInterceptionService:
    def __init__(self, app: InterceptedApp, tunnel_interface_index: int) -> None:
        self._redirect_table = RedirectTable()
        # The relay's listener is bound synchronously in its constructor
        # (bare socketserver.TCPServer behavior — see Socks5Bridge's
        # identical local_port-before-start property), so its ephemeral
        # port is already known here, before the interceptor needs it.
        self._relay = TransparentRelay(self._redirect_table, tunnel_interface_index)
        self._interceptor = NetworkInterceptor(self._redirect_table, relay_port=self._relay.local_port)
        self._flow_tracker = FlowTracker(app, on_flows_changed=self._on_flows_changed)

    def _on_flows_changed(self, flows: set[TrackedFlow]) -> None:
        tcp_ports = {flow.local_port for flow in flows if flow.protocol == "tcp"}
        self._interceptor.update_tracked_ports(tcp_ports)

    def start(self) -> None:
        self._relay.start()
        self._interceptor.start()
        self._flow_tracker.start()

    def stop(self) -> None:
        self._flow_tracker.stop()
        self._interceptor.stop()
        self._relay.stop()
