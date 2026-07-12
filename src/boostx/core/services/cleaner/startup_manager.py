import json
import platform

from boostx.config.paths import AppPaths
from boostx.core.services.cleaner.models import StartupEntry

try:
    import winreg
except ImportError:
    winreg = None

_RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
_STORE_FILENAME = "disabled_startup_entries.json"
_SCOPE_HIVES = {"HKCU": "HKEY_CURRENT_USER", "HKLM": "HKEY_LOCAL_MACHINE"}


class StartupManager:
    """Lists and toggles Windows startup entries (HKCU/HKLM Run keys).

    Disabling removes the value from the registry (matching what actually
    stops it from launching) but records name/command/scope in a local JSON
    store first, so the entry stays visible - and re-enabling still works -
    across app restarts. Returns an empty list on non-Windows platforms."""

    def __init__(self) -> None:
        self._store_path = AppPaths.data_dir() / _STORE_FILENAME

    def list_entries(self) -> list[StartupEntry]:
        if platform.system() != "Windows" or winreg is None:
            return []

        entries = self._read_scope("HKCU") + self._read_scope("HKLM")
        present_names = {entry.name for entry in entries}

        for name, info in self._load_disabled().items():
            if name in present_names:
                continue
            entries.append(StartupEntry(name=name, command=info["command"], enabled=False, scope=info["scope"]))
        return entries

    def set_enabled(self, entry: StartupEntry, enabled: bool) -> bool:
        if platform.system() != "Windows" or winreg is None:
            return False

        hive = getattr(winreg, _SCOPE_HIVES.get(entry.scope, ""), None)
        if hive is None:
            return False

        try:
            if enabled:
                with winreg.OpenKey(hive, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, entry.name, 0, winreg.REG_SZ, entry.command)
                self._remove_disabled(entry.name)
            else:
                self._save_disabled(entry.name, entry.command, entry.scope)
                with winreg.OpenKey(hive, _RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, entry.name)
            return True
        except OSError:
            return False

    def _read_scope(self, scope: str) -> list[StartupEntry]:
        hive = getattr(winreg, _SCOPE_HIVES[scope])
        entries: list[StartupEntry] = []
        try:
            with winreg.OpenKey(hive, _RUN_KEY_PATH, 0, winreg.KEY_READ) as key:
                index = 0
                while True:
                    try:
                        name, value, _value_type = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    entries.append(StartupEntry(name=name, command=value, enabled=True, scope=scope))
                    index += 1
        except OSError:
            pass
        return entries

    def _load_disabled(self) -> dict:
        if not self._store_path.exists():
            return {}
        try:
            return json.loads(self._store_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_disabled(self, name: str, command: str, scope: str) -> None:
        disabled = self._load_disabled()
        disabled[name] = {"command": command, "scope": scope}
        self._store_path.write_text(json.dumps(disabled), encoding="utf-8")

    def _remove_disabled(self, name: str) -> None:
        disabled = self._load_disabled()
        if name in disabled:
            del disabled[name]
            self._store_path.write_text(json.dumps(disabled), encoding="utf-8")
