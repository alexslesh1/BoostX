import sys

from loguru import logger
from PySide6.QtWidgets import QApplication

from boostx.core.logging.logger_setup import configure_logging
from boostx.ui.app_controller import AppController
from boostx.ui.theme.theme_loader import ThemeLoader


def run() -> int:
    configure_logging()
    logger.info("Starting Nexora")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setStyleSheet(ThemeLoader().load())

    controller = AppController()
    app.aboutToQuit.connect(controller.shutdown)
    controller.start()

    return app.exec()
