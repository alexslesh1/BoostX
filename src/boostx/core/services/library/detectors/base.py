from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import ClassVar

from boostx.core.services.library.game_entry import GameSource


@dataclass(frozen=True)
class DetectedGame:
    name: str
    executable_path: str | None
    install_dir: str | None
    source: GameSource


class GameDetector(ABC):
    source: ClassVar[GameSource]

    @abstractmethod
    def detect(self) -> list[DetectedGame]: ...
