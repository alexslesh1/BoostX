import sys

from loguru import logger
from PySide6.QtWidgets import QApplication

from boostx.core.logging.logger_setup import configure_logging
from boostx.ui.main_window.main_window import MainWindow
from boostx.ui.theme.theme_loader import ThemeLoader


def run() -> int:
    configure_logging()
    logger.info("Starting BoostX")

    app = QApplication(sys.argv)
    app.setStyleSheet(ThemeLoader().load())

    window = MainWindow()
    window.show()

    return app.exec()
