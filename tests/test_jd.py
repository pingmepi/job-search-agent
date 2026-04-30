"""Tests for JD schema validation (agents/inbox/jd.py)."""

from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from agents.inbox.jd import (
    _fill_missing_required_fields,
    _parse_json_object_from_llm_text,
    extract_jd_with_usage,
    validate_jd_schema,
)


class TestJDSchemaValidation:
    def test_valid_jd(self):
        data = {
            "company": "Acme Corp",
            "role": "AI Product Manager",
            "location": "San Francisco, CA",
            "experience_required": "3-5 years",
            "skills": ["Python", "SQL", "Product Management"],
            "description": "Lead AI product strategy and execution.",
        }
        jd = validate_jd_schema(data)
        assert jd.company == "Acme Corp"
        assert len(jd.skills) == 3

    def test_missing_required_field(self):
        data = {
            "role": "PM",
            "location": "Remote",
            "experience_required": "",
            "skills": [],
            "description": "A role.",
        }
        with pytest.raises(ValueError):
            validate_jd_schema(data)

    def test_skills_must_be_list(self):
        data = {
            "company": "Test",
            "role": "PM",
            "location": "NYC",
            "experience_required": "",
            "skills": "Python, SQL",  # string instead of list
            "description": "A role.",
        }
        with pytest.raises((ValueError, TypeError)):
            validate_jd_schema(data)

    def test_empty_strings_allowed_for_optional(self):
        data = {
            "company": "Test",
            "role": "PM",
            "location": "",
            "experience_required": "",
            "skills": [],
            "description": "",
        }
        jd = validate_jd_schema(data)
        assert jd.location == ""

    def test_fill_missing_required_fields_infers_company_and_role(self):
        raw_text = (
            "Acme Corp is hiring for a Senior Product Manager.\n"
            "Location: Remote\n"
            "Build AI products."
        )
        normalized = _fill_missing_required_fields(
            {"company": "", "role": "", "skills": []},
            raw_text,
        )
        assert normalized["company"] == "Acme Corp"
        assert "Senior Product Manager" in normalized["role"]

    def test_fill_missing_required_fields_uses_safe_defaults(self):
        normalized = _fill_missing_required_fields(
            {"company": "", "role": "", "skills": []},
            "No obvious metadata here",
        )
        assert normalized["company"] == "Unknown Company"
        assert normalized["role"] == "Unknown Role"

    def test_parse_json_from_fenced_response(self):
        parsed = _parse_json_object_from_llm_text(
            'Here you go:\n```json\n{"company":"Acme","role":"PM","skills":[]}\n```'
        )
        assert parsed["company"] == "Acme"
        assert parsed["role"] == "PM"

    def test_parse_json_from_prefixed_response(self):
        parsed = _parse_json_object_from_llm_text(
            'Result: {"company":"Acme","role":"PM","skills":[]} -- done'
        )
        assert parsed["company"] == "Acme"
        assert parsed["role"] == "PM"

    def test_extract_jd_with_usage_retries_after_invalid_json(self, monkeypatch):
        calls = {"count": 0}

        def _chat_text(_system: str, _user: str, *, json_mode: bool = False):
            assert json_mode is True
            calls["count"] += 1
            if calls["count"] == 1:
                return SimpleNamespace(
                    text="I cannot comply right now.",
                    model="test-model",
                    prompt_tokens=1,
                    completion_tokens=1,
                    total_tokens=2,
                    cost_estimate=0.0,
                    generation_id=None,
                )
            return SimpleNamespace(
                text='{"company":"Acme Corp","role":"Senior PM","location":"Remote","experience_required":"","skills":["Python"],"description":"desc"}',
                model="test-model",
                prompt_tokens=3,
                completion_tokens=2,
                total_tokens=5,
                cost_estimate=0.01,
                generation_id="gen-1",
            )

        fake_llm = SimpleNamespace(chat_text=_chat_text)
        fake_prompts = SimpleNamespace(load_prompt=lambda _name, version=1: "prompt")
        monkeypatch.setitem(sys.modules, "core.llm", fake_llm)
        monkeypatch.setitem(sys.modules, "core.prompts", fake_prompts)

        jd, usage = extract_jd_with_usage("Acme Corp is hiring Senior PM")

        assert calls["count"] == 2
        assert jd.company == "Acme Corp"
        assert jd.role == "Senior PM"
        assert usage["total_tokens"] == 5

    def test_extract_jd_with_usage_retries_transient_error(self, monkeypatch):
        calls = {"count": 0}

        def _chat_text(_system: str, _user: str, *, json_mode: bool = False):
            assert json_mode is True
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("Error code: 429 - Too Many Requests")
            return SimpleNamespace(
                text='{"company":"Acme Corp","role":"PM","location":"","experience_required":"","skills":[],"description":""}',
                model="test-model",
                prompt_tokens=2,
                completion_tokens=1,
                total_tokens=3,
                cost_estimate=0.0,
                generation_id=None,
            )

        fake_llm = SimpleNamespace(chat_text=_chat_text)
        fake_prompts = SimpleNamespace(load_prompt=lambda _name, version=1: "prompt")
        monkeypatch.setitem(sys.modules, "core.llm", fake_llm)
        monkeypatch.setitem(sys.modules, "core.prompts", fake_prompts)

        jd, _usage = extract_jd_with_usage("Acme Corp is hiring PM")

        assert calls["count"] == 2
        assert jd.company == "Acme Corp"
