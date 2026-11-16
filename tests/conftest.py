import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import time

import pytest


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def wait_until(qapp):
    """Runs the Qt event loop until `condition()` holds, so results that
    worker threads post back to the UI thread are delivered."""

    def wait(condition, timeout: float = 3.0, message: str = "condition") -> None:
        deadline = time.monotonic() + timeout
        while not condition():
            if time.monotonic() > deadline:
                raise AssertionError(f"timed out waiting for {message}")
            qapp.processEvents()
            time.sleep(0.005)
        qapp.processEvents()

    return wait


@pytest.fixture
def settle(qapp):
    """Lets queued work and its callbacks finish."""

    def run(duration: float = 0.15) -> None:
        deadline = time.monotonic() + duration
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.005)

    return run
