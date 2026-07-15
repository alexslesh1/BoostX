from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from boostx.i18n import i18n
from boostx.ui.components.language_switcher import LanguageSwitcher

_FEATURE_KEYS = ("marketing.feature_system", "marketing.feature_network", "marketing.feature_router")


class _FeatureRow(QWidget):
    def __init__(self, key: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._key = key
        self.setObjectName("MarketingFeatureRow")

        bullet = QLabel("●", self)
        bullet.setObjectName("MarketingFeatureBullet")
        self._label = QLabel(self)
        self._label.setObjectName("MarketingFeatureLabel")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 12, 0, 12)
        layout.setSpacing(12)
        layout.addWidget(bullet)
        layout.addWidget(self._label, stretch=1)

        self.retranslate()

    def retranslate(self) -> None:
        self._label.setText(i18n.tr(self._key))


class MarketingPanel(QWidget):
    """The left-hand marketing column of the auth screen (logo-less
    headline + feature list), persistent across the loading/login/register
    states so its language switcher is always reachable, as requested."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MarketingPanel")

        self._switcher = LanguageSwitcher(self)

        self._headline = QLabel(self)
        self._headline.setObjectName("MarketingHeadline")
        self._headline.setTextFormat(Qt.TextFormat.RichText)

        self._subtitle = QLabel(self)
        self._subtitle.setObjectName("MarketingSubtitle")
        self._subtitle.setWordWrap(True)

        self._feature_rows = [_FeatureRow(key, self) for key in _FEATURE_KEYS]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(56, 40, 40, 40)
        layout.addWidget(self._switcher, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        layout.addWidget(self._headline)
        layout.addSpacing(16)
        layout.addWidget(self._subtitle)
        layout.addSpacing(28)
        for index, row in enumerate(self._feature_rows):
            layout.addWidget(row)
            if index < len(self._feature_rows) - 1:
                divider = QFrame(self)
                divider.setObjectName("MarketingDivider")
                divider.setFrameShape(QFrame.Shape.HLine)
                layout.addWidget(divider)
        layout.addStretch(2)

        i18n.language_changed.connect(self.retranslate)
        self.retranslate()

    def retranslate(self, *_args: object) -> None:
        self._headline.setText(
            f'<span style="color:#FFFFFF;">{i18n.tr("marketing.headline_top")}</span><br>'
            f'<span style="color:#E03131;">{i18n.tr("marketing.headline_mid")}</span> '
            f'<span style="color:#FFFFFF;">{i18n.tr("marketing.headline_bottom")}</span>'
        )
        self._subtitle.setText(i18n.tr("marketing.subtitle"))
        for row in self._feature_rows:
            row.retranslate()
