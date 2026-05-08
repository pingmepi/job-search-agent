"""
Eval trend report — reads production run artifacts and prints a markdown summary.

Usage:
    python main.py eval-report              # markdown table to stdout
    python main.py eval-report --json       # raw JSON to stdout

Reads from runs/artifacts/*/eval_output.json (local files, no DB needed).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.config import get_settings


def _load_eval_artifacts(artifacts_dir: Path | None = None) -> list[dict[str, Any]]:
    """Load all eval_output.json files from the artifacts directory."""
    if artifacts_dir is None:
        artifacts_dir = get_settings().runs_dir / "artifacts"

    if not artifacts_dir.exists():
        return []

    results: list[dict[str, Any]] = []
    for eval_path in sorted(artifacts_dir.glob("*/eval_output.json")):
        try:
            data = json.loads(eval_path.read_text(encoding="utf-8"))
            data["_source_path"] = str(eval_path)
            results.append(data)
        except (json.JSONDecodeError, OSError):
            continue

    return results


def _extract_metrics(artifact: dict[str, Any]) -> dict[str, Any]:
    """Extract a flat metrics dict from an eval_output artifact."""
    er = artifact.get("eval_results", {})

    # Sum total tokens across all steps
    total_tokens = er.get("llm_total_tokens", 0)
    total_cost = er.get("llm_total_cost", 0.0)

    return {
        "run_id": artifact.get("run_id", "?"),
        "created_at": artifact.get("created_at", "?"),
        "compile_success": er.get("compile_success"),
        "compile_rollback_used": er.get("compile_rollback_used", False),
        "compile_outcome": er.get("compile_outcome"),
        "task_type": artifact.get("task_type"),
        "task_outcome": artifact.get("task_outcome"),
        "error_types": artifact.get("error_types"),
        "prompt_versions": artifact.get("prompt_versions"),
        "models_used": artifact.get("models_used"),
        "feedback_label": artifact.get("feedback_label"),
        "feedback_reason": artifact.get("feedback_reason"),
        "forbidden_claims": er.get("forbidden_claims_count", 0),
        "scope_violations": er.get("mutation_summary", {}).get("scope_violations_count", 0),
        "edit_violations": er.get("edit_scope_violations", 0),
        "draft_length_ok": er.get("draft_length_ok"),
        "cost_ok": er.get("cost_ok"),
        "keyword_coverage": er.get("keyword_coverage"),
        "jd_schema_valid": er.get("jd_schema_valid"),
        "single_page_met": er.get("single_page_target_met"),
        "single_page_status": er.get("single_page_status"),
        "condense_retries": er.get("condense_retries", 0),
        "soft_resume_relevance": er.get("soft_resume_relevance"),
        "soft_jd_accuracy": er.get("soft_jd_accuracy"),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
    }


def build_report(artifacts_dir: Path | None = None) -> dict[str, Any]:
    """
    Build a structured report from all eval artifacts.

    Returns a dict with:
      - runs: list of per-run metrics
      - summary: aggregate statistics
    """
    raw = _load_eval_artifacts(artifacts_dir)
    if not raw:
        return {"runs": [], "summary": {}}

    runs = [_extract_metrics(a) for a in raw]

    # ── Aggregate stats ───────────────────────────────────────────
    compile_runs = [r for r in runs if r["compile_success"] is not None]
    compile_successes = sum(1 for r in compile_runs if r["compile_success"])
    compile_rate = compile_successes / len(compile_runs) if compile_runs else None

    total_forbidden = sum(r["forbidden_claims"] for r in runs)
    total_violations = sum(r["edit_violations"] for r in runs)

    relevance_scores = [
        r["soft_resume_relevance"] for r in runs if r["soft_resume_relevance"] is not None
    ]
    accuracy_scores = [r["soft_jd_accuracy"] for r in runs if r["soft_jd_accuracy"] is not None]

    total_tokens_all = [r["total_tokens"] for r in runs if r["total_tokens"]]
    total_costs_all = [r["total_cost"] for r in runs if r["total_cost"] is not None]
    success_count = sum(1 for r in runs if r.get("task_outcome") == "success")
    partial_count = sum(1 for r in runs if r.get("task_outcome") == "partial")
    fail_count = sum(1 for r in runs if r.get("task_outcome") == "fail")
    helpful_count = sum(1 for r in runs if r.get("feedback_label") == "helpful")
    not_helpful_count = sum(1 for r in runs if r.get("feedback_label") == "not_helpful")
    no_error_runs = 0
    null_error_type_runs = 0
    error_type_counts: dict[str, int] = {}
    for r in runs:
        error_types = r.get("error_types")
        if error_types is None:
            null_error_type_runs += 1
        elif not error_types:
            no_error_runs += 1
        else:
            for error_type in error_types:
                error_type_counts[error_type] = error_type_counts.get(error_type, 0) + 1

    summary = {
        "total_runs": len(runs),
        "compile_rate": compile_rate,
        "compile_successes": compile_successes,
        "compile_total": len(compile_runs),
        "total_forbidden_claims": total_forbidden,
        "total_edit_violations": total_violations,
        "avg_resume_relevance": (
            sum(relevance_scores) / len(relevance_scores) if relevance_scores else None
        ),
        "min_resume_relevance": min(relevance_scores) if relevance_scores else None,
        "max_resume_relevance": max(relevance_scores) if relevance_scores else None,
        "avg_jd_accuracy": (
            sum(accuracy_scores) / len(accuracy_scores) if accuracy_scores else None
        ),
        "min_jd_accuracy": min(accuracy_scores) if accuracy_scores else None,
        "max_jd_accuracy": max(accuracy_scores) if accuracy_scores else None,
        "avg_tokens": (sum(total_tokens_all) / len(total_tokens_all) if total_tokens_all else None),
        "total_cost": sum(total_costs_all) if total_costs_all else 0.0,
        "success_count": success_count,
        "partial_count": partial_count,
        "fail_count": fail_count,
        "helpful_count": helpful_count,
        "not_helpful_count": not_helpful_count,
        "no_error_runs": no_error_runs,
        "null_error_type_runs": null_error_type_runs,
        "error_type_counts": error_type_counts,
    }

    return {"runs": runs, "summary": summary}


def format_markdown(report: dict[str, Any]) -> str:
    """Format the report as a markdown string."""
    runs = report.get("runs", [])
    summary = report.get("summary", {})

    if not runs:
        return "⚠️  No eval artifacts found in `runs/artifacts/`.\n"

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────
    lines.append("# Eval Trend Report")
    lines.append("")
    lines.append(f"**{summary['total_runs']} production runs** analyzed")
    lines.append("")

    # ── Summary ───────────────────────────────────────────────────
    lines.append("## Summary")
    lines.append("")

    compile_rate = summary.get("compile_rate")
    if compile_rate is not None:
        icon = "✅" if compile_rate >= 0.95 else "❌"
        lines.append("| Metric | Value | Status |")
        lines.append("| --- | --- | --- |")
        lines.append(
            f"| Compile rate | {compile_rate:.0%}"
            f" ({summary['compile_successes']}/{summary['compile_total']}) | {icon} |"
        )
    else:
        lines.append("| Metric | Value | Status |")
        lines.append("| --- | --- | --- |")

    fc = summary["total_forbidden_claims"]
    lines.append(f"| Forbidden claims | {fc} | {'✅' if fc == 0 else '❌'} |")
    ev = summary["total_edit_violations"]
    lines.append(f"| Edit violations | {ev} | {'✅' if ev == 0 else '❌'} |")

    avg_rel = summary.get("avg_resume_relevance")
    if avg_rel is not None:
        lines.append(
            f"| Resume relevance (avg) | {avg_rel:.2f}"
            f" [{summary['min_resume_relevance']:.2f}–{summary['max_resume_relevance']:.2f}]"
            f" | {'✅' if avg_rel >= 0.7 else '⚠️'} |"
        )
    avg_acc = summary.get("avg_jd_accuracy")
    if avg_acc is not None:
        lines.append(
            f"| JD accuracy (avg) | {avg_acc:.2f}"
            f" [{summary['min_jd_accuracy']:.2f}–{summary['max_jd_accuracy']:.2f}]"
            f" | {'✅' if avg_acc >= 0.8 else '⚠️'} |"
        )

    avg_tok = summary.get("avg_tokens")
    if avg_tok is not None:
        lines.append(f"| Avg tokens/run | {avg_tok:,.0f} | ℹ️ |")
    lines.append(f"| Total LLM cost | ${summary.get('total_cost', 0):.4f} | ℹ️ |")
    if summary.get("success_count") or summary.get("partial_count") or summary.get("fail_count"):
        lines.append(
            f"| Outcomes | success={summary.get('success_count', 0)}, partial={summary.get('partial_count', 0)}, fail={summary.get('fail_count', 0)} | ℹ️ |"
        )
    if summary.get("helpful_count") or summary.get("not_helpful_count"):
        lines.append(
            f"| Feedback | helpful={summary.get('helpful_count', 0)}, not_helpful={summary.get('not_helpful_count', 0)} | ℹ️ |"
        )
    lines.append(
        f"| Error classification coverage | none={summary.get('no_error_runs', 0)}, null={summary.get('null_error_type_runs', 0)} | ℹ️ |"
    )

    lines.append("")

    error_type_counts = summary.get("error_type_counts", {})
    if error_type_counts:
        lines.append("## Error Types")
        lines.append("")
        lines.append("| Error type | Count |")
        lines.append("| --- | --- |")
        for error_type, count in sorted(
            error_type_counts.items(),
            key=lambda item: (-item[1], item[0]),
        ):
            lines.append(f"| `{error_type}` | {count} |")
        lines.append("")

    # ── Per-run table ─────────────────────────────────────────────
    lines.append("## Per-Run Detail")
    lines.append("")
    lines.append(
        "| Run | Date | Outcome | Errors | Compile | Rollback | Forbidden | Scope Viol | Relevance | JD Acc | Tokens |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")

    for r in runs:
        run_id = r["run_id"]
        date = r["created_at"][:10] if r["created_at"] != "?" else "?"

        compile_icon = "—"
        if r["compile_success"] is True:
            compile_icon = "✅"
        elif r["compile_success"] is False:
            compile_icon = "❌"

        rollback = "yes" if r["compile_rollback_used"] else "no"
        forbidden = str(r["forbidden_claims"])
        scope_viol = str(r.get("scope_violations", 0))
        relevance = (
            f"{r['soft_resume_relevance']:.2f}" if r["soft_resume_relevance"] is not None else "—"
        )
        accuracy = f"{r['soft_jd_accuracy']:.2f}" if r["soft_jd_accuracy"] is not None else "—"
        tokens = f"{r['total_tokens']:,}" if r["total_tokens"] else "—"
        outcome = r.get("task_outcome") or "—"
        error_types = r.get("error_types")
        if error_types is None:
            error_cell = "null"
        elif not error_types:
            error_cell = "[]"
        else:
            error_cell = ", ".join(error_types)

        lines.append(
            f"| `{run_id}` | {date} | {outcome} | {error_cell} | {compile_icon}"
            f" | {rollback} | {forbidden} | {scope_viol} | {relevance} | {accuracy} | {tokens} |"
        )

    lines.append("")
    return "\n".join(lines)


def main(*, json_output: bool = False, artifacts_dir: Path | None = None) -> None:
    """Entry point for the eval-report CLI command."""
    report = build_report(artifacts_dir)

    if json_output:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(format_markdown(report))
