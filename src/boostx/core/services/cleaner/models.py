from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ScanCategory:
    key: str
    label: str
    size_bytes: int
    item_count: int
    paths: list[Path] = field(default_factory=list)
    selected: bool = True


@dataclass(frozen=True)
class ScanResult:
    categories: list[ScanCategory]

    @property
    def total_bytes(self) -> int:
        return sum(category.size_bytes for category in self.categories)


@dataclass(frozen=True)
class CategoryCleanResult:
    key: str
    freed_bytes: int
    errors: int


@dataclass(frozen=True)
class CleanResult:
    category_results: list[CategoryCleanResult]
    duration_seconds: float

    @property
    def freed_bytes(self) -> int:
        return sum(result.freed_bytes for result in self.category_results)

    @property
    def errors(self) -> int:
        return sum(result.errors for result in self.category_results)


@dataclass(frozen=True)
class MemorySnapshot:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    standby_bytes: int | None


@dataclass(frozen=True)
class MemoryOptimizationResult:
    before: MemorySnapshot
    after: MemorySnapshot
    freed_bytes: int

    @property
    def already_optimized(self) -> bool:
        return self.freed_bytes <= 0


@dataclass(frozen=True)
class StartupEntry:
    name: str
    command: str
    enabled: bool
    scope: str


@dataclass(frozen=True)
class LargeFileGroup:
    key: str
    label: str
    path: Path
    size_bytes: int
    item_count: int
