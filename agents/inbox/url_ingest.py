"""URL ingestion helpers for job-description fetching."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

_URL_PATTERN = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass
class URLIngestResult:
    """Result of URL ingestion attempt."""

    url: str
    ok: bool
    extracted_text: str = ""
    error: str | None = None


def extract_first_url(text: str) -> str | None:
    """Return the first HTTP(S) URL found in text."""
    match = _URL_PATTERN.search(text or "")
    return match.group(0) if match else None


def _html_to_text(raw_html: str) -> str:
    """Convert HTML into rough plain text for downstream JD extraction."""
    content = _SCRIPT_STYLE_RE.sub(" ", raw_html)
    content = _TAG_RE.sub(" ", content)
    content = html.unescape(content)
    return _WS_RE.sub(" ", content).strip()


def fetch_url_text(url: str, *, timeout_seconds: float = 8.0) -> URLIngestResult:
    """Fetch URL content and return extracted plain text."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return URLIngestResult(url=url, ok=False, error="Unsupported URL scheme")
    if not parsed.netloc:
        return URLIngestResult(url=url, ok=False, error="Invalid URL")

    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
            )
        },
    )

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            charset = resp.headers.get_content_charset() or "utf-8"
            body = resp.read().decode(charset, errors="replace")
    except HTTPError as e:
        return URLIngestResult(url=url, ok=False, error=f"HTTP {e.code}")
    except URLError as e:
        return URLIngestResult(url=url, ok=False, error=f"Network error: {e.reason}")
    except Exception as e:  # pragma: no cover - defensive
        return URLIngestResult(url=url, ok=False, error=str(e))

    extracted_text = _html_to_text(body)
    if len(extracted_text) < 120:
        return URLIngestResult(
            url=url,
            ok=False,
            extracted_text=extracted_text,
            error="Insufficient extracted text",
        )
    return URLIngestResult(url=url, ok=True, extracted_text=extracted_text)
