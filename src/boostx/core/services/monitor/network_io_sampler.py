import time

import psutil


class NetworkIoRateSampler:
    def __init__(self) -> None:
        self._prev_sent_bytes: int | None = None
        self._prev_recv_bytes: int | None = None
        self._prev_time: float | None = None

    def sample(self) -> tuple[float | None, float | None]:
        counters = psutil.net_io_counters()
        now = time.monotonic()

        if counters is None:
            return None, None

        if self._prev_time is None:
            self._prev_sent_bytes = counters.bytes_sent
            self._prev_recv_bytes = counters.bytes_recv
            self._prev_time = now
            return None, None

        elapsed = now - self._prev_time
        if elapsed <= 0:
            return None, None

        sent_rate = max((counters.bytes_sent - self._prev_sent_bytes) / elapsed, 0.0)
        recv_rate = max((counters.bytes_recv - self._prev_recv_bytes) / elapsed, 0.0)

        self._prev_sent_bytes = counters.bytes_sent
        self._prev_recv_bytes = counters.bytes_recv
        self._prev_time = now

        return sent_rate, recv_rate
