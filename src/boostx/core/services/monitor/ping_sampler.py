import platform
import re
import subprocess

from boostx.core.services.monitor.system_snapshot import PingStats

_TARGET = "8.8.8.8"
_LATENCY_PATTERN = re.compile(r"time[=<]\s*([\d.]+)\s*ms", re.IGNORECASE)


class PingSampler:
    def sample(self) -> PingStats:
        command = self._build_command()
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=2.0)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return PingStats(target=_TARGET, latency_ms=None, reachable=False)

        if result.returncode != 0:
            return PingStats(target=_TARGET, latency_ms=None, reachable=False)

        match = _LATENCY_PATTERN.search(result.stdout)
        if not match:
            return PingStats(target=_TARGET, latency_ms=None, reachable=False)

        return PingStats(target=_TARGET, latency_ms=float(match.group(1)), reachable=True)

    @staticmethod
    def _build_command() -> list[str]:
        if platform.system() == "Windows":
            return ["ping", "-n", "1", _TARGET]
        return ["ping", "-c", "1", _TARGET]
