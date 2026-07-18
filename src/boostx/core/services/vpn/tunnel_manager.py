"""Brings a WireGuard tunnel up/down via the official wireguard.exe (never
reimplements the WireGuard protocol itself). `Table = off` is injected
into the fetched .conf so wg-quick/wireguard.exe never touches the system
routing table — the tunnel adapter comes up with its own address only,
invisible to every other process on the machine. Split tunneling is then
achieved purely by binding specific sockets to this adapter (see
interface_binding.py), not by anything this module does.

"Ready" is verified in three stages before anything is reported as
active:
1. The tunnel's own Windows service must actually be RUNNING (not just
   installed) and a network adapter with the expected local address must
   exist — an adapter existing on its own proves nothing, it can be a
   stale leftover from a previous session.
2. A single scoped, very-high-metric default route is added for that
   interface (see _add_scoped_route) — `Table = off` means the interface
   otherwise has zero route table entries, and IP_UNICAST_IF-bound
   sockets can only *prefer* an interface among routes that already
   exist, not conjure one out of thin air. Without this, every
   interface-bound socket fails with WSAENETUNREACH (10051) regardless
   of how healthy the tunnel's own WireGuard handshake is.
3. A real bound TCP connect through the interface to a stable public
   endpoint, retried within the readiness window — the actual proof
   traffic can flow, not just that the pieces exist.
"""
from __future__ import annotations

import re
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from loguru import logger

from boostx.config.paths import AppPaths
from boostx.core.services.vpn.gui_suppressor import suppress_component_gui
from boostx.core.services.vpn.interface_binding import bind_socket_to_interface, find_interface_index_for_ip
from boostx.core.services.vpn.wireguard_dependency import find_wireguard_executable

_TUNNEL_NAME = "boostxvpn"
# WireGuard for Windows registers each tunnel as a Windows service named
# this way — this is how we verify the tunnel is genuinely running, not
# just how we tell it apart.
_SERVICE_NAME = f"WireGuardTunnel${_TUNNEL_NAME}"
_TUNNEL_READY_TIMEOUT_S = 15.0
_ADAPTER_POLL_INTERVAL_S = 0.3
_ELEVATED_ACTION_TIMEOUT_S = 30.0
_SERVICE_QUERY_TIMEOUT_S = 10.0
# A service being RUNNING and an adapter existing with the right address
# proves neither that the WireGuard handshake completed nor that the
# machine's network stack has a working path out through it — especially
# right after another VPN was toggled off, when Windows' network state
# can stay transitional for a few seconds. This probe is the actual
# proof: a real bound TCP connect through the interface to a stable
# public endpoint, retried within the readiness window rather than
# trusted on the first attempt.
_PROBE_HOST = "1.1.1.1"
_PROBE_PORT = 443
_PROBE_TIMEOUT_S = 3.0
# `Table = off` means wireguard.exe never adds ANY route referencing the
# tunnel interface — but IP_UNICAST_IF only *prefers* a given interface
# among routes that already exist; it can't manufacture a path out of
# thin air. With zero routes for the interface, every IP_UNICAST_IF-bound
# socket fails with WSAENETUNREACH (10051) no matter how healthy the
# tunnel's own handshake is. This route exists purely so those sockets
# have something to resolve against; the enormous metric keeps it from
# ever being preferred by the rest of the system's normal traffic.
_SCOPED_ROUTE_METRIC = 9999
_ADDRESS_LINE_PATTERN = re.compile(r"^\s*Address\s*=\s*([0-9.]+)", re.IGNORECASE | re.MULTILINE)
_GENERIC_FAILURE_MESSAGE = "VPN routing isn't ready yet. Please check your internet connection and try again."
# The real Win32 error code (ERROR_CANCELLED) a declined/cancelled UAC
# prompt surfaces as -- used as an unambiguous sentinel so a declined
# elevation can be told apart from the elevated command itself failing.
_UAC_DECLINED_EXIT_CODE = 1223
_OUTPUT_LOG_LIMIT = 4000


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


