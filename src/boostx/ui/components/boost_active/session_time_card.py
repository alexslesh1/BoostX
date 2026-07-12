from PySide6.QtWidgets import QWidget

from boostx.ui.components.boost_active.metric_card import MetricCard


class SessionTimeCard(MetricCard):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Session Time", parent)

    def update_seconds(self, elapsed_seconds: int) -> None:
        hours, remainder = divmod(elapsed_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            self._set_value(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
        else:
            self._set_value(f"{minutes:02d}:{seconds:02d}")
