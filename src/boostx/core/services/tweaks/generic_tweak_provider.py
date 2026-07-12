from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult
from boostx.core.services.tweaks.provider import TweakProviderHandler


class GenericTweakProvider(TweakProviderHandler):
    """Placeholder for future hardware tweak modules (ASUS, MSI, Gigabyte,
    laptop profiles, RAM tuning, ...)."""

    key = "generic"
    title = "Hardware Tweak"
    description = "More hardware optimizations are coming soon."
    icon_key = "generic"
    requires_device_selection = False
    coming_soon = True

    def check_dependency(self) -> DependencyStatus:
        return DependencyStatus(available=True, message="")

    def list_devices(self) -> list[DeviceOption]:
        return []

    def apply(self, device_key: str | None) -> TweakRunResult:
        del device_key
        return TweakRunResult(success=False, output="Not implemented yet.", duration_seconds=0.0)
