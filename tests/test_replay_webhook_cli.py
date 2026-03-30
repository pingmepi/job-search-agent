"""Tests for replay-webhook CLI path."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import main as main_module


class _FakeTelegramApp:
    def __init__(self) -> None:
        self.bot = object()
        self.called = False

    async def initialize(self) -> None:
        return None

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def process_update(self, update) -> None:
        self.called = True


def test_parse_replay_args_requires_exactly_one_selector() -> None:
    with pytest.raises(ValueError):
        main_module._parse_replay_webhook_args([])
    with pytest.raises(ValueError):
        main_module._parse_replay_webhook_args(["--event-id", "e1", "--update-id", "12"])


def test_parse_replay_args_accepts_event_id() -> None:
    parsed = main_module._parse_replay_webhook_args(["--event-id", "evt-1"])
    assert parsed["event_id"] == "evt-1"
    assert parsed["update_id"] is None


def test_replay_webhook_runs_process_update(monkeypatch) -> None:
    fake_app = _FakeTelegramApp()

    monkeypatch.setattr(
        "core.db.get_webhook_event",
        lambda **_kwargs: {
            "event_id": "evt-1",
            "update_id": 123,
            "payload": {"update_id": 123, "message": {"text": "hello"}},
        },
    )
    monkeypatch.setattr("agents.inbox.adapter.create_bot", lambda: fake_app)
    monkeypatch.setattr(
        "telegram.Update.de_json",
        lambda payload, bot: SimpleNamespace(update_id=payload.get("update_id")),
    )

    main_module._run_replay_webhook(["--event-id", "evt-1"])

    assert fake_app.called is True
