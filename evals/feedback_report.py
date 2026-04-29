"""Feedback-loop reporting and run annotation helpers."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any

from core.config import get_settings
from core.db import get_run, list_runs_for_feedback_report, update_run_feedback
from core.feedback import (
    FEEDBACK_LABEL_HELPFUL,
    FEEDBACK_LABEL_NOT_HELPFUL,
    VALID_FEEDBACK_LABELS,
    VALID_FEEDBACK_REASONS,
    summarize_error_types,
)


def annotate_run_feedback(
    run_id: str,
    *,
    feedback_label: str,
    feedback_reason: str | None = None,
) -> None:
    """Update DB state and mirror operator feedback into the eval artifact."""
    if feedback_label not in VALID_FEEDBACK_LABELS:
        raise ValueError(f"Invalid feedback label: {feedback_label}")
    if feedback_label == FEEDBACK_LABEL_HELPFUL and feedback_reason is not None:
        raise ValueError("Helpful feedback must not include a reason")
    if feedback_label == FEEDBACK_LABEL_NOT_HELPFUL and feedback_reason not in VALID_FEEDBACK_REASONS:
        raise ValueError("Not-helpful feedback requires a valid reason")

    run = get_run(run_id)
    if run is None:
        raise ValueError(f"Run not found: {run_id}")

    update_run_feedback(
        run_id,
        feedback_label=feedback_label,
        feedback_reason=feedback_reason,
    )
    _update_eval_artifact(
        run_id,
        feedback_label=feedback_label,
        feedback_reason=feedback_reason,
    )


def _update_eval_artifact(
    run_id: str,
    *,
    feedback_label: str,
    feedback_reason: str | None,
) -> None:
    artifact_path = get_settings().runs_dir / "artifacts" / run_id / "eval_output.json"
    if not artifact_path.exists():
        return

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    payload["feedback_label"] = feedback_label
    payload["feedback_reason"] = feedback_reason
    artifact_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_feedback_report(*, days: int = 7) -> dict[str, Any]:
    """Build a compact operator-facing report from persisted runs."""
    runs = list_runs_for_feedback_report(days=days)
    outcome_counts: Counter[str] = Counter()
    feedback_counts: Counter[str] = Counter()
    error_counts: Counter[str] = Counter()
    task_outcomes: dict[str, Counter[str]] = {}
    prompt_outcomes: dict[str, Counter[str]] = {}
    model_outcomes: dict[str, Counter[str]] = {}
    no_error_runs = 0
    null_error_type_runs = 0

    for run in runs:
        outcome = run.get("task_outcome")
        if outcome:
            outcome_counts[outcome] += 1
            task_type = run.get("task_type") or "unknown"
            task_outcomes.setdefault(task_type, Counter())[outcome] += 1

        feedback_label = run.get("feedback_label")
        if feedback_label:
            feedback_counts[feedback_label] += 1

        error_types = run.get("error_types")
        if error_types is None:
            null_error_type_runs += 1
        elif not error_types:
            no_error_runs += 1
        else:
            error_counts.update(summarize_error_types(error_types))

        for prompt in run.get("prompt_versions") or []:
            prompt_outcomes.setdefault(prompt, Counter())[outcome or "unknown"] += 1
        for model in run.get("models_used") or []:
            model_outcomes.setdefault(model, Counter())[outcome or "unknown"] += 1

    worst_task_types = []
    for task_type, counts in task_outcomes.items():
        total = sum(counts.values())
        fail_rate = (counts.get("fail", 0) / total) if total else 0.0
        worst_task_types.append({"task_type": task_type, "fail_rate": fail_rate, "total": total})
    worst_task_types.sort(key=lambda item: (-item["fail_rate"], -item["total"], item["task_type"]))

    return {
        "days": days,
        "total_runs": len(runs),
        "outcomes": dict(outcome_counts),
        "feedback": dict(feedback_counts),
        "top_error_types": error_counts.most_common(5),
        "no_error_runs": no_error_runs,
        "null_error_type_runs": null_error_type_runs,
        "worst_task_types": worst_task_types[:3],
        "prompt_performance": _rank_dimensions(prompt_outcomes),
        "model_performance": _rank_dimensions(model_outcomes),
    }


def _rank_dimensions(counts_by_name: dict[str, Counter[str]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for name, counts in counts_by_name.items():
        total = sum(counts.values())
        if not total:
            continue
        ranked.append(
            {
                "name": name,
                "total": total,
                "success": counts.get("success", 0),
                "partial": counts.get("partial", 0),
                "fail": counts.get("fail", 0),
                "success_rate": counts.get("success", 0) / total,
            }
        )
    ranked.sort(key=lambda item: (-item["success_rate"], -item["total"], item["name"]))
    return ranked[:5]


def format_feedback_report(report: dict[str, Any]) -> str:
    """Render the feedback report as markdown."""
    lines = ["# Feedback Report", ""]
    lines.append(f"Window: last {report['days']} days")
    lines.append(f"Runs: {report['total_runs']}")
    lines.append("")

    outcomes = report.get("outcomes", {})
    feedback = report.get("feedback", {})
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Success | {outcomes.get('success', 0)} |")
    lines.append(f"| Partial | {outcomes.get('partial', 0)} |")
    lines.append(f"| Fail | {outcomes.get('fail', 0)} |")
    lines.append(f"| Helpful | {feedback.get(FEEDBACK_LABEL_HELPFUL, 0)} |")
    lines.append(f"| Not helpful | {feedback.get(FEEDBACK_LABEL_NOT_HELPFUL, 0)} |")
    lines.append(f"| Runs with no classified errors | {report.get('no_error_runs', 0)} |")
    lines.append(f"| Runs with null error classifications | {report.get('null_error_type_runs', 0)} |")
    lines.append("")

    lines.append("## Error Types")
    lines.append("")
    if report.get("top_error_types"):
        lines.append("| Error type | Count |")
        lines.append("| --- | --- |")
        for error_type, count in report["top_error_types"]:
            lines.append(f"| `{error_type}` | {count} |")
    else:
        lines.append("No classified errors in the selected window.")
    lines.append("")

    lines.append("## Weak Spots")
    lines.append("")
    if report.get("worst_task_types"):
        for item in report["worst_task_types"]:
            lines.append(
                f"- `{item['task_type']}` fail_rate={item['fail_rate']:.0%} total={item['total']}"
            )
    else:
        lines.append("No task-type outcome data available.")
    lines.append("")

    lines.append("## Prompt Versions")
    lines.append("")
    if report.get("prompt_performance"):
        for item in report["prompt_performance"]:
            lines.append(
                f"- `{item['name']}` success={item['success']} partial={item['partial']} fail={item['fail']}"
            )
    else:
        lines.append("No prompt-version data available.")
    lines.append("")

    lines.append("## Models")
    lines.append("")
    if report.get("model_performance"):
        for item in report["model_performance"]:
            lines.append(
                f"- `{item['name']}` success={item['success']} partial={item['partial']} fail={item['fail']}"
            )
    else:
        lines.append("No model attribution data available.")
    lines.append("")
    return "\n".join(lines)
