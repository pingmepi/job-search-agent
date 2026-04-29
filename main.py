"""
Main entry point for the inbox-agent system.

Usage:
    python main.py webhook                       # Start Telegram webhook service
    python main.py init-db                       # Initialize database
    python main.py ci-gate                       # Run CI eval gate
    python main.py eval-report [--json]          # Print eval trend report from run artifacts
    python main.py feedback <run_id> ...         # Attach operator feedback to a completed run
    python main.py feedback-report [--days N]    # Summarize feedback-loop metrics from DB
    python main.py regression-run [options]      # Run inbox regression suite
    python main.py db-stats                      # Show DB summary for debugging
    python main.py pipeline-check                # Run pipeline integrity checks
    python main.py followup-runner [options]     # Run scheduled follow-up detection
    python main.py replay-webhook [options]      # Replay persisted webhook event
    python main.py build-skill-index             # Rebuild profile/skill_index.json
"""

from __future__ import annotations

import json
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stdout,
)


def _parse_replay_webhook_args(args: list[str]) -> dict[str, object]:
    opts: dict[str, object] = {
        "event_id": None,
        "update_id": None,
    }
    i = 0
    while i < len(args):
        token = args[i]
        if token == "--event-id":
            if i + 1 >= len(args):
                raise ValueError("--event-id requires a value")
            opts["event_id"] = args[i + 1]
            i += 1
        elif token == "--update-id":
            if i + 1 >= len(args):
                raise ValueError("--update-id requires a value")
            opts["update_id"] = int(args[i + 1])
            i += 1
        else:
            raise ValueError(f"Unknown replay-webhook argument: {token}")
        i += 1

    if bool(opts["event_id"]) == bool(opts["update_id"]):
        raise ValueError("Provide exactly one of --event-id or --update-id")
    return opts


def _run_replay_webhook(args: list[str]) -> None:
    import asyncio

    from telegram import Update

    from agents.inbox.adapter import create_bot
    from core.db import get_webhook_event

    opts = _parse_replay_webhook_args(args)
    event = get_webhook_event(
        event_id=opts["event_id"],  # type: ignore[arg-type]
        update_id=opts["update_id"],  # type: ignore[arg-type]
    )
    if event is None:
        raise ValueError("Webhook event not found")

    payload = event.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("Stored webhook payload is missing or invalid")

    async def _replay() -> None:
        tg_app = create_bot()
        await tg_app.initialize()
        await tg_app.start()
        try:
            update = Update.de_json(payload, tg_app.bot)
            if update is None:
                raise ValueError("Stored payload cannot be parsed as Telegram Update")
            await tg_app.process_update(update)
        finally:
            await tg_app.stop()
            await tg_app.shutdown()

    asyncio.run(_replay())
    print(
        "Webhook replay completed:"
        f" event_id={event.get('event_id')}"
        f" update_id={event.get('update_id')}"
    )


def _parse_followup_runner_args(args: list[str]) -> dict:
    opts = {
        "once": False,
        "dry_run": False,
        "persist_progress": True,
        "interval_minutes": 60,
        "max_cycles": None,
    }

    i = 0
    while i < len(args):
        token = args[i]
        if token == "--once":
            opts["once"] = True
        elif token == "--dry-run":
            opts["dry_run"] = True
        elif token == "--no-persist-progress":
            opts["persist_progress"] = False
        elif token == "--interval-minutes":
            if i + 1 >= len(args):
                raise ValueError("--interval-minutes requires a value")
            opts["interval_minutes"] = int(args[i + 1])
            i += 1
        elif token == "--max-cycles":
            if i + 1 >= len(args):
                raise ValueError("--max-cycles requires a value")
            opts["max_cycles"] = int(args[i + 1])
            i += 1
        else:
            raise ValueError(f"Unknown followup-runner argument: {token}")
        i += 1

    if opts["max_cycles"] is not None and opts["max_cycles"] <= 0:
        raise ValueError("--max-cycles must be > 0")
    if opts["interval_minutes"] <= 0:
        raise ValueError("--interval-minutes must be > 0")

    return opts


def _parse_feedback_args(args: list[str]) -> dict[str, object]:
    if not args:
        raise ValueError("feedback requires a run_id")
    opts: dict[str, object] = {
        "run_id": args[0],
        "label": None,
        "reason": None,
    }
    i = 1
    while i < len(args):
        token = args[i]
        if token == "--label":
            if i + 1 >= len(args):
                raise ValueError("--label requires a value")
            opts["label"] = args[i + 1]
            i += 1
        elif token == "--reason":
            if i + 1 >= len(args):
                raise ValueError("--reason requires a value")
            opts["reason"] = args[i + 1]
            i += 1
        else:
            raise ValueError(f"Unknown feedback argument: {token}")
        i += 1

    if not opts["label"]:
        raise ValueError("feedback requires --label")
    return opts


