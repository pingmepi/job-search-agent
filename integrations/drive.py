"""
Google Drive integration — upload artifacts to structured folders.

Folder structure: Jobs/{Company}/{Role}/{application_context_id}/
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
    """Backward-compatible single-file upload helper."""
    result = upload_application_artifacts(
        files={"resume_pdf": pdf_path},
        company=company,
        role=role,
        application_context_id="legacy",
    )
    resume_upload = result.get("files", {}).get("resume_pdf", {})
    if isinstance(resume_upload, dict):
        return resume_upload.get("webViewLink", "")
    return ""


def _mime_for_file(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return "application/pdf"
    return "text/plain"


def upload_application_artifacts(
    *,
    files: dict[str, Path],
    company: str,
    role: str,
    application_context_id: str,
) -> dict:
    """
    Upload selected application artifacts to Google Drive.

    Files are uploaded under Jobs/{Company}/{Role}/{application_context_id}/.
    """
    service = _get_drive_service()

    # Create folder structure
    jobs_id = _find_or_create_folder(service, "Jobs")
    company_id = _find_or_create_folder(service, company, jobs_id)
    role_id = _find_or_create_folder(service, role, company_id)
    app_id = _find_or_create_folder(service, application_context_id, role_id)

    from googleapiclient.http import MediaFileUpload

    uploads: dict[str, dict[str, str]] = {}
    for logical_name, path in files.items():
        file_metadata = {
            "name": path.name,
            "parents": [app_id],
        }
        try:
            media = MediaFileUpload(str(path), mimetype=_mime_for_file(path))
            file = service.files().create(
                body=file_metadata, media_body=media, fields="id,webViewLink,name"
            ).execute()
            uploads[logical_name] = {
                "status": "uploaded",
                "id": file["id"],
                "name": file["name"],
                "webViewLink": file.get("webViewLink", f"https://drive.google.com/file/d/{file['id']}"),
            }
            logger.info("Uploaded %s (%s) to Drive", path.name, logical_name)
        except Exception as upload_err:
            uploads[logical_name] = {
                "status": "failed",
                "error": str(upload_err),
                "name": path.name,
            }

    return {
        "folder": {
            "id": app_id,
            "path": f"Jobs/{company}/{role}/{application_context_id}",
        },
        "files": uploads,
    }
