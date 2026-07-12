import psutil

from boostx.core.services.monitor.system_snapshot import RamStats


class RamSampler:
    def sample(self) -> RamStats:
        memory = psutil.virtual_memory()
        return RamStats(
            total_bytes=memory.total,
            used_bytes=memory.used,
            available_bytes=memory.available,
            percent=memory.percent,
            speed_mhz=None,
        )
