from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from loguru import logger

from boostx.config.paths import AppPaths
from boostx.core.services.cleaner.models import CreateRestorePointResult, RestorePoint, RestorePointStatus

_DESCRIPTION = "Nexora Manual Restore Point"
_RESTORE_POINT_TYPE = "MODIFY_SETTINGS"
_MIN_INTERVAL = timedelta(hours=24)
_LIST_TIMEOUT_S = 15.0
_CREATE_TIMEOUT_S = 180.0
_SCRIPT_FILENAME = "create_restore_point.ps1"

_UNAVAILABLE_MESSAGE = "This feature is only available on Windows."
_GENERIC_FAILURE_MESSAGE = "Could not create a restore point. Please try again."

_LIST_COMMAND = (
    "Get-CimInstance -ClassName SystemRestore -Namespace root/default | "
    "Select-Object SequenceNumber, Description, "
    "@{Name='CreationTimeUtc';Expression={$_.CreationTime.ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')}} | "
    "ConvertTo-Json -Compress"
)


def list_restore_points() -> RestorePointStatus:
    if sys.platform != "win32":
        return RestorePointStatus(points=())
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _LIST_COMMAND],
            capture_output=True,
            text=True,
            timeout=_LIST_TIMEOUT_S,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(f"Failed to list restore points: {exc}")
        return RestorePointStatus(points=())
    return RestorePointStatus(points=_parse_points(result.stdout))


def create_restore_point() -> CreateRestorePointResult:
    if sys.platform != "win32":
        return CreateRestorePointResult(False, _UNAVAILABLE_MESSAGE)

    before = list_restore_points()
    before_max_sequence = max((point.sequence_number for point in before.points), default=0)

    exit_code = _run_elevated_checkpoint_script()

    after = list_restore_points()
    after_max_sequence = max((point.sequence_number for point in after.points), default=0)

    if after_max_sequence > before_max_sequence:
        return CreateRestorePointResult(True, "Restore point created successfully.")

    # No new restore point actually appeared -- most commonly Windows'
    # built-in 24-hour-per-restore-point limit silently no-ops
    # Checkpoint-Computer instead of raising an error, so verifying via a
    # real before/after comparison (rather than trusting the exit code
    # alone) is the only way to avoid reporting a false "success".
    latest = before.latest
    if latest is not None:
        next_allowed_at = latest.creation_time + _MIN_INTERVAL
        now = datetime.now(timezone.utc)
        if next_allowed_at > now:
            remaining = next_allowed_at - now
            hours, remainder_seconds = divmod(int(remaining.total_seconds()), 3600)
            minutes = remainder_seconds // 60
            return CreateRestorePointResult(
                False,
                "A restore point was already created recently — Windows allows only one every "
                f"24 hours. Try again in about {hours}h {minutes}m.",
            )

    if exit_code != 0:
        return CreateRestorePointResult(False, _GENERIC_FAILURE_MESSAGE)
    return CreateRestorePointResult(
        False,
        "No new restore point was created. System Protection may be turned off for this drive.",
    )


def open_restore_wizard() -> bool:
    """Opens Windows' own System Restore wizard (rstrui.exe) -- the actual
    rollback must go through this official, Microsoft-verified flow (it
    requires a special boot-time restart phase), never reimplemented here."""
    if sys.platform != "win32":
        return False
    try:
        subprocess.Popen(["rstrui.exe"])
        return True
    except OSError as exc:
        logger.warning(f"Failed to launch rstrui.exe: {exc}")
        return False


def _run_elevated_checkpoint_script() -> int:
    script_path = _write_checkpoint_script()
    try:
        arg_list = f"'-NoProfile','-ExecutionPolicy','Bypass','-File',\"{script_path}\""
        command = (
            f"$p = Start-Process -FilePath 'powershell' -ArgumentList {arg_list} "
            "-Verb RunAs -WindowStyle Hidden -PassThru -Wait; exit $p.ExitCode"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=_CREATE_TIMEOUT_S,
        )
        if result.returncode != 0:
            logger.warning(f"Elevated restore-point script exited {result.returncode}: {result.stderr.strip()}")
        return result.returncode
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning(f"Failed to run elevated restore-point script: {exc}")
        return 1
    finally:
        script_path.unlink(missing_ok=True)


def _write_checkpoint_script() -> Path:
    # Written under AppPaths.data_dir() rather than the OS temp dir --
    # a script on a redirected/virtualized temp path has previously
    # failed to load correctly for an elevated child process on this
    # project (see windivert_bootstrap.py), so this reuses the same
    # guaranteed-local, per-user directory instead.
    script_path = AppPaths.data_dir() / _SCRIPT_FILENAME
    script_path.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "try {\n"
        f"    Checkpoint-Computer -Description '{_DESCRIPTION}' -RestorePointType '{_RESTORE_POINT_TYPE}'\n"
        "    exit 0\n"
        "} catch {\n"
        "    exit 1\n"
        "}\n",
        encoding="utf-8",
    )
    return script_path


def _parse_points(raw_output: str) -> tuple[RestorePoint, ...]:
    raw_output = raw_output.strip()
    if not raw_output:
        return ()
    try:
        data = json.loads(raw_output)
    except ValueError:
        logger.warning(f"Could not parse restore point list output: {raw_output!r}")
        return ()
    if isinstance(data, dict):
        data = [data]

    points = []
    for item in data:
        creation_time = _parse_creation_time(item.get("CreationTimeUtc"))
        if creation_time is None:
            continue
        points.append(
            RestorePoint(
                sequence_number=int(item.get("SequenceNumber", 0)),
                description=item.get("Description") or "",
                creation_time=creation_time,
            )
        )
    return tuple(points)


def _parse_creation_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
