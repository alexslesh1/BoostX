from abc import ABC, abstractmethod

from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult


class TweakProviderHandler(ABC):
    """Base class for a single tweak module (NVIDIA, Intel, AMD, ...).

    New hardware tweak modules register themselves by adding an instance to
    TweaksService's provider list - the UI only ever iterates that list and
    calls these methods, so it never needs to change to support a new
    vendor.
    """

    key: str
    title: str
    description: str
    icon_key: str
    requires_device_selection: bool = True
    coming_soon: bool = False

    @abstractmethod
    def check_dependency(self) -> DependencyStatus: ...

    @abstractmethod
    def list_devices(self) -> list[DeviceOption]: ...

    @abstractmethod
    def apply(self, device_key: str | None) -> TweakRunResult: ...
