from dataclasses import dataclass
from pathlib import Path

from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.boost_repository import BoostRepository
from boostx.core.services.boost.catalog import DEMO_EXECUTABLE_SENTINEL, build_alias_index, normalize_name
from boostx.core.services.boost.running_detector import is_process_running
from boostx.core.services.boost.well_known_path_detector import discord_detector, telegram_detector
from boostx.core.services.launcher.process_launcher import launch_executable
from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.detectors.epic_detector import EpicDetector
from boostx.core.services.library.detectors.gog_detector import GogDetector
from boostx.core.services.library.detectors.riot_detector import RiotDetector
from boostx.core.services.library.detectors.steam_detector import SteamDetector


@dataclass(frozen=True)
class ScanResult:
    detected: int
    matched: int


def _default_sources() -> list[tuple[str, GameDetector]]:
    return [
        ("steam", SteamDetector()),
        ("epic", EpicDetector()),
        ("riot", RiotDetector()),
        ("gog", GogDetector()),
        ("discord", discord_detector()),
        ("telegram", telegram_detector()),
    ]


class BoostService:
    def __init__(
        self,
        repository: BoostRepository,
        sources: list[tuple[str, GameDetector]] | None = None,
    ) -> None:
        self._repository = repository
        self._sources = sources if sources is not None else _default_sources()
        self._alias_index = build_alias_index()

    def get_all_statuses(self) -> dict[str, BoostAppStatus]:
        return self._repository.get_all_statuses()

    def get_status(self, app_key: str) -> BoostAppStatus | None:
        return self._repository.get_status(app_key)

    def scan(self) -> ScanResult:
        detected_total = 0
        matched_total = 0
        for source_name, detector in self._sources:
            try:
                detected_games = detector.detect()
            except Exception:
                continue
            for game in detected_games:
                detected_total += 1
                app_key = self._match(game)
                if app_key is None:
                    continue
                matched_total += 1
                self._repository.upsert_from_scan(
                    app_key=app_key,
                    installed=True,
                    executable_path=game.executable_path,
                    install_dir=game.install_dir,
                    source=source_name,
                )
        return ScanResult(detected=detected_total, matched=matched_total)

    def _match(self, game: DetectedGame) -> str | None:
        key = self._alias_index.get(normalize_name(game.name))
        if key is not None:
            return key
        if game.install_dir:
            basename = Path(game.install_dir).name
            key = self._alias_index.get(normalize_name(basename))
            if key is not None:
                return key
        return None

    def locate_app(self, app_key: str, executable_path: str) -> None:
        self._repository.upsert_from_locate(app_key, executable_path)

    def launch_app(self, app_key: str) -> bool:
        status = self._repository.get_status(app_key)
        if status is None or status.executable_path is None:
            return False
        if status.executable_path == DEMO_EXECUTABLE_SENTINEL:
            self._repository.record_launch(app_key)
            return True
        launched = launch_executable(status.executable_path)
        if launched:
            self._repository.record_launch(app_key)
        return launched

    def get_running_app_keys(self) -> set[str]:
        running: set[str] = set()
        for app_key, status in self._repository.get_all_statuses().items():
            if not status.installed or not status.executable_path:
                continue
            if status.executable_path == DEMO_EXECUTABLE_SENTINEL:
                continue
            if is_process_running(status.executable_path):
                running.add(app_key)
        return running

    def get_setting(self, key: str) -> str | None:
        return self._repository.get_setting(key)

    def set_setting(self, key: str, value: str) -> None:
        self._repository.set_setting(key, value)
