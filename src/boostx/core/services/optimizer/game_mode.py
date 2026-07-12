import platform

from boostx.core.services.optimizer.optimizer_result import OptimizerResult

_STEP = "game_mode"


def enable_game_mode() -> OptimizerResult:
    if platform.system() != "Windows":
        return OptimizerResult(step=_STEP, success=True, skipped=True, message="Skipped (not on Windows)")

    try:
        import winreg

        key = winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\GameBar", 0, winreg.KEY_SET_VALUE
        )
        winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
        return OptimizerResult(step=_STEP, success=True, message="Game Mode enabled")
    except Exception as exc:
        return OptimizerResult(step=_STEP, success=False, message="Failed to enable Game Mode", error=str(exc))
