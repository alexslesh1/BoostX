"""Starts and stops the engine (nexora-engine.exe).

The engine captures packets, which Windows only allows an administrator
to do. This app stays unelevated and starts the engine through a single
UAC prompt the first time routing is needed; after that the same engine
process is reused until the app closes. The engine watches this process
and exits by itself if the app dies, so it can never be left behind
holding the machine's traffic.
"""
from __future__ import annotations

import os
import secrets
import socket
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from loguru import logger

from boostx.config.paths import AppPaths
from boostx.core.services.tunnel.engine_client import EngineClient
from boostx.core.services.tunnel.errors import ElevationDeclinedError, EngineError, TunnelError

ENGINE_EXECUTABLE = "nexora-engine.exe"
_REQUIRED_FILES = (ENGINE_EXECUTABLE, "WinDivert64.dll", "WinDivert64.sys")
_KEY_FILENAME = "engine.key"
_LOG_FILENAME = "engine.log"
_READY_TIMEOUT_S = 15.0
_READY_POLL_S = 0.2
_EXIT_TIMEOUT_S = 5.0
_ERROR_CANCELLED = 1223  # the user answered "No" to the UAC prompt


class ProcessHandle(Protocol):
    def is_alive(self) -> bool: ...
    def close(self) -> None: ...


Launcher = Callable[[Path, list[str]], ProcessHandle]


class EngineProcess:
    def __init__(
        self,
        engine_dir: Path | None = None,
        launcher: Launcher | None = None,
        client_factory: Callable[[int, str], EngineClient] = EngineClient,
        ready_timeout_s: float = _READY_TIMEOUT_S,
    ) -> None:
        self._engine_dir = engine_dir if engine_dir is not None else AppPaths.engine_dir()
        self._launcher = launcher
        self._client_factory = client_factory
        self._ready_timeout_s = ready_timeout_s
        self._handle: ProcessHandle | None = None
        self._client: EngineClient | None = None

    @property
    def log_path(self) -> Path:
        return AppPaths.logs_dir() / _LOG_FILENAME

    @property
    def is_running(self) -> bool:
        return self._client is not None and self._handle is not None and self._handle.is_alive()

    @property
    def client(self) -> EngineClient | None:
        """The client of the engine that is running now, if one is. Unlike
        ensure_running() this never starts one, so it never raises an
        administrator prompt the user did not ask for."""
        return self._client if self.is_running else None

    def ensure_running(self) -> EngineClient:
        """Returns a client for a live engine, starting one if needed."""
        if self.is_running:
            return self._client
        self._discard()
        return self._start()

    def stop(self) -> None:
        """Asks the engine to exit. Best-effort: if the request is lost the
        engine still exits on its own when this app does."""
        client, handle = self._client, self._handle
        if client is not None and handle is not None and handle.is_alive():
            try:
                client.shutdown()
            except EngineError as exc:
                logger.warning(f"Engine did not acknowledge shutdown: {exc}")
            deadline = time.monotonic() + _EXIT_TIMEOUT_S
            while handle.is_alive() and time.monotonic() < deadline:
                time.sleep(0.05)
        self._discard()

    def _discard(self) -> None:
        if self._client is not None:
            self._client.close()
        if self._handle is not None:
            self._handle.close()
        self._client = None
        self._handle = None

    def _start(self) -> EngineClient:
        launcher = self._launcher or _platform_launcher()
        missing = [name for name in _REQUIRED_FILES if not (self._engine_dir / name).is_file()]
        if missing:
            logger.error(f"Engine files missing from {self._engine_dir}: {missing}")
            raise TunnelError("A routing component is missing. Please reinstall Nexora.")

        key = secrets.token_hex(32)
        key_path = AppPaths.data_dir() / _KEY_FILENAME
        key_path.write_text(key + "\n", encoding="utf-8")
        port = _free_loopback_port()
        arguments = [
            "serve",
            "-listen", f"127.0.0.1:{port}",
            "-key-file", str(key_path),
            "-parent-pid", str(os.getpid()),
            "-log", str(self.log_path),
        ]  # fmt: skip

        handle = launcher(self._engine_dir / ENGINE_EXECUTABLE, arguments)
        client = self._client_factory(port, key)
        deadline = time.monotonic() + self._ready_timeout_s
        while True:
            try:
                client.status()
                break
            except EngineError:
                if not handle.is_alive() or time.monotonic() >= deadline:
                    reason = "exited during startup" if not handle.is_alive() else "did not answer in time"
                    logger.error(f"Engine {reason}. Last log lines: {self._log_tail()}")
                    client.close()
                    handle.close()
                    raise TunnelError("The routing component could not start.") from None
                time.sleep(_READY_POLL_S)

        logger.info(f"Engine is running on 127.0.0.1:{port}")
        self._handle, self._client = handle, client
        return client

    def _log_tail(self, lines: int = 5) -> str:
        try:
            content = self.log_path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
        except OSError:
            return "(no engine log)"
        return " | ".join(content[-lines:]) or "(empty engine log)"


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _platform_launcher() -> Launcher:
    if sys.platform != "win32":
        raise TunnelError("Traffic routing is available on Windows only.")
    return _launch_on_windows


# ---------------------------------------------------------------------------
# Windows
# ---------------------------------------------------------------------------
class _PopenHandle:
    def __init__(self, process: subprocess.Popen) -> None:
        self._process = process

    def is_alive(self) -> bool:
        return self._process.poll() is None

    def close(self) -> None:
        pass


class _ElevatedHandle:
    """A process started through ShellExecuteEx("runas"). The handle only
    allows waiting on the process, which is all that is needed: stopping it
    goes through its own control API."""

    def __init__(self, handle: int) -> None:
        self._handle = handle

    def is_alive(self) -> bool:
        import ctypes

        if not self._handle:
            return False
        wait_timeout = 0x102
        return ctypes.windll.kernel32.WaitForSingleObject(ctypes.c_void_p(self._handle), 0) == wait_timeout

    def close(self) -> None:
        import ctypes

        if self._handle:
            ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(self._handle))
            self._handle = 0


def _launch_on_windows(executable: Path, arguments: list[str]) -> ProcessHandle:
    import ctypes
    from ctypes import wintypes

    if ctypes.windll.shell32.IsUserAnAdmin():
        # Already elevated (e.g. started from an administrator terminal):
        # no prompt is needed, and none would be shown.
        process = subprocess.Popen(
            [str(executable), *arguments],
            cwd=str(executable.parent),
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return _PopenHandle(process)

    class ShellExecuteInfo(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIconOrMonitor", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    see_mask_nocloseprocess = 0x00000040
    see_mask_noasync = 0x00000100
    sw_hide = 0

    info = ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(ShellExecuteInfo)
    info.fMask = see_mask_nocloseprocess | see_mask_noasync
    info.lpVerb = "runas"
    info.lpFile = str(executable)
    info.lpParameters = subprocess.list2cmdline(arguments)
    info.lpDirectory = str(executable.parent)
    info.nShow = sw_hide

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(ShellExecuteInfo)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        error = ctypes.get_last_error()
        if error == _ERROR_CANCELLED:
            raise ElevationDeclinedError()
        logger.error(f"Could not start the engine elevated: Windows error {error}")
        raise TunnelError("The routing component could not start.")
    if not info.hProcess:
        raise TunnelError("The routing component could not start.")
    return _ElevatedHandle(info.hProcess)
