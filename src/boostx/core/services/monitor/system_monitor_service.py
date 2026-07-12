import time

import psutil

from boostx.core.services.monitor.cpu_sampler import CpuSampler
from boostx.core.services.monitor.disk_io_sampler import DiskIoRateSampler
from boostx.core.services.monitor.disk_usage_sampler import DiskUsageSampler
from boostx.core.services.monitor.gpu_sampler import GpuSampler
from boostx.core.services.monitor.local_ip_sampler import LocalIpSampler
from boostx.core.services.monitor.network_io_sampler import NetworkIoRateSampler
from boostx.core.services.monitor.ping_sampler import PingSampler
from boostx.core.services.monitor.ram_sampler import RamSampler
from boostx.core.services.monitor.system_snapshot import DiskStats, FastSnapshot, NetworkStats, SlowSnapshot


class SystemMonitorService:
    def __init__(self) -> None:
        psutil.cpu_percent(interval=None)

        self._cpu_sampler = CpuSampler()
        self._ram_sampler = RamSampler()
        self._disk_usage_sampler = DiskUsageSampler()
        self._disk_io_sampler = DiskIoRateSampler()
        self._network_io_sampler = NetworkIoRateSampler()
        self._local_ip_sampler = LocalIpSampler()
        self._gpu_sampler = GpuSampler()
        self._ping_sampler = PingSampler()

    def sample_fast(self) -> FastSnapshot:
        read_rate, write_rate = self._disk_io_sampler.sample()
        sent_rate, recv_rate = self._network_io_sampler.sample()

        return FastSnapshot(
            timestamp=time.monotonic(),
            cpu=self._cpu_sampler.sample(),
            ram=self._ram_sampler.sample(),
            disk=DiskStats(
                partitions=self._disk_usage_sampler.sample(),
                read_bytes_per_sec=read_rate,
                write_bytes_per_sec=write_rate,
            ),
            network=NetworkStats(
                sent_bytes_per_sec=sent_rate,
                recv_bytes_per_sec=recv_rate,
                local_ip=self._local_ip_sampler.sample(),
            ),
        )

    def sample_slow(self) -> SlowSnapshot:
        return SlowSnapshot(
            timestamp=time.monotonic(),
            gpu=self._gpu_sampler.sample(),
            ping=self._ping_sampler.sample(),
        )
