"""
LLM gateway — thin wrapper around the OpenAI SDK pointed at OpenRouter.

Provides a single `chat()` function that:
  1. Sends a prompt to the configured model via OpenRouter.
  2. Tracks token usage for telemetry.
  3. Returns both the response text and a usage dict.

Cost resolution is deferred — call `resolve_generation_cost()` with the
generation_id after the pipeline completes to avoid adding latency inline.

Any OpenAI-compatible model available on OpenRouter works —
including free-tier models.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_estimate: float = 0.0  # resolved later via resolve_generation_cost()
    generation_id: str | None = None  # OpenRouter generation ID for cost lookup


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


def resolve_generation_cost(generation_id: str) -> float:
    """
    Query OpenRouter's generation endpoint for real cost data.

    The endpoint can take 500–1500ms to populate after the completion
    response, so we retry once after a 1-second delay.

    Returns the total cost in USD, or 0.0 if the lookup fails
    (e.g. network error, free model with no cost data).

    This should be called AFTER the pipeline completes — not inline
    during LLM calls — to avoid adding latency to each request.
    """
    import time
    import urllib.request
    import json as _json

    settings = get_settings()
    url = f"{settings.openrouter_base_url.rstrip('/')}/generation?id={generation_id}"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = _json.loads(resp.read().decode("utf-8"))

            gen_data = data.get("data", data)
            total_cost = gen_data.get("total_cost")

            if total_cost is not None:
                return float(total_cost)

            # Cost not yet populated — wait and retry
            if attempt < max_attempts - 1:
                time.sleep(1.0)
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(1.0)
            else:
                return 0.0

    return 0.0


def resolve_costs_batch(generation_ids: list[str]) -> dict[str, float]:
    """
    Resolve real costs for a batch of generation IDs.

    Waits 1s before starting to give OpenRouter time to populate costs,
    then fetches all costs sequentially (no per-ID wait needed after
    the initial delay).

    Returns a dict mapping generation_id → cost in USD.
    """
    import time

    if not generation_ids:
        return {}

    # One upfront wait covers the propagation delay for all IDs
    time.sleep(1.0)

    costs: dict[str, float] = {}
    for gen_id in generation_ids:
        costs[gen_id] = resolve_generation_cost(gen_id)

    return costs


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
    LLMResponse with text, token counts, and generation_id.
    Cost is set to 0.0 — call resolve_generation_cost() or
    resolve_costs_batch() after the pipeline completes.
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

    prompt_tokens = usage.prompt_tokens if usage else 0
    completion_tokens = usage.completion_tokens if usage else 0
    total_tokens = prompt_tokens + completion_tokens

    # Store generation_id for deferred cost resolution
    generation_id = getattr(response, "id", None)

    return LLMResponse(
        text=choice.message.content or "",
        model=used_model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost_estimate=0.0,
        generation_id=generation_id,
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
