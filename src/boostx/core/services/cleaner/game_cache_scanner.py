import os
import platform
from pathlib import Path

from boostx.core.services.cleaner.fs_utils import clear_directory_contents, directory_stats, existing_paths
from boostx.core.services.cleaner.models import ScanCategory

_KEY = "game_cache"
_LABEL = "Game Cache"

_STEAM_INSTALL_CANDIDATES = ("C:/Program Files (x86)/Steam", "C:/Program Files/Steam")
_STEAM_CACHE_SUBDIRS = ("appcache", "depotcache", "htmlcache")

# NOTE: these are the commonly documented cache locations for each launcher,
# relative to %LOCALAPPDATA% / %PROGRAMDATA% on Windows. They have not all
# been verified against a live install of every launcher and may need
# adjustment - kept as a flat table so entries are easy to add/correct.
_LOCALAPPDATA_CACHE_SUBDIRS = (
    ("Epic Games", Path("EpicGamesLauncher") / "Saved" / "webcache"),
    ("Riot Games", Path("Riot Games") / "Riot Client" / "Data"),
    ("EA App", Path("Electronic Arts") / "EA Desktop" / "CacheStorage"),
    ("Ubisoft Connect", Path("Ubisoft Game Launcher") / "cache"),
    ("Battle.net", Path("Battle.net") / "Cache"),
)


class GameCacheScanner:
    """Scans cache folders for supported game launchers: Steam, Epic Games,
    Riot Games, EA App, Ubisoft Connect, Battle.net."""

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

    def _roots(self) -> list[Path]:
        if platform.system() != "Windows":
            return []

        candidates: list[Path] = []
        for install_dir in _STEAM_INSTALL_CANDIDATES:
            steam_root = Path(install_dir)
            if steam_root.is_dir():
                candidates.extend(steam_root / subdir for subdir in _STEAM_CACHE_SUBDIRS)
                break

        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            base = Path(local_appdata)
            candidates.extend(base / relative for _name, relative in _LOCALAPPDATA_CACHE_SUBDIRS)

        return existing_paths(candidates)
