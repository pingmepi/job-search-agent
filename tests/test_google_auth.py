"""Tests for integrations/google_auth.py — token storage and auth flow."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from integrations.google_auth import (
    TOKEN_FILENAME,
    GoogleAuthNotConfigured,
    _bootstrap_token_from_env,
)


class TestTokenFilename:
    def test_is_json_not_pickle(self):
        assert TOKEN_FILENAME.endswith(".json")
        assert "pickle" not in TOKEN_FILENAME


class TestBootstrapTokenFromEnv:
    def test_decodes_b64_to_disk(self, tmp_path, monkeypatch):
        import base64

        token_data = json.dumps(
            {
                "token": "test123",
                "refresh_token": "ref",
                "client_id": "id",
                "client_secret": "sec",
            }
        )
        b64 = base64.b64encode(token_data.encode()).decode()
        monkeypatch.setenv("GOOGLE_TOKEN_B64", b64)

        token_path = tmp_path / "google_token.json"
        _bootstrap_token_from_env(token_path)

        assert token_path.exists()
        loaded = json.loads(token_path.read_text())
        assert loaded["token"] == "test123"

    def test_skips_if_token_exists(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_TOKEN_B64", "dGVzdA==")
        token_path = tmp_path / "google_token.json"
        token_path.write_text("existing")

        _bootstrap_token_from_env(token_path)
        assert token_path.read_text() == "existing"

    def test_skips_if_env_var_empty(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GOOGLE_TOKEN_B64", raising=False)
        token_path = tmp_path / "google_token.json"
        _bootstrap_token_from_env(token_path)
        assert not token_path.exists()

    def test_handles_invalid_b64(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GOOGLE_TOKEN_B64", "not-valid-base64!!!")
        token_path = tmp_path / "google_token.json"
        _bootstrap_token_from_env(token_path)
        # Should not crash, just log warning
        assert not token_path.exists()


class TestGetGoogleCredentials:
    def test_raises_when_no_creds_and_no_token(self, monkeypatch):
        fake_settings = SimpleNamespace(google_credentials_path="/nonexistent/creds.json")
        monkeypatch.setattr("core.config.get_settings", lambda: fake_settings)
        monkeypatch.delenv("GOOGLE_TOKEN_B64", raising=False)

        from integrations.google_auth import get_google_credentials

        with pytest.raises(GoogleAuthNotConfigured):
            get_google_credentials(interactive=False)
