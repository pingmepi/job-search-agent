"""
Shared Google OAuth2 authentication and retry utilities.

Uses a single token file with both Drive and Calendar scopes.

Headless-safe credential loading for Railway deployment:
- Load cached token pickle → refresh if expired
- Decode base64-encoded token from GOOGLE_TOKEN_B64 env var on first call
- Interactive mode for local CLI bootstrap (`python main.py auth-google`)
- Never opens a browser in headless mode
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any

from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

ALL_SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/calendar.events",
]

TOKEN_FILENAME = "google_token.json"
TOKEN_ENV_VAR = "GOOGLE_TOKEN_B64"


# ── Exceptions ────────────────────────────────────────────────────


class GoogleAuthError(Exception):
    """Base class for Google auth errors."""


class GoogleAuthNotConfigured(GoogleAuthError):
    """Credentials file or token not available in headless mode."""


class GoogleAuthExpired(GoogleAuthError):
    """Token expired and automatic refresh failed."""


# ── Token bootstrap from env var ──────────────────────────────────


def _bootstrap_token_from_env(token_path: Path) -> None:
    """Decode a base64-encoded token from env var to disk if not already present.

    Validates the decoded content is parseable JSON so a malformed env var
    fails loudly instead of masquerading as "no valid token".
    """
    b64_raw = os.environ.get(TOKEN_ENV_VAR, "")
    if not b64_raw or token_path.exists():
        return

    # Strip whitespace and accidental surrounding quotes from Railway UI paste.
    b64 = b64_raw.strip().strip("'\"")

    token_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = base64.b64decode(b64, validate=False)
    except Exception as exc:
        logger.error(
            "%s base64 decode failed (env var len=%d, stripped len=%d): %s",
            TOKEN_ENV_VAR,
            len(b64_raw),
            len(b64),
            exc,
        )
        return

    try:
        parsed = json.loads(data.decode("utf-8"))
    except Exception as exc:
        preview = data[:80].decode("utf-8", errors="replace")
        logger.error(
            "%s decoded bytes (%d) are not valid JSON: %s | preview=%r",
            TOKEN_ENV_VAR,
            len(data),
            exc,
            preview,
        )
        return

    required = {"refresh_token", "client_id", "client_secret"}
    missing = required - set(parsed.keys())
    if missing:
        logger.error(
            "%s JSON is missing required fields: %s. "
            "Re-run 'python main.py auth-google' locally and re-encode.",
            TOKEN_ENV_VAR,
            sorted(missing),
        )
        return

    token_path.write_bytes(data)
    logger.info("Bootstrapped %s from %s (%d bytes)", token_path.name, TOKEN_ENV_VAR, len(data))


# ── Core credential loader ────────────────────────────────────────


def get_google_credentials(*, interactive: bool = False) -> Any:
    """
    Load or create Google OAuth2 credentials with Drive + Calendar scopes.

    Args:
        interactive: If True, open browser for OAuth flow. Must be False in headless.

    Returns:
        google.oauth2.credentials.Credentials

    Raises:
        GoogleAuthNotConfigured: No credentials file or no valid token in headless mode.
        GoogleAuthExpired: Token expired and refresh failed.
    """
    from core.config import get_settings

    settings = get_settings()
    creds_path = Path(settings.google_credentials_path)
    token_path = creds_path.parent / TOKEN_FILENAME

    _bootstrap_token_from_env(token_path)

    if not creds_path.exists() and not token_path.exists():
        raise GoogleAuthNotConfigured(
            f"Google credentials not found at {creds_path} and no cached token at {token_path}. "
            f"Run 'python main.py auth-google' locally to set up OAuth."
        )

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    creds = None
    if token_path.exists():
        try:
            token_data = json.loads(token_path.read_text(encoding="utf-8"))
            creds = Credentials.from_authorized_user_info(token_data, ALL_SCOPES)
        except Exception as exc:
            logger.warning("Failed to load token from %s: %s", token_path, exc)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json(), encoding="utf-8")
            logger.info("Refreshed Google token")
            return creds
        except Exception as exc:
            if not interactive:
                raise GoogleAuthExpired(
                    f"Token expired and refresh failed: {exc}. "
                    f"Run 'python main.py auth-google' locally to re-authenticate."
                ) from exc
            logger.warning("Token refresh failed, falling through to interactive: %s", exc)

    if not interactive:
        raise GoogleAuthNotConfigured(
            "No valid Google token and interactive mode is disabled. "
            "Run 'python main.py auth-google' locally to authenticate."
        )

    if not creds_path.exists():
        raise GoogleAuthNotConfigured(
            f"Cannot run interactive auth: credentials file not found at {creds_path}."
        )

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), ALL_SCOPES)
    creds = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")

    logger.info("Saved Google token with scopes: %s", ALL_SCOPES)
    return creds


# ── Retry decorator for Google API calls ──────────────────────────


def _is_transient_google_error(exc: BaseException) -> bool:
    """Check if a Google API error is transient (retryable)."""
    from googleapiclient.errors import HttpError

    if isinstance(exc, HttpError):
        return exc.resp.status in (429, 500, 503)
    msg = str(exc).lower()
    return "timeout" in msg or "connection" in msg


def google_api_retry():
    """Tenacity retry decorator for Google API calls."""
    return retry(
        retry=retry_if_exception(_is_transient_google_error),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
