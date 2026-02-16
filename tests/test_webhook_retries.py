"""Tests for webhook retry and dedupe behavior."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app as app_module


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 0.5


class _DummyChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _DummyUpdate:
    def __init__(self, chat_id: int = 123) -> None:
        self.effective_chat = _DummyChat(chat_id)


class _DummyBot:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))


class _AlwaysFailTelegramApp:
    def __init__(self) -> None:
        self.bot = _DummyBot()
        self.process_calls = 0

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:
        self.process_calls += 1
        raise RuntimeError("boom")


class _SuccessTelegramApp:
    def __init__(self) -> None:
        self.bot = _DummyBot()
        self.process_calls = 0

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:
        self.process_calls += 1
        return None


def test_webhook_retries_three_times_then_notifies(monkeypatch) -> None:
    tg_app = _AlwaysFailTelegramApp()

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(42))
    web_app = app_module.create_webhook_app(settings=_DummySettings(), telegram_app=tg_app)
    client = TestClient(web_app)

    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 999},
    )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert tg_app.process_calls == 3
    assert len(tg_app.bot.sent_messages) == 1
    assert tg_app.bot.sent_messages[0][0] == 42


def test_duplicate_update_id_is_not_reprocessed(monkeypatch) -> None:
    tg_app = _SuccessTelegramApp()

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(55))
    web_app = app_module.create_webhook_app(settings=_DummySettings(), telegram_app=tg_app)
    client = TestClient(web_app)

    first = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 111},
    )
    second = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json={"update_id": 111},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert tg_app.process_calls == 1
