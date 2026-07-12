from pathlib import Path


class AppPaths:
    @staticmethod
    def package_root() -> Path:
        return Path(__file__).resolve().parent.parent

    @classmethod
    def resources_dir(cls) -> Path:
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
    def project_root(cls) -> Path:
        return cls.package_root().parent.parent

    @classmethod
    def logs_dir(cls) -> Path:
        logs_dir = cls.project_root() / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

    @classmethod
    def data_dir(cls) -> Path:
        data_dir = cls.project_root() / "data"
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir
