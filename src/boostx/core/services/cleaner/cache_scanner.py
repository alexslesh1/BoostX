import os
import platform
from pathlib import Path

from boostx.config.paths import AppPaths
from boostx.core.services.cleaner.fs_utils import clear_directory_contents, directory_stats, existing_paths
from boostx.core.services.cleaner.models import ScanCategory

_WINDOWS_CACHE_KEY = "windows_cache"
_SHADER_CACHE_KEY = "shader_cache"
_CRASH_DUMPS_KEY = "crash_dumps"
_APP_LOGS_KEY = "application_logs"


class CacheScanner:
    """Scans Windows system caches (thumbnail cache, Delivery Optimization),
    GPU shader caches, crash dumps, and the app's own historical logs.
    Windows-only categories return an empty result on other platforms;
    Application Logs works cross-platform since it targets AppPaths."""

    def scan(self) -> list[ScanCategory]:
        return [
            self._scan_dirs(_WINDOWS_CACHE_KEY, "Windows Cache", self._windows_cache_roots()),
            self._scan_dirs(_SHADER_CACHE_KEY, "Shader Cache", self._shader_cache_roots()),
            self._scan_dirs(_CRASH_DUMPS_KEY, "Crash Dumps", self._crash_dump_roots()),
            self._scan_dirs(_APP_LOGS_KEY, "Application Logs", self._app_log_roots()),
        ]

    def clean(self, category: ScanCategory) -> tuple[int, int]:
        freed = 0
        errors = 0
        for root in category.paths:
            root_freed, root_errors = clear_directory_contents(root)
            freed += root_freed
            errors += root_errors
        return freed, errors

    @staticmethod
    def _scan_dirs(key: str, label: str, roots: list[Path]) -> ScanCategory:
        total_bytes = 0
        total_items = 0
        for root in roots:
            size, count = directory_stats(root)
            total_bytes += size
            total_items += count
        return ScanCategory(key=key, label=label, size_bytes=total_bytes, item_count=total_items, paths=roots)

    @staticmethod
    def _windows_cache_roots() -> list[Path]:
        if platform.system() != "Windows":
            return []
        local_appdata = os.environ.get("LOCALAPPDATA")
        system_root = os.environ.get("SystemRoot")
        candidates = []
        if local_appdata:
            candidates.append(Path(local_appdata) / "Microsoft" / "Windows" / "Explorer")
        if system_root:
            candidates.append(Path(system_root) / "SoftwareDistribution" / "DeliveryOptimization")
        return existing_paths(candidates)

    @staticmethod
    def _shader_cache_roots() -> list[Path]:
        # NOTE: covers the common D3D/NVIDIA shader cache locations; needs
        # verification against a real Windows install for AMD/Intel driver
        # cache paths, which vary more by GPU vendor.
        if platform.system() != "Windows":
            return []
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return []
        base = Path(local_appdata)
        return existing_paths(
            [
                base / "D3DSCache",
                base / "NVIDIA" / "DXCache",
                base / "NVIDIA" / "GLCache",
            ]
        )

    @staticmethod
    def _crash_dump_roots() -> list[Path]:
        if platform.system() != "Windows":
            return []
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return []
        return existing_paths([Path(local_appdata) / "CrashDumps"])

    @staticmethod
    def _app_log_roots() -> list[Path]:
        return existing_paths([AppPaths.logs_dir()])
