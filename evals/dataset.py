"""
Curated eval fixture dataset for CI gate (KAR-60, PRD §12).

This module provides a deterministic set of 10+ eval cases that represent
expected pipeline behaviour. The CI gate runs thresholds against these
fixtures — independent of the live SQLite run history, which can be
polluted by dev/exploratory runs.

Each fixture is a dict with:
  - id           : human-readable label
  - eval_results : the eval payload as stored in runs.eval_results
  - cost_estimate: per-run USD cost (float)
  - latency_ms   : end-to-end latency in milliseconds (int)
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Fixture definitions
# ---------------------------------------------------------------------------
# Naming convention:
#   "pass_*" — represent successful, clean runs (should not trip any gate)
#   "fail_*" — represent policy-violating inputs (used in gate unit tests
#               to verify the thresholds *detect* violations)
#
# The baseline dataset (EVAL_FIXTURES) contains only well-formed runs that
# the system should always produce.  The gate reports FAIL only when the
# fixture dataset itself degrades below PRD §12 thresholds.

EvalFixture = dict[str, Any]

EVAL_FIXTURES: list[EvalFixture] = [
    # ── Compile-success cases ──────────────────────────────────────────────
    {
        "id": "pass_compile_ai_pm_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.85,
        },
        "cost_estimate": 0.04,
        "latency_ms": 22000,
    },
    {
        "id": "pass_compile_growth_pm_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.78,
        },
        "cost_estimate": 0.06,
        "latency_ms": 28000,
    },
    {
        "id": "pass_compile_martech_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.91,
        },
        "cost_estimate": 0.05,
        "latency_ms": 19000,
    },
    {
        "id": "pass_compile_senior_pm_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.82,
        },
        "cost_estimate": 0.07,
        "latency_ms": 31000,
    },
    {
        "id": "pass_compile_product_lead_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.76,
        },
        "cost_estimate": 0.03,
        "latency_ms": 17000,
    },
    {
        "id": "pass_compile_strategy_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.88,
        },
        "cost_estimate": 0.08,
        "latency_ms": 35000,
    },
    # ── Rollback-used cases (mutated compile failed → reverted to base resume) ──
    # compile_success is intentionally absent: the base resume itself compiled
    # successfully; only the mutated attempt failed.  The rollback flag signals
    # the recovery path was exercised.  This run should NOT penalise the
    # compile-success rate gate.
    {
        "id": "pass_rollback_used_no_violations",
        "eval_results": {
            "compile_rollback_used": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.70,
        },
        "cost_estimate": 0.09,
        "latency_ms": 42000,
    },
    # ── Additional passing case to ensure ≥ 10 compile-success records ──────
    {
        "id": "pass_compile_data_pm_role",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.79,
        },
        "cost_estimate": 0.06,
        "latency_ms": 25000,
    },
    # ── Minimal-cost free-model run ──────────────────────────────────────
    {
        "id": "pass_free_model_zero_cost",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.65,
        },
        "cost_estimate": 0.00,
        "latency_ms": 14000,
    },
    # ── Near-threshold cost (just under $0.15) ───────────────────────────
    {
        "id": "pass_near_cost_threshold",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.80,
        },
        "cost_estimate": 0.14,
        "latency_ms": 50000,
    },
    # ── Near-threshold latency (just under 60s) ──────────────────────────
    {
        "id": "pass_near_latency_threshold",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.83,
        },
        "cost_estimate": 0.05,
        "latency_ms": 58000,
    },
    # ── Exact-threshold cost/latency ──────────────────────────────────────
    {
        "id": "pass_exact_thresholds",
        "eval_results": {
            "compile_success": True,
            "edit_scope_violations": 0,
            "forbidden_claims_count": 0,
            "keyword_coverage": 0.77,
        },
        "cost_estimate": 0.15,
        "latency_ms": 60000,
    },
]

# ---------------------------------------------------------------------------
# Helpers used by the CI gate
# ---------------------------------------------------------------------------


def get_fixtures() -> list[EvalFixture]:
    """Return the canonical eval fixture list."""
    return list(EVAL_FIXTURES)


def fixture_summary(fixtures: list[EvalFixture]) -> dict[str, Any]:
    """
    Compute aggregate statistics over a list of fixtures.

    Returns a dict with keys:
      total, compile_total, compile_successes, compile_rate,
      total_forbidden, total_violations,
      costs (list), avg_cost, max_cost,
      latencies_ms (list), avg_latency_ms, max_latency_ms
    """
    total = len(fixtures)
    compile_total = 0
    compile_successes = 0
    total_forbidden = 0
    total_violations = 0
    costs: list[float] = []
    latencies: list[int] = []

    for fix in fixtures:
        er = fix.get("eval_results", {})

        if "compile_success" in er:
            compile_total += 1
            if er["compile_success"]:
                compile_successes += 1

        total_forbidden += er.get("forbidden_claims_count", 0)
        total_violations += er.get("edit_scope_violations", 0)

        cost = fix.get("cost_estimate")
        if cost is not None:
            costs.append(float(cost))

        lat = fix.get("latency_ms")
        if lat is not None:
            latencies.append(int(lat))

    compile_rate = (compile_successes / compile_total) if compile_total else None

    return {
        "total": total,
        "compile_total": compile_total,
        "compile_successes": compile_successes,
        "compile_rate": compile_rate,
        "total_forbidden": total_forbidden,
        "total_violations": total_violations,
        "costs": costs,
        "avg_cost": (sum(costs) / len(costs)) if costs else None,
        "max_cost": max(costs) if costs else None,
        "latencies_ms": latencies,
        "avg_latency_ms": (sum(latencies) / len(latencies)) if latencies else None,
        "max_latency_ms": max(latencies) if latencies else None,
    }
