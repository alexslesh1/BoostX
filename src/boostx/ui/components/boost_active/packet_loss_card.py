from PySide6.QtWidgets import QWidget

from boostx.ui.components.boost_active.metric_card import MetricCard

_WARNING_THRESHOLD = 1.0
_ERROR_THRESHOLD = 3.0


class PacketLossCard(MetricCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Packet Loss", parent)
        self.set_severity("success")

    def update_percent(self, value: float) -> None:
        self._set_value(f"{value:.1f} %")
        if value >= _ERROR_THRESHOLD:
            self.set_severity("error")
        elif value >= _WARNING_THRESHOLD:
            self.set_severity("warning")
        else:
            self.set_severity("success")
