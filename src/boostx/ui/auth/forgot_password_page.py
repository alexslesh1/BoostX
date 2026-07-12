from typing import Callable

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QStackedLayout, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field

_STEP_REQUEST = 0
_STEP_CONFIRM = 1
_MIN_PASSWORD_LENGTH = 8


class ForgotPasswordPage(AuthFormPage):
    reset_completed = Signal()
    back_to_login_requested = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        self._email = ""
        super().__init__(
            title="Reset your password",
            subtitle="We'll email you a 6-digit code to reset your password.",
            parent=parent,
        )

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._steps = QStackedLayout()
        self._steps.addWidget(self._build_request_step())
        self._steps.addWidget(self._build_confirm_step())
        layout.addLayout(self._steps)

        back_button = QPushButton("Back to login", self)
        back_button.setObjectName("AuthLinkButton")
        back_button.clicked.connect(self.back_to_login_requested.emit)
        layout.addWidget(back_button)

    def _build_request_step(self) -> QWidget:
        step = QWidget(self)
        step_layout = QVBoxLayout(step)
        step_layout.setContentsMargins(0, 0, 0, 0)
        self._email_field = add_field(step_layout, step, "Email")

        self._send_button = QPushButton("Send Code", step)
        self._send_button.setObjectName("AuthPrimaryButton")
        self._send_button.clicked.connect(self._on_request)
        step_layout.addWidget(self._send_button)
        return step

    def _build_confirm_step(self) -> QWidget:
        step = QWidget(self)
        step_layout = QVBoxLayout(step)
        step_layout.setContentsMargins(0, 0, 0, 0)
        self._code_field = add_field(step_layout, step, "Verification code")
        self._new_password_field = add_field(step_layout, step, "New password", is_password=True)

        self._confirm_button = QPushButton("Reset Password", step)
        self._confirm_button.setObjectName("AuthPrimaryButton")
        self._confirm_button.clicked.connect(self._on_confirm)
        step_layout.addWidget(self._confirm_button)
        return step

    def _on_request(self) -> None:
        email = self._email_field.text().strip()
        if not email:
            self.show_error("Enter your email.")
            return
        self._email = email
        self.clear_messages()
        self._send_button.setEnabled(False)
        self._session_manager.request_password_reset(
            email, self._on_request_success, self._error_handler(self._send_button)
        )

    def _on_request_success(self) -> None:
        self._send_button.setEnabled(True)
        self._steps.setCurrentIndex(_STEP_CONFIRM)
        self.show_status("Check your email for the reset code.")

    def _on_confirm(self) -> None:
        code = self._code_field.text().strip()
        new_password = self._new_password_field.text()
        if not code or not new_password:
            self.show_error("Enter the code and a new password.")
            return
        if len(new_password) < _MIN_PASSWORD_LENGTH:
            self.show_error(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.")
            return
        self.clear_messages()
        self._confirm_button.setEnabled(False)
        self._session_manager.confirm_password_reset(
            self._email, code, new_password, self._on_confirm_success, self._error_handler(self._confirm_button)
        )

    def _on_confirm_success(self) -> None:
        self._confirm_button.setEnabled(True)
        self.reset_completed.emit()

    def _error_handler(self, button: QPushButton) -> Callable[[ApiError], None]:
        def _handle(error: ApiError) -> None:
            button.setEnabled(True)
            self.show_error(error.detail or str(error))

        return _handle
