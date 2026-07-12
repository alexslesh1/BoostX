from collections import deque


class RollingSeriesBuffer:
    def __init__(self, max_points: int = 60) -> None:
        self._values: deque[float] = deque(maxlen=max_points)

    def push(self, value: float) -> None:
        self._values.append(value)

    def clear(self) -> None:
        self._values.clear()

    def values(self) -> list[float]:
        return list(self._values)

    def max_value(self) -> float:
        return max(self._values) if self._values else 0.0
