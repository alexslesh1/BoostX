import ctypes
import os
import platform
from pathlib import Path

from boostx.core.services.cleaner.fs_utils import clear_directory_contents, directory_stats
from boostx.core.services.cleaner.models import ScanCategory

_KEY = "recycle_bin"
_LABEL = "Recycle Bin"

# SHERB flags for SHEmptyRecycleBinW: skip the confirmation dialog, the
# per-item progress UI, and the empty sound.
_SHERB_NOCONFIRMATION = 0x00000001
_SHERB_NOPROGRESSUI = 0x00000002
_SHERB_NOSOUND = 0x00000004


class _SHQueryRBInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint32),
        ("i64Size", ctypes.c_int64),
        ("i64NumItems", ctypes.c_int64),
    ]


class RecycleBinScanner:
    """Queries the Recycle Bin on Windows via the shell32 API (no need to
    walk $Recycle.Bin's per-SID folders, which usually requires elevated
    permissions). Falls back to the freedesktop.org Trash spec on Linux and
    ~/.Trash on macOS."""

    def scan(self) -> ScanCategory:
        system = platform.system()
        if system == "Windows":
            size_bytes, item_count = self._query_windows_recycle_bin()
            return ScanCategory(key=_KEY, label=_LABEL, size_bytes=size_bytes, item_count=item_count, paths=[])

        root = self._trash_files_dir(system)
        if root is None or not root.exists():
            return ScanCategory(key=_KEY, label=_LABEL, size_bytes=0, item_count=0, paths=[])
        size_bytes, item_count = directory_stats(root)
        return ScanCategory(key=_KEY, label=_LABEL, size_bytes=size_bytes, item_count=item_count, paths=[root])

    def clean(self, category: ScanCategory) -> tuple[int, int]:
        if platform.system() == "Windows":
            return self._empty_windows_recycle_bin(category.size_bytes)

        freed = 0
        errors = 0
        for root in category.paths:
            root_freed, root_errors = clear_directory_contents(root)
            freed += root_freed
            errors += root_errors
            info_dir = root.parent / "info"
            if info_dir.is_dir():
                clear_directory_contents(info_dir)
        return freed, errors

    @staticmethod
    def _query_windows_recycle_bin() -> tuple[int, int]:
        try:
            info = _SHQueryRBInfo()
            info.cbSize = ctypes.sizeof(_SHQueryRBInfo)
            result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
            if result != 0:
                return 0, 0
            return int(info.i64Size), int(info.i64NumItems)
        except OSError:
            return 0, 0

    @staticmethod
    def _empty_windows_recycle_bin(size_before: int) -> tuple[int, int]:
        try:
            flags = _SHERB_NOCONFIRMATION | _SHERB_NOPROGRESSUI | _SHERB_NOSOUND
            result = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
            return (size_before, 0) if result == 0 else (0, 1)
        except OSError:
            return 0, 1

    @staticmethod
    def _trash_files_dir(system: str) -> Path | None:
        if system == "Darwin":
            return Path.home() / ".Trash"
        if system == "Linux":
            xdg_data_home = os.environ.get("XDG_DATA_HOME")
            base = Path(xdg_data_home) if xdg_data_home else Path.home() / ".local" / "share"
            return base / "Trash" / "files"
        return None
