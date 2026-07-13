"""Defensive safety net: closes any visible window the VPN component's
own installer/manager might show, no matter why it appeared. This
feature is meant to be entirely invisible — `-WindowStyle Hidden` on
Start-Process only hints at a process's *initial* window state and does
not reliably suppress a GUI app that calls its own ShowWindow after
starting, so we actively sweep for and close any such window after every
elevated action rather than relying on that hint alone.
"""
from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes

_WM_CLOSE = 0x0010
_MATCH_SUBSTRING = "wireguard"
_SWEEP_ATTEMPTS = 6
_SWEEP_INTERVAL_S = 0.5


def _close_matching_windows_once() -> None:
    user32 = ctypes.WinDLL("user32.dll")
    enum_windows_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _callback(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        if _MATCH_SUBSTRING in buffer.value.lower():
            user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)
        return True

    user32.EnumWindows(enum_windows_proc(_callback), 0)


def suppress_component_gui(attempts: int = _SWEEP_ATTEMPTS, interval_s: float = _SWEEP_INTERVAL_S) -> None:
    """Repeatedly sweeps for a few seconds since a window spawned by an
    elevated child process can appear with a short delay after that
    process's own action already returned."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        return
    for _ in range(attempts):
        _close_matching_windows_once()
        time.sleep(interval_s)
