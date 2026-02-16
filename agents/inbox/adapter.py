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
    MessageHandler,
    ContextTypes,
    filters,
)

from core.config import get_settings
from core.router import route, AgentTarget

logger = logging.getLogger(__name__)


# ── Handlers ──────────────────────────────────────────────────────

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /start command."""
    await update.message.reply_text(
        "👋 Hi! I'm your Job Application Agent.\n\n"
        "Send me:\n"
        "📸 A screenshot of a job description\n"
        "🔗 A URL to a job listing\n"
        "📝 Raw JD text\n\n"
        "I'll generate a tailored resume, outreach drafts, and log everything."
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle the /help command."""
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
    logger.info("Handling photo message via OCR path")
    await update.message.reply_text("📸 Got your screenshot! Processing via OCR...")

    # Download the photo
    photo = update.message.photo[-1]  # highest resolution
    photo_file = await context.bot.get_file(photo.file_id)

    # Save to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        await photo_file.download_to_drive(tmp.name)
        image_path = Path(tmp.name)

    try:
        from agents.inbox.agent import run_pipeline

        pack = await asyncio.to_thread(
            run_pipeline,
            "",
            image_path=image_path,
            skip_upload=True,
            skip_calendar=True,
        )
        jd = pack.jd
        await update.message.reply_text(
            f"✅ **JD Extracted:**\n"
            f"🏢 Company: {jd.company}\n"
            f"💼 Role: {jd.role}\n"
            f"📍 Location: {jd.location}\n"
            f"🛠 Skills: {', '.join(jd.skills)}\n\n"
            f"📄 Resume base: {pack.resume_base}\n"
            f"✅ Compile: {'yes' if pack.pdf_path else 'no'}\n"
            f"✉️ Drafts: {'yes' if pack.email_draft and pack.linkedin_draft and pack.referral_draft else 'partial'}\n"
            f"🧪 Run ID: {pack.run_id or 'n/a'}",
            parse_mode="Markdown",
        )

        if pack.errors:
            await update.message.reply_text(
                "⚠️ Completed with issues:\n" + "\n".join(f"• {e}" for e in pack.errors[:5])
            )

    except Exception as e:
        logger.error(f"OCR/extraction error: {e}")
        await update.message.reply_text(f"❌ Error processing screenshot: {e}")
    finally:
        image_path.unlink(missing_ok=True)


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages — route to the appropriate agent."""
    text = update.message.text
    logger.info("Handling text message via router path")
    result = route(text)

    if result.target == AgentTarget.INBOX:
        await update.message.reply_text(f"📥 Routing to Inbox Agent... ({result.reason})")
        try:
            from agents.inbox.agent import run_pipeline

            pack = await asyncio.to_thread(
                run_pipeline,
                text,
                skip_upload=True,
                skip_calendar=True,
            )
            jd = pack.jd
            await update.message.reply_text(
                f"✅ **JD Extracted:**\n"
                f"🏢 Company: {jd.company}\n"
                f"💼 Role: {jd.role}\n"
                f"📍 Location: {jd.location}\n"
                f"🛠 Skills: {', '.join(jd.skills)}\n\n"
                f"📄 Resume base: {pack.resume_base}\n"
                f"✅ Compile: {'yes' if pack.pdf_path else 'no'}\n"
                f"🧪 Run ID: {pack.run_id or 'n/a'}",
                parse_mode="Markdown",
            )
            if pack.errors:
                await update.message.reply_text(
                    "⚠️ Completed with issues:\n" + "\n".join(f"• {e}" for e in pack.errors[:5])
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")

    elif result.target == AgentTarget.PROFILE:
        await update.message.reply_text(f"👤 Routing to Profile Agent... ({result.reason})")
        try:
            from agents.profile.agent import answer
            response_text, narrative, ungrounded = answer(text)
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
            "⚠️  Telegram token is 'placeholder'. "
            "Set TELEGRAM_TOKEN in .env to use the bot."
        )

    app = Application.builder().token(settings.telegram_token).build()

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