def _query_service(name: str) -> subprocess.CompletedProcess | None:
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        return None
    try:
        return subprocess.run(
            ["sc", "query", name],
            capture_output=True,
            text=True,
            timeout=_SERVICE_QUERY_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _ps_literal(value: str) -> str:
    """A PowerShell single-quoted string literal -- single quotes only need
    doubling to escape, unlike double-quoted strings which also expand
    variables, making this the safer choice for arbitrary values (paths,
    conf contents) that must not be interpreted."""
    return "'" + value.replace("'", "''") + "'"


def _build_elevated_payload_script(executable: str, args: list[str], output_path: Path) -> str:
    """A script that runs as the actual elevated process: invokes the real
    target command, captures its combined output to a file (its own exit
    code is preserved via $LASTEXITCODE, unaffected by that redirection),
    and exits with that real exit code."""
    argument_literals = " ".join(_ps_literal(arg) for arg in args)
    return (
        "$ErrorActionPreference = 'Continue'\n"
        f"& {_ps_literal(executable)} {argument_literals} 2>&1 | "
        f"Out-File -FilePath {_ps_literal(str(output_path))} -Encoding utf8\n"
        "exit $LASTEXITCODE\n"
    )


def _build_elevation_wrapper_command(payload_path: Path) -> str:
    """Elevates just the payload script above. Wrapped in try/catch so a
    declined/cancelled UAC prompt -- which makes Start-Process itself throw
    rather than return a process object -- exits with the real Win32
    ERROR_CANCELLED code instead of being indistinguishable from the
    elevated command's own failure."""
    script_args = ",".join(["'-NoProfile'", "'-ExecutionPolicy'", "'Bypass'", "'-File'", _ps_literal(str(payload_path))])
    return (
        "try {\n"
        f"    $p = Start-Process -FilePath 'powershell' -ArgumentList {script_args} "
        "-Verb RunAs -WindowStyle Hidden -PassThru -Wait\n"
        "    exit $p.ExitCode\n"
        "} catch {\n"
        f"    $code = {_UAC_DECLINED_EXIT_CODE}\n"
        "    if ($_.Exception.InnerException -and "
        "($_.Exception.InnerException.PSObject.Properties.Name -contains 'NativeErrorCode')) {\n"
        "        $code = $_.Exception.InnerException.NativeErrorCode\n"
        "    }\n"
        "    exit $code\n"
        "}"
    )


def _read_and_truncate(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace").strip()
    except OSError:
        return ""
    if len(text) > _OUTPUT_LOG_LIMIT:
        return text[:_OUTPUT_LOG_LIMIT] + "... (truncated)"
    return text


def is_tunnel_service_running() -> bool:
    result = _query_service(_SERVICE_NAME)
    return result is not None and result.returncode == 0 and "RUNNING" in result.stdout


def is_tunnel_service_registered() -> bool:
    """True if the service exists at all (installed), regardless of its
    current state -- a STOPPED-but-still-registered leftover from a crash
    or a failed bring-up/rollback blocks the next /installtunnelservice
    just as much as a RUNNING one does."""
    result = _query_service(_SERVICE_NAME)
    return result is not None and result.returncode == 0


def _probe_route_via_interface(interface_index: int) -> bool:
    """The actual proof the tunnel works: bind a test socket to the
    interface and make a real TCP connection through it. Service state
    and adapter presence can both be true while the network stack still
    has no working path out — this is the check that would have caught
    the exact WinError 10051 (network unreachable) seen in practice."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(_PROBE_TIMEOUT_S)
            bind_socket_to_interface(sock, interface_index)
            sock.connect((_PROBE_HOST, _PROBE_PORT))
            return True
        finally:
            sock.close()
    except OSError as exc:
        logger.debug(f"Tunnel route probe failed via interface {interface_index}: {exc}")
        return False


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
        to bind sockets to. Raises TunnelBringUpError — and rolls back any
        half-installed service — if the tunnel doesn't come up for real."""
        if self._interface_index is not None:
            return self._interface_index

        executable = find_wireguard_executable()
        if executable is None:
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        # A service left registered by a crash, a force-quit, or a rollback
        # that itself failed to complete blocks /installtunnelservice with
        # "already installed" just as much as a genuinely running one does
        # -- our own in-memory self._interface_index (checked above) can't
        # know about that, since it doesn't survive a restart. Clear it
        # before every install attempt rather than only reacting to the
        # resulting error.
        if is_tunnel_service_registered():
            logger.info(f"Found a leftover '{_SERVICE_NAME}' service from a previous session; removing it first")
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
            self._wait_for_teardown()

        patched_conf, local_ip = _prepare_conf(conf_text)
        conf_path = _conf_path()
        conf_path.write_text(patched_conf, encoding="utf-8")

        exit_code = self._run_elevated(str(executable), ["/installtunnelservice", str(conf_path)])
        if exit_code != 0:
            logger.warning(f"Tunnel bring-up exited {exit_code} (permission prompt may have been declined)")
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        interface_index = self._wait_for_adapter_and_service(local_ip)
        if interface_index is None:
            logger.warning("Tunnel service/adapter never reached a verified running state; rolling back")
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        if not self._add_scoped_route(interface_index):
            logger.warning("Failed to add the scoped tunnel route; rolling back")
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        if not self._wait_for_route_probe(interface_index):
            logger.warning(
                "Tunnel route probe never succeeded even with a scoped route present; rolling back"
            )
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        self._interface_index = interface_index
        self._local_ip = local_ip
        return interface_index

    def stop(self) -> None:
        if self._interface_index is None:
            return
        executable = find_wireguard_executable()
        if executable is not None:
            self._remove_scoped_route(self._interface_index)
            self._run_elevated(str(executable), ["/uninstalltunnelservice", _TUNNEL_NAME])
            if not self._wait_for_teardown():
                logger.warning("Tunnel service still reports running after an uninstall attempt")
        self._interface_index = None
        self._local_ip = None

    def _wait_for_adapter_and_service(self, local_ip: str) -> int | None:
        deadline = time.monotonic() + _TUNNEL_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if is_tunnel_service_running():
                try:
                    index = find_interface_index_for_ip(local_ip)
                except OSError:
                    return None
                if index is not None:
                    return index
            time.sleep(_ADAPTER_POLL_INTERVAL_S)
        return None

    def _wait_for_route_probe(self, interface_index: int) -> bool:
        deadline = time.monotonic() + _TUNNEL_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if _probe_route_via_interface(interface_index):
                return True
            logger.debug(
                f"Route probe failed via interface {interface_index}; "
                f"service_running={is_tunnel_service_running()} — retrying"
            )
            time.sleep(_ADAPTER_POLL_INTERVAL_S)
        return False

    def _add_scoped_route(self, interface_index: int) -> bool:
        exit_code = self._run_elevated(
            "netsh",
            [
                "interface", "ipv4", "add", "route",
                "prefix=0.0.0.0/0",
                f"interface={interface_index}",
                f"metric={_SCOPED_ROUTE_METRIC}",
                "store=active",
            ],
        )
        return exit_code == 0

    def _remove_scoped_route(self, interface_index: int) -> None:
        # Best-effort: removing the adapter itself (via /uninstalltunnelservice
        # right after this) purges any routes tied to it regardless, but this
        # cleans up immediately rather than relying on that.
        self._run_elevated(
            "netsh",
            ["interface", "ipv4", "delete", "route", "prefix=0.0.0.0/0", f"interface={interface_index}", "store=active"],
        )

    def _wait_for_teardown(self) -> bool:
        deadline = time.monotonic() + _TUNNEL_READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if not is_tunnel_service_running():
                return True
            time.sleep(_ADAPTER_POLL_INTERVAL_S)
        return not is_tunnel_service_running()

    @staticmethod
    def _run_elevated(executable: str, args: list[str]) -> int:
        """Runs `executable args...` with a UAC elevation prompt via
        PowerShell's Start-Process -Verb RunAs, which is the standard way
        to both elevate AND get a real exit code back (ShellExecuteW alone
        is fire-and-forget). Only this one action needs admin rights —
        everything else in the VPN feature runs unprivileged.

        The elevated command's own stdout/stderr is otherwise invisible to
        us: Start-Process's -Verb parameter (required for the UAC prompt)
        uses ShellExecute internally, which is incompatible with
        -RedirectStandardOutput/-RedirectStandardError. So instead the
        elevated target itself is a small generated .ps1 payload that
        redirects its own output to a file, which is then read back here —
        this is what actually lets a genuine failure inside `executable`
        (e.g. wireguard.exe's own "already installed" error) be told apart
        from the elevation step itself failing (UAC declined, surfaced as
        the real Win32 ERROR_CANCELLED code, 1223).

        -WindowStyle Hidden only hints at the *initial* window state of
        the launched process and does not reliably suppress a window a
        GUI app creates itself afterward, so this sweeps for and closes
        any such window afterward as a safety net — the whole feature is
        meant to be invisible regardless of what the external tool does.
        """
        if sys.platform != "win32":  # pragma: no cover - Windows-only feature
            raise TunnelBringUpError(_GENERIC_FAILURE_MESSAGE)

        run_id = uuid.uuid4().hex
        output_path = AppPaths.data_dir() / f"elevated_output_{run_id}.log"
        payload_path = AppPaths.data_dir() / f"elevated_payload_{run_id}.ps1"
        payload_path.write_text(_build_elevated_payload_script(executable, args, output_path), encoding="utf-8")

        try:
            outer_command = _build_elevation_wrapper_command(payload_path)
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", outer_command],
                capture_output=True,
                text=True,
                timeout=_ELEVATED_ACTION_TIMEOUT_S,
            )
            exit_code = result.returncode
            child_output = _read_and_truncate(output_path)
            command_desc = f"{executable} {' '.join(args)}"

            if exit_code == _UAC_DECLINED_EXIT_CODE:
                logger.warning(f"Elevated action '{command_desc}' was not launched -- the UAC prompt was declined or cancelled.")
            elif exit_code != 0:
                logger.warning(
                    f"Elevated action '{command_desc}' exited {exit_code}. "
                    f"Wrapper stderr: {result.stderr.strip() or '(none)'}. "
                    f"Command output: {child_output or '(no output captured)'}"
                )
            else:
                logger.debug(f"Elevated action '{command_desc}' succeeded. Output: {child_output or '(none)'}")

            suppress_component_gui()
            return exit_code
        finally:
            payload_path.unlink(missing_ok=True)
            output_path.unlink(missing_ok=True)
