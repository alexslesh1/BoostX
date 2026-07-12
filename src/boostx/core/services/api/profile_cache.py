from __future__ import annotations

import json
from dataclasses import asdict

from boostx.config.paths import AppPaths
from boostx.core.services.api.models import SubscriptionInfo, UserProfile

_CACHE_FILENAME = "profile_cache.json"


class ProfileCache:
    def __init__(self) -> None:
        self._path = AppPaths.data_dir() / _CACHE_FILENAME

    def save(self, user: UserProfile, subscription: SubscriptionInfo) -> None:
        self._path.write_text(
            json.dumps({"user": asdict(user), "subscription": asdict(subscription)}),
            encoding="utf-8",
        )

    def load(self) -> tuple[UserProfile, SubscriptionInfo] | None:
        if not self._path.exists():
            return None
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return UserProfile(**data["user"]), SubscriptionInfo(**data["subscription"])
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return None
