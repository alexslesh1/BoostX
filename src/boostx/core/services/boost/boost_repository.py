import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from boostx.core.services.boost.boost_app_status import BoostAppStatus
from boostx.core.services.boost.catalog import BOOST_CATALOG, DEMO_EXECUTABLE_SENTINEL

_SCHEMA = """
CREATE TABLE IF NOT EXISTS boost_app_status (
    app_key TEXT PRIMARY KEY,
    installed INTEGER NOT NULL DEFAULT 0,
    executable_path TEXT,
    install_dir TEXT,
    source TEXT,
    launch_count INTEGER NOT NULL DEFAULT 0,
    last_launch_at TEXT,
    custom_settings TEXT
);
CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


class BoostRepository:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path))
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()
        self._seed_catalog_rows()

    def _ensure_schema(self) -> None:
        with self._conn:
            self._conn.executescript(_SCHEMA)

    def _seed_catalog_rows(self) -> None:
        with self._conn:
            for entry in BOOST_CATALOG:
                if entry.is_demo:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO boost_app_status "
                        "(app_key, installed, executable_path, source) VALUES (?, 1, ?, ?)",
                        (entry.key, DEMO_EXECUTABLE_SENTINEL, "demo"),
                    )
                else:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO boost_app_status (app_key, installed) VALUES (?, 0)",
                        (entry.key,),
                    )

    def get_status(self, app_key: str) -> BoostAppStatus | None:
        row = self._conn.execute(
            "SELECT * FROM boost_app_status WHERE app_key = ?", (app_key,)
        ).fetchone()
        return self._row_to_status(row) if row else None

    def get_all_statuses(self) -> dict[str, BoostAppStatus]:
        rows = self._conn.execute("SELECT * FROM boost_app_status").fetchall()
        return {row["app_key"]: self._row_to_status(row) for row in rows}

    def upsert_from_scan(
        self,
        app_key: str,
        installed: bool,
        executable_path: str | None,
        install_dir: str | None,
        source: str | None,
    ) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE boost_app_status SET installed = ?, executable_path = ?, "
                "install_dir = ?, source = ? WHERE app_key = ?",
                (int(installed), executable_path, install_dir, source, app_key),
            )

    def upsert_from_locate(self, app_key: str, executable_path: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE boost_app_status SET installed = 1, executable_path = ?, source = ? "
                "WHERE app_key = ?",
                (executable_path, "manual", app_key),
            )

    def record_launch(self, app_key: str) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE boost_app_status SET launch_count = launch_count + 1, last_launch_at = ? "
                "WHERE app_key = ?",
                (datetime.now(timezone.utc).isoformat(), app_key),
            )

    def get_setting(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO app_settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def close(self) -> None:
        self._conn.close()

    @staticmethod
    def _row_to_status(row: sqlite3.Row) -> BoostAppStatus:
        return BoostAppStatus(
            app_key=row["app_key"],
            installed=bool(row["installed"]),
            executable_path=row["executable_path"],
            install_dir=row["install_dir"],
            source=row["source"],
            launch_count=row["launch_count"],
            last_launch_at=row["last_launch_at"],
            custom_settings=row["custom_settings"],
        )
