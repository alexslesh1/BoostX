import random
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class BoostMetricsSnapshot:
    ping_ms: float
    packet_loss_percent: float
    session_seconds: int
    power_plan: str
    average_fps: int
    cpu_usage_percent: float


# Returns (round-trip ms, loss percent) measured on the route the boosted
# application actually uses, or None when it is not routed through Nexora.
NetworkSource = Callable[[], "tuple[float, float] | None"]


class BoostMetricsProvider:
    """Samples live Boost session metrics.

    Ping and packet loss are real whenever the application is routed
    through Nexora (they come from the routing engine's own keepalives to
    the relay). Everything else — and ping/loss for an unrouted
    application — is still backed by dummy values; swap the sampling in
    `sample()` for real providers (FPS overlay, OS power plan) later
    without touching any UI code.
    """

    def __init__(self) -> None:
        self._start_time: float | None = None
        self._network_source: NetworkSource | None = None

    def set_network_source(self, source: NetworkSource | None) -> None:
        self._network_source = source

    def start(self) -> None:
        self._start_time = time.monotonic()

    def sample(self) -> BoostMetricsSnapshot:
        elapsed = int(time.monotonic() - self._start_time) if self._start_time is not None else 0
        measured = self._network_source() if self._network_source is not None else None
        ping_ms, packet_loss_percent = measured or (random.uniform(15, 45), random.uniform(0.0, 0.6))
        return BoostMetricsSnapshot(
            ping_ms=ping_ms,
            packet_loss_percent=packet_loss_percent,
            session_seconds=elapsed,
            power_plan="High Performance",
            average_fps=random.randint(90, 240),
            cpu_usage_percent=random.uniform(15, 45),
        )
