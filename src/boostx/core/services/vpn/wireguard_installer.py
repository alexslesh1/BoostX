"""Downloads and silently installs WireGuard for Windows, so the user is
never asked to go install it manually. Only triggered when
wireguard_dependency.find_wireguard_executable() finds nothing.

Downloaded, not bundled: the official installer is a self-contained
bootstrapper (not a bare MSI — it fetches/verifies/installs the real
package itself), refreshed on every WireGuard release, so downloading at
first-use keeps users on a current, patched build instead of whatever
version happened to ship with our app.
"""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from loguru import logger

from boostx.config.paths import AppPaths
from boostx.core.services.vpn.authenticode import verify_authenticode_signature
from boostx.core.services.vpn.wireguard_dependency import find_wireguard_executable

_INSTALLER_URL = "https://download.wireguard.com/windows-client/wireguard-installer.exe"
_DOWNLOAD_TIMEOUT_S = 60.0
_INSTALL_TIMEOUT_S = 120.0
_POST_INSTALL_POLL_INTERVAL_S = 0.5
_POST_INSTALL_TIMEOUT_S = 15.0


class WireguardInstallError(Exception):
    pass


@dataclass(frozen=True)
class InstallProgress:
    stage: str  # "downloading" | "verifying" | "installing" | "done"


def _installer_path() -> Path:
    return AppPaths.data_dir() / "wireguard-installer.exe"


def install_wireguard(on_progress: Callable[[InstallProgress], None] | None = None) -> Path:
    """Downloads, verifies, and silently installs WireGuard for Windows.
    Returns the path to the now-installed wireguard.exe. Raises
    WireguardInstallError on any failure — never leaves the system in a
    half-elevated, ambiguous state without a clear error."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        raise WireguardInstallError("WireGuard auto-install is only available on Windows.")

    def _report(stage: str) -> None:
        if on_progress is not None:
            on_progress(InstallProgress(stage=stage))

    _report("downloading")
    installer_path = _download_installer()

    _report("verifying")
    if not verify_authenticode_signature(installer_path):
        installer_path.unlink(missing_ok=True)
        raise WireguardInstallError(
            "The downloaded WireGuard installer failed signature verification and was discarded."
        )

    _report("installing")
    _run_elevated_silent_install(installer_path)

    executable = _wait_for_install(_POST_INSTALL_TIMEOUT_S)
    if executable is None:
        raise WireguardInstallError("WireGuard installation did not complete — please try again.")

    _report("done")
    return executable


def _download_installer() -> Path:
    target = _installer_path()
    try:
        with httpx.stream("GET", _INSTALLER_URL, timeout=_DOWNLOAD_TIMEOUT_S, follow_redirects=True) as response:
            response.raise_for_status()
            with open(target, "wb") as f:
                for chunk in response.iter_bytes():
                    f.write(chunk)
    except httpx.HTTPError as exc:
        target.unlink(missing_ok=True)
        raise WireguardInstallError(f"Failed to download the WireGuard installer: {exc}") from exc
    return target


def _run_elevated_silent_install(installer_path: Path) -> None:
    """The official installer already supports a silent switch and does
    its own internal package verification/selection — we just run it
    elevated and wait for it to finish."""
    command = (
        f"$p = Start-Process -FilePath '{installer_path}' -ArgumentList '/quiet' "
        "-Verb RunAs -WindowStyle Hidden -PassThru -Wait; exit $p.ExitCode"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=_INSTALL_TIMEOUT_S,
    )
    if result.returncode != 0:
        logger.warning(f"WireGuard installer exited {result.returncode}: {result.stderr.strip()}")
        raise WireguardInstallError(
            f"The WireGuard installer exited with code {result.returncode}. "
            "The UAC prompt may have been declined."
        )


def _wait_for_install(timeout_s: float) -> Path | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        executable = find_wireguard_executable()
        if executable is not None:
            return executable
        time.sleep(_POST_INSTALL_POLL_INTERVAL_S)
    return None
