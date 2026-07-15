class ApiError(Exception):
    def __init__(self, message: str, status_code: int | None = None, detail: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


class ApiConnectionError(ApiError):
    def __init__(self, message: str = "Could not reach the Nexora server") -> None:
        super().__init__(message)


class ApiAuthError(ApiError):
    pass
