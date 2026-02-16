"""
Google Calendar integration — create application events.

Creates:
1. "Applied" event on the current date
2. "Follow-up" event at +7 days
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def _get_calendar_service():
    """
    Build an authenticated Google Calendar service.

    Requires Google OAuth credentials to be configured.
    """
    from core.config import get_settings

    settings = get_settings()
    from pathlib import Path

    creds_path = Path(settings.google_credentials_path)

    if not creds_path.exists():
        raise FileNotFoundError(
            f"Google credentials not found at {creds_path}. "
            f"Follow the setup guide to configure OAuth."
        )

    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    import pickle

    SCOPES = ["https://www.googleapis.com/auth/calendar.events"]
    token_path = creds_path.parent / "calendar_token.pickle"

    creds = None
    if token_path.exists():
        with open(token_path, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "wb") as f:
            pickle.dump(creds, f)

    return build("calendar", "v3", credentials=creds)


def create_application_events(
    company: str,
    role: str,
    *,
    apply_date: Optional[datetime] = None,
    followup_days: int = 7,
) -> tuple[str, str]:
    """
    Create calendar events for a job application.

    Returns (apply_event_id, followup_event_id).
    """
    service = _get_calendar_service()
    now = apply_date or datetime.now(timezone.utc)

    # ── Applied event ─────────────────────────────────────────
    apply_event = {
        "summary": f"Applied: {company} — {role}",
        "description": f"Job application submitted for {role} at {company}.",
        "start": {
            "date": now.strftime("%Y-%m-%d"),
        },
        "end": {
            "date": now.strftime("%Y-%m-%d"),
        },
        "reminders": {"useDefault": False},
    }
    apply_result = service.events().insert(
        calendarId="primary", body=apply_event
    ).execute()

    # ── Follow-up event ───────────────────────────────────────
    followup_date = now + timedelta(days=followup_days)
    followup_event = {
        "summary": f"Follow-up: {company} — {role}",
        "description": (
            f"Follow up on job application for {role} at {company}.\n"
            f"Applied on {now.strftime('%Y-%m-%d')}."
        ),
        "start": {
            "date": followup_date.strftime("%Y-%m-%d"),
        },
        "end": {
            "date": followup_date.strftime("%Y-%m-%d"),
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 60},
            ],
        },
    }
    followup_result = service.events().insert(
        calendarId="primary", body=followup_event
    ).execute()

    logger.info(
        f"Calendar events created: "
        f"Applied ({apply_result['id']}), Follow-up ({followup_result['id']})"
    )

    return apply_result["id"], followup_result["id"]
