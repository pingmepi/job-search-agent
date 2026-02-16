"""
CI gate — exits non-zero if eval thresholds are breached.

Usage:
    python -m evals.ci_gate

Reads the latest run results from SQLite and checks:
  - compile_success rate ≥ 95%
  - forbidden_claims == 0 (across all runs)
  - edit_violations == 0
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from core.db import get_conn


def run_gate() -> bool:
    """
    Check eval results across all runs.

    Returns True if all gates pass, False otherwise.
    """
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT eval_results FROM runs WHERE eval_results IS NOT NULL"
        ).fetchall()

    if not rows:
        print("⚠️  No eval results found — gate passes vacuously.")
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

    # ── Check thresholds ──────────────────────────
    passed = True

    if total_compiles > 0:
        compile_rate = compile_successes / total_compiles
        if compile_rate < 0.95:
            print(f"❌ Compile success rate: {compile_rate:.1%} (threshold: 95%)")
            passed = False
        else:
            print(f"✅ Compile success rate: {compile_rate:.1%}")

    if total_forbidden > 0:
        print(f"❌ Forbidden claims: {total_forbidden} (threshold: 0)")
        passed = False
    else:
        print(f"✅ Forbidden claims: 0")

    if total_violations > 0:
        print(f"❌ Edit scope violations: {total_violations} (threshold: 0)")
        passed = False
    else:
        print(f"✅ Edit scope violations: 0")

    return passed


def main() -> None:
    if run_gate():
        print("\n🎉 All CI gates passed.")
        sys.exit(0)
    else:
        print("\n💥 CI gate FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()
