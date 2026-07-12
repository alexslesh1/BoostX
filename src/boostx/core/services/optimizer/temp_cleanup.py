import platform
import tempfile
import time
from pathlib import Path

from boostx.core.services.optimizer.optimizer_result import OptimizerResult

_STEP = "temp_cleanup"
_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def temp_cleanup() -> OptimizerResult:
    if platform.system() != "Windows":
        return OptimizerResult(step=_STEP, success=True, skipped=True, message="Skipped (not on Windows)")

    try:
        temp_dir = Path(tempfile.gettempdir())
        now = time.time()
        removed = 0
        for path in temp_dir.iterdir():
            try:
                if path.is_file() and (now - path.stat().st_mtime) > _MAX_AGE_SECONDS:
                    path.unlink()
                    removed += 1
            except OSError:
                continue
        return OptimizerResult(step=_STEP, success=True, message=f"Removed {removed} old temp files")
    except OSError as exc:
        return OptimizerResult(step=_STEP, success=False, message="Temp cleanup failed", error=str(exc))
