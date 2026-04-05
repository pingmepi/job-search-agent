#!/usr/bin/env bash
# Install git hooks for this repo.
# Works from the main repo or any worktree.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
HOOK_DIR="$(git rev-parse --git-common-dir)/hooks"

cp "$SCRIPT_DIR/pre-commit" "$HOOK_DIR/pre-commit"
chmod +x "$HOOK_DIR/pre-commit"

echo "✅ Pre-commit hook installed to $HOOK_DIR"
echo "   Checks: ruff lint, ruff format, pytest"
echo "   To skip once: git commit --no-verify"
