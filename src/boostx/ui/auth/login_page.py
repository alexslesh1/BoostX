from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field


class LoginPage(AuthFormPage):
    login_succeeded = Signal()
    register_requested = Signal()
    forgot_password_requested = Signal()
    verification_required = Signal(str)

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        super().__init__(title="Welcome back", subtitle="Log in to your BoostX account", parent=parent)

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._email_field = add_field(layout, self, "Email")
        self._password_field = add_field(layout, self, "Password", is_password=True)

        self._remember_checkbox = QCheckBox("Remember me", self)
        layout.addWidget(self._remember_checkbox)

        self._submit_button = QPushButton("Log In", self)
        self._submit_button.setObjectName("AuthPrimaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_button)

        forgot_button = QPushButton("Forgot password?", self)
        forgot_button.setObjectName("AuthLinkButton")
        forgot_button.clicked.connect(self.forgot_password_requested.emit)
        layout.addWidget(forgot_button)

        register_button = QPushButton("Don't have an account? Create one", self)
        register_button.setObjectName("AuthLinkButton")
        register_button.clicked.connect(self.register_requested.emit)
        layout.addWidget(register_button)

    def _on_submit(self) -> None:
        email = self._email_field.text().strip()
        password = self._password_field.text()
        if not email or not password:
            self.show_error("Enter your email and password.")
            return
        self.clear_messages()
        self._submit_button.setEnabled(False)
        self._session_manager.login(
            email, password, self._remember_checkbox.isChecked(), self._on_success, self._on_error
        )

    def _on_success(self) -> None:
        self._submit_button.setEnabled(True)
        user = self._session_manager.current_user
        if user is not None and not user.email_verified:
            self.verification_required.emit(user.email)
            return
        self.login_succeeded.emit()

    def _on_error(self, error: ApiError) -> None:
        self._submit_button.setEnabled(True)
        self.show_error(error.detail or str(error))
