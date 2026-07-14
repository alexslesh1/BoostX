"""Drives Discord's WinDivert-based split-tunnel VPN: launches Discord
with no proxy configuration at all (see launch_discord_plain) and
transparently redirects its traffic through the tunnel via
TcpInterceptionService. Discord never performs any proxy handshake or
sees any indication a VPN exists — unrelated to the always-on SOCKS5-based
Boost Discord feature, which is a separate feature entirely.
"""
from __future__ import annotations

from loguru import logger

from boostx.core.services.discord_boost.discord_launcher import find_discord_executable, launch_discord_plain
from boostx.core.services.interception.app_registry import DISCORD
from boostx.core.services.interception.tcp_interception_service import TcpInterceptionService
from boostx.core.services.vpn.models import VpnResult
from boostx.core.services.vpn.tunnel_manager import TunnelBringUpError
from boostx.core.services.vpn.vpn_coordinator import VpnCoordinator
from boostx.core.services.vpn.wireguard_dependency import check_wireguard

_APP_KEY = "discord"


class DiscordVpnService:
    def __init__(self, vpn_coordinator: VpnCoordinator) -> None:
        self._vpn_coordinator = vpn_coordinator
        self._interception: TcpInterceptionService | None = None

    @property
    def is_active(self) -> bool:
        return self._interception is not None

    def start(self, conf_text: str) -> VpnResult:
        if self._interception is not None:
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

        # Interception is brought up *before* launching Discord: its
        # FlowTracker needs to already be polling so Discord's PID (and
        # then its ports) are picked up as early as possible after launch.
        interception = TcpInterceptionService(DISCORD, interface_index)
        try:
            interception.start()
        except OSError as exc:
            logger.error(f"Failed to start packet interception for Discord: {exc}")
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to start VPN routing.")

        if not launch_discord_plain(executable_path):
            interception.stop()
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to launch Discord.")

        self._interception = interception
        return VpnResult(success=True)

    def stop(self) -> None:
        if self._interception is not None:
            self._interception.stop()
            self._interception = None
        self._vpn_coordinator.release(_APP_KEY)
