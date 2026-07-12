import platform
import subprocess
from pathlib import Path


def launch_executable(executable_path: str) -> bool:
    try:
        if platform.system() == "Darwin" and executable_path.endswith(".app"):
            # macOS app bundles are directories, not directly-executable files —
            # `open` is the standard way to launch one.
            subprocess.Popen(["open", executable_path])
        else:
            subprocess.Popen([executable_path], cwd=str(Path(executable_path).parent))
        return True
    except OSError:
        return False


def reveal_in_file_manager(executable_path: str | None, install_dir: str | None) -> bool:
    if executable_path:
        command = _build_reveal_command(executable_path, select=True)
    elif install_dir:
        command = _build_reveal_command(install_dir, select=False)
    else:
        return False
    try:
        subprocess.Popen(command)
        return True
    except OSError:
        return False


def _build_reveal_command(path: str, select: bool) -> list[str]:
    if platform.system() == "Windows":
        return ["explorer", f"/select,{path}"] if select else ["explorer", path]
    return ["open", "-R", path] if select else ["open", path]
