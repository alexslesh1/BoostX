from dataclasses import dataclass


@dataclass(frozen=True)
class DependencyStatus:
    available: bool
    message: str
    download_url: str | None = None


@dataclass(frozen=True)
class VpnResult:
    success: bool
    error: str | None = None
