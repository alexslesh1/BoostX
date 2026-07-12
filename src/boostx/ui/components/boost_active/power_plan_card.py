from PySide6.QtWidgets import QWidget

from boostx.ui.components.boost_active.metric_card import MetricCard


class PowerPlanCard(MetricCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Power Plan", parent)
        self.set_severity("success")

    def update_plan(self, plan_name: str) -> None:
        self._set_value(plan_name)
