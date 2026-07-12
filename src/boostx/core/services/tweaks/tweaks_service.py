from boostx.core.services.tweaks.amd_tweak_service import AmdPBOService
from boostx.core.services.tweaks.generic_tweak_provider import GenericTweakProvider
from boostx.core.services.tweaks.intel_tweak_service import IntelXTUService
from boostx.core.services.tweaks.nvidia_tweak_service import NvidiaTweakService
from boostx.core.services.tweaks.provider import TweakProviderHandler


class TweaksService:
    """Registry of tweak providers. Adding a new hardware tweak module later
    means registering one more TweakProviderHandler here - the UI only ever
    iterates this list and never needs to change."""

    def __init__(self) -> None:
        self._providers: list[TweakProviderHandler] = [
            NvidiaTweakService(),
            IntelXTUService(),
            AmdPBOService(),
            GenericTweakProvider(),
        ]

    def providers(self) -> list[TweakProviderHandler]:
        return list(self._providers)

    def get(self, key: str) -> TweakProviderHandler | None:
        return next((provider for provider in self._providers if provider.key == key), None)
