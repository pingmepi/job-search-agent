"""
Google Drive integration — upload artifacts to structured folders.

Folder structure: Jobs/{Company}/{Role}/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _get_drive_service():
    """
    Build an authenticated Google Drive service.

    Requires Google OAuth credentials to be configured.
    """
    from core.config import get_settings

    settings = get_settings()
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

    SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    token_path = creds_path.parent / "drive_token.pickle"

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

    return build("drive", "v3", credentials=creds)


def _find_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """Find or create a folder in Drive. Returns folder ID."""
    query = f"name = '{name}' and mimeType = 'application/vnd.google-apps.folder'"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    query += " and trashed = false"

    results = service.files().list(q=query, spaces="drive", fields="files(id)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]


def upload_to_drive(pdf_path: Path, company: str, role: str) -> str:
    """
    Upload a PDF to Google Drive under Jobs/{Company}/{Role}/.

    Returns the shareable link.
    """
    service = _get_drive_service()

    # Create folder structure
    jobs_id = _find_or_create_folder(service, "Jobs")
    company_id = _find_or_create_folder(service, company, jobs_id)
    role_id = _find_or_create_folder(service, role, company_id)

    # Upload file
    from googleapiclient.http import MediaFileUpload

    file_metadata = {
        "name": pdf_path.name,
        "parents": [role_id],
    }
    media = MediaFileUpload(str(pdf_path), mimetype="application/pdf")
    file = service.files().create(
        body=file_metadata, media_body=media, fields="id,webViewLink"
    ).execute()

    link = file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}")
    logger.info(f"Uploaded {pdf_path.name} → {link}")
    return link
