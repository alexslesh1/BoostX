from pathlib import Path

from boostx.core.services.cleaner.models import LargeFileGroup

_FOLDER_GROUPS = (
    ("downloads", "Downloads", "Downloads"),
    ("videos", "Videos", "Videos"),
)
_ISO_KEY = "isos"
_ISO_LABEL = "ISOs"


class LargeFileScanner:
    """Reports the size of well-known large-content user folders (Downloads,
    Videos) plus any .iso disc images found under Downloads. Never deletes
    files directly - the UI only offers to open the containing folder."""

    def scan(self) -> list[LargeFileGroup]:
        home = Path.home()
        groups: list[LargeFileGroup] = []

        for key, label, folder_name in _FOLDER_GROUPS:
            folder = home / folder_name
            size_bytes, item_count = self._folder_stats(folder)
            groups.append(
                LargeFileGroup(key=key, label=label, path=folder, size_bytes=size_bytes, item_count=item_count)
            )

        downloads = home / "Downloads"
        iso_size, iso_count = self._iso_stats(downloads)
        groups.append(
            LargeFileGroup(key=_ISO_KEY, label=_ISO_LABEL, path=downloads, size_bytes=iso_size, item_count=iso_count)
        )
        return groups

    @staticmethod
    def _folder_stats(folder: Path) -> tuple[int, int]:
        if not folder.is_dir():
            return 0, 0
        total_bytes = 0
        item_count = 0
        try:
            entries = list(folder.rglob("*"))
        except OSError:
            return 0, 0
        for entry in entries:
            try:
                if entry.is_file() and not entry.is_symlink():
                    total_bytes += entry.stat().st_size
                    item_count += 1
            except OSError:
                continue
        return total_bytes, item_count

    @staticmethod
    def _iso_stats(folder: Path) -> tuple[int, int]:
        if not folder.is_dir():
            return 0, 0
        total_bytes = 0
        item_count = 0
        try:
            iso_files = list(folder.rglob("*.iso"))
        except OSError:
            return 0, 0
        for entry in iso_files:
            try:
                total_bytes += entry.stat().st_size
                item_count += 1
            except OSError:
                continue
        return total_bytes, item_count
