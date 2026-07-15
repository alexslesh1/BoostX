from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QPushButton, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.i18n import i18n
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field


class LoginPage(AuthFormPage):
    login_succeeded = Signal()
    register_requested = Signal()
    forgot_password_requested = Signal()
    verification_required = Signal(str)

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        super().__init__(
            title=i18n.tr("auth.welcome_back"), subtitle=i18n.tr("auth.login_subtitle"), parent=parent
        )
        i18n.language_changed.connect(self._retranslate)

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._email_field = add_field(layout, self, i18n.tr("auth.email"))
        self._password_field = add_field(layout, self, i18n.tr("auth.password"), is_password=True)

        self._remember_checkbox = QCheckBox(i18n.tr("auth.remember_me"), self)
        layout.addWidget(self._remember_checkbox)

        self._submit_button = QPushButton(i18n.tr("auth.log_in"), self)
        self._submit_button.setObjectName("AuthPrimaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_button)

        self._forgot_button = QPushButton(i18n.tr("auth.forgot_password"), self)
        self._forgot_button.setObjectName("AuthLinkButton")
        self._forgot_button.clicked.connect(self.forgot_password_requested.emit)
        layout.addWidget(self._forgot_button)

        self._register_button = QPushButton(i18n.tr("auth.no_account"), self)
        self._register_button.setObjectName("AuthLinkButton")
        self._register_button.clicked.connect(self.register_requested.emit)
        layout.addWidget(self._register_button)

    def _retranslate(self, *_args: object) -> None:
        self.set_title(i18n.tr("auth.welcome_back"))
        self.set_subtitle(i18n.tr("auth.login_subtitle"))
        self._email_field.label.setText(i18n.tr("auth.email"))
        self._password_field.label.setText(i18n.tr("auth.password"))
        self._remember_checkbox.setText(i18n.tr("auth.remember_me"))
        self._submit_button.setText(i18n.tr("auth.log_in"))
        self._forgot_button.setText(i18n.tr("auth.forgot_password"))
        self._register_button.setText(i18n.tr("auth.no_account"))

    def _on_submit(self) -> None:
        email = self._email_field.text().strip()
        password = self._password_field.text()
        if not email or not password:
            self.show_error(i18n.tr("auth.enter_credentials"))
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
