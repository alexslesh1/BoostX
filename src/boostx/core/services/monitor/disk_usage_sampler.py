import psutil

from boostx.core.services.monitor.system_snapshot import DiskPartitionUsage


class DiskUsageSampler:
    def sample(self) -> tuple[DiskPartitionUsage, ...]:
        partitions: list[DiskPartitionUsage] = []
        for partition in psutil.disk_partitions(all=False):
            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except (PermissionError, OSError):
                continue
            partitions.append(
                DiskPartitionUsage(
                    mountpoint=partition.mountpoint,
                    total_bytes=usage.total,
                    used_bytes=usage.used,
                    free_bytes=usage.free,
                    percent=usage.percent,
                )
            )
        return tuple(partitions)
