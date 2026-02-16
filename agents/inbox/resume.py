"""
Resume engine — editable regions, mutation, selection, compilation.

Key constraints (PRD §10):
- Only modify content within %%BEGIN_EDITABLE / %%END_EDITABLE markers
- Max 3 bullets rewritten per mutation
- No new companies, metrics, or achievements invented
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class EditableRegion:
    """A region of LaTeX content that the agent is allowed to modify."""

    content: str
    start_line: int
    end_line: int


# ── Parsing ───────────────────────────────────────────────────────

_BEGIN_MARKER = "%%BEGIN_EDITABLE"
_END_MARKER = "%%END_EDITABLE"


def parse_editable_regions(tex_content: str) -> list[EditableRegion]:
    """
    Extract all editable regions from a LaTeX document.

    Regions are delimited by %%BEGIN_EDITABLE and %%END_EDITABLE markers.
    """
    regions: list[EditableRegion] = []
    lines = tex_content.split("\n")

    in_region = False
    region_start = 0
    region_lines: list[str] = []

    for i, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped == _BEGIN_MARKER:
            in_region = True
            region_start = i + 1
            region_lines = []
        elif stripped == _END_MARKER and in_region:
            regions.append(
                EditableRegion(
                    content="\n".join(region_lines),
                    start_line=region_start,
                    end_line=i - 1,
                )
            )
            in_region = False
        elif in_region:
            region_lines.append(line)

    return regions


# ── Mutation validation ───────────────────────────────────────────

def validate_mutation_count(count: int) -> None:
    """Raise if more than 3 mutations are attempted."""
    if count > 3:
        raise ValueError(f"Resume mutation produced {count} changes — at most 3 allowed")


def apply_mutations(
    tex_content: str,
    mutations: list[dict],
) -> str:
    """
    Apply a list of mutations to the LaTeX content.

    Each mutation: {"original": str, "replacement": str}

    Only applied within editable regions.
    """
    validate_mutation_count(len(mutations))

    regions = parse_editable_regions(tex_content)
    if not regions:
        return tex_content

    lines = tex_content.split("\n")

    # Apply in reverse so line-index math remains stable if replacements
    # change region lengths.
    for region in reversed(regions):
        start_idx = region.start_line - 1
        end_idx = region.end_line
        region_text = "\n".join(lines[start_idx:end_idx])

        for m in mutations:
            original = m["original"]
            replacement = m["replacement"]
            if original in region_text:
                region_text = region_text.replace(original, replacement, 1)

        lines[start_idx:end_idx] = region_text.split("\n")

    return "\n".join(lines)


# ── Resume selection ──────────────────────────────────────────────

def compute_keyword_overlap(jd_skills: list[str], tex_content: str) -> float:
    """Compute fraction of JD skills found in resume text."""
    if not jd_skills:
        return 0.0
    tex_lower = tex_content.lower()
    matches = sum(1 for skill in jd_skills if skill.lower() in tex_lower)
    return matches / len(jd_skills)


def select_base_resume(
    jd_skills: list[str],
    resumes_dir: Path,
) -> Path:
    """Select the best-matching base resume by keyword overlap."""
    best_path: Optional[Path] = None
    best_score = -1.0

    for tex_file in sorted(resumes_dir.glob("master_*.tex")):
        content = tex_file.read_text(encoding="utf-8")
        score = compute_keyword_overlap(jd_skills, content)
        if score > best_score:
            best_score = score
            best_path = tex_file

    if best_path is None:
        raise FileNotFoundError(f"No master_*.tex files found in {resumes_dir}")

    return best_path


# ── Compilation ───────────────────────────────────────────────────

def compile_latex(tex_path: Path, output_dir: Path | None = None) -> Path:
    """
    Compile a .tex file to PDF using pdflatex.

    Returns the path to the generated PDF.
    Raises subprocess.CalledProcessError on compile failure.
    """
    if output_dir is None:
        output_dir = tex_path.parent

    result = subprocess.run(
        [
            "pdflatex",
            "-interaction=nonstopmode",
            "-output-directory", str(output_dir),
            str(tex_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        raise subprocess.CalledProcessError(
            result.returncode, "pdflatex", result.stdout, result.stderr
        )

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        raise FileNotFoundError(f"pdflatex succeeded but PDF not found at {pdf_path}")

    return pdf_path
