from PySide6.QtCore import QObject, Signal, Slot

from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult
from boostx.core.services.tweaks.tweaks_service import TweaksService


class TweaksWorker(QObject):
    dependency_checked = Signal(str, object)
    devices_ready = Signal(str, object)
    tweak_finished = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self._service = TweaksService()

    @Slot(str)
    def check_dependency(self, provider_key: str) -> None:
        provider = self._service.get(provider_key)
        status = (
            provider.check_dependency()
            if provider is not None
            else DependencyStatus(available=False, message="Unknown tweak provider.")
        )
        self.dependency_checked.emit(provider_key, status)

    @Slot(str)
    def load_devices(self, provider_key: str) -> None:
        provider = self._service.get(provider_key)
        devices: list[DeviceOption] = provider.list_devices() if provider is not None else []
        self.devices_ready.emit(provider_key, devices)

    @Slot(str, object)
    def apply_tweak(self, provider_key: str, device_key: object) -> None:
        provider = self._service.get(provider_key)
        result = (
            provider.apply(device_key)
            if provider is not None
            else TweakRunResult(success=False, output="Unknown tweak provider.", duration_seconds=0.0)
        )
        self.tweak_finished.emit(provider_key, result)
