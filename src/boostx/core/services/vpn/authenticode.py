"""Verifies a downloaded file's Authenticode signature via Windows'
own trust-verification API (WinVerifyTrust) before we run it elevated.

This is the same check the OS performs on a double-clicked installer —
a valid, chain-trusted signature. We do it explicitly (rather than
relying on whatever msiexec/the installer does internally) because WE
are the one deciding to execute a file we just downloaded with admin
rights, and that decision needs its own verification step.
"""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

_WTD_UI_NONE = 2
_WTD_REVOKE_NONE = 0
_WTD_CHOICE_FILE = 1
_WTD_STATEACTION_VERIFY = 1
_WTD_STATEACTION_CLOSE = 2
_WTD_SAFER_FLAG = 0x100


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


# WINTRUST_ACTION_GENERIC_VERIFY_V2 = {00AAC56B-CD44-11d0-8CC2-00C04FC295EE}
_WINTRUST_ACTION_GENERIC_VERIFY_V2 = _GUID(
    0x00AAC56B, 0xCD44, 0x11D0, (ctypes.c_ubyte * 8)(0x8C, 0xC2, 0x00, 0xC0, 0x4F, 0xC2, 0x95, 0xEE)
)


class _WinTrustFileInfo(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pcwszFilePath", wintypes.LPCWSTR),
        ("hFile", wintypes.HANDLE),
        ("pgKnownSubject", ctypes.c_void_p),
    ]


class _WinTrustData(ctypes.Structure):
    _fields_ = [
        ("cbStruct", wintypes.DWORD),
        ("pPolicyCallbackData", ctypes.c_void_p),
        ("pSIPClientData", ctypes.c_void_p),
        ("dwUIChoice", wintypes.DWORD),
        ("fdwRevocationChecks", wintypes.DWORD),
        ("dwUnionChoice", wintypes.DWORD),
        ("pFile", ctypes.c_void_p),
        ("dwStateAction", wintypes.DWORD),
        ("hWVTStateData", wintypes.HANDLE),
        ("pwszURLReference", wintypes.LPCWSTR),
        ("dwProvFlags", wintypes.DWORD),
        ("dwUIContext", wintypes.DWORD),
        ("pSignatureSettings", ctypes.c_void_p),
    ]


def verify_authenticode_signature(path: Path) -> bool:
    """True only if `path` carries a valid Authenticode signature chained
    to a trusted root. False for any other outcome (unsigned, tampered,
    revoked, expired, or verification itself failing)."""
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        raise OSError("verify_authenticode_signature is only available on Windows")

    wintrust = ctypes.WinDLL("wintrust.dll")

    file_info = _WinTrustFileInfo(
        cbStruct=ctypes.sizeof(_WinTrustFileInfo),
        pcwszFilePath=str(path),
        hFile=None,
        pgKnownSubject=None,
    )

    trust_data = _WinTrustData(
        cbStruct=ctypes.sizeof(_WinTrustData),
        pPolicyCallbackData=None,
        pSIPClientData=None,
        dwUIChoice=_WTD_UI_NONE,
        fdwRevocationChecks=_WTD_REVOKE_NONE,
        dwUnionChoice=_WTD_CHOICE_FILE,
        pFile=ctypes.cast(ctypes.byref(file_info), ctypes.c_void_p),
        dwStateAction=_WTD_STATEACTION_VERIFY,
        hWVTStateData=None,
        pwszURLReference=None,
        dwProvFlags=_WTD_SAFER_FLAG,
        dwUIContext=0,
        pSignatureSettings=None,
    )

    result = wintrust.WinVerifyTrust(
        wintypes.HWND(-1), ctypes.byref(_WINTRUST_ACTION_GENERIC_VERIFY_V2), ctypes.byref(trust_data)
    )

    trust_data.dwStateAction = _WTD_STATEACTION_CLOSE
    wintrust.WinVerifyTrust(
        wintypes.HWND(-1), ctypes.byref(_WINTRUST_ACTION_GENERIC_VERIFY_V2), ctypes.byref(trust_data)
    )

    return result == 0
