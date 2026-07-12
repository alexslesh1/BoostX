from boostx.config.paths import AppPaths
from boostx.core.services.tweaks.cpu_catalog import load_amd_cpus
from boostx.core.services.tweaks.dependency_checker import DependencyChecker
from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult
from boostx.core.services.tweaks.provider import TweakProviderHandler
from boostx.core.services.tweaks.script_runner import ScriptRunner

_SCRIPT_NAME = "amd_pbo_tweak.py"


class AmdPBOService(TweakProviderHandler):
    key = "amd"
    title = "AMD PBO Tweak"
    description = "Apply safe Precision Boost Overdrive limits via RyzenAdj."
    icon_key = "amd"

    def __init__(self, dependency_checker: DependencyChecker | None = None, runner: ScriptRunner | None = None) -> None:
        self._dependency_checker = dependency_checker or DependencyChecker()
        self._runner = runner or ScriptRunner()

    def check_dependency(self) -> DependencyStatus:
        return self._dependency_checker.check_amd()

    def list_devices(self) -> list[DeviceOption]:
        return load_amd_cpus()

    def apply(self, device_key: str | None) -> TweakRunResult:
        script_path = AppPaths.scripts_dir() / _SCRIPT_NAME
        args = ["--apply"]
        if device_key:
            args.append(f"--cpu={device_key}")
        return self._runner.run(script_path, args)
