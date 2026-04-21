"""
Google Drive integration — upload artifacts to structured folders.

Folder structure: {ROOT_FOLDER}/{company_slug}_{role_slug}_{run_id}/
Files are renamed on upload to {CandidateName}_{Company}_{logical_name}.{ext}.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from integrations.google_auth import get_google_credentials, google_api_retry

logger = logging.getLogger(__name__)

ROOT_FOLDER_NAME = "Job search agent"
DEFAULT_CANDIDATE_NAME = "Mandalam_Karan"

_LOGICAL_NAME_MAP = {
    "resume_pdf": "resume",
    "email": "email",
    "linkedin": "linkedin",
    "referral": "referral",
}


def _slug(value: str, fallback: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return text or fallback


def _clean_company_for_filename(company: str) -> str:
    """Keep case, replace unsafe filename chars with underscores."""
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (company or "").strip()).strip("_")
    return cleaned or "Company"


def _build_filename(
    candidate_name: str, company: str, logical_name: str, original_path: Path
) -> str:
    short = _LOGICAL_NAME_MAP.get(logical_name, logical_name)
    company_clean = _clean_company_for_filename(company)
    return f"{candidate_name}_{company_clean}_{short}{original_path.suffix}"


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
        run_id="legacy",
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
    run_id: Optional[str] = None,
    candidate_name: str = DEFAULT_CANDIDATE_NAME,
) -> dict:
    """
    Upload selected application artifacts to Google Drive.

    Folder layout: {ROOT_FOLDER_NAME}/{company_slug}_{role_slug}_{run_id}/
    Filenames: {candidate_name}_{Company}_{logical_name}.{ext}
    """
    service = _get_drive_service()

    subfolder_token = run_id or application_context_id or "run"
    subfolder_name = f"{_slug(company, 'company')}_{_slug(role, 'role')}_{subfolder_token}"

    root_id = _find_or_create_folder(service, ROOT_FOLDER_NAME)
    app_id = _find_or_create_folder(service, subfolder_name, root_id)

    from googleapiclient.http import MediaFileUpload

    _upload_with_retry = google_api_retry()

    uploads: dict[str, dict[str, str]] = {}
    for logical_name, path in files.items():
        upload_name = _build_filename(candidate_name, company, logical_name, path)
        file_metadata = {
            "name": upload_name,
            "parents": [app_id],
        }
        try:
            media = MediaFileUpload(str(path), mimetype=_mime_for_file(path))

            @_upload_with_retry
            def _do_upload(meta=file_metadata, m=media):
                return (
                    service.files()
                    .create(body=meta, media_body=m, fields="id,webViewLink,name")
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
            logger.info("Uploaded %s as %s to Drive", path.name, upload_name)
        except Exception as upload_err:
            uploads[logical_name] = {
                "status": "failed",
                "error": str(upload_err),
                "name": upload_name,
            }

    return {
        "folder": {
            "id": app_id,
            "path": f"{ROOT_FOLDER_NAME}/{subfolder_name}",
        },
        "files": uploads,
    }
