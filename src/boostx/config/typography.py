from dataclasses import dataclass


@dataclass(frozen=True)
class Typography:
    FONT_FAMILY: str = "Inter"
    FONT_FAMILY_FALLBACK: str = "Segoe UI Variable"
    SIZE_DISPLAY: int = 32
    SIZE_HEADING: int = 24
    SIZE_SUBHEADING: int = 18
    SIZE_BODY: int = 14
    SIZE_SMALL: int = 12

    def font_family_stack(self) -> str:
        return f'"{self.FONT_FAMILY}", "{self.FONT_FAMILY_FALLBACK}", sans-serif'

    def as_qss_tokens(self) -> dict[str, str]:
        return {
            "FONT_FAMILY": self.font_family_stack(),
            "SIZE_DISPLAY": str(self.SIZE_DISPLAY),
            "SIZE_HEADING": str(self.SIZE_HEADING),
            "SIZE_SUBHEADING": str(self.SIZE_SUBHEADING),
            "SIZE_BODY": str(self.SIZE_BODY),
            "SIZE_SMALL": str(self.SIZE_SMALL),
        }
