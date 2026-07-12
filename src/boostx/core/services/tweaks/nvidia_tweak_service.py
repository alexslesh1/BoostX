from boostx.config.paths import AppPaths
from boostx.core.services.tweaks.dependency_checker import DependencyChecker
from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult
from boostx.core.services.tweaks.provider import TweakProviderHandler
from boostx.core.services.tweaks.script_runner import ScriptRunner

_SCRIPT_NAME = "nvidia_tweak.py"


class NvidiaTweakService(TweakProviderHandler):
    key = "nvidia"
    title = "NVIDIA Tweak"
    description = "Safely raise your GPU's power limit using NVML."
    icon_key = "nvidia"

    def __init__(self, dependency_checker: DependencyChecker | None = None, runner: ScriptRunner | None = None) -> None:
        self._dependency_checker = dependency_checker or DependencyChecker()
        self._runner = runner or ScriptRunner()

    def check_dependency(self) -> DependencyStatus:
        return self._dependency_checker.check_nvidia()

    def list_devices(self) -> list[DeviceOption]:
        try:
            import pynvml
        except ImportError:
            return []

        try:
            pynvml.nvmlInit()
        except pynvml.NVMLError:
            return []

        try:
            count = pynvml.nvmlDeviceGetCount()
            devices = []
            for index in range(count):
                handle = pynvml.nvmlDeviceGetHandleByIndex(index)
                name = pynvml.nvmlDeviceGetName(handle)
                if isinstance(name, bytes):
                    name = name.decode("utf-8", errors="replace")
                devices.append(DeviceOption(key=str(index), label=name))
            return devices
        except pynvml.NVMLError:
            return []
        finally:
            pynvml.nvmlShutdown()

    def apply(self, device_key: str | None) -> TweakRunResult:
        # nvidia_tweak.py applies its safe power-limit target to every
        # detected NVIDIA GPU in one run - it has no per-GPU selector, and
        # per the project's "don't rewrite the script" rule none is added
        # here either. device_key is accepted for interface symmetry with
        # the other providers but intentionally unused.
        del device_key
        script_path = AppPaths.scripts_dir() / _SCRIPT_NAME
        return self._runner.run(script_path, ["--apply"])
