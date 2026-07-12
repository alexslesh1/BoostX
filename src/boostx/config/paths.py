import os
import sys
from pathlib import Path

_APP_NAME = "Nexora"


class AppPaths:
    @staticmethod
    def package_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @classmethod
    def resources_dir(cls) -> Path:
        # PyInstaller (onefile and onedir) extracts bundled data next to
        # sys._MEIPASS at runtime; everything else (source checkout, editable
        # install, wheel install) resolves resources relative to the
        # installed package instead.
        frozen_base = getattr(sys, "_MEIPASS", None)
        if frozen_base is not None:
            return Path(frozen_base) / "resources"
        return cls.package_root() / "resources"

    @classmethod
    def icons_dir(cls) -> Path:
        return cls.resources_dir() / "icons"

    @classmethod
    def nav_icons_dir(cls) -> Path:
        return cls.icons_dir() / "nav"

    @classmethod
    def window_icons_dir(cls) -> Path:
        return cls.icons_dir() / "window"

    @classmethod
    def game_icons_dir(cls) -> Path:
        return cls.icons_dir() / "game"

    @classmethod
    def styles_dir(cls) -> Path:
        return cls.resources_dir() / "styles"

    @classmethod
    def scripts_dir(cls) -> Path:
        return cls.resources_dir() / "scripts"

    @classmethod
    def catalog_dir(cls) -> Path:
        """Bundled read-only reference data (e.g. CPU catalogs), distinct
        from data_dir() which is the writable per-user data directory."""
        return cls.resources_dir() / "data"

    @classmethod
    def user_data_root(cls) -> Path:
        """OS-appropriate per-user application data directory.

        Never derived from the install location, so it resolves the same
        way whether running from source, an editable install, a wheel, or a
        PyInstaller/Nuitka build - and is always writable by the current
        user, unlike a path relative to the package (which may sit in a
        read-only system location or a temporary extraction directory).
        """
        if sys.platform == "win32":
            base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        elif sys.platform == "darwin":
            base = str(Path.home() / "Library" / "Application Support")
        else:
            base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        path = Path(base) / _APP_NAME
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def logs_dir(cls) -> Path:
        logs_dir = cls.user_data_root() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    @classmethod
    def data_dir(cls) -> Path:
        data_dir = cls.user_data_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
