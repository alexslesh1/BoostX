"""Drives Discord's WireGuard-based split-tunnel VPN via a local,
unauthenticated SOCKS5 bridge (Discord's --proxy-server flag points at
it) whose upstream connector binds directly to the tunnel interface.

Reverted here from a WinDivert-based transparent-redirect architecture
(TcpInterceptionService) that was built and wired in for a time: on real
Windows 11 testing, WinDivert.sys was blocked by Microsoft's Windows
Driver Policy (WinError 1275) — the vulnerable/behavior-based driver
blocklist enabled by default since Windows 11 22H2 — and the
alternatives investigated (userspace WFP connect-redirect, DLL-injection
proxying a la Proxifier) either turned out to still require a kernel-mode
component (WFP redirect actions can't be performed from user-mode WFP
alone) or carry worse anti-cheat/EDR flagging risk. The WinDivert-based
code (core/services/interception/) is kept in the tree, unwired, as the
starting point for a future dedicated WFP-callout-driver project (WDK, EV
cert, WHQL) rather than deleted.
"""
from __future__ import annotations

from loguru import logger

from boostx.core.services.discord_boost.discord_launcher import find_discord_executable, launch_discord
from boostx.core.services.net.socks5_bridge import Socks5Bridge
from boostx.core.services.vpn.models import VpnResult
from boostx.core.services.vpn.tunnel_manager import TunnelBringUpError
from boostx.core.services.vpn.upstream_connector import WireguardUpstreamConnector
from boostx.core.services.vpn.vpn_coordinator import VpnCoordinator
from boostx.core.services.vpn.wireguard_dependency import check_wireguard

_APP_KEY = "discord"


class DiscordVpnService:
    def __init__(self, vpn_coordinator: VpnCoordinator) -> None:
        self._vpn_coordinator = vpn_coordinator
        self._bridge: Socks5Bridge | None = None

    @property
    def is_active(self) -> bool:
        return self._bridge is not None

    def start(self, conf_text: str) -> VpnResult:
        if self._bridge is not None:
            return VpnResult(success=False, error="Discord VPN is already active.")

        executable_path = find_discord_executable()
        if executable_path is None:
            return VpnResult(success=False, error="Discord installation not found.")

        dependency = check_wireguard()
        if not dependency.available:
            return VpnResult(success=False, error=dependency.message)

        try:
            interface_index = self._vpn_coordinator.ensure_tunnel(_APP_KEY, conf_text)
        except TunnelBringUpError as exc:
            return VpnResult(success=False, error=str(exc))

        bridge = Socks5Bridge(WireguardUpstreamConnector(interface_index))
        try:
            bridge.start()
        except OSError as exc:
            logger.error(f"Failed to start local VPN bridge for Discord: {exc}")
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to start the local VPN bridge.")

        if not launch_discord(executable_path, bridge.local_port):
            bridge.stop()
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to launch Discord.")

        self._bridge = bridge
        return VpnResult(success=True)

    def stop(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        self._vpn_coordinator.release(_APP_KEY)
