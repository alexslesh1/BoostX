import json
from pathlib import Path
from types import SimpleNamespace

from boostx.core.services.boost import running_detector
from boostx.core.services.library.detectors.epic_detector import epic_launch_uri


def write_manifest(folder: Path, name: str, **fields) -> None:
    (folder / f"{name}.item").write_text(json.dumps(fields), encoding="utf-8")


def test_fortnite_is_started_through_the_epic_launcher(tmp_path: Path):
    write_manifest(tmp_path, "other", InstallLocation=r"C:\Epic\Other", AppName="Other")
    write_manifest(
        tmp_path,
        "fortnite",
        DisplayName="Fortnite",
        InstallLocation=r"C:\Program Files\Epic Games\Fortnite",
        LaunchExecutable="FortniteGame/Binaries/Win64/FortniteLauncher.exe",
        AppName="Fortnite",
        CatalogNamespace="fn",
        CatalogItemId="4fe75bbc5a674f4f9b356b5c90567da5",
    )
    uri = epic_launch_uri(r"C:\Program Files\Epic Games\Fortnite", manifests_dir=tmp_path)
    assert uri == (
        "com.epicgames.launcher://apps/fn%3A4fe75bbc5a674f4f9b356b5c90567da5%3AFortnite?action=launch&silent=true"
    )


def test_epic_uri_falls_back_to_the_app_name_and_is_none_when_unknown(tmp_path: Path):
    write_manifest(tmp_path, "g", InstallLocation=r"D:\Games\G", AppName="Gname")
    assert epic_launch_uri(r"D:\Games\G", manifests_dir=tmp_path) == (
        "com.epicgames.launcher://apps/Gname?action=launch&silent=true"
    )
    assert epic_launch_uri(r"D:\Games\Missing", manifests_dir=tmp_path) is None
    assert epic_launch_uri(None, manifests_dir=tmp_path) is None


def fake_processes(monkeypatch, *processes):
    monkeypatch.setattr(
        running_detector.psutil,
        "process_iter",
        lambda _attrs: [SimpleNamespace(info={"name": name, "exe": exe}) for name, exe in processes],
    )


def test_game_counts_as_running_after_its_launcher_has_exited(monkeypatch, tmp_path: Path):
    install = tmp_path / "Fortnite"
    launcher = install / "FortniteGame" / "Binaries" / "Win64" / "FortniteLauncher.exe"
    client = install / "FortniteGame" / "Binaries" / "Win64" / "FortniteClient-Win64-Shipping.exe"
    fake_processes(monkeypatch, ("FortniteClient-Win64-Shipping.exe", str(client)))

    assert not running_detector.is_process_running(str(launcher)), "the launcher itself is gone"
    assert running_detector.is_process_running(str(launcher), extra_names=("FortniteClient-Win64-Shipping.exe",))
    assert running_detector.is_process_running(str(launcher), install_dir=str(install))


def test_process_name_without_a_readable_path_still_matches(monkeypatch, tmp_path: Path):
    # Protected game processes often refuse to tell an unelevated app their path.
    fake_processes(monkeypatch, ("FortniteClient-Win64-Shipping.exe", None))
    assert running_detector.is_process_running(
        str(tmp_path / "FortniteLauncher.exe"), extra_names=("FortniteClient-Win64-Shipping.exe",)
    )


def test_an_unrelated_program_does_not_count(monkeypatch, tmp_path: Path):
    fake_processes(monkeypatch, ("chrome.exe", str(tmp_path / "Chrome" / "chrome.exe")))
    assert not running_detector.is_process_running(
        str(tmp_path / "Fortnite" / "FortniteLauncher.exe"),
        extra_names=("FortniteClient-Win64-Shipping.exe",),
        install_dir=str(tmp_path / "Fortnite"),
    )


def test_api_url_order_env_then_file_then_build_default(monkeypatch, tmp_path: Path):
    import sys

    from boostx.config import build_config
    from boostx.core.services.api import api_config

    monkeypatch.delenv("NEXORA_API_URL", raising=False)
    monkeypatch.setattr(build_config, "DEFAULT_API_URL", None)
    assert api_config.ApiConfig().base_url == "http://localhost:8000/api/v1"

    monkeypatch.setattr(build_config, "DEFAULT_API_URL", "http://198.51.100.7:8000/api/v1/")
    assert api_config.ApiConfig().base_url == "http://198.51.100.7:8000/api/v1"

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "Nexora.exe"))
    (tmp_path / "api_url.txt").write_text("http://203.0.113.10:8000/api/v1\n", encoding="utf-8")
    assert api_config.ApiConfig().base_url == "http://203.0.113.10:8000/api/v1"

    monkeypatch.setenv("NEXORA_API_URL", "http://env.example:9000/api/v1")
    assert api_config.ApiConfig().base_url == "http://203.0.113.10:8000/api/v1", "a leftover env var must not win in an exe"
    (tmp_path / "api_url.txt").unlink()
    assert api_config.ApiConfig().base_url == "http://198.51.100.7:8000/api/v1"

    monkeypatch.setattr(sys, "frozen", False)
    assert api_config.ApiConfig().base_url == "http://env.example:9000/api/v1", "from source, the env var is the dev switch"


def test_connection_error_names_the_server(monkeypatch):
    import httpx
    import pytest as _pytest

    from boostx.core.services.api.api_client import ApiClient
    from boostx.core.services.api.api_config import ApiConfig
    from boostx.core.services.api.exceptions import ApiConnectionError

    client = ApiClient(ApiConfig(base_url="http://203.0.113.10:8000/api/v1"))
    client._client = httpx.Client(
        base_url="http://203.0.113.10:8000/api/v1",
        transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("timed out"))),
    )
    with _pytest.raises(ApiConnectionError, match=r"203\.0\.113\.10:8000"):
        client.request("GET", "/health")


def test_logging_works_without_a_console(monkeypatch, tmp_path: Path):
    # Nexora.exe is a windowed build: there is no stderr to log to.
    import sys

    from boostx.config.paths import AppPaths
    from boostx.core.logging import logger_setup

    monkeypatch.setattr(AppPaths, "logs_dir", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(sys, "stderr", None)
    logger_setup.configure_logging()
    logger_setup.logger.info("Starting Nexora")
    logger_setup.logger.remove()
    assert "Starting Nexora" in "".join(p.read_text(encoding="utf-8") for p in tmp_path.glob("*.log"))
