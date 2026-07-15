from loguru import logger
from PySide6.QtCore import QObject

from boostx.core.services.api.session_manager import SessionManager
from boostx.ui.auth.auth_window import AuthWindow
from boostx.ui.main_window.main_window import MainWindow


class AppController(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.session_manager = SessionManager()
        self._auth_window: AuthWindow | None = None
        self._main_window: MainWindow | None = None

        self.session_manager.logged_out.connect(self._show_auth_window)

    def start(self) -> None:
        # Show the auth window (starting on its loading screen) immediately,
        # rather than waiting on try_restore_session -- that's what gives
        # the loading spinner something real to cover instead of a fake
        # delay: if a session is restored, we skip straight to the main
        # window and the login form is never shown at all.
        self._auth_window = AuthWindow(self.session_manager)
        self._auth_window.authenticated.connect(self._show_main_window)
        self._auth_window.show()
        self.session_manager.try_restore_session(self._on_restore_done)

    def shutdown(self) -> None:
        self.session_manager.shutdown()

    def _on_restore_done(self, restored: bool) -> None:
        if restored:
            offline_note = " (offline)" if self.session_manager.is_offline else ""
            logger.info(f"Session restored{offline_note}")
            self._show_main_window()
        elif self._auth_window is not None:
            self._auth_window.show_login()

    def _show_auth_window(self) -> None:
        if self._auth_window is None:
            self._auth_window = AuthWindow(self.session_manager)
            self._auth_window.authenticated.connect(self._show_main_window)
            self._auth_window.show_login()
        else:
            self._auth_window.reset_to_login()
        self._auth_window.show()

        if self._main_window is not None:
            old_window = self._main_window
            self._main_window = None
            old_window.close()

    def _show_main_window(self) -> None:
        self._main_window = MainWindow(self.session_manager)
        self._main_window.show()

        if self._auth_window is not None:
            old_window = self._auth_window
            self._auth_window = None
            old_window.close()