def _parse_feedback_report_args(args: list[str]) -> dict[str, int]:
    opts = {"days": 7}
    i = 0
    while i < len(args):
        token = args[i]
        if token == "--days":
            if i + 1 >= len(args):
                raise ValueError("--days requires a value")
            opts["days"] = int(args[i + 1])
            i += 1
        else:
            raise ValueError(f"Unknown feedback-report argument: {token}")
        i += 1
    if opts["days"] <= 0:
        raise ValueError("--days must be > 0")
    return opts


def _parse_regression_run_args(args: list[str]) -> dict[str, object]:
    opts: dict[str, object] = {
        "json_output": False,
        "case_id": None,
    }
    i = 0
    while i < len(args):
        token = args[i]
        if token == "--json":
            opts["json_output"] = True
        elif token == "--case":
            if i + 1 >= len(args):
                raise ValueError("--case requires a value")
            opts["case_id"] = args[i + 1]
            i += 1
        else:
            raise ValueError(f"Unknown regression-run argument: {token}")
        i += 1
    return opts


def _run_followup_runner(args: list[str]) -> None:
    from agents.followup.runner import run_followup_cycle, run_scheduler

    opts = _parse_followup_runner_args(args)
    if opts["once"]:
        result = run_followup_cycle(
            dry_run=opts["dry_run"],
            persist_progress=opts["persist_progress"],
        )
        print(
            "Follow-up runner once:"
            f" run_id={result['run_id']}"
            f" jobs={result['count']}"
            f" dry_run={result['dry_run']}"
            f" persist_progress={result['persist_progress']}"
        )
        return

    results = run_scheduler(
        interval_minutes=opts["interval_minutes"],
        max_cycles=opts["max_cycles"],
        dry_run=opts["dry_run"],
        persist_progress=opts["persist_progress"],
    )
    print(
        "Follow-up runner finished:"
        f" cycles={len(results)}"
        f" total_jobs={sum(r['count'] for r in results)}"
        f" dry_run={opts['dry_run']}"
        f" persist_progress={opts['persist_progress']}"
    )


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command in {"webhook", "bot"}:
        from app import run_webhook_server

        run_webhook_server()

    elif command == "init-db":
        from core.db import init_db

        init_db()
        print("✅ Database initialized")

    elif command == "ci-gate":
        from evals.ci_gate import main as run_gate

        run_gate()

    elif command == "db-stats":
        from core.db import get_db_stats

        stats = get_db_stats()
        print(
            "Jobs:"
            f" total={stats['jobs'].get('total_jobs', 0)}"
            f" applied={stats['jobs'].get('applied_jobs', 0)}"
            f" follow_up_zero={stats['jobs'].get('follow_up_zero', 0)}"
            f" fit_score_nulls={stats['jobs'].get('fit_score_nulls', 0)}"
            f" drive_link_empty={stats['jobs'].get('drive_link_empty', 0)}"
        )
        print(
            "Runs:"
            f" total={stats['runs'].get('total_runs', 0)}"
            f" completed={stats['runs'].get('completed_runs', 0)}"
            f" tokens_nulls={stats['runs'].get('tokens_nulls', 0)}"
            f" latency_nulls={stats['runs'].get('latency_nulls', 0)}"
            f" with_errors={stats['runs'].get('runs_with_errors', 0)}"
        )
        print(
            "Compile:"
            f" success={stats['compile'].get('compile_successes', 0)}"
            f" failure={stats['compile'].get('compile_failures', 0)}"
        )
        print(
            "Webhook events:"
            f" total={stats['webhook_events'].get('total_events', 0)}"
            f" processed={stats['webhook_events'].get('processed_events', 0)}"
            f" failed={stats['webhook_events'].get('failed_events', 0)}"
        )

    elif command == "pipeline-check":
        from core.pipeline_checks import run_pipeline_checks

        result = run_pipeline_checks()
        print(f"Pipeline integrity: {'PASS' if result['ok'] else 'FAIL'}")
        print("Stats:")
        for key, value in result["stats"].items():
            print(f"  - {key}: {value}")
        if result["warnings"]:
            print("Warnings:")
            for warning in result["warnings"]:
                print(f"  - {warning}")
        if result["errors"]:
            print("Errors:")
            for error in result["errors"]:
                print(f"  - {error}")
            sys.exit(2)

    elif command == "runs":
        from core.db import get_run, get_run_steps, list_runs

        args = sys.argv[2:]
        if args and not args[0].startswith("--"):
            run_id = args[0]
            show_steps = "--steps" in args

            run = get_run(run_id)
            if not run:
                print(f"Run not found: {run_id}")
            else:
                print(json.dumps(run, indent=2, default=str))

                if show_steps:
                    steps = get_run_steps(run_id)
                    if not steps:
                        print("\nNo step audit data for this run.")
                    else:
                        print(f"\n--- Steps ({len(steps)}) ---")
                        for s in steps:
                            status_icon = "✅" if s["status"] == "completed" else "❌"
                            duration = f"{s.get('duration_ms', '?')}ms"
                            print(
                                f"\n{status_icon} {s['step_name']}  ({duration})  [{s['status']}]"
                            )
                            if s.get("input"):
                                print(f"  INPUT:  {json.dumps(s['input'], indent=4, default=str)}")
                            if s.get("output"):
                                print(f"  OUTPUT: {json.dumps(s['output'], indent=4, default=str)}")
                            if s.get("error_text"):
                                print(f"  ERROR:  {s['error_text']}")
        else:
            # List recent: python main.py runs [--limit 10]
            limit = 20
            for i, a in enumerate(args):
                if a == "--limit" and i + 1 < len(args):
                    limit = int(args[i + 1])
            runs = list_runs(limit=limit)
            for r in runs:
                status = "✅" if not r.get("errors") else f"⚠️ ({len(r['errors'])} errors)"
                company = r.get("company", "?")
                role = r.get("role", "?")
                print(
                    f"{r['run_id']}  {company} / {role}  {status}  tokens={r.get('tokens_used', 0)}  latency={r.get('latency_ms', 0)}ms  {r.get('created_at', '')}"
                )

    elif command == "followup-runner":
        _run_followup_runner(sys.argv[2:])

    elif command == "replay-webhook":
        _run_replay_webhook(sys.argv[2:])

    elif command == "eval-report":
        from evals.report import main as run_report

        json_output = "--json" in sys.argv[2:]
        run_report(json_output=json_output)

    elif command == "feedback":
        from evals.feedback_report import annotate_run_feedback

        opts = _parse_feedback_args(sys.argv[2:])
        annotate_run_feedback(
            opts["run_id"],  # type: ignore[arg-type]
            feedback_label=opts["label"],  # type: ignore[arg-type]
            feedback_reason=opts["reason"],  # type: ignore[arg-type]
        )
        print(
            f"Feedback saved: run_id={opts['run_id']} label={opts['label']}"
            f" reason={opts['reason'] or '-'}"
        )

    elif command == "feedback-report":
        from evals.feedback_report import build_feedback_report, format_feedback_report

        opts = _parse_feedback_report_args(sys.argv[2:])
        report = build_feedback_report(days=opts["days"])
        print(format_feedback_report(report))

    elif command == "regression-run":
        from evals.regression_runner import main as run_regression

        opts = _parse_regression_run_args(sys.argv[2:])
        run_regression(
            json_output=bool(opts["json_output"]),
            case_id=opts["case_id"],  # type: ignore[arg-type]
        )

    elif command == "build-skill-index":
        from scripts.build_skill_index import build_skill_index

        build_skill_index()

    elif command == "encode-token":
        import base64 as _b64
        from pathlib import Path as _Path

        from integrations.google_auth import TOKEN_FILENAME

        token_path = _Path("credentials") / TOKEN_FILENAME
        if not token_path.exists():
            print(f"Token file not found at {token_path}.")
            print("Run 'python main.py auth-google' first.")
            sys.exit(1)
        data = token_path.read_bytes()
        encoded = _b64.b64encode(data).decode("ascii")
        print(encoded)
        print(
            f"\n↑ Copy the single line above and paste it into Railway as "
            f"GOOGLE_TOKEN_B64 (no quotes, no wrapping). Length: {len(encoded)} chars.",
            file=sys.stderr,
        )

    elif command == "auth-google":
        from integrations.google_auth import TOKEN_FILENAME, get_google_credentials

        print("Authenticating Google (Drive + Calendar scopes)...")
        get_google_credentials(interactive=True)
        print(f"  Token saved to credentials/{TOKEN_FILENAME}")
        print("\nTo deploy to Railway, base64-encode the token:")
        print(f"  base64 < credentials/{TOKEN_FILENAME}")
        print("Then set GOOGLE_TOKEN_B64 in Railway env vars.")
        print(
            "Also set TELEGRAM_ENABLE_DRIVE_UPLOAD=true and TELEGRAM_ENABLE_CALENDAR_EVENTS=true."
        )

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
