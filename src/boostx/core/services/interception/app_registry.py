"""Registry of applications eligible for process-level packet interception
(split-tunnel VPN with no application-visible proxy configuration at all —
see core/services/interception and the WinDivert-based modules alongside
this one). Discord and Telegram are the first two entries, not the only
two: adding support for another app (a game, say) is meant to be adding one
more entry here, not touching the interception/NAT code itself.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InterceptedApp:
    key: str
    # A single logical app can span multiple OS processes at once (a main
    # process plus Chromium renderer/GPU helper processes, for Electron
    # apps like Discord) — hence a tuple, not a single expected name.
    process_names: tuple[str, ...]
    # For logs only — never surfaced to the end user in a VPN-branded way.
    display_name: str


DISCORD = InterceptedApp(key="discord", process_names=("Discord.exe",), display_name="Discord")
TELEGRAM = InterceptedApp(key="telegram", process_names=("Telegram.exe",), display_name="Telegram")

_REGISTRY: dict[str, InterceptedApp] = {app.key: app for app in (DISCORD, TELEGRAM)}


def get_app(key: str) -> InterceptedApp:
    return _REGISTRY[key]


def all_apps() -> tuple[InterceptedApp, ...]:
    return tuple(_REGISTRY.values())
