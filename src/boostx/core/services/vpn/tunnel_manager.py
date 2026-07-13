"""Brings a WireGuard tunnel up/down via the official wireguard.exe (never
reimplements the WireGuard protocol itself). `Table = off` is injected
into the fetched .conf so wg-quick/wireguard.exe never touches the system
routing table — the tunnel adapter comes up with its own address only,
invisible to every other process on the machine. Split tunneling is then
achieved purely by binding specific sockets to this adapter (see
interface_binding.py), not by anything this module does.
"""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

from loguru import logger

from boostx.config.paths import AppPaths
from boostx.core.services.vpn.interface_binding import find_interface_index_for_ip
from boostx.core.services.vpn.wireguard_dependency import find_wireguard_executable

_TUNNEL_NAME = "boostxvpn"
_ADAPTER_READY_TIMEOUT_S = 10.0
_ADAPTER_POLL_INTERVAL_S = 0.3
_ELEVATED_ACTION_TIMEOUT_S = 30.0
_ADDRESS_LINE_PATTERN = re.compile(r"^\s*Address\s*=\s*([0-9.]+)", re.IGNORECASE | re.MULTILINE)
_GENERIC_FAILURE_MESSAGE = "VPN routing isn't ready yet. Please check your internet connection and try again."


class TunnelBringUpError(Exception):
    pass


def _conf_path() -> Path:
    return AppPaths.data_dir() / f"{_TUNNEL_NAME}.conf"


def _prepare_conf(conf_text: str) -> tuple[str, str]:
    """Returns (patched_conf_text, tunnel_local_ip)."""
    match = _ADDRESS_LINE_PATTERN.search(conf_text)
    if match is None:
        raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)
    local_ip = match.group(1)

    if re.search(r"^\s*Table\s*=", conf_text, re.IGNORECASE | re.MULTILINE) is None:
        conf_text = conf_text.replace("[Interface]", "[Interface]\nTable = off", 1)

    return conf_text, local_ip


class TunnelManager:
    def __init__(self) -> None:
        self._interface_index: int | None = None
        self._local_ip: str | None = None

    @property
    def is_active(self) -> bool:
        return self._interface_index is not None

    @property
    def interface_index(self) -> int | None:
        return self._interface_index

    def start(self, conf_text: str) -> int:
        """Idempotent: if already active, returns the existing interface
        index without reinstalling the tunnel. Returns the interface index
        to bind sockets to."""
        if self._interface_index is not None:
            return self._interface_index

        executable = find_wireguard_executable()
        if executable is None:
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        patched_conf, local_ip = _prepare_conf(conf_text)
        conf_path = _conf_path()
        conf_path.write_text(patched_conf, encoding="utf-8")

        exit_code = self._run_elevated(str(executable), ["/installtunnelservice", str(conf_path)])
        if exit_code != 0:
            logger.warning(f"Tunnel bring-up exited {exit_code} (permission prompt may have been declined)")
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        interface_index = self._wait_for_adapter(local_ip)
        if interface_index is None:
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        self._interface_index = interface_index
        self._local_ip = local_ip
        return interface_index

    def stop(self) -> None:
        if self._interface_index is None:
            return
        executable = find_wireguard_executable()
        if executable is not None:
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
        self._interface_index = None
        self._local_ip = None

    def _wait_for_adapter(self, local_ip: str) -> int | None:
        deadline = time.monotonic() + _ADAPTER_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            try:
                index = find_interface_index_for_ip(local_ip)
            except OSError:
                return None
            if index is not None:
                return index
            time.sleep(_ADAPTER_POLL_INTERVAL_S)
        return None

    @staticmethod
    def _run_elevated(executable: str, args: list[str]) -> int:
        """Runs `executable args...` with a UAC elevation prompt via
        PowerShell's Start-Process -Verb RunAs, which is the standard way
        to both elevate AND get a real exit code back (ShellExecuteW alone
        is fire-and-forget). Only this one action needs admin rights —
        everything else in the VPN feature runs unprivileged."""
        if sys.platform != "win32":  # pragma: no cover - Windows-only feature
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        arg_list = ",".join(f"'{arg}'" for arg in args)
        command = (
            f"$p = Start-Process -FilePath '{executable}' -ArgumentList {arg_list} "
            "-Verb RunAs -WindowStyle Hidden -PassThru -Wait; exit $p.ExitCode"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=_ELEVATED_ACTION_TIMEOUT_S,
        )
        if result.returncode != 0:
            logger.warning(f"Elevated component action exited {result.returncode}: {result.stderr.strip()}")
        return result.returncode
