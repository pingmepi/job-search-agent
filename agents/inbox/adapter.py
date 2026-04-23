"""
Telegram bot adapter — receives messages the user sends and routes them.

Handles:
- Text messages → router
- Photo messages (JD screenshots) → OCR → Inbox Agent
- URL detection → Inbox Agent

Uses python-telegram-bot (async) with webhook delivery.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from agents.inbox.collateral import normalize_collateral_selection
from agents.inbox.url_ingest import extract_first_url, fetch_url_text
from core.config import get_settings
from core.router import AgentTarget, route

logger = logging.getLogger(__name__)


def _is_chat_allowed(update: Update) -> bool:
    """Check if the chat is in the allowlist (empty list = allow all)."""
    settings = get_settings()
    allowlist = settings.telegram_allowed_chat_ids.strip()
    if not allowlist:
        return True
    allowed = {int(cid.strip()) for cid in allowlist.split(",") if cid.strip()}
    chat = getattr(update, "effective_chat", None)
    return chat is not None and chat.id in allowed


URL_FALLBACK_PROMPT = (
    "⚠️ I couldn't reliably extract the job description from that URL. "
    "Please send a screenshot of the job posting so I can continue."
)
COLLATERAL_PROMPT = (
    "Which collateral should I generate for this job?\n"
    "Reply with one or more: `email`, `linkedin`, `referral`.\n"
    "Examples: `email` or `email, linkedin`.\n"
    "Reply `none` to skip collateral generation."
)


async def _run_and_respond(
    update: Update,
    *,
    raw_text: str,
    image_path: Optional[Path],
    selected_collateral: list[str],
    skip_upload: bool,
    skip_calendar: bool,
    user_vetted: bool,
) -> None:
    from agents.inbox.agent import run_pipeline
    from agents.inbox.ocr import OCRQualityError

    try:
        pack = await asyncio.to_thread(
            run_pipeline,
            raw_text,
            image_path=image_path,
            selected_collateral=selected_collateral,
            skip_upload=skip_upload,
            skip_calendar=skip_calendar,
            user_vetted=user_vetted,
        )
        logger.info(
            "Pipeline result run_id=%s pdf_file=%s pdf_path=%s errors=%s selected=%s generated=%s",
            pack.run_id,
            pack.pdf_path.name if pack.pdf_path else None,
            str(pack.pdf_path) if pack.pdf_path else None,
            len(pack.errors),
            pack.selected_collateral,
            pack.generated_collateral,
        )
        if not pack.pdf_path:
            details = (
                "\n".join(f"• {e}" for e in pack.errors[:5])
                or "• No compiled one-page resume artifact was produced."
            )
            await update.message.reply_text(
                "❌ Process failed\n"
                "I couldn't produce a valid one-page terminal resume artifact.\n"
                f"🧪 Run ID: {pack.run_id or 'n/a'}\n"
                "Details:\n"
                f"{details}"
            )
            return
        jd = pack.jd
        generated_label = (
            ", ".join(pack.generated_collateral) if pack.generated_collateral else "none"
        )
        await update.message.reply_text(
            f"✅ Process completed\n"
            f"✅ JD Extracted:\n"
            f"🏢 Company: {jd.company}\n"
            f"💼 Role: {jd.role}\n"
            f"📍 Location: {jd.location}\n"
            f"🛠 Skills: {', '.join(jd.skills)}\n\n"
            f"📄 Resume base: {pack.resume_base}\n"
            f"✅ Compile: {'yes' if pack.pdf_path else 'no'}\n"
            f"✉️ Collateral generated: {generated_label}\n"
            f"🧪 Run ID: {pack.run_id or 'n/a'}"
        )

        # Send the PDF resume if compile succeeded. Isolate failures so a
        # Telegram upload/network blip does not trigger the outer
        # "❌ Error: Timed out" reply after the pipeline itself succeeded.
        async def _send_safe(coro_factory, label: str) -> None:
            try:
                await coro_factory()
            except Exception as send_err:
                logger.warning("Failed to send %s: %s", label, send_err)
                pack.errors.append(f"{label} send failed: {send_err}")

        if pack.pdf_path and pack.pdf_path.exists():

            async def _send_pdf() -> None:
                with open(pack.pdf_path, "rb") as pdf_file:
                    await update.message.reply_document(
                        document=pdf_file,
                        filename=pack.pdf_path.name,
                        caption=f"📄 Tailored resume for {jd.company} — {jd.role}",
                    )

            await _send_safe(_send_pdf, "Resume PDF")
        if pack.email_draft:
            await _send_safe(
                lambda: update.message.reply_text(f"✉️ Email draft:\n\n{pack.email_draft}"),
                "Email draft",
            )
        if pack.linkedin_draft:
            await _send_safe(
                lambda: update.message.reply_text(f"💬 LinkedIn DM:\n\n{pack.linkedin_draft}"),
                "LinkedIn draft",
            )
        if pack.referral_draft:
            await _send_safe(
                lambda: update.message.reply_text(f"🤝 Referral note:\n\n{pack.referral_draft}"),
                "Referral draft",
            )
        if pack.errors:
            # Telegram caps messages at 4096 chars. Truncate each error to
            # ~500 chars and the whole payload to ~3500 so ✨we stay under the
            # limit even with emojis/markup. Full errors remain in the run's
            # errors_json for offline inspection.
            def _trunc(s: str, limit: int = 500) -> str:
                return s if len(s) <= limit else s[:limit] + f"... [+{len(s) - limit} chars]"

            payload = "⚠️ Completed with issues:\n" + "\n".join(
                f"• {_trunc(e)}" for e in pack.errors[:5]
            )
            if len(payload) > 3500:
                payload = payload[:3500] + "\n... [truncated — see runs.errors_json]"
            await update.message.reply_text(payload)
    except OCRQualityError as e:
        logger.warning("OCR quality too low: %s", e)
        await update.message.reply_text(
            "⚠️ I couldn't extract a reliable job description from that screenshot. "
            "Please send a clearer screenshot (full JD section, readable text, minimal cropping)."
        )
    except Exception as e:
        logger.error("Pipeline execution error: %s", e)
        await update.message.reply_text(f"❌ Error: {e}")
    finally:
        if image_path:
            image_path.unlink(missing_ok=True)


# ── Handlers ──────────────────────────────────────────────────────


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    if not update.message:
        return
    await update.message.reply_text(
        "👋 Hi! I'm your Job Application Agent.\n\n"
        "Send me:\n"
        "📸 A screenshot of a job description\n"
        "🔗 A URL to a job listing\n"
        "📝 Raw JD text\n\n"
        "I'll generate a tailored resume, then ask which collateral you want."
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
    if not update.message:
        return
    await update.message.reply_text(
        "Commands:\n"
        "/start — Welcome message\n"
        "/help — This message\n"
        "/status — Check pending follow-ups\n"
        "/profile — Ask about Karan's background\n\n"
        "Or just send a JD (text, URL, or screenshot)!"
    )


async def status_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /status command — check pending follow-ups."""
    if not update.message:
        return
    from agents.followup.agent import detect_followups

    jobs = detect_followups()
    if not jobs:
        await update.message.reply_text("✅ No follow-ups pending.")
        return

    lines = ["📋 **Pending follow-ups:**\n"]
    for job in jobs:
        tier = job.get("escalation_tier", {})
        lines.append(
            f"• {job['company']} — {job['role']} "
            f"(tier {job.get('tier_number', 0) + 1}: {tier.get('label', 'follow-up')})"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages (JD screenshots)."""
    if not update.message:
        return
    if not _is_chat_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    logger.info("Handling photo message via OCR path")
    await update.message.reply_text("📸 Got your screenshot.")

    # Download the photo
    photo = update.message.photo[-1]  # highest resolution
    photo_file = await context.bot.get_file(photo.file_id)

    # Save to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await photo_file.download_to_drive(tmp.name)
        image_path = Path(tmp.name)

    settings = get_settings()
    context.user_data["pending_inbox_request"] = {
        "raw_text": "",
        "image_path": str(image_path),
        "skip_upload": not settings.telegram_enable_drive_upload,
        "skip_calendar": not settings.telegram_enable_calendar_events,
        "input_mode": "photo",
        "user_vetted": True,
    }
    await update.message.reply_text(COLLATERAL_PROMPT, parse_mode="Markdown")


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages — route to the appropriate agent."""
    if not update.message:
        return
    if not _is_chat_allowed(update):
        await update.message.reply_text("⛔ Unauthorized.")
        return
    text = update.message.text
    pending_request = context.user_data.get("pending_inbox_request")
    if pending_request:
        selected_collateral, valid = normalize_collateral_selection(text or "")
        if not valid or selected_collateral is None:
            await update.message.reply_text(
                "I couldn't parse that collateral selection.\n" + COLLATERAL_PROMPT,
                parse_mode="Markdown",
            )
            return

        image_path = pending_request.get("image_path")
        context.user_data.pop("pending_inbox_request", None)
        await update.message.reply_text("⏳ Process started (JD pipeline)...")
        await _run_and_respond(
            update,
            raw_text=pending_request.get("raw_text", ""),
            image_path=Path(image_path) if image_path else None,
            selected_collateral=selected_collateral,
            skip_upload=bool(pending_request.get("skip_upload", False)),
            skip_calendar=bool(pending_request.get("skip_calendar", False)),
            user_vetted=bool(pending_request.get("user_vetted", False)),
        )
        return

    logger.info("Handling text message via router path")
    result = route(text)
    input_mode = "url" if extract_first_url(text or "") else "text"
    preview = (text or "").replace("\n", " ").strip()
    if len(preview) > 80:
        preview = preview[:80] + "..."
    logger.info(
        "Router decision update_id=%s target=%s reason=%s text_preview=%s",
        getattr(update, "update_id", None),
        result.target.value,
        result.reason,
        preview,
    )
    logger.info(
        "Router telemetry update_id=%s route_target=%s route_reason_code=%s input_mode=%s",
        getattr(update, "update_id", None),
        result.target.value,
        result.reason_code,
        input_mode,
    )

    if result.target == AgentTarget.INBOX:
        await update.message.reply_text(
            f"📥 Routing to Inbox Agent... ({result.reason})\nPreparing job input..."
        )
        try:
            settings = get_settings()
            skip_upload = not settings.telegram_enable_drive_upload
            skip_calendar = not settings.telegram_enable_calendar_events

            pipeline_input = text
            url = extract_first_url(text or "")
            if url:
                ingest = await asyncio.to_thread(fetch_url_text, url)
                if ingest.ok:
                    pipeline_input = ingest.extracted_text
                    await update.message.reply_text(
                        "🔗 Fetched job URL successfully. Processing extracted content..."
                    )
                else:
                    await update.message.reply_text(URL_FALLBACK_PROMPT)
                    return

            context.user_data["pending_inbox_request"] = {
                "raw_text": pipeline_input,
                "image_path": None,
                "skip_upload": skip_upload,
                "skip_calendar": skip_calendar,
                "input_mode": input_mode,
                "user_vetted": True,
            }
            await update.message.reply_text(COLLATERAL_PROMPT, parse_mode="Markdown")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    elif result.target == AgentTarget.PROFILE:
        await update.message.reply_text(f"👤 Routing to Profile Agent... ({result.reason})")
        try:
            from agents.profile.agent import run_profile_agent

            response_text, narrative, ungrounded = run_profile_agent(text)
            warning = ""
            if ungrounded:
                warning = f"\n⚠️ Potential ungrounded claims: {', '.join(ungrounded)}"
            await update.message.reply_text(
                f"[{narrative.upper()} angle]\n\n{response_text}{warning}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    elif result.target == AgentTarget.FOLLOWUP:
        await status_handler(update, context)

    elif result.target == AgentTarget.ARTICLE:
        await update.message.reply_text("📰 Summarizing article...")
        try:
            from agents.article.agent import run_article_agent

            summary, signals, run_id = run_article_agent(text)
            signal_text = "\n".join(f"• {s}" for s in signals) if signals else "None detected."
            await update.message.reply_text(
                f"📰 Article Summary\n\n{summary}\n\n"
                f"🔍 Job search signals:\n{signal_text}\n\n"
                f"🧪 Run ID: {run_id}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error summarizing article: {e}")

    elif result.target == AgentTarget.AMBIGUOUS_NON_JOB:
        await update.message.reply_text(
            "🤔 I need a job description input to proceed. "
            "Send a JD URL, a screenshot, or paste the JD text."
        )

    elif result.target == AgentTarget.CLARIFY:
        await update.message.reply_text(
            "🤔 I'm not sure what to do with that. You can:\n"
            "• Send a JD (text, URL, or screenshot)\n"
            "• Ask about Karan's profile\n"
            "• Check /status for follow-ups"
        )


# ── Bot startup ───────────────────────────────────────────────────


def create_bot() -> Application:
    """Create and configure the Telegram bot application."""
    settings = get_settings()

    if settings.telegram_token == "placeholder":
        logger.warning(
            "⚠️  Telegram token is 'placeholder'. Set TELEGRAM_TOKEN in .env to use the bot."
        )

    # Default PTB write_timeout=5s is too short for reply_document uploads
    # of tailored resume PDFs; raise all HTTP timeouts to tolerate slow
    # Railway egress and Telegram API blips.
    app = (
        Application.builder()
        .token(settings.telegram_token)
        .connect_timeout(15.0)
        .read_timeout(30.0)
        .write_timeout(60.0)
        .pool_timeout(5.0)
        .build()
    )

    # Register handlers
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("status", status_handler))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    logger.info(
        "This module now serves webhook mode only. "
        "Start the service with: `python main.py webhook`."
    )
