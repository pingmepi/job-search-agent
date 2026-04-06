"""
Tests for evals/ci_gate.py — CI gate logic (KAR-60, PRD §7, §12).

All tests use inline fixture dicts and do NOT touch the live SQLite DB.
Covers: all individual threshold failures, passing baselines, edge cases,
and the curated EVAL_FIXTURES dataset itself.
"""

from __future__ import annotations

import pytest

from evals.ci_gate import (
    COST_THRESHOLD,
    LATENCY_THRESHOLD_MS,
    run_gate_on_fixtures,
)
from evals.dataset import EVAL_FIXTURES, fixture_summary, get_fixtures

# ── Helpers ──────────────────────────────────────────────────────────────────


def _fix(
    *,
    compile_success: bool = True,
    forbidden: int = 0,
    violations: int = 0,
    cost: float = 0.05,
    latency_ms: int = 20_000,
) -> dict:
    """Build a minimal fixture dict for parametrised tests."""
    return {
        "id": "test_fixture",
        "eval_results": {
            "compile_success": compile_success,
            "forbidden_claims_count": forbidden,
            "edit_scope_violations": violations,
        },
        "cost_estimate": cost,
        "latency_ms": latency_ms,
    }


# ── Dataset sanity tests ──────────────────────────────────────────────────────


class TestEvalDataset:
    def test_dataset_has_at_least_ten_fixtures(self):
        """PRD §12 requires 10+ eval cases."""
        assert len(EVAL_FIXTURES) >= 10

    def test_fixture_ids_are_unique(self):
        ids = [f["id"] for f in EVAL_FIXTURES]
        assert len(ids) == len(set(ids)), "Fixture IDs must be unique"

    def test_all_fixtures_have_required_keys(self):
        for fix in EVAL_FIXTURES:
            assert "id" in fix
            assert "eval_results" in fix
            assert "cost_estimate" in fix
            assert "latency_ms" in fix

    def test_get_fixtures_returns_copy(self):
        a = get_fixtures()
        b = get_fixtures()
        assert a == b
        assert a is not b  # independent lists

    def test_fixture_summary_counts_are_consistent(self):
        stats = fixture_summary(EVAL_FIXTURES)
        assert stats["total"] == len(EVAL_FIXTURES)
        assert stats["compile_successes"] <= stats["compile_total"]
        assert stats["compile_total"] <= stats["total"]


# ── Passing gate tests ────────────────────────────────────────────────────────


class TestGatePasses:
    def test_all_clean_fixtures_pass(self):
        fixtures = [_fix() for _ in range(10)]
        assert run_gate_on_fixtures(fixtures) is True

    def test_empty_dataset_passes_vacuously(self):
        """Empty fixture list should pass (nothing to evaluate)."""
        assert run_gate_on_fixtures([]) is True

    def test_exactly_at_cost_threshold_passes(self):
        fixtures = [_fix(cost=COST_THRESHOLD)]
        assert run_gate_on_fixtures(fixtures) is True

    def test_exactly_at_latency_threshold_passes(self):
        fixtures = [_fix(latency_ms=LATENCY_THRESHOLD_MS)]
        assert run_gate_on_fixtures(fixtures) is True

    def test_curated_fixture_dataset_passes_gate(self):
        """The canonical EVAL_FIXTURES must pass every PRD §12 threshold."""
        assert run_gate_on_fixtures(EVAL_FIXTURES) is True


# ── Failing gate tests ────────────────────────────────────────────────────────


class TestGateFails:
    def test_compile_rate_below_threshold_fails(self):
        """All compile failures → 0 % < 95 % threshold."""
        fixtures = [_fix(compile_success=False) for _ in range(10)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_compile_rate_exactly_at_boundary_fails(self):
        """94 % compile rate (just below 95 %) must fail."""
        # 94 successes out of 100
        fixtures = [_fix(compile_success=True)] * 94 + [_fix(compile_success=False)] * 6
        assert run_gate_on_fixtures(fixtures) is False

    def test_single_forbidden_claim_fails(self):
        fixtures = [_fix(forbidden=1)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_multiple_forbidden_claims_fails(self):
        fixtures = [_fix(forbidden=0), _fix(forbidden=3), _fix(forbidden=0)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_single_edit_violation_fails(self):
        fixtures = [_fix(violations=1)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_avg_cost_above_threshold_fails(self):
        """Average cost above $0.15 must fail."""
        fixtures = [_fix(cost=0.20), _fix(cost=0.20), _fix(cost=0.20)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_avg_latency_above_threshold_fails(self):
        """Average latency above 60 000 ms must fail."""
        fixtures = [_fix(latency_ms=90_000), _fix(latency_ms=90_000)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_one_bad_fixture_in_otherwise_clean_set_fails(self):
        """A single forbidden claim in a 10-fixture set must still fail."""
        fixtures = [_fix()] * 9 + [_fix(forbidden=1)]
        assert run_gate_on_fixtures(fixtures) is False

    def test_compile_zero_percent_fails(self):
        """0% compile rate is the worst case — must fail clearly."""
        fixtures = [_fix(compile_success=False)]
        assert run_gate_on_fixtures(fixtures) is False


# ── fixture_summary unit tests ────────────────────────────────────────────────


class TestFixtureSummary:
    def test_compile_rate_calculated_correctly(self):
        fixtures = [_fix(compile_success=True)] * 3 + [_fix(compile_success=False)] * 1
        stats = fixture_summary(fixtures)
        assert stats["compile_rate"] == pytest.approx(0.75)

    def test_avg_cost_calculated_correctly(self):
        fixtures = [_fix(cost=0.10), _fix(cost=0.20)]
        stats = fixture_summary(fixtures)
        assert stats["avg_cost"] == pytest.approx(0.15)

    def test_avg_latency_calculated_correctly(self):
        fixtures = [_fix(latency_ms=20_000), _fix(latency_ms=40_000)]
        stats = fixture_summary(fixtures)
        assert stats["avg_latency_ms"] == pytest.approx(30_000)

    def test_empty_list_returns_none_for_rates(self):
        stats = fixture_summary([])
        assert stats["compile_rate"] is None
        assert stats["avg_cost"] is None
        assert stats["avg_latency_ms"] is None
