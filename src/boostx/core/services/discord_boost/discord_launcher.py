import json
import os
import platform
import subprocess
from pathlib import Path

from loguru import logger

# No such CLI flag or environment variable exists on Discord's side --
# verified against community-maintained update-skipping tooling (e.g.
# Flathub's own Discord packaging script) before adding anything here.
# The real, working mechanism is two keys in Discord's own settings.json:
# SKIP_HOST_UPDATE and SKIP_MODULE_UPDATE. This is gated behind an
# explicit BoostX-side env var (never passed to Discord itself) because,
# unlike a CLI flag scoped to one process launch, writing these keys
# persists across every future Discord launch -- including ones outside
# BoostX -- until manually reverted. That's a reasonable trade for fast
# iteration on a test machine but not something to apply to a real user's
# Discord installation by default.
_DISABLE_UPDATER_ENV_VAR = "BOOSTX_DISABLE_DISCORD_UPDATER"


def find_discord_executable() -> Path | None:
    system = platform.system()
    if system == "Windows":
        return _find_windows()
    if system == "Darwin":
        return _find_macos()
    return _find_linux()


def launch_discord(executable_path: Path, local_socks_port: int) -> bool:
    if os.environ.get(_DISABLE_UPDATER_ENV_VAR) == "1":
        _skip_discord_updater()
    proxy_flag = f"--proxy-server=socks5://127.0.0.1:{local_socks_port}"
    try:
        if platform.system() == "Darwin" and executable_path.suffix == ".app":
            subprocess.Popen(["open", str(executable_path), "--args", proxy_flag])
        else:
            subprocess.Popen([str(executable_path), proxy_flag], cwd=str(executable_path.parent))
        return True
    except OSError:
        return False


def launch_discord_plain(executable_path: Path) -> bool:
    """Launches Discord with no proxy configuration at all. The
    WinDivert-based VPN (core/services/interception) redirects Discord's
    traffic transparently at the packet level, so unlike `launch_discord`
    above (the SOCKS5-based path), Discord's own process is never given
    any flag or configuration indicating a proxy exists."""
    if os.environ.get(_DISABLE_UPDATER_ENV_VAR) == "1":
        _skip_discord_updater()
    try:
        if platform.system() == "Darwin" and executable_path.suffix == ".app":
            subprocess.Popen(["open", str(executable_path)])
        else:
            subprocess.Popen([str(executable_path)], cwd=str(executable_path.parent))
        return True
    except OSError:
        return False


def _discord_settings_path() -> Path | None:
    system = platform.system()
    if system == "Windows":
        app_data = os.environ.get("APPDATA")
        if not app_data:
            return None
        return Path(app_data) / "discord" / "settings.json"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "discord" / "settings.json"
    return Path.home() / ".config" / "discord" / "settings.json"


def _skip_discord_updater() -> None:
    """Merges SKIP_HOST_UPDATE/SKIP_MODULE_UPDATE into Discord's own
    settings.json so its update-check cycle -- which can loop for hours
    if the network path to updates.discord.com is unhealthy -- is skipped
    entirely and Discord goes straight to its normal window. Best-effort
    only: never blocks the actual launch on failure here."""
    settings_path = _discord_settings_path()
    if settings_path is None:
        return
    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        existing: dict = {}
        if settings_path.is_file():
            try:
                existing = json.loads(settings_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
        existing["SKIP_HOST_UPDATE"] = True
        existing["SKIP_MODULE_UPDATE"] = True
        tmp_path = settings_path.with_name(settings_path.name + ".tmp")
        tmp_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        tmp_path.replace(settings_path)
    except OSError as exc:
        logger.warning(f"Could not update Discord's settings.json to skip its updater: {exc}")


def _find_windows() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    discord_dir = Path(local_app_data) / "Discord"
    if not discord_dir.is_dir():
        return None
    for app_dir in sorted(discord_dir.glob("app-*"), reverse=True):
        candidate = app_dir / "Discord.exe"
        if candidate.is_file():
            return candidate
    return None


def _find_macos() -> Path | None:
    candidate = Path("/Applications/Discord.app")
    return candidate if candidate.is_dir() else None


def _find_linux() -> Path | None:
    candidates = (
        Path("/usr/bin/discord"),
        Path("/usr/share/discord/Discord"),
        Path("/snap/bin/discord"),
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin" / "com.discordapp.Discord",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
