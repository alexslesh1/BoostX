from __future__ import annotations

import platform
import uuid

from boostx.config.paths import AppPaths
from boostx.core.services.api.models import DeviceInfo

_DEVICE_ID_FILENAME = "device_id.txt"


def get_device_info() -> DeviceInfo:
    return DeviceInfo(
        device_id=_load_or_create_device_id(),
        device_name=platform.node() or "BoostX Desktop",
        os=f"{platform.system()} {platform.release()}".strip(),
    )


def _load_or_create_device_id() -> str:
    path = AppPaths.data_dir() / _DEVICE_ID_FILENAME
    if path.exists():
        device_id = path.read_text(encoding="utf-8").strip()
        if device_id:
            return device_id
    device_id = str(uuid.uuid4())
    path.write_text(device_id, encoding="utf-8")
    return device_id
