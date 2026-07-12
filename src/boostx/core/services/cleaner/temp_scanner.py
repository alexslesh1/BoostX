import os
import platform
import tempfile
from pathlib import Path

from boostx.core.services.cleaner.fs_utils import clear_directory_contents, directory_stats, existing_paths
from boostx.core.services.cleaner.models import ScanCategory

_KEY = "temp_files"
_LABEL = "Temporary Files"


class TempScanner:
    """Scans %TEMP%, the Windows system temp folder, and per-user temp
    folders. clean() empties each root's contents rather than deleting the
    root itself, since these are shared system folders that must keep
    existing."""

    def _roots(self) -> list[Path]:
        candidates = [Path(tempfile.gettempdir())]
        if platform.system() == "Windows":
            system_root = os.environ.get("SystemRoot")
            if system_root:
                candidates.append(Path(system_root) / "Temp")
        return existing_paths(candidates)

    def scan(self) -> ScanCategory:
        roots = self._roots()
        total_bytes = 0
        total_items = 0
        for root in roots:
            size, count = directory_stats(root)
            total_bytes += size
            total_items += count
        return ScanCategory(key=_KEY, label=_LABEL, size_bytes=total_bytes, item_count=total_items, paths=roots)

    def clean(self, category: ScanCategory) -> tuple[int, int]:
        freed = 0
        errors = 0
        for root in category.paths:
            root_freed, root_errors = clear_directory_contents(root)
            freed += root_freed
            errors += root_errors
        return freed, errors
