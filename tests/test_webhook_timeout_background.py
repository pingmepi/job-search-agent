"""Regression test: webhook timeout must not cancel in-flight update processing."""

from __future__ import annotations

import asyncio
import importlib
import sys
import time
from types import ModuleType

from fastapi.testclient import TestClient


def _load_app_module_with_stubs():
    telegram_mod = ModuleType("telegram")

    class _Update:
        @staticmethod
        def de_json(payload, bot):  # pragma: no cover - patched in tests
            return payload

    telegram_mod.Update = _Update
    sys.modules["telegram"] = telegram_mod

    adapter_mod = ModuleType("agents.inbox.adapter")
    adapter_mod.create_bot = lambda: None
    sys.modules["agents.inbox.adapter"] = adapter_mod

    return importlib.import_module("app")


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 0.05
    database_url = ""


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
            await asyncio.sleep(0.15)
            await self.bot.send_message(chat_id=update.effective_chat.id, text="done")
            self.completed = True
        except BaseException:
            self.canceled = True
            raise


def test_webhook_timeout_runs_handler_in_background_without_duplicate_processing(
    monkeypatch, db
) -> None:
    app_module = _load_app_module_with_stubs()
    tg_app = _SlowTelegramApp()

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(77))
    settings = _DummySettings()
    settings.database_url = db
    web_app = app_module.create_webhook_app(settings=settings, telegram_app=tg_app)

    with TestClient(web_app) as client:
        first = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 5001},
        )
        second = client.post(
            "/telegram/webhook",
            headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
            json={"update_id": 5001},
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert tg_app.process_calls == 1

        time.sleep(0.3)

    assert tg_app.completed is True
    assert tg_app.canceled is False
    assert tg_app.bot.sent_messages == [(77, "done")]
