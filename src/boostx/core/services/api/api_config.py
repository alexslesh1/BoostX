import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from boostx.config import build_config

_LOCAL_BASE_URL = "http://localhost:8000/api/v1"
_DEFAULT_TIMEOUT_SECONDS = 10.0
# A file next to Nexora.exe that points the app at another server without
# rebuilding it: one line, e.g. http://203.0.113.10:8000/api/v1
OVERRIDE_FILENAME = "api_url.txt"


def _override_from_file() -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    path = Path(sys.executable).resolve().parent / OVERRIDE_FILENAME
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def _default_base_url() -> str:
    """In order: NEXORA_API_URL, api_url.txt beside the exe, the address
    baked into the build, the local development server."""
    url = (
        os.environ.get("NEXORA_API_URL")
        or _override_from_file()
        or build_config.DEFAULT_API_URL
        or _LOCAL_BASE_URL
    )
    return url.rstrip("/")


@dataclass(frozen=True)
class ApiConfig:
    base_url: str = field(default_factory=_default_base_url)
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
