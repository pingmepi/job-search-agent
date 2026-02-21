"""Tests for core/llm.py fallback model behavior."""

from __future__ import annotations

from dataclasses import dataclass

import core.llm as llm


@dataclass
class _DummyUsage:
    prompt_tokens: int = 10
    completion_tokens: int = 5


@dataclass
class _DummyMessage:
    content: str


@dataclass
class _DummyChoice:
    message: _DummyMessage


@dataclass
class _DummyResponse:
    choices: list[_DummyChoice]
    usage: _DummyUsage


class _DummyCompletions:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == "google/gemma-2-9b-it:free":
            raise Exception("No endpoints found for google/gemma-2-9b-it:free.")
        return _DummyResponse(
            choices=[_DummyChoice(message=_DummyMessage(content="ok"))],
            usage=_DummyUsage(),
        )


class _DummyCompletionsProviderError:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == "openrouter/free":
            raise Exception(
                "Provider returned error: Developer instruction is not enabled for models/gemma-3-4b-it"
            )
        return _DummyResponse(
            choices=[_DummyChoice(message=_DummyMessage(content="ok-provider-fallback"))],
            usage=_DummyUsage(),
        )


class _DummyCompletionsRateLimit:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        if model == "stepfun/step-3.5-flash:free":
            raise Exception("Error code: 429 - Too Many Requests (rate limit)")
        return _DummyResponse(
            choices=[_DummyChoice(message=_DummyMessage(content="ok-rate-limit-fallback"))],
            usage=_DummyUsage(),
        )


class _DummyClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _DummyCompletions()})()


class _DummyClientProviderError:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _DummyCompletionsProviderError()})()


class _DummyClientRateLimit:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": _DummyCompletionsRateLimit()})()


class _DummySettings:
    llm_model = "google/gemma-2-9b-it:free"
    llm_fallback_models = "openai/gpt-4o-mini"
    llm_temperature = 0.2
    llm_max_tokens = 4096


def test_chat_retries_on_endpoint_error(monkeypatch):
    dummy = _DummyClient()

    monkeypatch.setattr(llm, "get_settings", lambda: _DummySettings())
    monkeypatch.setattr(llm, "_get_client", lambda: dummy)

    response = llm.chat_text("system", "user")

    assert response.text == "ok"
    assert response.model == "openai/gpt-4o-mini"
    assert dummy.chat.completions.calls == [
        "google/gemma-2-9b-it:free",
        "openai/gpt-4o-mini",
    ]


class _DummySettingsProviderError:
    llm_model = "openrouter/free"
    llm_fallback_models = "stepfun/step-3.5-flash:free"
    llm_temperature = 0.2
    llm_max_tokens = 4096


def test_chat_retries_on_provider_capability_error(monkeypatch):
    dummy = _DummyClientProviderError()

    monkeypatch.setattr(llm, "get_settings", lambda: _DummySettingsProviderError())
    monkeypatch.setattr(llm, "_get_client", lambda: dummy)

    response = llm.chat_text("system", "user")

    assert response.text == "ok-provider-fallback"
    assert response.model == "stepfun/step-3.5-flash:free"
    assert dummy.chat.completions.calls == [
        "openrouter/free",
        "stepfun/step-3.5-flash:free",
    ]


class _DummySettingsRateLimit:
    llm_model = "stepfun/step-3.5-flash:free"
    llm_fallback_models = "qwen/qwen3-coder:free"
    llm_temperature = 0.2
    llm_max_tokens = 4096


def test_chat_retries_on_rate_limit_error(monkeypatch):
    dummy = _DummyClientRateLimit()

    monkeypatch.setattr(llm, "get_settings", lambda: _DummySettingsRateLimit())
    monkeypatch.setattr(llm, "_get_client", lambda: dummy)

    response = llm.chat_text("system", "user")

    assert response.text == "ok-rate-limit-fallback"
    assert response.model == "qwen/qwen3-coder:free"
    assert dummy.chat.completions.calls == [
        "stepfun/step-3.5-flash:free",
        "qwen/qwen3-coder:free",
    ]
