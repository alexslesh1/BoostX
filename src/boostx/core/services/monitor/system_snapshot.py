from dataclasses import dataclass


@dataclass(frozen=True)
class CpuStats:
    percent: float
    core_count: int
    thread_count: int
    frequency_mhz: float | None
    temperature_c: float | None
    model_name: str


@dataclass(frozen=True)
class RamStats:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    percent: float
    speed_mhz: float | None


@dataclass(frozen=True)
class DiskPartitionUsage:
    mountpoint: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float


@dataclass(frozen=True)
class DiskStats:
    partitions: tuple[DiskPartitionUsage, ...]
    read_bytes_per_sec: float | None
    write_bytes_per_sec: float | None


@dataclass(frozen=True)
class NetworkStats:
    sent_bytes_per_sec: float | None
    recv_bytes_per_sec: float | None
    local_ip: str | None


@dataclass(frozen=True)
class GpuStats:
    available: bool
    name: str | None
    load_percent: float | None
    memory_used_mb: float | None
    memory_total_mb: float | None
    temperature_c: float | None


@dataclass(frozen=True)
class PingStats:
    target: str
    latency_ms: float | None
    reachable: bool


@dataclass(frozen=True)
class FastSnapshot:
    timestamp: float
    cpu: CpuStats
    ram: RamStats
    disk: DiskStats
    network: NetworkStats


@dataclass(frozen=True)
class SlowSnapshot:
    timestamp: float
    gpu: GpuStats
    ping: PingStats


@dataclass(frozen=True)
class SystemSnapshot:
    timestamp: float
    cpu: CpuStats
    ram: RamStats
    disk: DiskStats
    network: NetworkStats
    gpu: GpuStats
    ping: PingStats
