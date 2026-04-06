"""
CI gate — exits non-zero if eval thresholds are breached (KAR-60, PRD §7, §12).

Usage:
    python main.py ci-gate
    python -m evals.ci_gate

Gate logic (primary — fixture-based):
  Runs PRD §12 thresholds against the curated fixture dataset in
  evals/dataset.py.  This is deterministic and independent of live
  DB history, which can be polluted by dev / exploratory runs.

  Thresholds:
    - compile_success rate  ≥ 95%
    - forbidden_claims      == 0  (total across all fixtures)
    - edit_scope_violations == 0  (total across all fixtures)
    - avg cost_estimate     ≤ $0.15
    - avg latency_ms        ≤ 60 000 ms  (60 s)

Informational report (secondary — live DB):
  Prints compile rate, forbidden claims, and edit violations from
  actual SQLite run history for situational awareness.  These do NOT
  block CI.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from core.db import get_conn
from evals.dataset import fixture_summary, get_fixtures

# ── Threshold constants (PRD §12) ────────────────────────────────
COMPILE_RATE_THRESHOLD = 0.95  # 95 %
FORBIDDEN_CLAIMS_MAX = 0  # zero tolerance
EDIT_VIOLATIONS_MAX = 0  # zero tolerance
COST_THRESHOLD = 0.15  # USD per run
LATENCY_THRESHOLD_MS = 60_000  # 60 seconds


# ── Fixture-based gate ────────────────────────────────────────────


def run_gate_on_fixtures(
    fixtures: list[dict[str, Any]] | None = None,
) -> bool:
    """
    Run CI thresholds against the curated eval fixture dataset.

    Parameters
    ----------
    fixtures:
        Optional override for the fixture list (used in tests).
        Defaults to evals.dataset.get_fixtures().

    Returns
    -------
    True if all thresholds pass, False otherwise.
    """
    if fixtures is None:
        fixtures = get_fixtures()

    if not fixtures:
        print("⚠️  Fixture dataset is empty — gate passes vacuously.")
        return True

    stats = fixture_summary(fixtures)
    passed = True

    # ── Compile success rate ──────────────────────────────────────
    if stats["compile_rate"] is not None:
        rate = stats["compile_rate"]
        if rate < COMPILE_RATE_THRESHOLD:
            print(
                f"❌ [fixture] Compile success rate: {rate:.1%}"
                f" (threshold: {COMPILE_RATE_THRESHOLD:.0%})"
            )
            passed = False
        else:
            print(f"✅ [fixture] Compile success rate: {rate:.1%}")

    # ── Forbidden claims ──────────────────────────────────────────
    total_forbidden = stats["total_forbidden"]
    if total_forbidden > FORBIDDEN_CLAIMS_MAX:
        print(f"❌ [fixture] Forbidden claims: {total_forbidden} (threshold: 0)")
        passed = False
    else:
        print("✅ [fixture] Forbidden claims: 0")

    # ── Edit scope violations ─────────────────────────────────────
    total_violations = stats["total_violations"]
    if total_violations > EDIT_VIOLATIONS_MAX:
        print(f"❌ [fixture] Edit scope violations: {total_violations} (threshold: 0)")
        passed = False
    else:
        print("✅ [fixture] Edit scope violations: 0")

    # ── Avg cost ──────────────────────────────────────────────────
    if stats["avg_cost"] is not None:
        avg_cost = stats["avg_cost"]
        if avg_cost > COST_THRESHOLD:
            print(f"❌ [fixture] Avg cost: ${avg_cost:.4f} (threshold: ${COST_THRESHOLD:.2f})")
            passed = False
        else:
            print(f"✅ [fixture] Avg cost: ${avg_cost:.4f} (max: ${stats['max_cost']:.4f})")

    # ── Avg latency ───────────────────────────────────────────────
    if stats["avg_latency_ms"] is not None:
        avg_lat = stats["avg_latency_ms"]
        if avg_lat > LATENCY_THRESHOLD_MS:
            print(
                f"❌ [fixture] Avg latency: {avg_lat / 1000:.1f}s"
                f" (threshold: {LATENCY_THRESHOLD_MS / 1000:.0f}s)"
            )
            passed = False
        else:
            print(
                f"✅ [fixture] Avg latency: {avg_lat / 1000:.1f}s"
                f" (max: {stats['max_latency_ms'] / 1000:.1f}s)"
            )

    return passed


# ── Live DB informational report ─────────────────────────────────


def _report_db_stats() -> None:
    """Print live DB metrics as informational output (non-blocking)."""
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT eval_results, cost_estimate, latency_ms"
                " FROM runs WHERE eval_results IS NOT NULL"
            ).fetchall()
    except Exception as exc:
        print(f"ℹ️  [db] Could not read run history: {exc}")
        return

    if not rows:
        print("ℹ️  [db] No historical run data found.")
        return

    total_compiles = 0
    compile_successes = 0
    total_forbidden = 0
    total_violations = 0
    costs: list[float] = []
    latencies: list[int] = []

    for row in rows:
        results = json.loads(row["eval_results"])

        if "compile_success" in results:
            total_compiles += 1
            if results["compile_success"]:
                compile_successes += 1

        total_forbidden += results.get("forbidden_claims_count", 0)
        total_violations += results.get("edit_scope_violations", 0)

        if row["cost_estimate"] is not None:
            costs.append(float(row["cost_estimate"]))
        if row["latency_ms"] is not None:
            latencies.append(int(row["latency_ms"]))

    print("\n── Live DB (informational, non-blocking) ────────────────")
    if total_compiles:
        rate = compile_successes / total_compiles
        symbol = "✅" if rate >= COMPILE_RATE_THRESHOLD else "⚠️ "
        print(
            f"{symbol} [db] Compile success rate: {rate:.1%} ({compile_successes}/{total_compiles})"
        )
    symbol = "✅" if total_forbidden == 0 else "⚠️ "
    print(f"{symbol} [db] Forbidden claims: {total_forbidden}")
    symbol = "✅" if total_violations == 0 else "⚠️ "
    print(f"{symbol} [db] Edit scope violations: {total_violations}")
    if costs:
        avg = sum(costs) / len(costs)
        symbol = "✅" if avg <= COST_THRESHOLD else "⚠️ "
        print(f"{symbol} [db] Avg cost: ${avg:.4f} (n={len(costs)})")
    if latencies:
        avg = sum(latencies) / len(latencies)
        symbol = "✅" if avg <= LATENCY_THRESHOLD_MS else "⚠️ "
        print(f"{symbol} [db] Avg latency: {avg / 1000:.1f}s (n={len(latencies)})")
    print("─────────────────────────────────────────────────────────\n")


# ── Legacy DB-only gate (kept for backwards compat / testing) ────


def run_gate() -> bool:
    """
    Legacy gate: check eval results across all historical DB runs.

    This is kept for backwards compatibility but is no longer the
    primary CI signal.  Use run_gate_on_fixtures() instead.
    """
    try:
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT eval_results FROM runs WHERE eval_results IS NOT NULL"
            ).fetchall()
    except Exception:
        return True

    if not rows:
        return True

    total_compiles = 0
    compile_successes = 0
    total_forbidden = 0
    total_violations = 0

    for row in rows:
        results = json.loads(row["eval_results"])
        if "compile_success" in results:
            total_compiles += 1
            if results["compile_success"]:
                compile_successes += 1
        total_forbidden += results.get("forbidden_claims_count", 0)
        total_violations += results.get("edit_scope_violations", 0)

    passed = True
    if total_compiles > 0:
        rate = compile_successes / total_compiles
        if rate < COMPILE_RATE_THRESHOLD:
            passed = False
    if total_forbidden > FORBIDDEN_CLAIMS_MAX:
        passed = False
    if total_violations > EDIT_VIOLATIONS_MAX:
        passed = False

    return passed


# ── Entrypoint ───────────────────────────────────────────────────


def main() -> None:
    print("── Fixture-based CI gate (PRD §12) ──────────────────────")
    fixture_passed = run_gate_on_fixtures()

    _report_db_stats()

    if fixture_passed:
        print("🎉 All CI gates passed.")
        sys.exit(0)
    else:
        print("💥 CI gate FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
