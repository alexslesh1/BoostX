from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.models import DeviceRecord
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.components.card import Card
from boostx.ui.components.monogram import render_monogram_pixmap
from boostx.ui.components.status_chip import StatusChip
from boostx.ui.pages.base_page import BasePage

_AVATAR_SIZE = QSize(56, 56)
_PLAN_LABELS = {"free": "Free", "pro": "Pro", "lifetime": "Lifetime"}


class AccountPage(BasePage):
    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        super().__init__(title="Account", subtitle="Manage your Nexora account", parent=parent)
        self._session_manager.auth_state_changed.connect(self._refresh_profile)
        self._refresh_profile()
        self._refresh_devices()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_devices()

    def _build_body(self, layout: QVBoxLayout) -> None:
        layout.addWidget(self._build_profile_card())
        layout.addSpacing(16)
        layout.addWidget(self._build_subscription_card())
        layout.addSpacing(16)
        layout.addWidget(self._build_devices_card())
        layout.addSpacing(16)
        layout.addWidget(self._build_security_card())
        layout.addStretch(1)

    # -- profile ------------------------------------------------------------
    def _build_profile_card(self) -> Card:
        card = Card(self)
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 18, 20, 18)
        row.setSpacing(16)

        self._avatar_label = QLabel(card)
        self._avatar_label.setFixedSize(_AVATAR_SIZE)
        row.addWidget(self._avatar_label)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        self._username_label = QLabel(card)
        self._username_label.setObjectName("StatCardValue")
        self._email_label = QLabel(card)
        self._email_label.setObjectName("CardPlaceholderLabel")
        text_layout.addWidget(self._username_label)
        text_layout.addWidget(self._email_label)
        row.addLayout(text_layout, stretch=1)

        self._verified_chip = StatusChip("", "neutral", card)
        row.addWidget(self._verified_chip, alignment=Qt.AlignmentFlag.AlignTop)

        logout_button = QPushButton("Log Out", card)
        logout_button.clicked.connect(self._on_logout)
        row.addWidget(logout_button, alignment=Qt.AlignmentFlag.AlignTop)

        return card

    def _refresh_profile(self) -> None:
        user = self._session_manager.current_user
        if user is None:
            return
        self._username_label.setText(user.username)
        self._email_label.setText(user.email)
        self._avatar_label.setPixmap(render_monogram_pixmap(user.username, user.id, _AVATAR_SIZE))
        if user.email_verified:
            self._verified_chip.setText("Verified")
            self._verified_chip.set_severity("success")
        else:
            self._verified_chip.setText("Not verified")
            self._verified_chip.set_severity("warning")
        self._refresh_subscription()

    def _on_logout(self) -> None:
        self._session_manager.logout(lambda: None)

    # -- subscription -------------------------------------------------------
    def _build_subscription_card(self) -> Card:
        card = Card(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(6)

        title = QLabel("Subscription", card)
        title.setObjectName("StatCardTitle")
        layout.addWidget(title)

        row = QHBoxLayout()
        self._plan_chip = StatusChip("Free", "neutral", card)
        row.addWidget(self._plan_chip)
        self._subscription_detail_label = QLabel("", card)
        self._subscription_detail_label.setObjectName("CardPlaceholderLabel")
        row.addWidget(self._subscription_detail_label, stretch=1)

        upgrade_button = QPushButton("Upgrade (coming soon)", card)
        upgrade_button.setEnabled(False)
        row.addWidget(upgrade_button)

        layout.addLayout(row)
        self._subscription_card = card
        return card

    def _refresh_subscription(self) -> None:
        subscription = self._session_manager.current_subscription
        if subscription is None:
            return
        plan_label = _PLAN_LABELS.get(subscription.plan, subscription.plan.title())
        self._plan_chip.setText(plan_label)
        self._plan_chip.set_severity("success" if subscription.status == "active" else "neutral")
        if subscription.current_period_end:
            self._subscription_detail_label.setText(f"Renews / expires {subscription.current_period_end}")
        else:
            self._subscription_detail_label.setText(f"Status: {subscription.status}")

    # -- devices --------------------------------------------------------------
    def _build_devices_card(self) -> Card:
        card = Card(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(8)

        title = QLabel("Devices", card)
        title.setObjectName("StatCardTitle")
        layout.addWidget(title)

        self._devices_layout = QVBoxLayout()
        self._devices_layout.setSpacing(6)
        layout.addLayout(self._devices_layout)

        self._devices_empty_label = QLabel("No devices registered yet.", card)
        self._devices_empty_label.setObjectName("CardPlaceholderLabel")
        layout.addWidget(self._devices_empty_label)

        self._devices_card = card
        return card

    def _refresh_devices(self) -> None:
        if not self._session_manager.is_authenticated or self._session_manager.is_offline:
            return
        self._session_manager.refresh_devices(self._on_devices_loaded, lambda _err: None)

    def _on_devices_loaded(self, devices: list[DeviceRecord]) -> None:
        while self._devices_layout.count():
            item = self._devices_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._devices_empty_label.setVisible(not devices)
        for device in devices:
            self._devices_layout.addWidget(self._build_device_row(device))

    def _build_device_row(self, device: DeviceRecord) -> QWidget:
        row = QWidget(self._devices_card)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)
        name_label = QLabel(device.device_name, row)
        name_label.setObjectName("ConnectionRowName")
        detail_label = QLabel(f"{device.os} • last seen {device.last_seen}", row)
        detail_label.setObjectName("ConnectionRowDetail")
        text_layout.addWidget(name_label)
        text_layout.addWidget(detail_label)
        row_layout.addLayout(text_layout, stretch=1)

        remove_button = QPushButton("Remove", row)
        remove_button.clicked.connect(lambda: self._on_remove_device(device.device_id))
        row_layout.addWidget(remove_button)
        return row

    def _on_remove_device(self, device_id: str) -> None:
        self._session_manager.remove_device(device_id, self._refresh_devices, lambda _err: None)

    # -- security -----------------------------------------------------------
    def _build_security_card(self) -> Card:
        card = Card(self)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title = QLabel("Security", card)
        title.setObjectName("StatCardTitle")
        layout.addWidget(title)

        toggle_row = QHBoxLayout()
        change_password_toggle = QPushButton("Change Password", card)
        change_password_toggle.clicked.connect(lambda: self._security_stack.setCurrentIndex(0))
        change_email_toggle = QPushButton("Change Email", card)
        change_email_toggle.clicked.connect(lambda: self._security_stack.setCurrentIndex(1))
        toggle_row.addWidget(change_password_toggle)
        toggle_row.addWidget(change_email_toggle)
        toggle_row.addStretch(1)
        layout.addLayout(toggle_row)

        self._security_stack = QStackedLayout()
        self._security_stack.addWidget(self._build_change_password_form(card))
        self._security_stack.addWidget(self._build_change_email_form(card))
        layout.addLayout(self._security_stack)

        self._security_message_label = QLabel("", card)
        self._security_message_label.setObjectName("AuthErrorLabel")
        self._security_message_label.setWordWrap(True)
        self._security_message_label.hide()
        layout.addWidget(self._security_message_label)

        return card

    def _build_change_password_form(self, parent: QWidget) -> QWidget:
        form = QWidget(parent)
        form_layout = QHBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)

        self._current_password_field = QLineEdit(form)
        self._current_password_field.setPlaceholderText("Current password")
        self._current_password_field.setEchoMode(QLineEdit.EchoMode.Password)

        self._new_password_field = QLineEdit(form)
        self._new_password_field.setPlaceholderText("New password")
        self._new_password_field.setEchoMode(QLineEdit.EchoMode.Password)

        submit_button = QPushButton("Update", form)
        submit_button.clicked.connect(self._on_change_password)

        form_layout.addWidget(self._current_password_field)
        form_layout.addWidget(self._new_password_field)
        form_layout.addWidget(submit_button)
        return form

    def _on_change_password(self) -> None:
        self._security_message_label.hide()
        current = self._current_password_field.text()
        new = self._new_password_field.text()
        if not current or not new:
            self._show_security_message("Enter your current and new password.")
            return
        self._session_manager.change_password(
            current,
            new,
            lambda: self._on_security_success("Password updated."),
            self._on_security_error,
        )

    def _build_change_email_form(self, parent: QWidget) -> QWidget:
        form = QWidget(parent)
        form_layout = QHBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)

        self._new_email_field = QLineEdit(form)
        self._new_email_field.setPlaceholderText("New email")
        request_button = QPushButton("Send Code", form)
        request_button.clicked.connect(self._on_request_email_change)

        self._email_change_code_field = QLineEdit(form)
        self._email_change_code_field.setPlaceholderText("Confirmation code")
        self._email_change_code_field.setMaxLength(6)
        confirm_button = QPushButton("Confirm", form)
        confirm_button.clicked.connect(self._on_confirm_email_change)

        form_layout.addWidget(self._new_email_field)
        form_layout.addWidget(request_button)
        form_layout.addWidget(self._email_change_code_field)
        form_layout.addWidget(confirm_button)
        return form

    def _on_request_email_change(self) -> None:
        self._security_message_label.hide()
        new_email = self._new_email_field.text().strip()
        if not new_email:
            self._show_security_message("Enter a new email address.")
            return
        self._session_manager.request_email_change(
            new_email,
            lambda: self._on_security_success("Confirmation code sent to the new address."),
            self._on_security_error,
        )

    def _on_confirm_email_change(self) -> None:
        self._security_message_label.hide()
        code = self._email_change_code_field.text().strip()
        if not code:
            self._show_security_message("Enter the confirmation code.")
            return
        self._session_manager.confirm_email_change(
            code, lambda: self._on_security_success("Email updated."), self._on_security_error
        )

    def _on_security_success(self, message: str) -> None:
        self._current_password_field.clear()
        self._new_password_field.clear()
        self._email_change_code_field.clear()
        self._show_security_message(message)

    def _on_security_error(self, error: ApiError) -> None:
        self._show_security_message(error.detail or str(error))

    def _show_security_message(self, message: str) -> None:
        self._security_message_label.setText(message)
        self._security_message_label.show()
