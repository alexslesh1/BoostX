import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class GameSource(Enum):
    MANUAL = "manual"
    STEAM = "steam"
    EPIC = "epic"
    RIOT = "riot"
    GOG = "gog"


@dataclass(frozen=True)
class GameEntry:
    id: str
    name: str
    executable_path: str | None
    install_dir: str | None
    source: GameSource
    added_at: str

    @classmethod
    def create(
        cls,
        name: str,
        executable_path: str | None,
        install_dir: str | None,
        source: GameSource,
    ) -> "GameEntry":
        return cls(
            id=uuid.uuid4().hex,
            name=name,
            executable_path=executable_path,
            install_dir=install_dir,
            source=source,
            added_at=datetime.now(timezone.utc).isoformat(),
        )
