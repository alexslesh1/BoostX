import os
import platform
import subprocess
from pathlib import Path


def find_discord_executable() -> Path | None:
    system = platform.system()
    if system == "Windows":
        return _find_windows()
    if system == "Darwin":
        return _find_macos()
    return _find_linux()


def launch_discord(executable_path: Path, local_socks_port: int) -> bool:
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
    try:
        if platform.system() == "Darwin" and executable_path.suffix == ".app":
            subprocess.Popen(["open", str(executable_path)])
        else:
            subprocess.Popen([str(executable_path)], cwd=str(executable_path.parent))
        return True
    except OSError:
        return False


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
