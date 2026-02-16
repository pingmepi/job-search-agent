"""
Main entry point for the inbox-agent system.

Usage:
    python main.py webhook     # Start Telegram webhook service
    python main.py init-db     # Initialize database
    python main.py ci-gate     # Run CI eval gate
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

    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
