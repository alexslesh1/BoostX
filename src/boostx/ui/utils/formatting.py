_UNITS = ("B", "KB", "MB", "GB", "TB")


def format_bytes(value: float) -> str:
    size = float(value)
    for unit in _UNITS:
        if size < 1024 or unit == _UNITS[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size:.0f} {unit}"
        size /= 1024
    return f"{size:.1f} {_UNITS[-1]}"


def format_bytes_per_sec(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{format_bytes(value)}/s"


def format_percent(value: float) -> str:
    return f"{value:.0f}%"
