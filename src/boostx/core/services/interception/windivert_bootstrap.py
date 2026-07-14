"""Copies pydivert's bundled WinDivert64.dll/.sys to a guaranteed-local
directory before first use, and points pydivert at the copy.

pydivert hardcodes its DLL path to wherever its own package directory
happens to be:

    DLL_PATH = os.path.join(os.path.dirname(__file__), "WinDivert64.dll")

That's fine when pydivert is installed onto a real local NTFS volume,
but if the package directory sits behind a virtualized/redirected
filesystem — a VM shared folder (e.g. Parallels' `C:\Mac\...` mount), a
mapped network drive, etc. — Windows' kernel driver loader refuses to
load the `.sys` from that location, even when the file's hash and
Authenticode signature are byte-identical to a copy sitting on a genuine
local path. This was confirmed directly on real hardware: the exact
same file (same SHA256, same valid signature) loaded successfully from
`C:\Program Files\...` but failed with WinError 1275 from a
Parallels-shared venv path. This is a separate, path-based kernel loader
restriction with a symptom nearly identical to the Vulnerable Driver
Blocklist — not the same mechanism.

Copying unconditionally to AppPaths.data_dir() (rather than trying to
detect whether the current path counts as "real" local storage)
sidesteps the detection problem entirely — some virtualized filesystem
drivers report themselves as fixed volumes to GetDriveType(), so
detection isn't reliable anyway.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

from loguru import logger

from boostx.config.paths import AppPaths

_bootstrapped = False


def ensure_local_windivert_binaries() -> None:
    """Idempotent; must run before the first pydivert call in the
    process (pydivert lazily loads its DLL on first use). Safe to call
    repeatedly and from multiple call sites — only copies/patches once."""
    global _bootstrapped
    if _bootstrapped:
        return
    if sys.platform != "win32":  # pragma: no cover - Windows-only feature
        return

    import pydivert.windivert_dll as windivert_dll

    source_dir = Path(windivert_dll.__file__).parent
    dest_dir = AppPaths.data_dir() / "windivert"
    dest_dir.mkdir(parents=True, exist_ok=True)

    for filename in ("WinDivert64.dll", "WinDivert64.sys"):
        source = source_dir / filename
        if not source.is_file():
            continue
        dest = dest_dir / filename
        if not dest.is_file() or source.stat().st_mtime > dest.stat().st_mtime:
            shutil.copy2(source, dest)

    windivert_dll.DLL_PATH = str(dest_dir / "WinDivert64.dll")
    logger.debug(f"WinDivert binaries staged at a guaranteed-local path: {dest_dir}")
    _bootstrapped = True
