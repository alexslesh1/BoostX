import subprocess

from boostx.core.services.monitor.system_snapshot import GpuStats

_UNAVAILABLE = GpuStats(
    available=False,
    name=None,
    load_percent=None,
    memory_used_mb=None,
    memory_total_mb=None,
    temperature_c=None,
)

_QUERY_FIELDS = "name,utilization.gpu,temperature.gpu,memory.used,memory.total"


class GpuSampler:
    def sample(self) -> GpuStats:
        try:
            result = subprocess.run(
                ["nvidia-smi", f"--query-gpu={_QUERY_FIELDS}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=True,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
            return _UNAVAILABLE

        first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        if not first_line:
            return _UNAVAILABLE

        try:
            name, load, temperature, used_mb, total_mb = (part.strip() for part in first_line.split(","))
            return GpuStats(
                available=True,
                name=name,
                load_percent=float(load),
                temperature_c=float(temperature),
                memory_used_mb=float(used_mb),
                memory_total_mb=float(total_mb),
            )
        except (ValueError, IndexError):
            return _UNAVAILABLE
