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
    assert result.error_type == "unsupported_scheme"


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
        def read(size=-1):
            body = (
                "<html><body><h1>JD</h1>"
                + ("This is a long job description sentence. " * 20)
                + "</body></html>"
            )
            return body.encode("utf-8")

    monkeypatch.setattr(
        "agents.inbox.url_ingest.urlopen", lambda *_args, **_kwargs: _FakeResponse()
    )
    monkeypatch.setattr("agents.inbox.url_ingest._is_safe_url", lambda url: (True, ""))
    result = fetch_url_text("https://example.com/job")
    assert result.ok is True
    assert "job description" in result.extracted_text.lower()
    assert result.error_type is None


class TestSSRFProtection:
    def test_blocks_localhost(self, monkeypatch):
        monkeypatch.setattr(
            "agents.inbox.url_ingest.socket.getaddrinfo",
            lambda *args, **kwargs: [(2, 1, 0, "", ("127.0.0.1", 80))],
        )
        result = fetch_url_text("http://localhost/evil")
        assert result.ok is False
        assert result.error_type == "ssrf_blocked"

    def test_blocks_cloud_metadata(self, monkeypatch):
        monkeypatch.setattr(
            "agents.inbox.url_ingest.socket.getaddrinfo",
            lambda *args, **kwargs: [(2, 1, 0, "", ("169.254.169.254", 80))],
        )
        result = fetch_url_text("http://metadata.internal/latest/")
        assert result.ok is False
        assert result.error_type == "ssrf_blocked"

    def test_blocks_private_ip(self, monkeypatch):
        monkeypatch.setattr(
            "agents.inbox.url_ingest.socket.getaddrinfo",
            lambda *args, **kwargs: [(2, 1, 0, "", ("10.0.0.1", 80))],
        )
        result = fetch_url_text("http://internal-service.local/api")
        assert result.ok is False
        assert result.error_type == "ssrf_blocked"

    def test_allows_public_ip(self, monkeypatch):
        monkeypatch.setattr(
            "agents.inbox.url_ingest.socket.getaddrinfo",
            lambda *args, **kwargs: [(2, 1, 0, "", ("93.184.216.34", 80))],
        )
        # Still need to mock urlopen since we're not actually fetching
        monkeypatch.setattr(
            "agents.inbox.url_ingest.urlopen",
            lambda *a, **kw: (_ for _ in ()).throw(Exception("not testing fetch")),
        )
        result = fetch_url_text("https://example.com/job")
        # Should get past SSRF check (fail on fetch mock, not SSRF)
        assert result.error_type != "ssrf_blocked"
