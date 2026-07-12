import shutil
from pathlib import Path


def directory_stats(path: Path) -> tuple[int, int]:
    """Return (total_bytes, item_count) for a file or directory tree.
    Never raises - unreadable entries are skipped."""
    if not path.exists():
        return 0, 0
    if path.is_file():
        try:
            return path.stat().st_size, 1
        except OSError:
            return 0, 0

    total_bytes = 0
    item_count = 0
    try:
        entries = list(path.rglob("*"))
    except OSError:
        return 0, 0
    for entry in entries:
        try:
            if entry.is_file() and not entry.is_symlink():
                total_bytes += entry.stat().st_size
                item_count += 1
        except OSError:
            continue
    return total_bytes, item_count


def existing_paths(candidates: list[Path]) -> list[Path]:
    return [path for path in candidates if path.exists()]


def delete_path(path: Path) -> tuple[int, int]:
    """Delete a file or directory tree. Returns (bytes_freed, error_count).
    Best-effort: files in use or permission-denied are skipped, never raised."""
    if not path.exists():
        return 0, 0

    if path.is_file() or path.is_symlink():
        try:
            size = path.stat().st_size
            path.unlink()
            return size, 0
        except OSError:
            return 0, 1

    freed = 0
    errors = 0
    for entry in sorted(path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if entry.is_file() or entry.is_symlink():
                freed += entry.stat().st_size
                entry.unlink()
            elif entry.is_dir():
                entry.rmdir()
        except OSError:
            errors += 1
    try:
        path.rmdir()
    except OSError:
        pass
    return freed, errors


def clear_directory_contents(path: Path) -> tuple[int, int]:
    """Delete everything inside a directory but keep the directory itself
    (used for roots we don't own, like the OS temp folder)."""
    if not path.is_dir():
        return 0, 0
    freed = 0
    errors = 0
    for child in path.iterdir():
        try:
            if child.is_dir() and not child.is_symlink():
                freed += sum(f.stat().st_size for f in child.rglob("*") if f.is_file())
                shutil.rmtree(child, ignore_errors=True)
            else:
                freed += child.stat().st_size
                child.unlink()
        except OSError:
            errors += 1
    return freed, errors
