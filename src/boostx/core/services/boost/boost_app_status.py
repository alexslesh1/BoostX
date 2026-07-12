from dataclasses import dataclass


@dataclass(frozen=True)
class BoostAppStatus:
    app_key: str
    installed: bool
    executable_path: str | None
    install_dir: str | None
    source: str | None
    launch_count: int
    last_launch_at: str | None
    custom_settings: str | None
