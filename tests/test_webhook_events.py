"""Tests for webhook event persistence and lifecycle."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import app as app_module
from core.db import get_webhook_event


class _DummySettings:
    telegram_webhook_secret = "test-secret"
    telegram_webhook_path = "/telegram/webhook"
    webhook_process_timeout_seconds = 0.5

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path


class _DummyChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class _DummyUpdate:
    def __init__(self, chat_id: int = 123) -> None:
        self.effective_chat = _DummyChat(chat_id)


class _DummyBot:
    async def send_message(self, chat_id: int, text: str) -> None:
        return None


class _SuccessTelegramApp:
    def __init__(self) -> None:
        self.bot = _DummyBot()

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:
        return None


class _FailTelegramApp(_SuccessTelegramApp):
    async def process_update(self, update) -> None:
        raise RuntimeError("boom")


def test_webhook_persists_processed_event(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "events.db"
    settings = _DummySettings(db_path)

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(42))
    web_app = app_module.create_webhook_app(settings=settings, telegram_app=_SuccessTelegramApp())
    client = TestClient(web_app)

    payload = {"update_id": 991, "message": {"text": "hello"}}
    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json=payload,
    )

    assert response.status_code == 200
    event = get_webhook_event(update_id=991, db_path=db_path)
    assert event is not None
    assert event["processing_status"] == "processed"
    assert event["payload"]["update_id"] == 991


def test_webhook_persists_failed_event_after_retries(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "events.db"
    settings = _DummySettings(db_path)

    monkeypatch.setattr(app_module.Update, "de_json", lambda payload, bot: _DummyUpdate(42))
    web_app = app_module.create_webhook_app(settings=settings, telegram_app=_FailTelegramApp())
    client = TestClient(web_app)

    payload = {"update_id": 992, "message": {"text": "hello"}}
    response = client.post(
        "/telegram/webhook",
        headers={"X-Telegram-Bot-Api-Secret-Token": "test-secret"},
        json=payload,
    )

    assert response.status_code == 200
    event = get_webhook_event(update_id=992, db_path=db_path)
    assert event is not None
    assert event["processing_status"] == "failed"
    assert event["error_text"] is not None
