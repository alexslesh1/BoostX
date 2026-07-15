from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget

from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.forgot_password_page import ForgotPasswordPage
from boostx.ui.auth.login_page import LoginPage
from boostx.ui.auth.register_page import RegisterPage
from boostx.ui.auth.startup_loading_page import StartupLoadingPage
from boostx.ui.auth.verify_email_page import VerifyEmailPage

_LOADING, _LOGIN, _REGISTER, _VERIFY, _FORGOT = range(5)
_FADE_DURATION_MS = 280


class AuthStack(QStackedWidget):
    authenticated = Signal()

    def __init__(self, session_manager: SessionManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("PageStack")
        self._verify_authenticates = False
        self._fade_animation: QPropertyAnimation | None = None

        self._loading_page = StartupLoadingPage(self)
        self._login_page = LoginPage(session_manager, self)
        self._register_page = RegisterPage(session_manager, self)
        self._verify_page = VerifyEmailPage(session_manager, self)
        self._forgot_page = ForgotPasswordPage(session_manager, self)

        self.insertWidget(_LOADING, self._loading_page)
        self.insertWidget(_LOGIN, self._login_page)
        self.insertWidget(_REGISTER, self._register_page)
        self.insertWidget(_VERIFY, self._verify_page)
        self.insertWidget(_FORGOT, self._forgot_page)

        self._login_page.login_succeeded.connect(self.authenticated.emit)
        self._login_page.register_requested.connect(lambda: self.setCurrentIndex(_REGISTER))
        self._login_page.forgot_password_requested.connect(lambda: self.setCurrentIndex(_FORGOT))
        self._login_page.verification_required.connect(lambda email: self._show_verify(email, from_login=True))

        self._register_page.login_requested.connect(lambda: self.setCurrentIndex(_LOGIN))
        self._register_page.registered.connect(lambda email: self._show_verify(email, from_login=False))

        self._verify_page.back_to_login_requested.connect(lambda: self.setCurrentIndex(_LOGIN))
        self._verify_page.verified.connect(self._on_verified)

        self._forgot_page.back_to_login_requested.connect(lambda: self.setCurrentIndex(_LOGIN))
        self._forgot_page.reset_completed.connect(self._on_reset_completed)

        self.setCurrentIndex(_LOADING)
        self._loading_page.start_spin()

    def show_login(self) -> None:
        """Called once AppController knows session restore did not succeed
        -- fades from the startup loading page into the login form in place."""
        self._loading_page.stop_spin()
        self._fade_to(_LOGIN)

    def reset_to_login(self) -> None:
        self._login_page.clear_messages()
        self.setCurrentIndex(_LOGIN)

    def _fade_to(self, index: int) -> None:
        widget = self.widget(index)
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        self.setCurrentIndex(index)

        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(_FADE_DURATION_MS)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)
        self._fade_animation = animation

    def _show_verify(self, email: str, from_login: bool) -> None:
        self._verify_authenticates = from_login
        self._verify_page.set_email(email)
        self.setCurrentIndex(_VERIFY)

    def _on_verified(self) -> None:
        if self._verify_authenticates:
            self.authenticated.emit()
            return
        self.setCurrentIndex(_LOGIN)
        self._login_page.show_status("Email verified. You can now log in.")

    def _on_reset_completed(self) -> None:
        self.setCurrentIndex(_LOGIN)
        self._login_page.show_status("Password reset. You can now log in.")
