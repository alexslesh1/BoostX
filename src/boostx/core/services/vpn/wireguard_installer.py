"""Downloads and silently installs the VPN routing component (WireGuard
for Windows) so the user is never asked to go install anything manually.
Only triggered when wireguard_dependency.find_wireguard_executable()
finds nothing. Runs entirely without prompts on our side — no dialog,
no name of the underlying technology anywhere in what the user sees;
the only thing Windows itself still shows is its own UAC elevation
prompt, which we cannot suppress or relabel (see authenticode.py for why
we deliberately don't touch the downloaded binary to try to disguise it).

Downloaded, not bundled: the official installer is a self-contained
bootstrapper (not a bare MSI — it fetches/verifies/installs the real
package itself), refreshed on every release, so downloading at first-use
keeps users on a current, patched build instead of whatever version
happened to ship with our app. The on-disk filename is our own choice
(renaming a signed binary doesn't touch its signature or its embedded
publisher metadata — see authenticode.py) so Task Manager shows our own
neutral name, not the vendor's, during the few seconds it runs.
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
_INSTALLER_FILENAME = "boostx-component-setup.exe"
_DOWNLOAD_TIMEOUT_S = 60.0
_INSTALL_TIMEOUT_S = 120.0
_POST_INSTALL_POLL_INTERVAL_S = 0.5
_POST_INSTALL_TIMEOUT_S = 15.0

_GENERIC_FAILURE_MESSAGE = "Setup couldn't finish. Please check your internet connection and try again."


class ComponentInstallError(Exception):
    pass


@dataclass(frozen=True)
class InstallProgress:
    stage: str  # "downloading" | "verifying" | "installing" | "done"


def _installer_path() -> Path:
    return AppPaths.data_dir() / _INSTALLER_FILENAME


def install_wireguard(on_progress: Callable[[InstallProgress], None] | None = None) -> Path:
    """Downloads, verifies, and silently installs the VPN routing
    component. Returns the path to the now-installed executable. Raises
    ComponentInstallError with a generic, non-technical message on any
    failure — never leaves the system in a half-elevated, ambiguous
    state without a clear (if unspecific) error."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        raise ComponentInstallError(_GENERIC_FAILURE_MESSAGE)

    def _report(stage: str) -> None:
        if on_progress is not None:
            on_progress(InstallProgress(stage=stage))

    _report("downloading")
    installer_path = _download_installer()

    _report("verifying")
    if not verify_authenticode_signature(installer_path):
        installer_path.unlink(missing_ok=True)
        logger.error("Downloaded setup component failed signature verification; discarded.")
        raise ComponentInstallError(_GENERIC_FAILURE_MESSAGE)

    _report("installing")
    _run_elevated_silent_install(installer_path)

    executable = _wait_for_install(_POST_INSTALL_TIMEOUT_S)
    if executable is None:
        raise ComponentInstallError(_GENERIC_FAILURE_MESSAGE)

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
        logger.warning(f"Component download failed: {exc}")
        raise ComponentInstallError(_GENERIC_FAILURE_MESSAGE) from exc
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
        logger.warning(f"Component setup exited {result.returncode}: {result.stderr.strip()}")
        raise ComponentInstallError(_GENERIC_FAILURE_MESSAGE)


def _wait_for_install(timeout_s: float) -> Path | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        executable = find_wireguard_executable()
        if executable is not None:
            return executable
        time.sleep(_POST_INSTALL_POLL_INTERVAL_S)
    return None
