from PySide6.QtWidgets import QWidget

from boostx.ui.components.boost_active.metric_card import MetricCard

_WARNING_THRESHOLD = 60.0
_ERROR_THRESHOLD = 85.0


class CPUUsageCard(MetricCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("CPU Usage", parent)
        self.set_severity("success")

    def update_percent(self, value: float) -> None:
        self._set_value(f"{value:.0f} %")
        if value >= _ERROR_THRESHOLD:
            self.set_severity("error")
        elif value >= _WARNING_THRESHOLD:
            self.set_severity("warning")
        else:
            self.set_severity("success")
