"""
LLM gateway — thin wrapper around the OpenAI SDK pointed at OpenRouter.

Provides a single `chat()` function that:
  1. Sends a prompt to the configured model via OpenRouter.
  2. Tracks token usage and cost for telemetry.
  3. Returns both the response text and a usage dict.

Any OpenAI-compatible model available on OpenRouter works —
including free-tier models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from core.config import get_settings


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_estimate: float  # rough — based on OpenRouter pricing headers


def _build_client() -> OpenAI:
    """Construct an OpenAI client pointed at OpenRouter."""
    settings = get_settings()
    return OpenAI(
        base_url=settings.openrouter_base_url,
        api_key=settings.openrouter_api_key,
    )


_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = _build_client()
    return _client


def _parse_fallback_models(raw: str) -> list[str]:
    return [m.strip() for m in raw.split(",") if m.strip()]


def _is_model_endpoint_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return (
        "no endpoints found" in message
        or "model not found" in message
        or "not available" in message
        or "developer instruction is not enabled" in message
        or "provider returned error" in message
        or "rate limit" in message
        or "too many requests" in message
        or "error code: 429" in message
    )


def chat(
    messages: list[dict[str, str]],
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> LLMResponse:
    """
    Send a chat completion request via OpenRouter.

    Parameters
    ----------
    messages : list of {"role": ..., "content": ...} dicts
    model : override the default model from config
    temperature : override default temperature
    max_tokens : override default max_tokens
    json_mode : if True, request JSON output format

    Returns
    -------
    LLMResponse with text, token counts, and estimated cost.
    """
    settings = get_settings()
    client = _get_client()

    requested_model = model or settings.llm_model
    models_to_try = [requested_model]
    if model is None:
        for fallback in _parse_fallback_models(settings.llm_fallback_models):
            if fallback != requested_model:
                models_to_try.append(fallback)

    kwargs: dict[str, Any] = {
        "model": requested_model,
        "messages": messages,
        "temperature": temperature if temperature is not None else settings.llm_temperature,
        "max_tokens": max_tokens or settings.llm_max_tokens,
    }

    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_error: Exception | None = None
    response = None
    used_model = requested_model
    for candidate_model in models_to_try:
        try:
            kwargs["model"] = candidate_model
            response = client.chat.completions.create(**kwargs)
            used_model = candidate_model
            break
        except Exception as exc:
            last_error = exc
            if _is_model_endpoint_error(exc) and candidate_model != models_to_try[-1]:
                continue
            raise

    if response is None:
        if last_error is not None:
            raise last_error
        raise RuntimeError("LLM request failed without a concrete error.")

    choice = response.choices[0]
    usage = response.usage

    # Rough cost estimate (OpenRouter returns this in headers but
    # the SDK doesn't expose it easily — we approximate here).
    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = prompt_tokens + completion_tokens

    # Very rough $/1k token estimate — varies by model.
    # OpenRouter's actual cost is available via their /generation endpoint.
    cost_estimate = total_tokens * 0.00001  # $0.01 / 1k tokens placeholder

    return LLMResponse(
        text=choice.message.content or "",
        model=used_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_estimate=cost_estimate,
    )


def chat_text(
    system: str,
    user: str,
    *,
    model: str | None = None,
    json_mode: bool = False,
) -> LLMResponse:
    """Convenience: system + user message → LLMResponse."""
    return chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        model=model,
        json_mode=json_mode,
    )
