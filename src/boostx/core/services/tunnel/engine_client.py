"""Client for the engine's control API (see nexora-core/engine/api.go).

The engine is a separate elevated process; this app talks to it over
loopback HTTP and therefore never needs administrator rights itself.
"""
from __future__ import annotations

import httpx

from boostx.core.services.tunnel.errors import EngineError
from boostx.core.services.tunnel.models import AppRule

_DEFAULT_TIMEOUT_S = 5.0
# Opening the capture driver for the first time after boot installs it.
_START_TIMEOUT_S = 30.0
# The engine probes every relay in parallel, a few attempts each.
_PROBE_TIMEOUT_S = 15.0


class EngineClient:
    def __init__(self, port: int, key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=f"http://127.0.0.1:{port}",
            headers={"X-Nexora-Key": key},
            timeout=_DEFAULT_TIMEOUT_S,
            # Never send loopback control traffic to a system-wide proxy.
            trust_env=False,
            transport=transport,
        )

    def status(self) -> dict:
        return self._request("GET", "/v1/status")

    def start(self, relay_address: str, relay_public_key: str, token: str, rules: list[AppRule]) -> dict:
        body = {
            "relay": relay_address,
            "relay_public_key": relay_public_key,
            "token": token,
            "rules": [rule.to_json() for rule in rules],
        }
        return self._request("POST", "/v1/start", body, timeout=_START_TIMEOUT_S)

    def set_rules(self, rules: list[AppRule]) -> dict:
        return self._request("POST", "/v1/rules", {"rules": [rule.to_json() for rule in rules]})

    def set_token(self, token: str) -> dict:
        return self._request("POST", "/v1/token", {"token": token})

    def stop(self) -> dict:
        return self._request("POST", "/v1/stop")

    def probe(self, relay_addresses: list[str]) -> list[dict]:
        """Round-trip time to each relay, fastest first, unreachable last."""
        return self._request("POST", "/v1/probe", {"relays": relay_addresses}, timeout=_PROBE_TIMEOUT_S)

    def shutdown(self) -> None:
        self._request("POST", "/v1/shutdown")

    def close(self) -> None:
        self._client.close()

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float | None = None):
        try:
            response = self._client.request(
                method, path, json=body, timeout=timeout if timeout is not None else _DEFAULT_TIMEOUT_S
            )
        except httpx.RequestError as exc:
            raise EngineError(f"engine is not responding: {exc}") from exc
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.status_code >= 400:
            message = payload.get("error") if isinstance(payload, dict) else None
            raise EngineError(message or f"engine returned {response.status_code}", response.status_code)
        return payload
