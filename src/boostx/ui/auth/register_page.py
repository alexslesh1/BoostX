from PySide6.QtCore import Signal
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from boostx.core.services.api.exceptions import ApiError
from boostx.core.services.api.session_manager import SessionManager
from boostx.i18n import i18n
from boostx.ui.auth.auth_form_page import AuthFormPage
from boostx.ui.auth.form_fields import add_field

_MIN_PASSWORD_LENGTH = 8


class RegisterPage(AuthFormPage):
    registered = Signal(str)
    login_requested = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        self._session_manager = session_manager
        super().__init__(
            title=i18n.tr("auth.create_account_title"),
            subtitle=i18n.tr("auth.create_account_subtitle"),
            parent=parent,
        )
        i18n.language_changed.connect(self._retranslate)

    def _build_form(self, layout: QVBoxLayout) -> None:
        self._username_field = add_field(layout, self, i18n.tr("auth.username"))
        self._email_field = add_field(layout, self, i18n.tr("auth.email"))
        self._password_field = add_field(layout, self, i18n.tr("auth.password"), is_password=True)

        self._submit_button = QPushButton(i18n.tr("auth.create_account_button"), self)
        self._submit_button.setObjectName("AuthPrimaryButton")
        self._submit_button.clicked.connect(self._on_submit)
        layout.addWidget(self._submit_button)

        self._login_button = QPushButton(i18n.tr("auth.have_account"), self)
        self._login_button.setObjectName("AuthLinkButton")
        self._login_button.clicked.connect(self.login_requested.emit)
        layout.addWidget(self._login_button)

    def _retranslate(self, *_args: object) -> None:
        self.set_title(i18n.tr("auth.create_account_title"))
        self.set_subtitle(i18n.tr("auth.create_account_subtitle"))
        self._username_field.label.setText(i18n.tr("auth.username"))
        self._email_field.label.setText(i18n.tr("auth.email"))
        self._password_field.label.setText(i18n.tr("auth.password"))
        self._submit_button.setText(i18n.tr("auth.create_account_button"))
        self._login_button.setText(i18n.tr("auth.have_account"))

    def _on_submit(self) -> None:
        username = self._username_field.text().strip()
        email = self._email_field.text().strip()
        password = self._password_field.text()
        if not username or not email or not password:
            self.show_error(i18n.tr("auth.fill_all_fields"))
            return
        if len(password) < _MIN_PASSWORD_LENGTH:
            self.show_error(i18n.tr("auth.password_min_length", min_length=_MIN_PASSWORD_LENGTH))
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
