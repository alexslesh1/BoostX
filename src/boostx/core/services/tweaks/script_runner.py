import subprocess
import sys
import time
from pathlib import Path

from boostx.core.services.tweaks.models import TweakRunResult

_TIMEOUT_SECONDS = 120.0
_FAILURE_MARKER = "❌"


class ScriptRunner:
    """Launches one of the bundled vendor tweak scripts as a subprocess and
    captures its output. Never re-implements or modifies the scripts' own
    optimization logic - just starts them, waits, and reports what
    happened.

    The bundled scripts print "<marker>" and return normally (exit code 0)
    on several of their own logical-failure paths (tool not found, unknown
    CPU model, ...) rather than calling sys.exit(1). Since that convention
    is consistent across all three scripts, treating that marker in the
    captured output as a failure signal - in addition to a non-zero exit
    code - gives an honest success/failure result without touching the
    scripts themselves.
    """

    def run(self, script_path: Path, args: list[str]) -> TweakRunResult:
        start = time.monotonic()
        command = [sys.executable, str(script_path), *args]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=_TIMEOUT_SECONDS)
            output = (result.stdout or "") + (result.stderr or "")
            success = result.returncode == 0 and _FAILURE_MARKER not in output
        except subprocess.TimeoutExpired as exc:
            partial_output = exc.output if isinstance(exc.output, str) else ""
            output = f"Timed out after {_TIMEOUT_SECONDS:.0f}s.\n{partial_output}"
            success = False
        except OSError as exc:
            output = f"Failed to launch script: {exc}"
            success = False
        duration = time.monotonic() - start
        return TweakRunResult(success=success, output=output.strip(), duration_seconds=duration)
