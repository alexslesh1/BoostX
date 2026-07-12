from pathlib import Path

import psutil


def disk_health_percent() -> int:
    """Real disk-health gauge: percentage of free space on the user's
    primary drive. Not a fabricated score - directly derived from
    psutil.disk_usage()."""
    usage = psutil.disk_usage(str(Path.home().anchor))
    return max(0, min(100, round(100 - usage.percent)))
