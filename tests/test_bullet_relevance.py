"""Tests for bullet bank relevance scoring."""

from agents.inbox.bullet_relevance import (
    _normalize_company,
    score_bullet_relevance,
    select_relevant_bullets,
)


class TestScoreBulletRelevance:
    def test_perfect_tag_match(self):
        bullet = {"bullet": "Led ML pipeline", "tags": ["ml", "python"]}
        score = score_bullet_relevance(bullet, ["ml", "python"], "")
        assert score > 0.5

    def test_no_match(self):
        bullet = {"bullet": "Built marketing pipeline", "tags": ["marketing", "crm"]}
        score = score_bullet_relevance(bullet, ["kubernetes", "go"], "")
        assert score == 0.0

    def test_partial_tag_match(self):
        bullet = {"bullet": "Led team", "tags": ["ml", "python", "data"]}
        score = score_bullet_relevance(bullet, ["ml"], "")
        assert 0.0 < score < 1.0

    def test_keyword_overlap_in_bullet_text(self):
        bullet = {"bullet": "Built python automation for data pipeline", "tags": []}
        score = score_bullet_relevance(bullet, ["python", "automation"], "")
        assert score > 0.0  # keyword match even without tags

    def test_empty_skills_returns_zero(self):
        bullet = {"bullet": "anything", "tags": ["ml"]}
        assert score_bullet_relevance(bullet, [], "") == 0.0

    def test_hyphen_normalization(self):
        bullet = {"bullet": "Built system", "tags": ["marketing-automation"]}
        score = score_bullet_relevance(bullet, ["marketing automation"], "")
        assert score > 0.0

    def test_no_tags_no_keyword_match(self):
        bullet = {"bullet": "irrelevant content", "tags": []}
        assert score_bullet_relevance(bullet, ["python"], "") == 0.0

    def test_none_in_skills_does_not_crash(self):
        bullet = {"bullet": "Built python automation", "tags": ["python"]}
        score = score_bullet_relevance(bullet, ["python", None, "sql"], "")
        assert score > 0.0

    def test_all_none_skills_returns_zero(self):
        bullet = {"bullet": "anything", "tags": ["ml"]}
        assert score_bullet_relevance(bullet, [None, None], "") == 0.0

    def test_none_bullet_text_does_not_crash(self):
        bullet = {"bullet": None, "tags": ["python"]}
        score = score_bullet_relevance(bullet, ["python"], "")
        assert score >= 0.0

    def test_none_tag_does_not_crash(self):
        bullet = {"bullet": "test", "tags": [None, "python"]}
        score = score_bullet_relevance(bullet, ["python"], "")
        assert score >= 0.0


class TestSelectRelevantBullets:
    def _make_bank(self, n: int) -> list[dict]:
        return [{"id": f"b-{i}", "bullet": f"Bullet {i}", "tags": [f"skill-{i}"]} for i in range(n)]

    def test_top_n_respected(self):
        bank = self._make_bank(20)
        result = select_relevant_bullets(bank, ["skill-0"], "", top_n=5)
        assert len(result) == 5

    def test_fewer_than_n_returns_all(self):
        bank = self._make_bank(3)
        result = select_relevant_bullets(bank, ["skill-0"], "", top_n=10)
        assert len(result) == 3

    def test_sorted_by_score_descending(self):
        bank = [
            {"id": "low", "bullet": "nothing relevant", "tags": ["unrelated"]},
            {"id": "high", "bullet": "python ml expert", "tags": ["python", "ml"]},
        ]
        result = select_relevant_bullets(bank, ["python", "ml"], "")
        assert result[0]["id"] == "high"

    def test_relevance_score_attached(self):
        bank = [{"id": "a", "bullet": "test", "tags": ["python"]}]
        result = select_relevant_bullets(bank, ["python"], "")
        assert "_relevance_score" in result[0]
        assert isinstance(result[0]["_relevance_score"], float)


class TestNormalizeCompany:
    def test_lowercase_and_trim(self):
        assert _normalize_company("  Acme  ") == "acme"

    def test_strip_inc_suffix(self):
        assert _normalize_company("Acme Inc") == "acme"
        assert _normalize_company("Acme Inc.") == "acme"

    def test_strip_llc_ltd_corp(self):
        assert _normalize_company("Acme LLC") == "acme"
        assert _normalize_company("Acme Ltd") == "acme"
        assert _normalize_company("Acme Corp") == "acme"

    def test_strip_longest_suffix_wins(self):
        # "corporation" must strip before "corp" matches partially.
        assert _normalize_company("Acme Corporation") == "acme"

    def test_no_suffix_unchanged(self):
        assert _normalize_company("Google") == "google"

    def test_none_and_empty(self):
        assert _normalize_company(None) == ""
        assert _normalize_company("") == ""
        assert _normalize_company("   ") == ""

    def test_internal_whitespace_collapsed(self):
        assert _normalize_company("Miles  Education") == "miles education"


class TestTargetReferenceFilter:
    def _bank(self) -> list[dict]:
        return [
            {"id": "a-1", "bullet": "Did A work", "tags": ["python"], "reference": "Acme Inc"},
            {"id": "a-2", "bullet": "More A work", "tags": ["python"], "reference": "Acme Inc."},
            {"id": "b-1", "bullet": "Did B work", "tags": ["python"], "reference": "Globex LLC"},
        ]

    def test_target_reference_none_returns_all(self):
        result = select_relevant_bullets(self._bank(), ["python"], "", target_reference=None)
        assert len(result) == 3

    def test_target_reference_filters_other_companies(self):
        result = select_relevant_bullets(self._bank(), ["python"], "", target_reference="Acme")
        assert {b["id"] for b in result} == {"a-1", "a-2"}

    def test_target_reference_case_and_suffix_insensitive(self):
        result = select_relevant_bullets(self._bank(), ["python"], "", target_reference="acme corp")
        # "acme corp" normalizes to "acme", matches Acme Inc / Acme Inc.
        assert {b["id"] for b in result} == {"a-1", "a-2"}

    def test_target_reference_no_match_falls_back_to_full_bank(self):
        # Applying to a never-worked-at company: filter yields 0,
        # so we fall back to the unscoped bank to preserve prior behavior.
        result = select_relevant_bullets(self._bank(), ["python"], "", target_reference="Initech")
        assert len(result) == 3

    def test_target_reference_excludes_bullets_with_missing_reference(self):
        bank = [
            {"id": "a-1", "bullet": "Acme work", "tags": ["python"], "reference": "Acme"},
            {"id": "u-1", "bullet": "Unknown work", "tags": ["python"]},
            {"id": "u-2", "bullet": "Empty ref", "tags": ["python"], "reference": ""},
        ]
        result = select_relevant_bullets(bank, ["python"], "", target_reference="Acme")
        assert {b["id"] for b in result} == {"a-1"}

    def test_target_reference_empty_string_treated_as_none(self):
        result = select_relevant_bullets(self._bank(), ["python"], "", target_reference="")
        assert len(result) == 3
