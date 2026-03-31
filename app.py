"""FastAPI webhook service for Telegram updates."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from telegram import Update

from agents.inbox.adapter import create_bot
from core.config import Settings, get_settings
from core.db import init_db, insert_webhook_event, update_webhook_event

logger = logging.getLogger(__name__)


class TelegramWebhookRuntime:
    """Holds the telegram application instance used by FastAPI routes."""

    def __init__(self, telegram_app: Any | None = None) -> None:
        self.telegram_app = telegram_app
        self.processed_update_ids: set[int] = set()
        self.processing_update_ids: set[int] = set()
        self.update_attempts: dict[int, int] = {}
        self.background_update_tasks: dict[int, asyncio.Task[Any]] = {}
        self.lock: asyncio.Lock | None = None


async def _start_telegram_app(runtime: TelegramWebhookRuntime) -> None:
    if runtime.telegram_app is None:
        runtime.telegram_app = create_bot()
    await runtime.telegram_app.initialize()
    await runtime.telegram_app.start()


async def _stop_telegram_app(runtime: TelegramWebhookRuntime) -> None:
    await runtime.telegram_app.stop()
    await runtime.telegram_app.shutdown()


def _event_id_for_payload(update_id: int | None, payload: dict[str, Any]) -> str:
    """Build a deterministic id from update id + canonical payload."""
    canonical_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()[:16]
    if isinstance(update_id, int):
        return f"upd-{update_id}-{digest}"
    return f"upd-unknown-{digest}"


def create_webhook_app(
    *,
    settings: Settings | Any | None = None,
    telegram_app: Any | None = None,
) -> FastAPI:
    """Create a FastAPI app that processes Telegram webhook updates."""
    resolved_settings = settings or get_settings()
    runtime = TelegramWebhookRuntime(telegram_app)
    resolved_db_path = Path(resolved_settings.db_path) if hasattr(resolved_settings, "db_path") else None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.info("Initializing Telegram webhook runtime")
        if get_settings().database_url:
            await asyncio.to_thread(init_db)
        await _start_telegram_app(runtime)
        try:
            yield
        finally:
            logger.info("Shutting down Telegram webhook runtime")
            await _stop_telegram_app(runtime)

    web_app = FastAPI(lifespan=lifespan)
    webhook_path = resolved_settings.telegram_webhook_path or "/telegram/webhook"

    @web_app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    async def _notify_processing_failed(update: Update) -> None:
        """Notify user when an update fails all retry attempts."""
        try:
            chat = getattr(update, "effective_chat", None)
            if chat is None or getattr(chat, "id", None) is None:
                return
            await runtime.telegram_app.bot.send_message(
                chat_id=chat.id,
                text=(
                    "❌ Processing failed after 3 attempts. "
                    "Please resend your message or screenshot."
                ),
            )
        except Exception:
            logger.exception("Failed to send processing-failed notification")

    @web_app.post(webhook_path)
    async def telegram_webhook(
        request: Request,
        x_telegram_bot_api_secret_token: Optional[str] = Header(default=None),
    ) -> dict[str, bool]:
        if runtime.lock is None:
            runtime.lock = asyncio.Lock()
        expected_secret = resolved_settings.telegram_webhook_secret
        client_host = request.client.host if request.client else "unknown"
        payload = await request.json()
        update_id = payload.get("update_id")
        event_id = _event_id_for_payload(update_id if isinstance(update_id, int) else None, payload)
        has_secret_header = x_telegram_bot_api_secret_token is not None
        secret_matches = x_telegram_bot_api_secret_token == expected_secret
        logger.info(
            "Webhook request received client=%s update_id=%s secret_header_present=%s secret_valid=%s",
            client_host,
            update_id,
            has_secret_header,
            secret_matches,
        )

        if not expected_secret or expected_secret == "placeholder":
            raise HTTPException(
                status_code=500,
                detail="TELEGRAM_WEBHOOK_SECRET is not configured.",
            )

        if x_telegram_bot_api_secret_token != expected_secret:
            raise HTTPException(status_code=401, detail="Invalid webhook secret token")

        request_headers = {
            "x_telegram_bot_api_secret_token": x_telegram_bot_api_secret_token,
            "content_type": request.headers.get("content-type"),
            "user_agent": request.headers.get("user-agent"),
            "client_host": client_host,
        }
        await asyncio.to_thread(
            insert_webhook_event,
            event_id,
            update_id=update_id if isinstance(update_id, int) else None,
            payload=payload,
            headers=request_headers,
            secret_valid=True,
            processing_status="received",
            db_path=resolved_db_path,
        )

        started = time.perf_counter()
        logger.info("Webhook update received update_id=%s event_id=%s", update_id, event_id)

        if runtime.telegram_app is None:
            raise HTTPException(status_code=503, detail="Telegram runtime not initialized")

        try:
            update = Update.de_json(payload, runtime.telegram_app.bot)
        except Exception as exc:
            logger.warning("Invalid Telegram update payload parse error=%s", exc)
            await asyncio.to_thread(
                update_webhook_event,
                event_id,
                processing_status="failed",
                error_text=f"payload-parse-error: {exc}",
                mark_processed=True,
                db_path=resolved_db_path,
            )
            raise HTTPException(status_code=400, detail="Invalid Telegram update payload") from exc
        if update is None:
            await asyncio.to_thread(
                update_webhook_event,
                event_id,
                processing_status="failed",
                error_text="payload-parse-error: update is None",
                mark_processed=True,
                db_path=resolved_db_path,
            )
            raise HTTPException(status_code=400, detail="Invalid Telegram update payload")

        # Ensure each update_id is processed at-most-once across retries.
        if isinstance(update_id, int):
            async with runtime.lock:
                if update_id in runtime.processed_update_ids:
                    logger.info("Skipping already-processed update_id=%s", update_id)
                    await asyncio.to_thread(
                        update_webhook_event,
                        event_id,
                        processing_status="processed",
                        mark_processed=True,
                        db_path=resolved_db_path,
                    )
                    return {"ok": True}
                if update_id in runtime.processing_update_ids:
                    logger.info("Skipping in-flight update_id=%s", update_id)
                    return {"ok": True}
                runtime.processing_update_ids.add(update_id)

        async def _finalize_background_update(
            *,
            update_id: int,
            event_id: str,
            update: Update,
            task: asyncio.Task[Any],
        ) -> None:
            error_text: str | None = None
            status = "processed"
            try:
                await task
            except Exception as exc:
                status = "failed"
                error_text = str(exc)
                await _notify_processing_failed(update)
                logger.error(
                    "Background update failed after webhook timeout update_id=%s error=%s",
                    update_id,
                    exc,
                )
            finally:
                async with runtime.lock:
                    runtime.background_update_tasks.pop(update_id, None)
                    runtime.processing_update_ids.discard(update_id)
                    runtime.processed_update_ids.add(update_id)
                    runtime.update_attempts.pop(update_id, None)
                await asyncio.to_thread(
                    update_webhook_event,
                    event_id,
                    processing_status=status,
                    error_text=error_text,
                    mark_processed=True,
                    db_path=resolved_db_path,
                )

        max_attempts = 3
        last_error: Exception | None = None
        deferred_to_background = False
        try:
            await asyncio.to_thread(
                update_webhook_event,
                event_id,
                processing_status="processing",
                db_path=resolved_db_path,
            )
            for attempt in range(1, max_attempts + 1):
                try:
                    if isinstance(update_id, int):
                        runtime.update_attempts[update_id] = attempt
                    logger.info("Processing update_id=%s attempt=%s/%s", update_id, attempt, max_attempts)
                    process_task = asyncio.create_task(runtime.telegram_app.process_update(update))
                    await asyncio.wait_for(
                        asyncio.shield(process_task),
                        timeout=resolved_settings.webhook_process_timeout_seconds,
                    )
                    last_error = None
                    if isinstance(update_id, int):
                        async with runtime.lock:
                            runtime.processed_update_ids.add(update_id)
                            runtime.update_attempts.pop(update_id, None)
                    await asyncio.to_thread(
                        update_webhook_event,
                        event_id,
                        processing_status="processed",
                        mark_processed=True,
                        db_path=resolved_db_path,
                    )
                    break
                except asyncio.TimeoutError:
                    # Keep the in-flight task alive in background so handlers can finish
                    # and still send Telegram replies after webhook ACK timeout.
                    logger.warning(
                        "Update processing timed out update_id=%s attempt=%s timeout_seconds=%s",
                        update_id,
                        attempt,
                        resolved_settings.webhook_process_timeout_seconds,
                    )
                    last_error = None
                    if isinstance(update_id, int):
                        async with runtime.lock:
                            runtime.background_update_tasks[update_id] = process_task
                        process_task.add_done_callback(
                            lambda done, uid=update_id, eid=event_id, upd=update: asyncio.create_task(
                                _finalize_background_update(
                                    update_id=uid,
                                    event_id=eid,
                                    update=upd,
                                    task=done,
                                )
                            )
                        )
                        deferred_to_background = True
                    await asyncio.to_thread(
                        update_webhook_event,
                        event_id,
                        processing_status="processing",
                        error_text="processing timeout; continuing in background",
                        mark_processed=False,
                        db_path=resolved_db_path,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    logger.warning("Update processing failed update_id=%s attempt=%s error=%s", update_id, attempt, exc)
                    if attempt == max_attempts:
                        await _notify_processing_failed(update)
                        if isinstance(update_id, int):
                            async with runtime.lock:
                                runtime.processed_update_ids.add(update_id)
                                runtime.update_attempts.pop(update_id, None)
                        await asyncio.to_thread(
                            update_webhook_event,
                            event_id,
                            processing_status="failed",
                            error_text=str(exc),
                            mark_processed=True,
                            db_path=resolved_db_path,
                        )
                    else:
                        await asyncio.sleep(0.2)
        finally:
            if isinstance(update_id, int):
                async with runtime.lock:
                    if not deferred_to_background:
                        runtime.processing_update_ids.discard(update_id)

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        if last_error is None:
            logger.info("Webhook update processed update_id=%s latency_ms=%s", update_id, elapsed_ms)
        else:
            logger.error(
                "Webhook update failed after retries update_id=%s latency_ms=%s",
                update_id,
                elapsed_ms,
            )
        return {"ok": True}

    return web_app


app = create_webhook_app()


def run_webhook_server() -> None:
    """Run the FastAPI webhook server with uvicorn."""
    settings = get_settings()
    uvicorn.run("app:app", host=settings.webhook_host, port=settings.webhook_port, log_level="info")


if __name__ == "__main__":
    run_webhook_server()
