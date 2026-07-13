from __future__ import annotations

from loguru import logger

from boostx.core.services.net.socks5_bridge import Socks5Bridge
from boostx.core.services.telegram_boost.telegram_launcher import (
    find_telegram_executable,
    launch_telegram_via_local_bridge,
)
from boostx.core.services.vpn.models import VpnResult
from boostx.core.services.vpn.tunnel_manager import TunnelBringUpError
from boostx.core.services.vpn.upstream_connector import WireguardUpstreamConnector
from boostx.core.services.vpn.vpn_coordinator import VpnCoordinator
from boostx.core.services.vpn.wireguard_dependency import check_wireguard

_APP_KEY = "telegram"


class TelegramVpnService:
    def __init__(self, vpn_coordinator: VpnCoordinator) -> None:
        self._vpn_coordinator = vpn_coordinator
        self._bridge: Socks5Bridge | None = None

    @property
    def is_active(self) -> bool:
        return self._bridge is not None

    def start(self, conf_text: str) -> VpnResult:
        if self._bridge is not None:
            return VpnResult(success=False, error="Telegram VPN is already active.")

        executable_path = find_telegram_executable()
        if executable_path is None:
            return VpnResult(success=False, error="Telegram installation not found.")

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
            logger.error(f"Failed to start local VPN bridge for Telegram: {exc}")
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to start the local VPN bridge.")

        if not launch_telegram_via_local_bridge(executable_path, bridge.local_port):
            bridge.stop()
            self._vpn_coordinator.release(_APP_KEY)
            return VpnResult(success=False, error="Unable to open the Telegram proxy link.")

        self._bridge = bridge
        return VpnResult(success=True)

    def stop(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
        self._vpn_coordinator.release(_APP_KEY)
