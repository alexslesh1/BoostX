import random
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class BoostMetricsSnapshot:
    ping_ms: float
    packet_loss_percent: float
    session_seconds: int
    power_plan: str
    average_fps: int
    cpu_usage_percent: float


class BoostMetricsProvider:
    """Samples live Boost session metrics.

    Currently backed by dummy values; swap the sampling in `sample()` for
    real providers (system monitor, FPS overlay, OS power plan) later
    without touching any UI code.
    """

    def __init__(self) -> None:
        self._start_time: float | None = None

    def start(self) -> None:
        self._start_time = time.monotonic()

    def sample(self) -> BoostMetricsSnapshot:
        elapsed = int(time.monotonic() - self._start_time) if self._start_time is not None else 0
        return BoostMetricsSnapshot(
            ping_ms=random.uniform(15, 45),
            packet_loss_percent=random.uniform(0.0, 0.6),
            session_seconds=elapsed,
            power_plan="High Performance",
            average_fps=random.randint(90, 240),
            cpu_usage_percent=random.uniform(15, 45),
        )
