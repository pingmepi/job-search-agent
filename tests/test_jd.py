"""Tests for JD schema validation (agents/inbox/jd.py)."""

from __future__ import annotations

import json
import pytest

from agents.inbox.jd import validate_jd_schema, JDSchema


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
