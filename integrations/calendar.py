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

from integrations.google_auth import get_google_credentials, google_api_retry

logger = logging.getLogger(__name__)


def _get_calendar_service():
    """Build an authenticated Google Calendar service."""
    creds = get_google_credentials()
    from googleapiclient.discovery import build
    return build("calendar", "v3", credentials=creds)


@google_api_retry()
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

    apply_event = {
        "summary": f"Applied: {company} — {role}",
        "description": f"Job application submitted for {role} at {company}.",
        "start": {"date": now.strftime("%Y-%m-%d")},
        "end": {"date": now.strftime("%Y-%m-%d")},
        "reminders": {"useDefault": False},
    }
    apply_result = service.events().insert(
        calendarId="primary", body=apply_event
    ).execute()

    followup_date = now + timedelta(days=followup_days)
    followup_event = {
        "summary": f"Follow-up: {company} — {role}",
        "description": (
            f"Follow up on job application for {role} at {company}.\n"
            f"Applied on {now.strftime('%Y-%m-%d')}."
        ),
        "start": {"date": followup_date.strftime("%Y-%m-%d")},
        "end": {"date": followup_date.strftime("%Y-%m-%d")},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 60}],
        },
    }
    followup_result = service.events().insert(
        calendarId="primary", body=followup_event
    ).execute()

    logger.info(
        "Calendar events created: Applied (%s), Follow-up (%s)",
        apply_result["id"],
        followup_result["id"],
    )

    return apply_result["id"], followup_result["id"]
