"""Tests for bullet bank relevance scoring."""

from agents.inbox.bullet_relevance import score_bullet_relevance, select_relevant_bullets


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


class TestSelectRelevantBullets:
    def _make_bank(self, n: int) -> list[dict]:
        return [
            {"id": f"b-{i}", "bullet": f"Bullet {i}", "tags": [f"skill-{i}"]}
            for i in range(n)
        ]

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
