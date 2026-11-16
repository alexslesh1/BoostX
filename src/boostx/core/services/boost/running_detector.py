import os

import psutil


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def is_process_running(
    executable_path: str, extra_names: tuple[str, ...] = (), install_dir: str | None = None
) -> bool:
    """True if `executable_path` is running, or a process named one of
    `extra_names`, or any program inside `install_dir`."""
    target_norm = _norm(executable_path)
    target_basename = os.path.basename(executable_path)
    if target_basename.endswith(".app"):
        target_basename = target_basename[: -len(".app")]
    target_basename_lower = target_basename.lower()
    extra_lower = {name.lower() for name in extra_names}
    folder_prefix = _norm(install_dir) + os.sep if install_dir else None

    for proc in psutil.process_iter(["name", "exe"]):
        try:
            exe = proc.info.get("exe")
            name = proc.info.get("name") or ""
            if exe:
                exe_norm = _norm(exe)
                if exe_norm == target_norm or exe_norm.startswith(target_norm + os.sep):
                    return True
                if folder_prefix is not None and exe_norm.startswith(folder_prefix):
                    return True
            if target_basename_lower and target_basename_lower in name.lower():
                return True
            if name.lower() in extra_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False
