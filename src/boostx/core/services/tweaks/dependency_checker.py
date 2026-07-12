import shutil
from pathlib import Path

from boostx.core.services.tweaks.models import DependencyStatus

_NVIDIA_DRIVER_URL = "https://www.nvidia.com/Download/index.aspx"
_INTEL_XTU_URL = "https://www.intel.com/content/www/us/en/download/17881/intel-extreme-tuning-utility-intel-xtu.html"
_RYZENADJ_URL = "https://github.com/FlyGoat/RyzenAdj/releases"

_XTU_CLI_CANDIDATES = [
    r"C:\Program Files\Intel\Intel(R) Extreme Tuning Utility\Client\xtucli.exe",
    "xtucli",
]

_NVIDIA_MISSING_MESSAGE = "Required component not found. Please install the latest NVIDIA Driver."
_INTEL_MISSING_MESSAGE = "Intel Extreme Tuning Utility is not installed. Install Intel XTU to continue."
_AMD_MISSING_MESSAGE = "Required AMD component is missing. Please install RyzenAdj to continue."


class DependencyChecker:
    """Verifies each vendor's external tool is present before the UI ever
    offers to launch the corresponding tweak script."""

    def check_nvidia(self) -> DependencyStatus:
        try:
            import pynvml
        except ImportError:
            return DependencyStatus(available=False, message=_NVIDIA_MISSING_MESSAGE, download_url=_NVIDIA_DRIVER_URL)

        try:
            pynvml.nvmlInit()
            pynvml.nvmlShutdown()
        except pynvml.NVMLError:
            return DependencyStatus(available=False, message=_NVIDIA_MISSING_MESSAGE, download_url=_NVIDIA_DRIVER_URL)
        return DependencyStatus(available=True, message="NVIDIA driver detected.")

    def check_intel(self) -> DependencyStatus:
        for candidate in _XTU_CLI_CANDIDATES:
            if shutil.which(candidate) or Path(candidate).is_file():
                return DependencyStatus(available=True, message="Intel XTU CLI detected.")
        return DependencyStatus(available=False, message=_INTEL_MISSING_MESSAGE, download_url=_INTEL_XTU_URL)

    def check_amd(self) -> DependencyStatus:
        if shutil.which("ryzenadj") or shutil.which("ryzenadj.exe"):
            return DependencyStatus(available=True, message="RyzenAdj detected.")
        return DependencyStatus(available=False, message=_AMD_MISSING_MESSAGE, download_url=_RYZENADJ_URL)
