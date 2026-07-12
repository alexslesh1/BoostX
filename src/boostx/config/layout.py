from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutConstants:
    MIN_WIDTH: int = 1300
    MIN_HEIGHT: int = 800
    SIDEBAR_WIDTH: int = 220
    TITLEBAR_HEIGHT: int = 40
    RESIZE_MARGIN: int = 6
    BORDER_RADIUS: int = 10
    BORDER_RADIUS_SMALL: int = 6
    WINDOW_BORDER_RADIUS: int = 14

    def as_qss_tokens(self) -> dict[str, str]:
        return {
            "SIDEBAR_WIDTH": str(self.SIDEBAR_WIDTH),
            "TITLEBAR_HEIGHT": str(self.TITLEBAR_HEIGHT),
            "RADIUS": str(self.BORDER_RADIUS),
            "RADIUS_SMALL": str(self.BORDER_RADIUS_SMALL),
            "WINDOW_RADIUS": str(self.WINDOW_BORDER_RADIUS),
        }
