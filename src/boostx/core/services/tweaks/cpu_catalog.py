import json

from boostx.config.paths import AppPaths
from boostx.core.services.tweaks.models import DeviceOption


def _load(filename: str) -> list[DeviceOption]:
    path = AppPaths.catalog_dir() / filename
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return [DeviceOption(key=entry["key"], label=entry["label"]) for entry in raw]


def load_amd_cpus() -> list[DeviceOption]:
    return _load("amd_cpus.json")


def load_intel_cpus() -> list[DeviceOption]:
    return _load("intel_cpus.json")
