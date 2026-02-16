"""
Versioned prompt loader.

Prompts live as plain-text files under core/prompts/ with the naming
convention:  {name}_v{version}.txt

Usage:
    from core.prompts import load_prompt
    system = load_prompt("jd_extract", version=1)
"""

from __future__ import annotations

from pathlib import Path

from core.config import get_settings


def load_prompt(name: str, *, version: int = 1) -> str:
    """Load a prompt template by name and version number."""
    prompts_dir = get_settings().prompts_dir
    filename = f"{name}_v{version}.txt"
    path = prompts_dir / filename

    if not path.exists():
        raise FileNotFoundError(
            f"Prompt '{filename}' not found in {prompts_dir}. "
            f"Available: {[p.name for p in prompts_dir.glob('*.txt')]}"
        )

    return path.read_text(encoding="utf-8").strip()


def list_prompts() -> list[str]:
    """List all available prompt template filenames."""
    prompts_dir = get_settings().prompts_dir
    if not prompts_dir.exists():
        return []
    return sorted(p.name for p in prompts_dir.glob("*.txt"))
