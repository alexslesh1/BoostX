import ctypes
import platform

import psutil

from boostx.core.services.cleaner.models import MemoryOptimizationResult, MemorySnapshot


class _WindowsPerformanceInformation(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", ctypes.c_ulong),
        ("ProcessCount", ctypes.c_ulong),
        ("ThreadCount", ctypes.c_ulong),
    ]


class MemoryOptimizer:
    """Measures real memory usage via psutil and performs safe, best-effort
    optimization: trims this process's own working set and (Windows only)
    attempts to purge the standby memory list. The reported "freed" amount
    is always the actual measured before/after delta - never a fabricated
    number - so a no-op platform or a failed privileged call just reports 0
    rather than pretending something was cleaned."""

    def snapshot(self) -> MemorySnapshot:
        memory = psutil.virtual_memory()
        return MemorySnapshot(
            total_bytes=memory.total,
            used_bytes=memory.used,
            available_bytes=memory.available,
            standby_bytes=self._standby_bytes(memory),
        )

    def optimize(self) -> MemoryOptimizationResult:
        before = self.snapshot()
        self._trim_own_working_set()
        self._purge_standby_list()
        after = self.snapshot()
        freed = max(0, before.used_bytes - after.used_bytes)
        return MemoryOptimizationResult(before=before, after=after, freed_bytes=freed)

    @staticmethod
    def _standby_bytes(memory: object) -> int | None:
        system = platform.system()
        if system == "Linux":
            return getattr(memory, "cached", None)
        if system == "Windows":
            return MemoryOptimizer._windows_system_cache_bytes()
        return None

    @staticmethod
    def _windows_system_cache_bytes() -> int | None:
        try:
            info = _WindowsPerformanceInformation()
            info.cb = ctypes.sizeof(_WindowsPerformanceInformation)
            ok = ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb)
            if not ok:
                return None
            return int(info.SystemCache) * int(info.PageSize)
        except OSError:
            return None

    @staticmethod
    def _trim_own_working_set() -> None:
        if platform.system() != "Windows":
            return
        try:
            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            psapi.EmptyWorkingSet(kernel32.GetCurrentProcess())
        except OSError:
            pass

    @staticmethod
    def _purge_standby_list() -> None:
        # NOTE: best-effort. NtSetSystemInformation(SystemMemoryListInformation,
        # MemoryPurgeStandbyList) is an undocumented-but-well-known technique
        # (the same one SysInternals RAMMap / EmptyStandbyList.exe use) that
        # typically requires SeProfileSingleProcessPrivilege, i.e. running
        # elevated. It silently does nothing if unavailable; since freed_bytes
        # always comes from the real before/after snapshot, a no-op here
        # never fabricates savings - needs verification on a real Windows
        # install, ideally both elevated and non-elevated.
        if platform.system() != "Windows":
            return
        try:
            ntdll = ctypes.WinDLL("ntdll.dll")
            system_memory_list_information = ctypes.c_int(80)
            memory_purge_standby_list = ctypes.c_int(4)
            ntdll.NtSetSystemInformation(
                system_memory_list_information,
                ctypes.byref(memory_purge_standby_list),
                ctypes.sizeof(memory_purge_standby_list),
            )
        except OSError:
            pass
