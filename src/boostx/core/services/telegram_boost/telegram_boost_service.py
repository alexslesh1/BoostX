from __future__ import annotations

from dataclasses import dataclass

from boostx.core.services.api.models import ProxyCredentials
from boostx.core.services.telegram_boost.telegram_launcher import (
    find_telegram_executable,
    launch_telegram_with_proxy,
)


@dataclass(frozen=True)
class TelegramBoostResult:
    success: bool
    error: str | None = None


class TelegramBoostService:
    """Unlike Discord, Telegram Desktop has native SOCKS5 login/password
    support via a tg://socks deep link, so there is no local proxy bridge
    to manage — `is_active` just tracks whether we successfully handed the
    deep link to Telegram, not a live connection we own."""

    def __init__(self) -> None:
        self._active = False

    @property
    def is_active(self) -> bool:
        return self._active

    def start(self, credentials: ProxyCredentials) -> TelegramBoostResult:
        if self._active:
            return TelegramBoostResult(success=False, error="Telegram boost is already active.")

        executable_path = find_telegram_executable()
        if executable_path is None:
            return TelegramBoostResult(success=False, error="Telegram installation not found.")

        opened = launch_telegram_with_proxy(
            executable_path, credentials.host, credentials.port, credentials.login, credentials.password
        )
        if not opened:
            return TelegramBoostResult(success=False, error="Unable to open the Telegram proxy link.")

        self._active = True
        return TelegramBoostResult(success=True)

    def stop(self) -> None:
        self._active = False
