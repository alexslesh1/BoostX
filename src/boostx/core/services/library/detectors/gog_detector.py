import os
import platform
import sqlite3
from pathlib import Path

from boostx.core.services.library.detectors.base import DetectedGame, GameDetector
from boostx.core.services.library.game_entry import GameSource

_QUERY = """
SELECT ibp.productId AS product_id, ibp.installationPath AS install_dir
FROM InstalledBaseProducts ibp
"""


class GogDetector(GameDetector):
    source = GameSource.GOG

    # NOTE: GOG Galaxy's on-disk schema isn't officially documented; this queries the table
    # name observed in community documentation (InstalledBaseProducts) and falls back to an
    # empty result on any schema mismatch rather than guessing further. Needs verification
    # against a real GOG Galaxy install on Windows.
    def detect(self) -> list[DetectedGame]:
        db_path = self._db_path()
        if db_path is None or not db_path.is_file():
            return []

        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return []

        games: list[DetectedGame] = []
        try:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "InstalledBaseProducts" not in tables:
                return []
            for product_id, install_dir in conn.execute(_QUERY):
                if not install_dir:
                    continue
                games.append(
                    DetectedGame(
                        name=str(product_id),
                        executable_path=None,
                        install_dir=install_dir,
                        source=GameSource.GOG,
                    )
                )
        except sqlite3.Error:
            return []
        finally:
            conn.close()
        return games

    @staticmethod
    def _db_path() -> Path | None:
        if platform.system() != "Windows":
            return None
        program_data = os.environ.get("PROGRAMDATA")
        if not program_data:
            return None
        return Path(program_data) / "GOG.com" / "Galaxy" / "storage" / "galaxy-2.0.db"
