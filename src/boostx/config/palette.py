from dataclasses import dataclass


@dataclass(frozen=True)
class Palette:
    BACKGROUND: str = "#101010"
    SIDEBAR: str = "#171717"
    CARD: str = "#1E1E1E"
    HOVER: str = "#262626"
    BORDER: str = "#2F2F2F"
    PRIMARY: str = "#D32F2F"
    PRIMARY_HOVER: str = "#F44336"
    TEXT: str = "#FFFFFF"
    TEXT_SECONDARY: str = "#B3B3B3"
    SUCCESS: str = "#4CAF50"
    WARNING: str = "#FFC107"
    ERROR: str = "#E53935"
    SUCCESS_BG: str = "rgba(76, 175, 80, 0.15)"
    WARNING_BG: str = "rgba(255, 193, 7, 0.15)"
    ERROR_BG: str = "rgba(229, 57, 53, 0.15)"
    CHART_SERIES_A: str = "#3987E5"
    CHART_SERIES_B: str = "#9085E9"

    def as_qss_tokens(self) -> dict[str, str]:
        return {
            "BACKGROUND": self.BACKGROUND,
            "SIDEBAR": self.SIDEBAR,
            "CARD": self.CARD,
            "HOVER": self.HOVER,
            "BORDER": self.BORDER,
            "PRIMARY": self.PRIMARY,
            "PRIMARY_HOVER": self.PRIMARY_HOVER,
            "TEXT": self.TEXT,
            "TEXT_SECONDARY": self.TEXT_SECONDARY,
            "SUCCESS": self.SUCCESS,
            "WARNING": self.WARNING,
            "ERROR": self.ERROR,
            "SUCCESS_BG": self.SUCCESS_BG,
            "WARNING_BG": self.WARNING_BG,
            "ERROR_BG": self.ERROR_BG,
        }
