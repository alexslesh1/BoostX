from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceOption:
    key: str
    label: str


@dataclass(frozen=True)
class DependencyStatus:
    available: bool
    message: str
    download_url: str | None = None


@dataclass(frozen=True)
class TweakRunResult:
    success: bool
    output: str
    duration_seconds: float
