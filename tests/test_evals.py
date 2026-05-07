"""Tests for evals/hard.py — hard evaluation functions."""

from __future__ import annotations

from agents.inbox.resume import EditableRegion
from evals.hard import (
    check_cost,
    check_draft_length,
    check_edit_scope,
    check_forbidden_claims,
    check_forbidden_claims_per_bullet,
    check_jd_schema,
    check_scope_violations,
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
            original_bullets,
            mutated_bullets,
            bullet_bank=["Worked at Acme"],
        )
        assert count > 0

    def test_invented_numeric_metric(self):
        original_bullets = ["Improved retention by 10%"]
        mutated_bullets = ["Improved retention by 35%"]
        count = check_forbidden_claims(original_bullets, mutated_bullets, bullet_bank=[])
        assert count > 0


class TestForbiddenClaimsPerBullet:
    def test_returns_list_of_dicts(self):
        results = check_forbidden_claims_per_bullet(
            ["Led team of 5"],
            ["Led team of 5"],
            bullet_bank=[],
        )
        assert isinstance(results, list)
        assert len(results) == 1
        assert "flagged" in results[0]
        assert "reasons" in results[0]

    def test_clean_bullets_not_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Led team of 5", "Built ML pipeline"],
            ["Led cross-functional team of 5", "Built scalable ML pipeline"],
            bullet_bank=[],
        )
        assert all(not r["flagged"] for r in results)

    def test_only_bad_bullet_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Worked at Acme", "Led team of 5"],
            ["Worked at Goldman Sachs", "Led team of 5"],
            bullet_bank=[],
        )
        assert results[0]["flagged"] is True  # Goldman Sachs is new
        assert results[1]["flagged"] is False  # unchanged

    def test_allowed_tools_not_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Built system"],
            ["Built system using Python and Tableau"],
            bullet_bank=[],
            allowed_tools=["Python", "Tableau"],
        )
        assert all(not r["flagged"] for r in results)

    def test_common_words_not_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Did work"],
            ["Product roadmap defined for the team"],
            bullet_bank=[],
        )
        # "Product" is in the common skip set
        flagged_ents = [r for r in results[0]["reasons"] if "product" in r]
        assert len(flagged_ents) == 0

    def test_jd_terms_not_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Built system"],
            ["Built Kubernetes deployment pipeline"],
            bullet_bank=[],
            jd_text="Kubernetes deployment experience required",
        )
        assert all(not r["flagged"] for r in results)

    def test_real_company_still_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Built system"],
            ["Built system at Goldman Sachs"],
            bullet_bank=[],
            jd_text="remote startup role",
        )
        assert results[0]["flagged"] is True
        assert any("goldman sachs" in r for r in results[0]["reasons"])

    def test_invented_metric_flagged(self):
        results = check_forbidden_claims_per_bullet(
            ["Improved retention by 10%"],
            ["Improved retention by 35%"],
            bullet_bank=[],
        )
        assert results[0]["flagged"] is True
        assert any("35" in r for r in results[0]["reasons"])


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


class TestScopeViolations:
    def _region(self, content: str, reference: str | None) -> EditableRegion:
        return EditableRegion(content=content, start_line=1, end_line=2, reference=reference)

    def _bank(self) -> list[dict]:
        return [
            {"id": "miles-001", "bullet": "Miles bullet", "reference": "Miles Education"},
            {"id": "upgrad-001", "bullet": "upGrad bullet", "reference": "upGrad"},
        ]

    def test_no_violations_when_bullet_matches_region(self):
        regions = [self._region("Miles bullet", "Miles Education")]
        mutations = [{"type": "SWAP", "source": "bank:miles-001", "original": "Miles bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []

    def test_violation_when_bullet_placed_in_wrong_region(self):
        regions = [self._region("some upGrad bullet", "upGrad")]
        mutations = [{"type": "SWAP", "source": "bank:miles-001", "original": "some upGrad bullet"}]
        violations = check_scope_violations(mutations, regions, self._bank())
        assert len(violations) == 1
        assert violations[0]["bullet_id"] == "miles-001"
        assert violations[0]["placed_in_region"] == "upGrad"
        assert violations[0]["bullet_reference"] == "Miles Education"

    def test_rewrite_mutations_never_flagged(self):
        regions = [self._region("some bullet", "upGrad")]
        mutations = [{"type": "REWRITE", "source": "bank:miles-001", "original": "some bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []

    def test_generate_mutations_never_flagged(self):
        regions = [self._region("some bullet", "upGrad")]
        mutations = [{"type": "GENERATE", "source": "profile:x", "original": "some bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []

    def test_unscoped_region_not_flagged(self):
        regions = [self._region("Miles bullet", None)]
        mutations = [{"type": "SWAP", "source": "bank:miles-001", "original": "Miles bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []

    def test_unknown_bullet_id_not_flagged(self):
        regions = [self._region("some bullet", "upGrad")]
        mutations = [{"type": "SWAP", "source": "bank:nonexistent", "original": "some bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []

    def test_empty_mutations_returns_empty(self):
        regions = [self._region("Miles bullet", "Miles Education")]
        assert check_scope_violations([], regions, self._bank()) == []

    def test_original_not_in_any_region_skipped(self):
        regions = [self._region("other content entirely", "upGrad")]
        mutations = [{"type": "SWAP", "source": "bank:miles-001", "original": "Miles bullet"}]
        assert check_scope_violations(mutations, regions, self._bank()) == []
