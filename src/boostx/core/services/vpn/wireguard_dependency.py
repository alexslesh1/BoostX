import os
import shutil
from pathlib import Path

from boostx.core.services.vpn.models import DependencyStatus

_MISSING_MESSAGE = "VPN routing isn't ready yet. Please check your internet connection and try again."

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
        return DependencyStatus(available=False, message=_MISSING_MESSAGE)
    return DependencyStatus(available=True, message="ready")
