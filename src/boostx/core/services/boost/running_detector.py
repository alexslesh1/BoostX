import os

import psutil


def is_process_running(executable_path: str) -> bool:
    target_norm = os.path.normcase(os.path.normpath(executable_path))
    target_basename = os.path.basename(executable_path)
    if target_basename.endswith(".app"):
        target_basename = target_basename[: -len(".app")]
    target_basename_lower = target_basename.lower()

    for proc in psutil.process_iter(["name", "exe"]):
        try:
            exe = proc.info.get("exe")
            name = proc.info.get("name") or ""
            if exe:
                exe_norm = os.path.normcase(os.path.normpath(exe))
                if exe_norm == target_norm or exe_norm.startswith(target_norm + os.sep):
                    return True
            if target_basename_lower and target_basename_lower in name.lower():
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False
