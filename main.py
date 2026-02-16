"""
Main entry point for the inbox-agent system.

Usage:
    python main.py webhook     # Start Telegram webhook service
    python main.py init-db     # Initialize database
    python main.py ci-gate     # Run CI eval gate
    python main.py db-stats    # Show DB summary for debugging
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
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

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
