import platform
import subprocess

from boostx.core.services.optimizer.optimizer_result import OptimizerResult

_STEP = "power_plan"
_HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"


def set_high_performance_power_plan() -> OptimizerResult:
    if platform.system() != "Windows":
        return OptimizerResult(step=_STEP, success=True, skipped=True, message="Skipped (not on Windows)")

    try:
        result = subprocess.run(
            ["powercfg", "/setactive", _HIGH_PERFORMANCE_GUID],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if result.returncode == 0:
            return OptimizerResult(step=_STEP, success=True, message="High Performance power plan active")
        return OptimizerResult(
            step=_STEP, success=False, message="Failed to switch power plan", error=result.stderr
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return OptimizerResult(step=_STEP, success=False, message="Failed to switch power plan", error=str(exc))
