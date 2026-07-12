import os
import platform
import subprocess
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

from boostx.core.services.boost.running_detector import is_process_running

_POST_LAUNCH_WAIT_SECONDS = 2.5


def find_telegram_executable() -> Path | None:
    system = platform.system()
    if system == "Windows":
        return _find_windows()
    if system == "Darwin":
        return _find_macos()
    return _find_linux()


def launch_telegram_with_proxy(executable_path: Path, host: str, port: int, login: str, password: str) -> bool:
    if not is_process_running(str(executable_path)):
        if not _launch(executable_path):
            return False
        time.sleep(_POST_LAUNCH_WAIT_SECONDS)

    deep_link = f"tg://socks?server={quote(host)}&port={port}&user={quote(login)}&pass={quote(password)}"
    return webbrowser.open(deep_link)


def _launch(executable_path: Path) -> bool:
    try:
        if platform.system() == "Darwin" and executable_path.suffix == ".app":
            subprocess.Popen(["open", str(executable_path)])
        else:
            subprocess.Popen([str(executable_path)], cwd=str(executable_path.parent))
        return True
    except OSError:
        return False


def _find_windows() -> Path | None:
    app_data = os.environ.get("APPDATA")
    if not app_data:
        return None
    candidate = Path(app_data) / "Telegram Desktop" / "Telegram.exe"
    return candidate if candidate.is_file() else None


def _find_macos() -> Path | None:
    candidate = Path("/Applications/Telegram.app")
    return candidate if candidate.is_dir() else None


def _find_linux() -> Path | None:
    candidates = (
        Path("/usr/bin/telegram-desktop"),
        Path("/snap/bin/telegram-desktop"),
        Path.home() / ".local" / "share" / "flatpak" / "exports" / "bin" / "org.telegram.desktop",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None
