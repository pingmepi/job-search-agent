"""
Main entry point for the inbox-agent system.

Usage:
    python main.py webhook                       # Start Telegram webhook service
    python main.py init-db                       # Initialize database
    python main.py ci-gate                       # Run CI eval gate
    python main.py db-stats                      # Show DB summary for debugging
    python main.py followup-runner [options]     # Run scheduled follow-up detection
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
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
        path = init_db()
        print(f"✅ Database initialized at {path}")

    elif command == "ci-gate":
        from evals.ci_gate import main as run_gate
        run_gate()

    elif command == "db-stats":
        from core.db import get_db_stats

        stats = get_db_stats()
        print(f"DB: {stats['db_path']}")
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

    elif command == "followup-runner":
        _run_followup_runner(sys.argv[2:])

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
