from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from boostx.core.services.api.models import ProxyCredentials
from boostx.core.services.discord_boost.discord_launcher import find_discord_executable, launch_discord
from boostx.core.services.discord_boost.socks5_bridge import Socks5Bridge, UpstreamProxyConfig


@dataclass(frozen=True)
class BoostDiscordResult:
    success: bool
    error: str | None = None


class BoostDiscordService:
    def __init__(self) -> None:
        self._bridge: Socks5Bridge | None = None

    @property
    def is_active(self) -> bool:
        return self._bridge is not None

    def start(self, credentials: ProxyCredentials) -> BoostDiscordResult:
        if self._bridge is not None:
            return BoostDiscordResult(success=False, error="Boost Discord is already active.")

        executable_path = find_discord_executable()
        if executable_path is None:
            return BoostDiscordResult(success=False, error="Discord installation not found.")

        upstream = UpstreamProxyConfig(
            host=credentials.host,
            port=credentials.port,
            login=credentials.login,
            password=credentials.password,
        )
        bridge = Socks5Bridge(upstream)
        try:
            bridge.start()
        except OSError as exc:
            logger.error(f"Failed to start local proxy bridge: {exc}")
            return BoostDiscordResult(success=False, error="Unable to start the local proxy bridge.")

        if not launch_discord(executable_path, bridge.local_port):
            bridge.stop()
            return BoostDiscordResult(success=False, error="Unable to launch Discord.")

        self._bridge = bridge
        return BoostDiscordResult(success=True)

    def stop(self) -> None:
        if self._bridge is not None:
            self._bridge.stop()
            self._bridge = None
