from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field

_MIN_PASSWORD_LENGTH = 8


class RegisterPage(AuthFormPage):
    registered = Signal(str)
    login_requested = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        super().__init__(
            title="Create your account",
            subtitle="Sign up to sync your BoostX settings and subscription",
            parent=parent,
        )

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._username_field = add_field(layout, self, "Username")
        self._email_field = add_field(layout, self, "Email")
        self._password_field = add_field(layout, self, "Password", is_password=True)

        self._submit_button = QPushButton("Create Account", self)
        self._submit_button.setObjectName("AuthPrimaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_button)

        login_button = QPushButton("Already have an account? Log in", self)
        login_button.setObjectName("AuthLinkButton")
        login_button.clicked.connect(self.login_requested.emit)
        layout.addWidget(login_button)

    def _on_submit(self) -> None:
        username = self._username_field.text().strip()
        email = self._email_field.text().strip()
        password = self._password_field.text()
        if not username or not email or not password:
            self.show_error("Fill in all fields.")
            return
        if len(password) < _MIN_PASSWORD_LENGTH:
            self.show_error(f"Password must be at least {_MIN_PASSWORD_LENGTH} characters.")
            return
        self.clear_messages()
        self._submit_button.setEnabled(False)
        self._session_manager.register(username, email, password, lambda: self._on_success(email), self._on_error)

    def _on_success(self, email: str) -> None:
        self._submit_button.setEnabled(True)
        self.registered.emit(email)

    def _on_error(self, error: ApiError) -> None:
        self._submit_button.setEnabled(True)
        self.show_error(error.detail or str(error))
