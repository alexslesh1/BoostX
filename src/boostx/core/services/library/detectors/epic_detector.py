import json
import os
import platform
from pathlib import Path, PureWindowsPath
from urllib.parse import quote

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


def epic_launch_uri(install_dir: str | None, manifests_dir: Path | None = None) -> str | None:
    """The URI that asks the Epic Games Launcher to start the game installed
    in `install_dir`. Epic games cannot be started by running their exe:
    the one in the manifest (e.g. FortniteLauncher.exe) only works when the
    Epic launcher passes it a fresh login, which this URI makes it do."""
    if not install_dir:
        return None
    folder = manifests_dir if manifests_dir is not None else EpicDetector._manifests_dir()
    if folder is None or not folder.is_dir():
        return None
    wanted = os.path.normcase(os.path.normpath(install_dir))
    for item_path in folder.glob("*.item"):
        try:
            data = json.loads(item_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict) or not data.get("InstallLocation") or not data.get("AppName"):
            continue
        if os.path.normcase(os.path.normpath(data["InstallLocation"])) != wanted:
            continue
        parts = [data.get("CatalogNamespace"), data.get("CatalogItemId"), data["AppName"]]
        app_id = ":".join(parts) if all(parts) else data["AppName"]
        return f"com.epicgames.launcher://apps/{quote(app_id, safe='')}?action=launch&silent=true"
    return None
