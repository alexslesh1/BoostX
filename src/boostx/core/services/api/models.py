from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    device_name: str
    os: str


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    device_name: str
    os: str
    last_seen: str
    created_at: str


@dataclass(frozen=True)
class UserProfile:
    id: str
    username: str
    email: str
    avatar_url: str | None
    email_verified: bool
    created_at: str
    updated_at: str
    last_login: str | None


@dataclass(frozen=True)
class SubscriptionInfo:
    plan: str
    status: str
    current_period_end: str | None
    started_at: str


@dataclass(frozen=True)
class AuthTokens:
    access_token: str
    refresh_token: str
    token_type: str
    expires_in: int
