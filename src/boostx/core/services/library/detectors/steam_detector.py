import platform
from pathlib import Path

from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.detectors.steam_vdf import VdfParseError, parse_vdf
from boostx.core.services.library.game_entry import GameSource


class SteamDetector(GameDetector):
    source = GameSource.STEAM

    def detect(self) -> list[DetectedGame]:
        steam_root = self._find_steam_root()
        if steam_root is None:
            return []

        games: list[DetectedGame] = []
        for library_path in self._read_library_paths(steam_root):
            steamapps_dir = library_path / "steamapps"
            if not steamapps_dir.is_dir():
                continue
            for manifest_path in steamapps_dir.glob("appmanifest_*.acf"):
                game = self._read_manifest(manifest_path)
                if game is not None:
                    games.append(game)
        return games

    @staticmethod
    def _find_steam_root() -> Path | None:
        if platform.system() == "Windows":
            candidates = [Path("C:/Program Files (x86)/Steam"), Path("C:/Program Files/Steam")]
        else:
            candidates = [
                Path.home() / "Library/Application Support/Steam",
                Path.home() / ".steam/steam",
                Path.home() / ".local/share/Steam",
            ]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
        return None

    @staticmethod
    def _read_library_paths(steam_root: Path) -> list[Path]:
        paths = [steam_root]
        libraryfolders_path = steam_root / "steamapps" / "libraryfolders.vdf"
        if not libraryfolders_path.is_file():
            return paths
        try:
            data = parse_vdf(libraryfolders_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, VdfParseError):
            return paths
        root = data.get("libraryfolders")
        if not isinstance(root, dict):
            return paths
        for value in root.values():
            if isinstance(value, dict) and value.get("path"):
                paths.append(Path(value["path"]))
        return paths

    @staticmethod
    def _read_manifest(manifest_path: Path) -> DetectedGame | None:
        try:
            data = parse_vdf(manifest_path.read_text(encoding="utf-8", errors="ignore"))
        except (OSError, VdfParseError):
            return None
        app_state = data.get("AppState")
        if not isinstance(app_state, dict):
            return None
        name = app_state.get("name")
        installdir = app_state.get("installdir")
        if not name or not installdir:
            return None
        install_dir = str(manifest_path.parent / "common" / installdir)
        # Steam resolves the launch executable internally at runtime; it isn't present in
        # the manifest, so this detector can never populate executable_path.
        return DetectedGame(
            name=name,
            executable_path=None,
            install_dir=install_dir,
            source=GameSource.STEAM,
        )
