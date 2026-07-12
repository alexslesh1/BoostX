from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from boostx.core.services.api.exceptions import ApiError


class _WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(object)


class _ApiTask(QRunnable):
    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception as exc:
            self.signals.error.emit(ApiError(str(exc)))
        else:
            self.signals.success.emit(result)


# QThreadPool takes C++-side ownership of a QRunnable, which does not keep its
# Python wrapper (or the signals QObject it owns) alive on the Python side.
# Without this, the signals object can be garbage-collected before its queued
# cross-thread emit is delivered, silently dropping the callback.
_active_tasks: set[_ApiTask] = set()


def run_async(
    fn: Callable[[], Any],
    on_success: Callable[[Any], None] | None = None,
    on_error: Callable[[ApiError], None] | None = None,
) -> None:
    task = _ApiTask(fn)
    _active_tasks.add(task)

    def _release(_: Any) -> None:
        _active_tasks.discard(task)

    if on_success is not None:
        task.signals.success.connect(on_success)
    if on_error is not None:
        task.signals.error.connect(on_error)
    task.signals.success.connect(_release)
    task.signals.error.connect(_release)
    QThreadPool.globalInstance().start(task)
