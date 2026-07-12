import json
import platform
from pathlib import Path, PureWindowsPath

from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.game_entry import GameSource

_CLIENT_ALIAS_PREFIXES = ("rc_",)


class RiotDetector(GameDetector):
    source = GameSource.RIOT

    # NOTE: RiotClientInstalls.json is documented (by community reverse-engineering, not an
    # official Riot spec) to primarily expose the shared Riot Client launcher's own install
    # paths (keys like "rc_live"/"rc_default"), not necessarily separate per-title entries for
    # League of Legends/VALORANT/etc. This detector is written defensively and may find nothing
    # useful in practice - it needs verification against a real Riot Client install on Windows.
    def detect(self) -> list[DetectedGame]:
        installs_path = self._installs_path()
        if installs_path is None or not installs_path.is_file():
            return []

        try:
            data = json.loads(installs_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, json.JSONDecodeError):
            return []
        if not isinstance(data, dict):
            return []

        games: list[DetectedGame] = []
        for key, value in data.items():
            if key.startswith(_CLIENT_ALIAS_PREFIXES) or not isinstance(value, str) or not value:
                continue
            executable_path = PureWindowsPath(value)
            games.append(
                DetectedGame(
                    name=key,
                    executable_path=str(executable_path),
                    install_dir=str(executable_path.parent),
                    source=GameSource.RIOT,
                )
            )
        return games

    @staticmethod
    def _installs_path() -> Path | None:
        if platform.system() != "Windows":
            return None
        return Path("C:/ProgramData/Riot Games/RiotClientInstalls.json")
