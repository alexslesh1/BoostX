import sys

from loguru import logger

from boostx.config.paths import AppPaths


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True)
    logger.add(
        AppPaths.logs_dir() / "boostx_{time:YYYY-MM-DD}.log",
        rotation="10 MB",
        retention="7 days",
        level="DEBUG",
        encoding="utf-8",
    )
