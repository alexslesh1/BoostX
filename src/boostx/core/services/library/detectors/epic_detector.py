import json
import os
import platform
from pathlib import Path, PureWindowsPath

from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.game_entry import GameSource


class EpicDetector(GameDetector):
    source = GameSource.EPIC

    def detect(self) -> list[DetectedGame]:
        manifests_dir = self._manifests_dir()
        if manifests_dir is None or not manifests_dir.is_dir():
            return []

        games: list[DetectedGame] = []
        for item_path in manifests_dir.glob("*.item"):
            game = self._read_manifest(item_path)
            if game is not None:
                games.append(game)
        return games

    @staticmethod
    def _manifests_dir() -> Path | None:
        if platform.system() != "Windows":
            return None
        program_data = os.environ.get("PROGRAMDATA")
        if not program_data:
            return None
        return Path(program_data) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"

    @staticmethod
    def _read_manifest(item_path: Path) -> DetectedGame | None:
        try:
            data = json.loads(item_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict):
            return None
        name = data.get("DisplayName")
        install_location = data.get("InstallLocation")
        launch_executable = data.get("LaunchExecutable")
        if not name or not install_location:
            return None
        executable_path = (
            str(PureWindowsPath(install_location) / launch_executable) if launch_executable else None
        )
        return DetectedGame(
            name=name,
            executable_path=executable_path,
            install_dir=install_location,
            source=GameSource.EPIC,
        )
