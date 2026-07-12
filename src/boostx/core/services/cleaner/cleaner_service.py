import time
from typing import Callable

from boostx.core.services.cleaner.cache_scanner import CacheScanner
from boostx.core.services.cleaner.game_cache_scanner import GameCacheScanner
from boostx.core.services.cleaner.models import CategoryCleanResult, CleanResult, ScanCategory, ScanResult
from boostx.core.services.cleaner.recycle_bin_scanner import RecycleBinScanner
from boostx.core.services.cleaner.temp_scanner import TempScanner

_TEMP_FILES_KEY = "temp_files"
_GAME_CACHE_KEY = "game_cache"
_RECYCLE_BIN_KEY = "recycle_bin"


class CleanerService:
    """Orchestrates every disk-space scanner into a single scan()/clean()
    pair. Remembers the concrete paths found by the last scan so clean()
    only ever touches what was actually shown to the user."""

    def __init__(self) -> None:
        self._temp_scanner = TempScanner()
        self._cache_scanner = CacheScanner()
        self._game_cache_scanner = GameCacheScanner()
        self._recycle_bin_scanner = RecycleBinScanner()
        self._last_categories: dict[str, ScanCategory] = {}

    def scan(self) -> ScanResult:
        categories = [
            self._temp_scanner.scan(),
            *self._cache_scanner.scan(),
            self._game_cache_scanner.scan(),
            self._recycle_bin_scanner.scan(),
        ]
        self._last_categories = {category.key: category for category in categories}
        return ScanResult(categories=categories)

    def clean(
        self, selected_keys: set[str], on_progress: Callable[[str], None] | None = None
    ) -> CleanResult:
        start = time.monotonic()
        results: list[CategoryCleanResult] = []
        for key in selected_keys:
            category = self._last_categories.get(key)
            if category is None or category.size_bytes == 0:
                continue
            if on_progress is not None:
                on_progress(category.label)
            freed, errors = self._clean_category(category)
            results.append(CategoryCleanResult(key=key, freed_bytes=freed, errors=errors))
        duration = time.monotonic() - start
        return CleanResult(category_results=results, duration_seconds=duration)

    def _clean_category(self, category: ScanCategory) -> tuple[int, int]:
        if category.key == _TEMP_FILES_KEY:
            return self._temp_scanner.clean(category)
        if category.key == _GAME_CACHE_KEY:
            return self._game_cache_scanner.clean(category)
        if category.key == _RECYCLE_BIN_KEY:
            return self._recycle_bin_scanner.clean(category)
        return self._cache_scanner.clean(category)
