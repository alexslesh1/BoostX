from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from boostx.core.services.tweaks.tweaks_service import TweaksService
from boostx.ui.components.tweaks.tweak_flow_screen import TweakFlowScreen
from boostx.ui.components.tweaks.tweak_provider_card import TweakProviderCard
from boostx.ui.controllers.tweaks_controller import TweaksController
from boostx.ui.navigation.fade_stacked_widget import FadeStackedWidget
from boostx.ui.pages.base_page import BasePage

_HOME_INDEX = 0
_FLOW_INDEX = 1


class TweaksPage(BasePage):
    def __init__(self, parent: QWidget | None = None) -> None:
        self._tweaks_service = TweaksService()

        super().__init__(
            title="Tweaks",
            subtitle="Safe hardware optimizations for your CPU and GPU",
            parent=parent,
        )

        # TweaksController is a QObject parented to self, so it can only be
        # constructed after QWidget.__init__ has run (i.e. after super().__init__()).
        self._controller = TweaksController(self)
        self._flow_screen = TweakFlowScreen(self._controller, self._stack)
        self._flow_screen.back_requested.connect(self._on_back_requested)
        self._stack.addWidget(self._flow_screen)

    def _build_body(self, layout: QVBoxLayout) -> None:
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(12)

        title = QLabel("Hardware Tweaks", content)
        title.setObjectName("CleanerSectionTitle")
        content_layout.addWidget(title)

        for provider in self._tweaks_service.providers():
            card = TweakProviderCard(provider, content)
            card.clicked.connect(self._on_provider_clicked)
            content_layout.addWidget(card)
        content_layout.addStretch(1)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(content)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        self._stack = FadeStackedWidget(self)
        self._stack.addWidget(scroll_area)

        layout.addWidget(self._stack, stretch=1)

    def _on_provider_clicked(self, provider_key: str) -> None:
        provider = self._tweaks_service.get(provider_key)
        if provider is None:
            return
        self._flow_screen.start(provider)
        self._stack.setCurrentIndex(_FLOW_INDEX)

    def _on_back_requested(self) -> None:
        self._stack.setCurrentIndex(_HOME_INDEX)

    def shutdown(self) -> None:
        self._controller.shutdown()
