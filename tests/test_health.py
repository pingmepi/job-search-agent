"""Webhook service health and auth tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_webhook_app


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 1.0


class _DummyTelegramApp:
    bot = object()

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:  # pragma: no cover - not reached here
        return None


def test_health_returns_ok() -> None:
    app = create_webhook_app(settings=_DummySettings(), telegram_app=_DummyTelegramApp())
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_webhook_rejects_invalid_secret() -> None:
    app = create_webhook_app(settings=_DummySettings(), telegram_app=_DummyTelegramApp())
    client = TestClient(app)

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={"update_id": 12345},
    )

    assert response.status_code == 401
