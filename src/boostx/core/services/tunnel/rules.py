"""Turns a boosted application into the engine's notion of "its programs".

A game is rarely one process: launchers, anti-cheat services and crash
handlers live in the same install folder and often open the connections
that matter. So an application is selected by its install folder where
that is safe, plus the executable names known for it.
"""
from __future__ import annotations

from pathlib import PureWindowsPath

from boostx.core.services.tunnel.models import AppRule

# Folders that hold many unrelated programs. Selecting one of these would
# route far more than the application the user chose.
_SHARED_FOLDER_NAMES = frozenset(
    {
        "windows",
        "system32",
        "syswow64",
        "program files",
        "program files (x86)",
        "programdata",
        "users",
        "desktop",
        "downloads",
        "documents",
        "appdata",
        "local",
        "locallow",
        "roaming",
        "temp",
        "common",
        "steamapps",
        "steam",
        "games",
    }
)
_MIN_FOLDER_DEPTH = 2  # e.g. C:\Games\Title — never a drive root or one level under it


def is_specific_folder(folder: str) -> bool:
    path = PureWindowsPath(folder)
    if not path.drive or not path.is_absolute():
        return False
    components = path.parts[1:]
    if len(components) < _MIN_FOLDER_DEPTH:
        return False
    return components[-1].lower() not in _SHARED_FOLDER_NAMES


def build_rule(
    app_key: str,
    executable_path: str,
    install_dir: str | None = None,
    extra_exes: tuple[str, ...] = (),
) -> AppRule:
    exe = PureWindowsPath(executable_path)
    exes: list[str] = []
    for name in (exe.name, *extra_exes):
        if name and name.lower().endswith(".exe") and name.lower() not in {e.lower() for e in exes}:
            exes.append(name)

    dirs: list[str] = []
    for folder in (install_dir, str(exe.parent)):
        if folder and is_specific_folder(folder):
            dirs.append(str(PureWindowsPath(folder)))
            break
    return AppRule(name=app_key, exes=tuple(exes), dirs=tuple(dirs))
