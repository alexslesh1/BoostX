from __future__ import annotations

from typing import Callable

from loguru import logger
from PySide6.QtCore import QObject, QTimer, Signal

from boostx.core.services.api.api_client import ApiClient
from boostx.core.services.api.api_worker import run_async
from boostx.core.services.api.auth_service import AuthService
from boostx.core.services.api.device_identity import get_device_info
from boostx.core.services.api.exceptions import ApiConnectionError, ApiError
from boostx.core.services.api.models import (
    AuthTokens,
    DeviceRecord,
    ProxyCredentials,
    SubscriptionInfo,
    UserProfile,
)
from boostx.core.services.api.profile_cache import ProfileCache
from boostx.core.services.api.token_storage import TokenStorage

_OFFLINE_RETRY_INTERVAL_MS = 30_000
_REFRESH_MARGIN_SECONDS = 30
_MIN_REFRESH_DELAY_MS = 5_000

OnSuccess = Callable[[], None]
OnError = Callable[[ApiError], None]


class SessionManager(QObject):
    session_restored = Signal(bool)
    login_succeeded = Signal()
    logged_out = Signal()
    auth_state_changed = Signal()
    offline_changed = Signal(bool)

    def __init__(
        self,
        auth_service: AuthService | None = None,
        token_storage: TokenStorage | None = None,
        profile_cache: ProfileCache | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._auth_service = auth_service or AuthService(ApiClient())
        self._token_storage = token_storage or TokenStorage()
        self._profile_cache = profile_cache or ProfileCache()
        self._device = get_device_info()

        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._user: UserProfile | None = None
        self._subscription: SubscriptionInfo | None = None
        self._offline = False

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self._on_refresh_timer)

        self._retry_timer = QTimer(self)
        self._retry_timer.setInterval(_OFFLINE_RETRY_INTERVAL_MS)
        self._retry_timer.timeout.connect(self._retry_sync)

    # -- properties -------------------------------------------------------
    @property
    def is_authenticated(self) -> bool:
        return self._user is not None

    @property
    def is_offline(self) -> bool:
        return self._offline

    @property
    def current_user(self) -> UserProfile | None:
        return self._user

    @property
    def current_subscription(self) -> SubscriptionInfo | None:
        return self._subscription

    @property
    def access_token(self) -> str | None:
        return self._access_token

    # -- startup ------------------------------------------------------------
    def try_restore_session(self, on_done: Callable[[bool], None]) -> None:
        refresh_token = self._token_storage.load_refresh_token()
        if refresh_token is None:
            on_done(False)
            return

        def _do_restore() -> tuple[AuthTokens, UserProfile, SubscriptionInfo]:
            tokens = self._auth_service.refresh(refresh_token)
            user = self._auth_service.get_profile(tokens.access_token)
            subscription = self._auth_service.get_subscription(tokens.access_token)
            return tokens, user, subscription

        def _on_success(result: tuple[AuthTokens, UserProfile, SubscriptionInfo]) -> None:
            tokens, user, subscription = result
            self._apply_session(tokens, user, subscription)
            self._set_offline(False)
            self.session_restored.emit(False)
            on_done(True)

        def _on_error(error: ApiError) -> None:
            if isinstance(error, ApiConnectionError):
                cached = self._profile_cache.load()
                if cached is not None:
                    self._user, self._subscription = cached
                    self._refresh_token = refresh_token
                    self._set_offline(True)
                    self.session_restored.emit(True)
                    self.auth_state_changed.emit()
                    on_done(True)
                    return
                on_done(False)
                return
            logger.info(f"Session restore rejected by server: {error}")
            self._token_storage.clear()
            on_done(False)

        run_async(_do_restore, _on_success, _on_error)

    # -- auth actions ---------------------------------------------------------
    def register(self, username: str, email: str, password: str, on_success: OnSuccess, on_error: OnError) -> None:
        run_async(lambda: self._auth_service.register(username, email, password), lambda _: on_success(), on_error)

    def login(self, email: str, password: str, remember_me: bool, on_success: OnSuccess, on_error: OnError) -> None:
        def _do_login() -> tuple[AuthTokens, UserProfile, SubscriptionInfo]:
            return self._auth_service.login(email, password, remember_me, self._device)

        def _on_success(result: tuple[AuthTokens, UserProfile, SubscriptionInfo]) -> None:
            tokens, user, subscription = result
            self._apply_session(tokens, user, subscription)
            self._set_offline(False)
            run_async(lambda: self._auth_service.register_device(tokens.access_token, self._device), None, None)
            self.login_succeeded.emit()
            on_success()

        run_async(_do_login, _on_success, on_error)

    def logout(self, on_done: Callable[[], None]) -> None:
        access_token = self._access_token
        refresh_token = self._refresh_token

        def _do_logout() -> None:
            if access_token and refresh_token:
                self._auth_service.logout(access_token, refresh_token)

        def _finish(_result: object = None) -> None:
            self._clear_session()
            self.logged_out.emit()
            on_done()

        run_async(_do_logout, _finish, lambda _err: _finish())

    def verify_email(self, email: str, code: str, on_success: OnSuccess, on_error: OnError) -> None:
        run_async(lambda: self._auth_service.verify_email(email, code), lambda _: on_success(), on_error)

    def resend_verification(self, email: str, on_success: OnSuccess, on_error: OnError) -> None:
        run_async(lambda: self._auth_service.resend_verification(email), lambda _: on_success(), on_error)

    def request_password_reset(self, email: str, on_success: OnSuccess, on_error: OnError) -> None:
        run_async(lambda: self._auth_service.request_password_reset(email), lambda _: on_success(), on_error)

    def confirm_password_reset(
        self, email: str, code: str, new_password: str, on_success: OnSuccess, on_error: OnError
    ) -> None:
        run_async(
            lambda: self._auth_service.confirm_password_reset(email, code, new_password),
            lambda _: on_success(),
            on_error,
        )

    def change_password(self, current_password: str, new_password: str, on_success: OnSuccess, on_error: OnError) -> None:
        token = self._access_token
        run_async(
            lambda: self._auth_service.change_password(token, current_password, new_password),
            lambda _: on_success(),
            on_error,
        )

    def request_email_change(self, new_email: str, on_success: OnSuccess, on_error: OnError) -> None:
        token = self._access_token
        run_async(lambda: self._auth_service.request_email_change(token, new_email), lambda _: on_success(), on_error)

    def confirm_email_change(self, code: str, on_success: OnSuccess, on_error: OnError) -> None:
        token = self._access_token

        def _do() -> UserProfile:
            self._auth_service.confirm_email_change(token, code)
            return self._auth_service.get_profile(token)

        def _on_success(user: UserProfile) -> None:
            self._user = user
            if self._subscription is not None:
                self._profile_cache.save(user, self._subscription)
            self.auth_state_changed.emit()
            on_success()

        run_async(_do, _on_success, on_error)

    def refresh_devices(self, on_success: Callable[[list[DeviceRecord]], None], on_error: OnError) -> None:
        token = self._access_token
        run_async(lambda: self._auth_service.list_devices(token), on_success, on_error)

    def remove_device(self, device_id: str, on_success: OnSuccess, on_error: OnError) -> None:
        token = self._access_token
        run_async(lambda: self._auth_service.remove_device(token, device_id), lambda _: on_success(), on_error)

    def get_proxy_credentials(
        self, on_success: Callable[[ProxyCredentials], None], on_error: OnError
    ) -> None:
        token = self._access_token
        run_async(lambda: self._auth_service.get_proxy_credentials(token), on_success, on_error)

    def shutdown(self) -> None:
        self._refresh_timer.stop()
        self._retry_timer.stop()
        self._auth_service.close()

    # -- internals --------------------------------------------------------------
    def _apply_session(self, tokens: AuthTokens, user: UserProfile, subscription: SubscriptionInfo) -> None:
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        self._user = user
        self._subscription = subscription
        self._token_storage.save_refresh_token(tokens.refresh_token)
        self._profile_cache.save(user, subscription)
        self._schedule_refresh(tokens.expires_in)
        self.auth_state_changed.emit()

    def _clear_session(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._user = None
        self._subscription = None
        self._token_storage.clear()
        self._refresh_timer.stop()
        self._retry_timer.stop()
        self._offline = False
        self.auth_state_changed.emit()

    def _set_offline(self, offline: bool) -> None:
        if offline == self._offline:
            return
        self._offline = offline
        self.offline_changed.emit(offline)
        if offline:
            self._retry_timer.start()
        else:
            self._retry_timer.stop()

    def _schedule_refresh(self, expires_in: int) -> None:
        delay_ms = max((expires_in - _REFRESH_MARGIN_SECONDS) * 1000, _MIN_REFRESH_DELAY_MS)
        self._refresh_timer.start(delay_ms)

    def _on_refresh_timer(self) -> None:
        if self._refresh_token is None:
            return
        run_async(
            lambda: self._auth_service.refresh(self._refresh_token),
            self._on_silent_refresh_success,
            self._on_silent_refresh_error,
        )

    def _on_silent_refresh_success(self, tokens: AuthTokens) -> None:
        self._access_token = tokens.access_token
        self._refresh_token = tokens.refresh_token
        self._token_storage.save_refresh_token(tokens.refresh_token)
        self._schedule_refresh(tokens.expires_in)
        self._set_offline(False)

    def _on_silent_refresh_error(self, error: ApiError) -> None:
        if isinstance(error, ApiConnectionError):
            self._set_offline(True)
            return
        logger.info(f"Background token refresh rejected: {error}")
        self._clear_session()
        self.logged_out.emit()

    def _retry_sync(self) -> None:
        if self._refresh_token is None:
            self._retry_timer.stop()
            return
        self._on_refresh_timer()
