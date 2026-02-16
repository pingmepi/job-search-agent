"""
Centralised configuration for inbox-agent.

Reads from .env and exposes a Settings dataclass.
All model names, thresholds, and paths live here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# ── locate project root (parent of core/) ────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable app-wide settings.  Instantiate once at startup."""

    # ── LLM (OpenRouter) ──────────────────────────────────────────
    openrouter_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENROUTER_API_KEY", "")
    )
    llm_model: str = field(
        default_factory=lambda: os.environ.get("LLM_MODEL", "google/gemma-2-9b-it:free")
    )
    llm_fallback_models: str = field(
        default_factory=lambda: os.environ.get("LLM_FALLBACK_MODELS", "")
    )
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_temperature: float = 0.2
    llm_max_tokens: int = 4096

    # ── Telegram ──────────────────────────────────────────────────
    telegram_token: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_TOKEN", "placeholder")
    )
    telegram_bot_username: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_BOT_USERNAME", "@job_notes_bot")
    )
    telegram_webhook_secret: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_WEBHOOK_SECRET", "placeholder")
    )
    public_base_url: str = field(
        default_factory=lambda: os.environ.get("PUBLIC_BASE_URL", "")
    )
    telegram_webhook_path: str = field(
        default_factory=lambda: os.environ.get("TELEGRAM_WEBHOOK_PATH", "/telegram/webhook")
    )
    webhook_host: str = field(
        default_factory=lambda: os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    )
    webhook_port: int = field(
        default_factory=lambda: int(os.environ.get("WEBHOOK_PORT", "8000"))
    )
    webhook_process_timeout_seconds: float = field(
        default_factory=lambda: float(os.environ.get("WEBHOOK_PROCESS_TIMEOUT_SECONDS", "10"))
    )
    telegram_enable_drive_upload: bool = field(
        default_factory=lambda: _env_bool("TELEGRAM_ENABLE_DRIVE_UPLOAD", default=False)
    )
    telegram_enable_calendar_events: bool = field(
        default_factory=lambda: _env_bool("TELEGRAM_ENABLE_CALENDAR_EVENTS", default=False)
    )

    # ── Google Cloud ──────────────────────────────────────────────
    google_credentials_path: str = field(
        default_factory=lambda: os.environ.get(
            "GOOGLE_CREDENTIALS_PATH", "credentials/google_oauth.json"
        )
    )

    # ── Cost ──────────────────────────────────────────────────────
    max_cost_per_job: float = field(
        default_factory=lambda: float(os.environ.get("MAX_COST_PER_JOB", "0.15"))
    )

    # ── Paths ─────────────────────────────────────────────────────
    project_root: Path = PROJECT_ROOT
    db_path: Path = field(
        default_factory=lambda: PROJECT_ROOT
        / os.environ.get("DB_PATH", "data/inbox_agent.db")
    )
    prompts_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "core" / "prompts")
    profile_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "profile" / "profile.json"
    )
    bullet_bank_path: Path = field(
        default_factory=lambda: PROJECT_ROOT / "profile" / "bullet_bank.json"
    )
    resumes_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "resumes")
    runs_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "runs")


# ── Singleton accessor ────────────────────────────────────────────
_settings: Settings | None = None


def get_settings() -> Settings:
    """Return (and cache) the global Settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
