import os
from dataclasses import dataclass, field

_DEFAULT_BASE_URL = "http://localhost:8000/api/v1"
_DEFAULT_TIMEOUT_SECONDS = 10.0


def _default_base_url() -> str:
    return os.environ.get("NEXORA_API_URL", _DEFAULT_BASE_URL)


@dataclass(frozen=True)
class ApiConfig:
    base_url: str = field(default_factory=_default_base_url)
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
