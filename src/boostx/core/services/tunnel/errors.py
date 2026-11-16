from __future__ import annotations


class TunnelError(Exception):
    """A routing failure with a message that is fit to show to the user."""


class ElevationDeclinedError(TunnelError):
    def __init__(self) -> None:
        super().__init__("Administrator permission is needed to route traffic.")


class EngineError(Exception):
    """The engine's control API refused a request or could not be reached."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
