from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from boostx.core.services.tweaks.models import DependencyStatus, DeviceOption, TweakRunResult
from boostx.core.services.tweaks.provider import TweakProviderHandler
from boostx.ui.components.card import Card
from boostx.ui.components.progress_bar import ProgressBar
from boostx.ui.components.tweaks.device_option_card import DeviceOptionCard
from boostx.ui.controllers.tweaks_controller import TweaksController

_STEP_LOADING = 0
_STEP_DEPENDENCY_MISSING = 1
_STEP_DEVICE_LIST = 2
_STEP_CONFIRM = 3
_STEP_PROGRESS = 4
_STEP_RESULT = 5
_STEP_COMING_SOON = 6


class TweakFlowScreen(QWidget):
    """The equivalent of BoostScreen for the Tweaks module: one reusable
    screen that walks through dependency check -> device selection ->
    confirmation -> progress -> result for whichever provider start() was
    called with."""

    back_requested = Signal()

    def __init__(self, controller: TweaksController, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._provider: TweakProviderHandler | None = None
        self._selected_device: DeviceOption | None = None
        self._dependency_download_url: str | None = None
        self._log_visible = False

        self._back_button = QPushButton("← Back", self)
        self._back_button.setObjectName("BoostScreenBackButton")
        self._back_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_button.clicked.connect(self.back_requested.emit)
        back_row = QHBoxLayout()
        back_row.addWidget(self._back_button)
        back_row.addStretch(1)

        self._title_label = QLabel("", self)
        self._title_label.setObjectName("PageHeading")
        self._subtitle_label = QLabel("", self)
        self._subtitle_label.setObjectName("PageSubtitle")

        self._steps = QStackedLayout()
        self._steps.addWidget(self._build_loading_step())
        self._steps.addWidget(self._build_dependency_missing_step())
        self._steps.addWidget(self._build_device_list_step())
        self._steps.addWidget(self._build_confirm_step())
        self._steps.addWidget(self._build_progress_step())
        self._steps.addWidget(self._build_result_step())
        self._steps.addWidget(self._build_coming_soon_step())

        card = Card(self)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(28, 24, 28, 24)
        card_layout.addLayout(self._steps)

        scroll_area = QScrollArea(self)
        scroll_area.setWidget(card)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)

        outer_layout = QVBoxLayout(self)
        outer_layout.setSpacing(12)
        outer_layout.addLayout(back_row)
        outer_layout.addWidget(self._title_label)
        outer_layout.addWidget(self._subtitle_label)
        outer_layout.addSpacing(4)
        outer_layout.addWidget(scroll_area, stretch=1)

        self._controller.dependency_checked.connect(self._on_dependency_checked)
        self._controller.devices_ready.connect(self._on_devices_ready)
        self._controller.tweak_finished.connect(self._on_tweak_finished)

    # -- entry point ------------------------------------------------------
    def start(self, provider: TweakProviderHandler) -> None:
        self._provider = provider
        self._selected_device = None
        self._back_button.setEnabled(True)
        self._title_label.setText(provider.title)
        self._subtitle_label.setText(provider.description)

        if provider.coming_soon:
            self._steps.setCurrentIndex(_STEP_COMING_SOON)
            return

        self._loading_label.setText("Checking requirements...")
        self._steps.setCurrentIndex(_STEP_LOADING)
        self._controller.check_dependency(provider.key)

    # -- step builders ------------------------------------------------------
    def _build_loading_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        self._loading_label = QLabel("Checking requirements...", step)
        self._loading_label.setObjectName("CardPlaceholderLabel")
        self._loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(self._loading_label)
        layout.addStretch(1)
        return step

    def _build_dependency_missing_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setSpacing(10)

        self._dependency_message_label = QLabel("", step)
        self._dependency_message_label.setObjectName("MetricCardValue")
        self._dependency_message_label.setWordWrap(True)
        self._dependency_message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._dependency_download_button = QPushButton("Download", step)
        self._dependency_download_button.setObjectName("CleanerPrimaryButton")
        self._dependency_download_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._dependency_download_button.clicked.connect(self._on_download_clicked)

        layout.addStretch(1)
        layout.addWidget(self._dependency_message_label)
        layout.addSpacing(10)
        layout.addWidget(self._dependency_download_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return step

    def _build_device_list_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setSpacing(10)

        title = QLabel("Select your device", step)
        title.setObjectName("CleanerSectionTitle")
        layout.addWidget(title)

        self._device_list_layout = QVBoxLayout()
        self._device_list_layout.setSpacing(8)
        layout.addLayout(self._device_list_layout)
        layout.addStretch(1)
        return step

    def _build_confirm_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setSpacing(10)

        title = QLabel("Selected Device", step)
        title.setObjectName("MetricCardLabel")
        self._confirm_device_label = QLabel("", step)
        self._confirm_device_label.setObjectName("PageHeading")

        apply_button = QPushButton("Apply Safe Tweak", step)
        apply_button.setObjectName("CleanerPrimaryButton")
        apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        apply_button.clicked.connect(self._on_apply_clicked)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(self._confirm_device_label)
        layout.addSpacing(16)
        layout.addWidget(apply_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch(1)
        return step

    def _build_progress_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setSpacing(12)

        title = QLabel("Applying Hardware Tweak...", step)
        title.setObjectName("CleanerSectionTitle")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._progress_bar = ProgressBar(step)
        self._progress_bar.setRange(0, 0)

        please_wait = QLabel("Please wait...", step)
        please_wait.setObjectName("CardPlaceholderLabel")
        please_wait.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addStretch(1)
        layout.addWidget(title)
        layout.addWidget(self._progress_bar)
        layout.addWidget(please_wait)
        layout.addStretch(1)
        return step

    def _build_result_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        layout.setSpacing(10)

        self._result_title_label = QLabel("", step)
        self._result_title_label.setObjectName("TweakResultTitle")

        self._result_message_label = QLabel("", step)
        self._result_message_label.setObjectName("CardPlaceholderLabel")
        self._result_message_label.setWordWrap(True)

        self._result_log_view = QPlainTextEdit(step)
        self._result_log_view.setObjectName("TweakLogView")
        self._result_log_view.setReadOnly(True)
        self._result_log_view.setFixedHeight(160)
        self._result_log_view.hide()

        self._view_log_button = QPushButton("View Log", step)
        self._view_log_button.setObjectName("TweakSecondaryButton")
        self._view_log_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view_log_button.clicked.connect(self._on_toggle_log)
        self._view_log_button.hide()

        self._try_again_button = QPushButton("Try Again", step)
        self._try_again_button.setObjectName("CleanerPrimaryButton")
        self._try_again_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._try_again_button.clicked.connect(self._on_try_again)
        self._try_again_button.hide()

        self._restart_later_button = QPushButton("Restart Later", step)
        self._restart_later_button.setObjectName("TweakSecondaryButton")
        self._restart_later_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restart_later_button.clicked.connect(self.back_requested.emit)
        self._restart_later_button.hide()

        self._restart_now_button = QPushButton("Restart Now", step)
        self._restart_now_button.setObjectName("CleanerPrimaryButton")
        self._restart_now_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._restart_now_button.clicked.connect(self.back_requested.emit)
        self._restart_now_button.hide()

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        button_row.addWidget(self._view_log_button)
        button_row.addWidget(self._try_again_button)
        button_row.addWidget(self._restart_later_button)
        button_row.addWidget(self._restart_now_button)
        button_row.addStretch(1)

        layout.addWidget(self._result_title_label)
        layout.addWidget(self._result_message_label)
        layout.addSpacing(6)
        layout.addLayout(button_row)
        layout.addWidget(self._result_log_view)
        layout.addStretch(1)
        return step

    def _build_coming_soon_step(self) -> QWidget:
        step = QWidget(self)
        layout = QVBoxLayout(step)
        label = QLabel("Coming Soon", step)
        label.setObjectName("HealthPercentLabel")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        layout.addWidget(label)
        layout.addStretch(1)
        return step

    # -- dependency ---------------------------------------------------------
    def _on_dependency_checked(self, provider_key: str, status: DependencyStatus) -> None:
        if self._provider is None or provider_key != self._provider.key:
            return
        if not status.available:
            self._dependency_message_label.setText(status.message)
            self._dependency_download_button.setVisible(status.download_url is not None)
            self._dependency_download_url = status.download_url
            self._steps.setCurrentIndex(_STEP_DEPENDENCY_MISSING)
            return

        if not self._provider.requires_device_selection:
            self._show_confirm(None)
            return

        self._loading_label.setText("Detecting hardware...")
        self._steps.setCurrentIndex(_STEP_LOADING)
        self._controller.load_devices(provider_key)

    def _on_download_clicked(self) -> None:
        if self._dependency_download_url:
            QDesktopServices.openUrl(QUrl(self._dependency_download_url))

    # -- device selection ---------------------------------------------------
    def _on_devices_ready(self, provider_key: str, devices: list[DeviceOption]) -> None:
        if self._provider is None or provider_key != self._provider.key:
            return

        if not devices:
            self._dependency_message_label.setText("No supported hardware was detected on this system.")
            self._dependency_download_button.hide()
            self._steps.setCurrentIndex(_STEP_DEPENDENCY_MISSING)
            return

        if len(devices) == 1:
            self._show_confirm(devices[0])
            return

        while self._device_list_layout.count():
            item = self._device_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for device in devices:
            card = DeviceOptionCard(device, self._device_list_layout.parentWidget())
            card.clicked.connect(lambda key, options=devices: self._on_device_selected(key, options))
            self._device_list_layout.addWidget(card)

        self._steps.setCurrentIndex(_STEP_DEVICE_LIST)

    def _on_device_selected(self, key: str, options: list[DeviceOption]) -> None:
        device = next((option for option in options if option.key == key), None)
        if device is not None:
            self._show_confirm(device)

    def _show_confirm(self, device: DeviceOption | None) -> None:
        self._selected_device = device
        self._confirm_device_label.setText(device.label if device is not None else "All detected hardware")
        self._steps.setCurrentIndex(_STEP_CONFIRM)

    # -- apply ---------------------------------------------------------------
    def _on_apply_clicked(self) -> None:
        if self._provider is None:
            return
        self._back_button.setEnabled(False)
        self._steps.setCurrentIndex(_STEP_PROGRESS)
        device_key = self._selected_device.key if self._selected_device is not None else None
        self._controller.apply_tweak(self._provider.key, device_key)

    def _on_tweak_finished(self, provider_key: str, result: TweakRunResult) -> None:
        if self._provider is None or provider_key != self._provider.key:
            return

        self._back_button.setEnabled(True)
        self._log_visible = False
        self._result_log_view.setPlainText(result.output)
        self._result_log_view.hide()
        self._view_log_button.setText("View Log")

        if result.success:
            self._result_title_label.setText("✓ Tweak Applied Successfully")
            self._result_title_label.setProperty("severity", "success")
            self._result_message_label.setText(
                "Your hardware optimization has been completed. A system restart may be recommended."
            )
            self._view_log_button.hide()
            self._try_again_button.hide()
            self._restart_later_button.show()
            self._restart_now_button.show()
        else:
            self._result_title_label.setText("Tweak Failed")
            self._result_title_label.setProperty("severity", "error")
            self._result_message_label.setText(
                "The optimization could not be completed. Please verify that:\n"
                "• Administrator privileges are enabled\n"
                "• Required software is installed\n"
                "• Your hardware is supported"
            )
            self._view_log_button.show()
            self._try_again_button.show()
            self._restart_later_button.hide()
            self._restart_now_button.hide()

        style = self._result_title_label.style()
        style.unpolish(self._result_title_label)
        style.polish(self._result_title_label)

        self._steps.setCurrentIndex(_STEP_RESULT)

    def _on_toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        self._result_log_view.setVisible(self._log_visible)
        self._view_log_button.setText("Hide Log" if self._log_visible else "View Log")

    def _on_try_again(self) -> None:
        if self._provider is not None:
            self.start(self._provider)
