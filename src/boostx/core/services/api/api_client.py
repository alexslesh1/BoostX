from __future__ import annotations

import httpx
from loguru import logger

from boostx.core.services.api.api_config import ApiConfig
from boostx.core.services.api.exceptions import ApiConnectionError, ApiError


class ApiClient:
    def __init__(self, config: ApiConfig | None = None) -> None:
        self._config = config or ApiConfig()
        self._client = httpx.Client(base_url=self._config.base_url, timeout=self._config.timeout_seconds)

    def request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        token: str | None = None,
    ) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else None
        try:
            response = self._client.request(method, path, json=json, headers=headers)
        except httpx.RequestError as exc:
            logger.warning(f"API request failed: {method} {path}: {exc}")
            raise ApiConnectionError() from exc

        if response.status_code >= 400:
            detail = self._extract_detail(response)
            raise ApiError(
                detail or f"Request failed ({response.status_code})",
                status_code=response.status_code,
                detail=detail,
            )

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    @staticmethod
    def _extract_detail(response: httpx.Response) -> str | None:
        try:
            body = response.json()
        except ValueError:
            return None
        detail = body.get("detail") if isinstance(body, dict) else None
        return detail if isinstance(detail, str) else None

    def close(self) -> None:
        self._client.close()
