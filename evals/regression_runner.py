"""Offline regression runner for inbox pipeline."""

from __future__ import annotations

import json
import time
from typing import Any, Callable

from evals.regression_dataset import RegressionCase, get_regression_cases


def _case_by_id(cases: list[RegressionCase], case_id: str) -> RegressionCase:
    for case in cases:
        if case["id"] == case_id:
            return case
    raise ValueError(f"Unknown regression case: {case_id}")


def _pipeline_executor(case: RegressionCase) -> dict[str, Any]:
    """Execute a regression case via inbox pipeline."""
    from agents.inbox.agent import run_pipeline
    from core.db import get_run

    image_path = case.get("image_path")
    pack = run_pipeline(
        case.get("raw_text", ""),
        image_path=image_path,
        selected_collateral=case.get("selected_collateral", []),
        skip_upload=True,
        skip_calendar=True,
        user_vetted=False,
    )
    run = get_run(pack.run_id) if pack.run_id else None
    return {
        "run_id": pack.run_id,
        "pack_eval_results": pack.eval_results,
        "pack_errors": list(pack.errors or []),
        "db_run": run,
    }


def _evaluate_case(case: RegressionCase, observed: dict[str, Any]) -> tuple[bool, list[str]]:
    expected = case.get("expected", {})
    failures: list[str] = []

    run = observed.get("db_run") or {}
    eval_results = run.get("eval_results") or observed.get("pack_eval_results") or {}
    outcome = run.get("task_outcome")
    error_types = run.get("error_types")

    allowed_outcomes = expected.get("task_outcome_in")
    if allowed_outcomes is not None and outcome not in allowed_outcomes:
        failures.append(
            f"task_outcome expected in {allowed_outcomes}, got {outcome!r}"
        )

    if "compile_success" in expected:
        got_compile = eval_results.get("compile_success")
        if got_compile is not expected["compile_success"]:
            failures.append(
                f"compile_success expected {expected['compile_success']}, got {got_compile!r}"
            )

    max_forbidden = expected.get("max_forbidden_claims")
    if max_forbidden is not None:
        got = int(eval_results.get("forbidden_claims_count", 0) or 0)
        if got > int(max_forbidden):
            failures.append(f"forbidden_claims_count expected <= {max_forbidden}, got {got}")

    max_violations = expected.get("max_edit_scope_violations")
    if max_violations is not None:
        got = int(eval_results.get("edit_scope_violations", 0) or 0)
        if got > int(max_violations):
            failures.append(f"edit_scope_violations expected <= {max_violations}, got {got}")

    min_keyword = expected.get("min_keyword_coverage")
    if min_keyword is not None:
        got = eval_results.get("keyword_coverage")
        if got is None or float(got) < float(min_keyword):
            failures.append(f"keyword_coverage expected >= {min_keyword}, got {got!r}")

    required_error_types = expected.get("require_error_types")
    if required_error_types:
        observed_types = set(error_types or [])
        missing = [et for et in required_error_types if et not in observed_types]
        if missing:
            failures.append(f"missing required error_types: {missing}")

    allowed_error_types = expected.get("allow_error_types")
    if allowed_error_types is not None and error_types is not None:
        disallowed = [et for et in error_types if et not in set(allowed_error_types)]
        if disallowed:
            failures.append(f"disallowed error_types present: {disallowed}")

    return (len(failures) == 0, failures)


def run_regression(
    *,
    case_id: str | None = None,
    executor: Callable[[RegressionCase], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run full regression suite or a single case."""
    cases = get_regression_cases()
    if case_id:
        cases = [_case_by_id(cases, case_id)]

    exec_fn = executor or _pipeline_executor
    started = time.time()
    results: list[dict[str, Any]] = []

    for case in cases:
        t0 = time.time()
        try:
            observed = exec_fn(case)
            passed, failures = _evaluate_case(case, observed)
            results.append(
                {
                    "id": case["id"],
                    "description": case.get("description", ""),
                    "passed": passed,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "failures": failures,
                    "run_id": observed.get("run_id"),
                    "task_outcome": (observed.get("db_run") or {}).get("task_outcome"),
                    "error_types": (observed.get("db_run") or {}).get("error_types"),
                }
            )
        except Exception as exc:
            results.append(
                {
                    "id": case["id"],
                    "description": case.get("description", ""),
                    "passed": False,
                    "duration_ms": int((time.time() - t0) * 1000),
                    "failures": [f"execution_error: {exc}"],
                    "run_id": None,
                    "task_outcome": None,
                    "error_types": None,
                }
            )

    passed_count = sum(1 for r in results if r["passed"])
    failed_count = len(results) - passed_count
    return {
        "suite": "inbox_regression_v1",
        "total_cases": len(results),
        "passed": passed_count,
        "failed": failed_count,
        "duration_ms": int((time.time() - started) * 1000),
        "results": results,
    }


def format_regression_report(report: dict[str, Any]) -> str:
    """Format regression result for terminal output."""
    lines = ["# Regression Run", ""]
    lines.append(f"Suite: `{report['suite']}`")
    lines.append(
        f"Cases: {report['total_cases']}  Passed: {report['passed']}  Failed: {report['failed']}"
    )
    lines.append(f"Duration: {report['duration_ms']}ms")
    lines.append("")
    lines.append("| Case | Status | Outcome | Errors |")
    lines.append("| --- | --- | --- | --- |")
    for row in report.get("results", []):
        status = "PASS" if row["passed"] else "FAIL"
        outcome = row.get("task_outcome") or "-"
        error_types = row.get("error_types")
        error_cell = "null" if error_types is None else (", ".join(error_types) if error_types else "[]")
        lines.append(f"| `{row['id']}` | {status} | {outcome} | {error_cell} |")
        if row.get("failures"):
            for failure in row["failures"]:
                lines.append(f"  - {failure}")
    lines.append("")
    return "\n".join(lines)


def main(*, json_output: bool = False, case_id: str | None = None) -> None:
    """CLI entrypoint for regression run."""
    report = run_regression(case_id=case_id)
    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_regression_report(report))
