import platform

import psutil

from boostx.core.services.monitor.system_snapshot import CpuStats


class CpuSampler:
    def sample(self) -> CpuStats:
        frequency = psutil.cpu_freq()
        return CpuStats(
            percent=psutil.cpu_percent(interval=None),
            core_count=psutil.cpu_count(logical=False) or 0,
            thread_count=psutil.cpu_count(logical=True) or 0,
            frequency_mhz=frequency.current if frequency else None,
            temperature_c=self._read_temperature(),
            model_name=platform.processor() or "Unknown CPU",
        )

    @staticmethod
    def _read_temperature() -> float | None:
        sensors = getattr(psutil, "sensors_temperatures", None)
        if sensors is None:
            return None
        try:
            readings = sensors()
        except Exception:
            return None
        for label in ("coretemp", "cpu_thermal", "k10temp"):
            entries = readings.get(label)
            if entries:
                return entries[0].current
        return None
