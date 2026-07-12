from __future__ import annotations

from boostx.core.services.api.api_client import ApiClient
from boostx.core.services.api.models import (
    AuthTokens,
    DeviceInfo,
    DeviceRecord,
    SubscriptionInfo,
    UserProfile,
)


class AuthService:
    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def register(self, username: str, email: str, password: str) -> None:
        self._client.request(
            "POST",
            "/auth/register",
            json={"username": username, "email": email, "password": password},
        )

    def login(
        self, email: str, password: str, remember_me: bool, device: DeviceInfo
    ) -> tuple[AuthTokens, UserProfile, SubscriptionInfo]:
        body = self._client.request(
            "POST",
            "/auth/login",
            json={
                "email": email,
                "password": password,
                "remember_me": remember_me,
                "device": {
                    "device_id": device.device_id,
                    "device_name": device.device_name,
                    "os": device.os,
                },
            },
        )
        return self._tokens_from(body), self._profile_from(body["user"]), self._subscription_from(body["subscription"])

    def refresh(self, refresh_token: str) -> AuthTokens:
        body = self._client.request("POST", "/auth/refresh", json={"refresh_token": refresh_token})
        return self._tokens_from(body)

    def logout(self, access_token: str, refresh_token: str) -> None:
        self._client.request("POST", "/auth/logout", json={"refresh_token": refresh_token}, token=access_token)

    def verify_email(self, email: str, code: str) -> None:
        self._client.request("POST", "/auth/verify-email", json={"email": email, "code": code})

    def resend_verification(self, email: str) -> None:
        self._client.request("POST", "/auth/resend-verification", json={"email": email})

    def request_password_reset(self, email: str) -> None:
        self._client.request("POST", "/auth/password-reset/request", json={"email": email})

    def confirm_password_reset(self, email: str, code: str, new_password: str) -> None:
        self._client.request(
            "POST",
            "/auth/password-reset/confirm",
            json={"email": email, "code": code, "new_password": new_password},
        )

    def change_password(self, access_token: str, current_password: str, new_password: str) -> None:
        self._client.request(
            "POST",
            "/auth/change-password",
            json={"current_password": current_password, "new_password": new_password},
            token=access_token,
        )

    def request_email_change(self, access_token: str, new_email: str) -> None:
        self._client.request(
            "POST", "/auth/change-email/request", json={"new_email": new_email}, token=access_token
        )

    def confirm_email_change(self, access_token: str, code: str) -> None:
        self._client.request("POST", "/auth/change-email/confirm", json={"code": code}, token=access_token)

    def get_profile(self, access_token: str) -> UserProfile:
        body = self._client.request("GET", "/users/me", token=access_token)
        return self._profile_from(body)

    def update_profile(
        self, access_token: str, username: str | None = None, avatar_url: str | None = None
    ) -> UserProfile:
        payload = {k: v for k, v in {"username": username, "avatar_url": avatar_url}.items() if v is not None}
        body = self._client.request("PATCH", "/users/me", json=payload, token=access_token)
        return self._profile_from(body)

    def get_subscription(self, access_token: str) -> SubscriptionInfo:
        body = self._client.request("GET", "/subscriptions/me", token=access_token)
        return self._subscription_from(body)

    def list_devices(self, access_token: str) -> list[DeviceRecord]:
        body = self._client.request("GET", "/devices", token=access_token)
        items = body if isinstance(body, list) else body.get("items", [])
        return [
            DeviceRecord(
                device_id=item["device_id"],
                device_name=item["device_name"],
                os=item["os"],
                last_seen=item["last_seen"],
                created_at=item["created_at"],
            )
            for item in items
        ]

    def register_device(self, access_token: str, device: DeviceInfo) -> None:
        self._client.request(
            "POST",
            "/devices/register",
            json={"device_id": device.device_id, "device_name": device.device_name, "os": device.os},
            token=access_token,
        )

    def remove_device(self, access_token: str, device_id: str) -> None:
        self._client.request("DELETE", f"/devices/{device_id}", token=access_token)

    def check_health(self) -> bool:
        try:
            self._client.request("GET", "/health")
            return True
        except Exception:
            return False

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _tokens_from(body: dict) -> AuthTokens:
        return AuthTokens(
            access_token=body["access_token"],
            refresh_token=body["refresh_token"],
            token_type=body.get("token_type", "bearer"),
            expires_in=body["expires_in"],
        )

    @staticmethod
    def _profile_from(body: dict) -> UserProfile:
        return UserProfile(
            id=body["id"],
            username=body["username"],
            email=body["email"],
            avatar_url=body.get("avatar_url"),
            email_verified=bool(body.get("email_verified", False)),
            created_at=body["created_at"],
            updated_at=body["updated_at"],
            last_login=body.get("last_login"),
        )

    @staticmethod
    def _subscription_from(body: dict) -> SubscriptionInfo:
        return SubscriptionInfo(
            plan=body["plan"],
            status=body["status"],
            current_period_end=body.get("current_period_end"),
            started_at=body["started_at"],
        )
