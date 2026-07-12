from __future__ import annotations

import json
import os
import stat

from boostx.config.paths import AppPaths

_SESSION_FILENAME = "session.json"


class TokenStorage:
    def __init__(self) -> None:
        self._path = AppPaths.data_dir() / _SESSION_FILENAME

    def load_refresh_token(self) -> str | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None
        token = data.get("refresh_token")
        return token if isinstance(token, str) and token else None

    def save_refresh_token(self, refresh_token: str) -> None:
        self._path.write_text(json.dumps({"refresh_token": refresh_token}), encoding="utf-8")
        self._restrict_permissions()

    def clear(self) -> None:
        if self._path.exists():
            self._path.unlink()

    def _restrict_permissions(self) -> None:
        if os.name == "posix":
            os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)
