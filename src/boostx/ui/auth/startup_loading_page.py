from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from boostx.i18n import i18n
from boostx.ui.components.spinner import SpinnerWidget


class StartupLoadingPage(QWidget):
    """Shown while AppController waits on SessionManager.try_restore_session().
    Deliberately just a spinner: there's no real multi-megabyte payload to
    report progress on at this stage (restoring a session means a token
    refresh + a couple of small JSON API calls), so no MB counter is shown.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AuthPage")

        self._spinner = SpinnerWidget(self)
        self._status_label = QLabel(self)
        self._status_label.setObjectName("AuthSubtitle")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.addStretch(1)
        layout.addWidget(self._spinner, alignment=Qt.AlignmentFlag.AlignHCenter)
        layout.addSpacing(16)
        layout.addWidget(self._status_label)
        layout.addStretch(1)

        i18n.language_changed.connect(self._retranslate)
        self._retranslate()

    def _retranslate(self, *_args: object) -> None:
        self._status_label.setText(i18n.tr("loading.status"))

    def start_spin(self) -> None:
        self._spinner.start()

    def stop_spin(self) -> None:
        self._spinner.stop()
