import platform
import subprocess
from pathlib import Path

from boostx.core.services.optimizer.optimizer_result import OptimizerResult

_STEP = "run_startup_script"


def run_startup_script(script_path: Path, timeout_s: float = 30.0) -> OptimizerResult:
    if platform.system() != "Windows":
        return OptimizerResult(step=_STEP, success=True, skipped=True, message="Skipped (not on Windows)")

    if not script_path.is_file():
        return OptimizerResult(
            step=_STEP, success=False, message="Startup script not found", error=str(script_path)
        )

    try:
        result = subprocess.run(
            ["cmd", "/c", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode == 0:
            return OptimizerResult(step=_STEP, success=True, message="Startup script completed")
        return OptimizerResult(
            step=_STEP,
            success=False,
            message="Startup script failed",
            error=result.stderr or f"exit code {result.returncode}",
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return OptimizerResult(step=_STEP, success=False, message="Startup script failed", error=str(exc))
