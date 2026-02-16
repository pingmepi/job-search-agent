"""Webhook API E2E tests with realistic Telegram payloads."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app import create_webhook_app


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 1.0


class _DummyBot:
    async def send_message(self, chat_id: int, text: str) -> None:
        return None


class _CaptureTelegramApp:
    def __init__(self) -> None:
        self.bot = _DummyBot()
        self.received_update_ids: list[int] = []
        self.received_texts: list[str] = []
        self.received_chat_ids: list[int] = []

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:
        self.received_update_ids.append(update.update_id)
        if update.message is not None:
            self.received_texts.append(update.message.text)
            self.received_chat_ids.append(update.message.chat.id)


def test_webhook_e2e_processes_realistic_text_update() -> None:
    tg_app = _CaptureTelegramApp()
    web_app = create_webhook_app(settings=_DummySettings(), telegram_app=tg_app)
    client = TestClient(web_app)

    payload = {
        "update_id": 123456789,
        "message": {
            "message_id": 42,
            "date": 1700000000,
            "chat": {
                "id": 777,
                "type": "private",
                "first_name": "Karan",
            },
            "from": {
                "id": 777,
                "is_bot": False,
                "first_name": "Karan",
                "username": "karan",
                "language_code": "en",
            },
            "text": "Check status for followups",
            "entities": [{"offset": 0, "length": 5, "type": "bot_command"}],
        },
    }

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json=payload,
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert tg_app.received_update_ids == [123456789]
    assert tg_app.received_texts == ["Check status for followups"]
    assert tg_app.received_chat_ids == [777]


def test_webhook_e2e_rejects_invalid_update_payload() -> None:
    tg_app = _CaptureTelegramApp()
    web_app = create_webhook_app(settings=_DummySettings(), telegram_app=tg_app)
    client = TestClient(web_app)

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"foo": "bar"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid Telegram update payload"
    assert tg_app.received_update_ids == []
