import platform

from boostx.core.services.optimizer.optimizer_result import OptimizerResult

_STEP = "memory_cleanup"


def memory_cleanup() -> OptimizerResult:
    if platform.system() != "Windows":
        return OptimizerResult(step=_STEP, success=True, skipped=True, message="Skipped (not on Windows)")

    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        psapi = ctypes.windll.psapi
        handle = kernel32.GetCurrentProcess()
        psapi.EmptyWorkingSet(handle)
        return OptimizerResult(step=_STEP, success=True, message="Memory cleaned")
    except Exception as exc:
        return OptimizerResult(step=_STEP, success=False, message="Memory cleanup failed", error=str(exc))
