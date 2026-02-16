"""Tests for URL ingestion helpers."""

from __future__ import annotations

from agents.inbox.url_ingest import extract_first_url, fetch_url_text


def test_extract_first_url_returns_first_match() -> None:
    text = "See https://example.com/a and then http://example.org/b"
    assert extract_first_url(text) == "https://example.com/a"


def test_extract_first_url_none_when_no_url() -> None:
    assert extract_first_url("no links here") is None


def test_fetch_url_text_invalid_scheme() -> None:
    result = fetch_url_text("ftp://example.com/file")
    assert result.ok is False
    assert "Unsupported URL scheme" in (result.error or "")


def test_fetch_url_text_success(monkeypatch) -> None:
    class _FakeHeaders:
        @staticmethod
        def get_content_charset():
            return "utf-8"

    class _FakeResponse:
        headers = _FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        @staticmethod
        def read():
            body = (
                "<html><body><h1>JD</h1>"
                + ("This is a long job description sentence. " * 20)
                + "</body></html>"
            )
            return body.encode("utf-8")

    monkeypatch.setattr("agents.inbox.url_ingest.urlopen", lambda *_args, **_kwargs: _FakeResponse())
    result = fetch_url_text("https://example.com/job")
    assert result.ok is True
    assert "job description" in result.extracted_text.lower()
