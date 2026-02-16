"""Tests for evals/hard.py — hard evaluation functions."""

from __future__ import annotations

import pytest

from evals.hard import (
    check_jd_schema,
    check_edit_scope,
    check_forbidden_claims,
    check_draft_length,
    check_cost,
)


class TestJDSchemaEval:
    def test_valid_schema_passes(self):
        jd = {
            "company": "Acme",
            "role": "PM",
            "location": "NYC",
            "experience_required": "3yr",
            "skills": ["Python"],
            "description": "A PM role.",
        }
        assert check_jd_schema(jd) is True

    def test_missing_field_fails(self):
        jd = {"company": "Acme", "role": "PM"}
        assert check_jd_schema(jd) is False


class TestEditScope:
    def test_no_violations(self):
        result = check_edit_scope(
            original_tex=r"%%BEGIN_EDITABLE\n\item A\n%%END_EDITABLE",
            mutated_tex=r"%%BEGIN_EDITABLE\n\item B\n%%END_EDITABLE",
            outside_changed=False,
        )
        assert result is True

    def test_outside_edit_violation(self):
        result = check_edit_scope(
            original_tex="\\section{Exp}",
            mutated_tex="\\section{Experience}",
            outside_changed=True,
        )
        assert result is False


class TestForbiddenClaims:
    def test_no_forbidden_claims(self):
        original_bullets = ["Led team of 5", "Built ML pipeline"]
        mutated_bullets = ["Led cross-functional team of 5", "Built scalable ML pipeline"]
        count = check_forbidden_claims(original_bullets, mutated_bullets, bullet_bank=[])
        assert count == 0

    def test_invented_company(self):
        original_bullets = ["Worked at Acme"]
        mutated_bullets = ["Worked at Google and Acme"]
        # "Google" was not in original or bullet bank — should flag
        count = check_forbidden_claims(
            original_bullets, mutated_bullets,
            bullet_bank=["Worked at Acme"],
        )
        assert count > 0


class TestDraftLength:
    def test_linkedin_under_limit(self):
        assert check_draft_length("Hi! Interested in the PM role at Acme.", max_chars=300) is True

    def test_linkedin_over_limit(self):
        assert check_draft_length("x" * 301, max_chars=300) is False

    def test_empty_draft_fails(self):
        assert check_draft_length("", max_chars=300) is False


class TestCost:
    def test_under_threshold(self):
        assert check_cost(0.05, threshold=0.15) is True

    def test_over_threshold(self):
        assert check_cost(0.20, threshold=0.15) is False

    def test_at_threshold(self):
        assert check_cost(0.15, threshold=0.15) is True
