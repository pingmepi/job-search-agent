"""
Google Drive integration — upload artifacts to structured folders.

Folder structure: Jobs/{Company}/{Role}/{application_context_id}/
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from integrations.google_auth import get_google_credentials, google_api_retry

logger = logging.getLogger(__name__)


def _get_drive_service():
    """Build an authenticated Google Drive service."""
    creds = get_google_credentials()
    from googleapiclient.discovery import build

    return build("drive", "v3", credentials=creds)


@google_api_retry()
def _find_or_create_folder(service, name: str, parent_id: Optional[str] = None) -> str:
    """Find or create a folder in Drive. Returns folder ID."""
    escaped_name = name.replace("\\", "\\\\").replace("'", "\\'")
    query = f"name = '{escaped_name}' and mimeType = 'application/vnd.google-apps.folder'"
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

    jobs_id = _find_or_create_folder(service, "Jobs")
    company_id = _find_or_create_folder(service, company, jobs_id)
    role_id = _find_or_create_folder(service, role, company_id)
    app_id = _find_or_create_folder(service, application_context_id, role_id)

    from googleapiclient.http import MediaFileUpload

    _upload_with_retry = google_api_retry()

    uploads: dict[str, dict[str, str]] = {}
    for logical_name, path in files.items():
        file_metadata = {
            "name": path.name,
            "parents": [app_id],
        }
        try:
            media = MediaFileUpload(str(path), mimetype=_mime_for_file(path))

            @_upload_with_retry
            def _do_upload():
                return (
                    service.files()
                    .create(body=file_metadata, media_body=media, fields="id,webViewLink,name")
                    .execute()
                )

            file = _do_upload()
            uploads[logical_name] = {
                "status": "uploaded",
                "id": file["id"],
                "name": file["name"],
                "webViewLink": file.get(
                    "webViewLink", f"https://drive.google.com/file/d/{file['id']}"
                ),
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
