import time

import psutil


class DiskIoRateSampler:
    def __init__(self) -> None:
        self._prev_read_bytes: int | None = None
        self._prev_write_bytes: int | None = None
        self._prev_time: float | None = None

    def sample(self) -> tuple[float | None, float | None]:
        counters = psutil.disk_io_counters()
        now = time.monotonic()

        if counters is None:
            return None, None

        if self._prev_time is None:
            self._prev_read_bytes = counters.read_bytes
            self._prev_write_bytes = counters.write_bytes
            self._prev_time = now
            return None, None

        elapsed = now - self._prev_time
        if elapsed <= 0:
            return None, None

        read_rate = max((counters.read_bytes - self._prev_read_bytes) / elapsed, 0.0)
        write_rate = max((counters.write_bytes - self._prev_write_bytes) / elapsed, 0.0)

        self._prev_read_bytes = counters.read_bytes
        self._prev_write_bytes = counters.write_bytes
        self._prev_time = now

        return read_rate, write_rate
