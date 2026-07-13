"""Ref-counts the single shared WireGuard tunnel across independent
per-app toggles (Discord VPN, Telegram VPN, ...): the tunnel comes up
once when the first app enables it, and only actually goes down once
every app has released it. Enabling both never brings up two tunnels.
"""
from __future__ import annotations

from boostx.core.services.vpn.tunnel_manager import TunnelManager


class VpnCoordinator:
    def __init__(self) -> None:
        self._tunnel = TunnelManager()
        self._active_apps: set[str] = set()

    @property
    def is_tunnel_active(self) -> bool:
        return self._tunnel.is_active

    def ensure_tunnel(self, app_key: str, conf_text: str) -> int:
        """Idempotent: brings the tunnel up if it isn't already, and
        returns the interface index to bind sockets to either way."""
        interface_index = self._tunnel.start(conf_text)
        self._active_apps.add(app_key)
        return interface_index

    def release(self, app_key: str) -> None:
        self._active_apps.discard(app_key)
        if not self._active_apps:
            self._tunnel.stop()

    def shutdown(self) -> None:
        self._active_apps.clear()
        self._tunnel.stop()
