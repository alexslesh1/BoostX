import os
import platform
from pathlib import Path

from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.game_entry import GameSource


class WellKnownPathDetector(GameDetector):
    source = GameSource.MANUAL

    def __init__(self, name: str, local_appdata_relative_paths: list[str]) -> None:
        self._name = name
        self._relative_paths = local_appdata_relative_paths

    def detect(self) -> list[DetectedGame]:
        if platform.system() != "Windows":
            return []
        local_appdata = os.environ.get("LOCALAPPDATA")
        if not local_appdata:
            return []
        base = Path(local_appdata)
        for relative_path in self._relative_paths:
            candidate = base / relative_path
            if candidate.is_file():
                return [
                    DetectedGame(
                        name=self._name,
                        executable_path=str(candidate),
                        install_dir=str(candidate.parent),
                        source=GameSource.MANUAL,
                    )
                ]
        return []


def discord_detector() -> WellKnownPathDetector:
    return WellKnownPathDetector("Discord", ["Discord/Update.exe"])


def telegram_detector() -> WellKnownPathDetector:
    return WellKnownPathDetector("Telegram", ["Telegram Desktop/Telegram.exe"])
