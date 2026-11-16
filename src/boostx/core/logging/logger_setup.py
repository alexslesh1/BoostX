import sys

from loguru import logger

from boostx.config.paths import AppPaths


def configure_logging() -> None:
    logger.remove()
    # A windowed build (Nexora.exe) has no console: sys.stderr is None there,
    # and handing None to loguru would stop the app before it opens.
    if sys.stderr is not None:
        logger.add(sys.stderr, level="INFO", colorize=True)
    logger.add(
        AppPaths.logs_dir() / "nexora_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )
