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
    """A packaged exe uses api_url.txt beside it, else the address baked
    into the build: an NEXORA_API_URL left over from development on that PC
    must not silently send it somewhere else. Running from source uses
    NEXORA_API_URL, else the baked address, else the local dev server."""
    if getattr(sys, "frozen", False):
        url = _override_from_file() or build_config.DEFAULT_API_URL or _LOCAL_BASE_URL
    else:
        url = os.environ.get("NEXORA_API_URL") or build_config.DEFAULT_API_URL or _LOCAL_BASE_URL
    return url.rstrip("/")


@dataclass(frozen=True)
class ApiConfig:
    base_url: str = field(default_factory=_default_base_url)
    timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS
