import os
import shutil
from pathlib import Path

from boostx.core.services.vpn.models import DependencyStatus

_WIREGUARD_DOWNLOAD_URL = "https://www.wireguard.com/install/"
_MISSING_MESSAGE = "WireGuard for Windows is not installed. Install it to enable VPN routing."

_CANDIDATES = [
    r"C:\Program Files\WireGuard\wireguard.exe",
    r"C:\Program Files (x86)\WireGuard\wireguard.exe",
    "wireguard",
]


def find_wireguard_executable() -> Path | None:
    for candidate in _CANDIDATES:
        if Path(candidate).is_file():
            return Path(candidate)
        found = shutil.which(candidate)
        if found:
            return Path(found)
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidate = Path(program_files) / "WireGuard" / "wireguard.exe"
        if candidate.is_file():
            return candidate
    return None


def check_wireguard() -> DependencyStatus:
    executable = find_wireguard_executable()
    if executable is None:
        return DependencyStatus(available=False, message=_MISSING_MESSAGE, download_url=_WIREGUARD_DOWNLOAD_URL)
    return DependencyStatus(available=True, message="WireGuard for Windows detected.")
