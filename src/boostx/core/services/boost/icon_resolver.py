from pathlib import Path

from boostx.core.services.boost.catalog import normalize_name

_ICON_EXTENSIONS = (".png",)


def build_icon_index(icons_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not icons_dir.is_dir():
        return index
    for path in icons_dir.iterdir():
        if path.suffix.lower() in _ICON_EXTENSIONS:
            index[normalize_name(path.stem)] = path
    return index


def resolve_icon_path(display_name: str, icon_index: dict[str, Path]) -> Path | None:
    return icon_index.get(normalize_name(display_name))
