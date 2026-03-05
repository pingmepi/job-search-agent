"""Tests for webhook retry and dedupe behavior."""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 0.5
    db_path = Path("/tmp/job-search-agent-test-webhook-retries.db")


class _ShortTimeoutSettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 0.05
    db_path = Path("/tmp/job-search-agent-test-webhook-retries-timeout.db")


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


class _SlowTelegramApp:
    def __init__(self) -> None:
        self.bot = _DummyBot()
        self.process_calls = 0
        self.completed = False
        self.canceled = False

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
        try:
            await time_async_sleep(0.15)
            await self.bot.send_message(chat_id=update.effective_chat.id, text="done")
            self.completed = True
        except BaseException:
            self.canceled = True
            raise


async def time_async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


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


def test_timeout_does_not_cancel_inflight_handler_and_preserves_dedupe(monkeypatch) -> None:
    tg_app = _SlowTelegramApp()

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(77))
    web_app = app_module.create_webhook_app(settings=_ShortTimeoutSettings(), telegram_app=tg_app)

    with TestClient(web_app) as client:
        first = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 222},
        )
        # While first processing continues in background, duplicate update should be deduped.
        second = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 222},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert tg_app.process_calls == 1

        time.sleep(0.25)

    assert tg_app.completed is True
    assert tg_app.canceled is False
    assert tg_app.bot.sent_messages == [(77, "done")]
