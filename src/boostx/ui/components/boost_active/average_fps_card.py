from PySide6.QtWidgets import QWidget

from boostx.ui.components.boost_active.metric_card import MetricCard


class AverageFPSCard(MetricCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Average FPS", parent)

    def update_fps(self, fps: int) -> None:
        self._set_value(str(fps))
