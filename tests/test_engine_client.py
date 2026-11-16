import json

import httpx
import pytest

from boostx.core.services.tunnel.engine_client import EngineClient
from boostx.core.services.tunnel.errors import EngineError
from boostx.core.services.tunnel.models import AppRule


def client_with(handler) -> EngineClient:
    return EngineClient(47600, "secret-key", transport=httpx.MockTransport(handler))


def test_requests_carry_the_key_and_the_documented_bodies():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        seen.append((request.method, request.url.path, request.headers.get("X-Nexora-Key"), body))
        return httpx.Response(200, json=[] if request.url.path == "/v1/probe" else {"running": True})

    client = client_with(handler)
    rule = AppRule("cs2", exes=("cs2.exe",), dirs=(r"C:\Games\CS2",))
    client.start("203.0.113.10:4700", "pubkey", "token", [rule])
    client.set_rules([rule])
    client.set_token("token-2")
    client.probe(["203.0.113.10:4700"])
    client.status()
    client.stop()
    client.shutdown()

    rule_json = {"name": "cs2", "exes": ["cs2.exe"], "dirs": [r"C:\Games\CS2"]}
    assert seen == [
        ("POST", "/v1/start", "secret-key",
         {"relay": "203.0.113.10:4700", "relay_public_key": "pubkey", "token": "token", "rules": [rule_json]}),
        ("POST", "/v1/rules", "secret-key", {"rules": [rule_json]}),
        ("POST", "/v1/token", "secret-key", {"token": "token-2"}),
        ("POST", "/v1/probe", "secret-key", {"relays": ["203.0.113.10:4700"]}),
        ("GET", "/v1/status", "secret-key", None),
        ("POST", "/v1/stop", "secret-key", None),
        ("POST", "/v1/shutdown", "secret-key", None),
    ]  # fmt: skip


def test_engine_error_message_is_surfaced():
    client = client_with(lambda request: httpx.Response(500, json={"error": "WinDivertOpen: access denied"}))
    with pytest.raises(EngineError, match="access denied") as caught:
        client.start("a:1", "k", "t", [])
    assert caught.value.status_code == 500


def test_unreachable_engine_is_an_engine_error_not_a_crash():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EngineError, match="not responding"):
        client_with(handler).status()
