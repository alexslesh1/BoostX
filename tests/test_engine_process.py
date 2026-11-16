from pathlib import Path

import pytest

from boostx.config.paths import AppPaths
from boostx.core.services.tunnel import engine_process
from boostx.core.services.tunnel.engine_process import EngineProcess
from boostx.core.services.tunnel.errors import ElevationDeclinedError, EngineError, TunnelError


class Handle:
    def __init__(self) -> None:
        self.alive = True
        self.closed = False

    def is_alive(self) -> bool:
        return self.alive

    def close(self) -> None:
        self.closed = True


class Client:
    def __init__(self, port: int, key: str, ready_after: int = 0, handle: Handle | None = None) -> None:
        self.port, self.key = port, key
        self.ready_after = ready_after
        self.handle = handle
        self.status_calls = 0
        self.shutdown_called = False
        self.closed = False

    def status(self) -> dict:
        self.status_calls += 1
        if self.status_calls <= self.ready_after:
            raise EngineError("engine is not responding")
        return {"running": False}

    def shutdown(self) -> None:
        self.shutdown_called = True
        if self.handle is not None:
            self.handle.alive = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def engine_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(AppPaths, "data_dir", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(AppPaths, "logs_dir", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(engine_process, "_READY_POLL_S", 0.001)
    folder = tmp_path / "engine"
    folder.mkdir()
    for name in ("nexora-engine.exe", "WinDivert64.dll", "WinDivert64.sys"):
        (folder / name).write_bytes(b"x")
    return folder


def build(engine_dir: Path, ready_after: int = 0, **kwargs):
    launched: list[tuple[Path, list[str]]] = []
    clients: list[Client] = []
    handles: list[Handle] = []

    def launcher(executable: Path, arguments: list[str]) -> Handle:
        launched.append((executable, arguments))
        handles.append(Handle())
        return handles[-1]

    def factory(port: int, key: str) -> Client:
        clients.append(Client(port, key, ready_after=ready_after, handle=handles[-1]))
        return clients[-1]

    process = EngineProcess(engine_dir=engine_dir, launcher=launcher, client_factory=factory, **kwargs)
    return process, launched, clients, handles


def test_engine_is_started_once_with_a_key_only_this_app_knows(engine_dir: Path, tmp_path: Path):
    import os

    process, launched, clients, _ = build(engine_dir, ready_after=3)
    client = process.ensure_running()
    assert process.ensure_running() is client
    assert len(launched) == 1, "a second start would be a second administrator prompt"

    executable, arguments = launched[0]
    assert executable == engine_dir / "nexora-engine.exe"
    options = dict(zip(arguments[1::2], arguments[2::2]))
    assert arguments[0] == "serve"
    assert options["-parent-pid"] == str(os.getpid()), "the engine must exit when this app does"
    assert options["-listen"] == f"127.0.0.1:{client.port}"

    key = Path(options["-key-file"]).read_text().strip()
    assert key == client.key and len(key) == 64
    assert clients[0].status_calls == 4, "waited until the engine answered"


def test_each_start_uses_a_fresh_key(engine_dir: Path):
    process, _, clients, handles = build(engine_dir)
    process.ensure_running()
    handles[0].alive = False  # closed from Task Manager
    process.ensure_running()
    assert len(clients) == 2 and clients[0].key != clients[1].key
    assert clients[0].closed and handles[0].closed


def test_client_is_never_handed_out_for_a_dead_engine(engine_dir: Path):
    process, launched, _, handles = build(engine_dir)
    assert process.client is None and not process.is_running
    process.ensure_running()
    assert process.client is not None
    handles[0].alive = False
    assert process.client is None and not process.is_running
    assert len(launched) == 1, "looking must not start anything"


def test_missing_engine_files_are_reported_without_prompting(engine_dir: Path):
    (engine_dir / "WinDivert64.sys").unlink()
    process, launched, _, _ = build(engine_dir)
    with pytest.raises(TunnelError, match="component is missing"):
        process.ensure_running()
    assert launched == []


def test_engine_that_exits_during_startup_is_reported(engine_dir: Path):
    launched = []

    def launcher(executable, arguments):
        handle = Handle()
        handle.alive = False
        launched.append(handle)
        return handle

    process = EngineProcess(
        engine_dir=engine_dir, launcher=launcher, client_factory=lambda port, key: Client(port, key, ready_after=10**9)
    )
    with pytest.raises(TunnelError, match="could not start"):
        process.ensure_running()
    assert launched[0].closed
    assert not process.is_running


def test_engine_that_never_answers_times_out(engine_dir: Path):
    process, _, clients, handles = build(engine_dir, ready_after=10**9, ready_timeout_s=0.05)
    with pytest.raises(TunnelError, match="could not start"):
        process.ensure_running()
    assert clients[0].closed and handles[0].closed


def test_declined_prompt_propagates(engine_dir: Path):
    def launcher(executable, arguments):
        raise ElevationDeclinedError()

    process = EngineProcess(engine_dir=engine_dir, launcher=launcher, client_factory=Client)
    with pytest.raises(ElevationDeclinedError):
        process.ensure_running()


def test_stop_asks_the_engine_to_exit_and_releases_everything(engine_dir: Path):
    process, _, clients, handles = build(engine_dir)
    process.ensure_running()
    process.stop()
    assert clients[0].shutdown_called and clients[0].closed and handles[0].closed
    assert not process.is_running
    process.stop()  # harmless when nothing is running


def test_routing_is_refused_off_windows_with_a_clear_message(engine_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(engine_process.sys, "platform", "darwin")
    with pytest.raises(TunnelError, match="Windows only"):
        EngineProcess(engine_dir=engine_dir).ensure_running()
