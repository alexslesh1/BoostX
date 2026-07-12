from string import Template

from boostx.config.layout import LayoutConstants
from boostx.config.palette import Palette
from boostx.config.paths import AppPaths
from boostx.config.typography import Typography


class ThemeLoader:
    def __init__(
        self,
        palette: Palette | None = None,
        typography: Typography | None = None,
        layout: LayoutConstants | None = None,
    ) -> None:
        self._palette = palette or Palette()
        self._typography = typography or Typography()
        self._layout = layout or LayoutConstants()

    def load(self) -> str:
        template_path = AppPaths.styles_dir() / "theme.qss.tmpl"
        template_text = template_path.read_text(encoding="utf-8")
        tokens: dict[str, str] = {
            **self._palette.as_qss_tokens(),
            **self._typography.as_qss_tokens(),
            **self._layout.as_qss_tokens(),
        }
        return Template(template_text).substitute(**tokens)
