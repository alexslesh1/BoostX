from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field


class VerifyEmailPage(AuthFormPage):
    verified = Signal()
    back_to_login_requested = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        self._email = ""
        super().__init__(
            title="Verify your email",
            subtitle="Enter the 6-digit code we sent to your email address.",
            parent=parent,
        )

    def set_email(self, email: str) -> None:
        self._email = email
        self._code_field.clear()
        self.clear_messages()

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._code_field = add_field(layout, self, "Verification code")
        self._code_field.setMaxLength(6)

        self._submit_button = QPushButton("Verify", self)
        self._submit_button.setObjectName("AuthPrimaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_button)

        resend_button = QPushButton("Resend code", self)
        resend_button.setObjectName("AuthLinkButton")
        resend_button.clicked.connect(self._on_resend)
        layout.addWidget(resend_button)

        back_button = QPushButton("Back to login", self)
        back_button.setObjectName("AuthLinkButton")
        back_button.clicked.connect(self.back_to_login_requested.emit)
        layout.addWidget(back_button)

    def _on_submit(self) -> None:
        code = self._code_field.text().strip()
        if not code:
            self.show_error("Enter the verification code.")
            return
        self.clear_messages()
        self._submit_button.setEnabled(False)
        self._session_manager.verify_email(self._email, code, self._on_success, self._on_error)

    def _on_success(self) -> None:
        self._submit_button.setEnabled(True)
        self.verified.emit()

    def _on_resend(self) -> None:
        self.clear_messages()
        self._session_manager.resend_verification(
            self._email, lambda: self.show_status("A new code has been sent."), self._on_error
        )

    def _on_error(self, error: ApiError) -> None:
        self._submit_button.setEnabled(True)
        self.show_error(error.detail or str(error))
