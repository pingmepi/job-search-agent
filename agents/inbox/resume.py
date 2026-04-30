"""
Resume engine — editable regions, mutation, selection, compilation.

Key constraints (PRD §10):
- Only modify content within %%BEGIN_EDITABLE / %%END_EDITABLE markers
- No new companies, metrics, or achievements invented
- Resume must fit on a single page
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


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


# LaTeX special chars that break compilation when unescaped in plain text.
# Excludes \ { } ~ ^ because those may appear in intentional TeX commands
# the LLM includes on purpose (e.g. \textbf{...}). The five below almost
# never appear intentionally unescaped in bullet prose.
_LATEX_SPECIALS = {
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
}


def escape_latex_specials(text: str) -> str:
    """Escape LaTeX special chars in plain-text mutation replacements.

    Skips characters already preceded by a backslash (already escaped),
    and preserves intentional math-mode delimiter pairs like `$\\sim$`,
    `$\\rightarrow$`, `$\\times$` — the opening/closing `$` in those
    pairs must NOT be escaped to `\\$` or the inner math command
    (`\\sim`, etc.) runs in text mode and triggers
    `! Missing $ inserted`.
    """
    if not text:
        return text

    # Protect `$\command$` patterns (math-mode delimiters around a TeX
    # command) by stashing them behind a placeholder so the per-char
    # escape loop can't touch their delimiters.
    placeholder = "\x00MATHPAIR{}\x00"
    stashed: list[str] = []

    def _stash(match: re.Match) -> str:
        stashed.append(match.group(0))
        return placeholder.format(len(stashed) - 1)

    protected = re.sub(r"\$\\[a-zA-Z]+(?:\{[^}]*\})?\$", _stash, text)

    out: list[str] = []
    i = 0
    while i < len(protected):
        ch = protected[i]
        prev = protected[i - 1] if i > 0 else ""
        if ch in _LATEX_SPECIALS and prev != "\\":
            out.append(_LATEX_SPECIALS[ch])
        else:
            out.append(ch)
        i += 1
    result = "".join(out)

    # Restore stashed math-mode pairs verbatim.
    for idx, original in enumerate(stashed):
        result = result.replace(placeholder.format(idx), original)
    return result


def apply_mutations(
    tex_content: str,
    mutations: list[dict],
) -> str:
    """
    Apply a list of mutations to the LaTeX content.

    Each mutation: {"original": str, "replacement": str}

    Only applied within editable regions.
    """

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
            original = m.get("original")
            replacement = m.get("replacement")
            if not isinstance(original, str) or not isinstance(replacement, str):
                continue
            if original and original in region_text:
                safe_replacement = escape_latex_specials(replacement)
                region_text = region_text.replace(original, safe_replacement, 1)

        lines[start_idx:end_idx] = region_text.split("\n")

    return "\n".join(lines)


# ── Resume selection ──────────────────────────────────────────────


def _normalize_text(text: str) -> str:
    """Lowercase, convert hyphens/underscores to spaces."""
    return re.sub(r"[-_]", " ", text.lower())


def _skill_matches(skill_raw: str, text_normalized: str) -> bool:
    """Check if a JD skill appears in normalized resume text.

    Handles slash splitting, phrase normalization, word-boundary matching
    for short tokens, and token fallback for multi-word skills.
    """
    skill = _normalize_text(skill_raw.strip())
    if not skill:
        return False

    # Slash splitting: "AI/ML" → check "ai" and "ml" individually
    # Filter single-char segments to avoid "A/B Testing" matching article "a"
    if "/" in skill:
        parts = [p.strip() for p in skill.split("/") if len(p.strip()) > 1]
        if parts:
            return any(_skill_matches(part, text_normalized) for part in parts)
        # All segments were single-char (e.g., "A/B") — match as whole phrase
        return skill.replace("/", "") in text_normalized or skill in text_normalized

    # Short tokens (≤3 chars): require word boundaries to avoid false positives
    # For skills with non-word chars (C++, C#), also try exact substring match
    if len(skill) <= 3:
        if bool(re.search(r"\b" + re.escape(skill) + r"\b", text_normalized)):
            return True
        # Fallback for symbol-containing skills where \b won't anchor correctly
        if not skill.isalnum() and skill in text_normalized:
            return True
        return False

    # Direct substring match
    if skill in text_normalized:
        return True

    # Token fallback: for multi-word skills, match if any substantial token appears
    tokens = skill.split()
    if len(tokens) > 1:
        for token in tokens:
            if len(token) <= 2:
                continue
            if len(token) <= 3:
                if re.search(r"\b" + re.escape(token) + r"\b", text_normalized):
                    return True
            elif token in text_normalized:
                return True

    return False


# ── Skill index ──────────────────────────────────────────────────

_skill_index_cache: dict[str, Any] | None = None


def load_skill_index(path: Path | None = None) -> dict[str, Any] | None:
    """Load the pre-committed skill index JSON. Returns None if missing."""
    global _skill_index_cache
    if _skill_index_cache is not None:
        return _skill_index_cache
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        _skill_index_cache = data
        return data
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        logger.debug("Skill index not available: %s", exc)
        return None


def _expand_skill_with_synonyms(skill_raw: str, synonyms: dict[str, list[str]]) -> set[str]:
    """Expand a JD skill into a set of normalized variants using the synonym map."""
    skill = _normalize_text(skill_raw.strip())
    if not skill:
        return set()
    variants = {skill}

    # Slash splitting
    if "/" in skill:
        for part in skill.split("/"):
            part = part.strip()
            if part:
                variants.add(part)
                variants.update(synonyms.get(part, []))

    # Direct synonym lookup
    variants.update(synonyms.get(skill, []))

    # Check each token for synonyms too
    for token in skill.split():
        variants.update(synonyms.get(token, []))

    return variants


def _skill_matches_index(
    skill_raw: str,
    resume_skills: list[str],
    synonyms: dict[str, list[str]],
) -> bool:
    """Check if a JD skill matches any skill in a resume's indexed skill list."""
    variants = _expand_skill_with_synonyms(skill_raw, synonyms)
    resume_skills_set = {s.lower() for s in resume_skills}

    for variant in variants:
        # Direct match
        if variant in resume_skills_set:
            return True
        # Substring containment both ways
        for rs in resume_skills_set:
            if len(variant) > 2 and (variant in rs or rs in variant):
                return True
    return False


_JD_SIGNAL_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "you",
        "are",
        "our",
        "your",
        "this",
        "that",
        "will",
        "from",
        "have",
        "has",
        "had",
        "into",
        "their",
        "they",
        "them",
        "then",
        "than",
        "but",
        "all",
        "any",
        "can",
        "may",
        "who",
        "what",
        "when",
        "where",
        "why",
        "how",
        "ours",
        "yours",
        "team",
        "role",
        "work",
        "join",
        "looking",
        "seeking",
        "must",
        "should",
        "would",
        "could",
        "well",
        "more",
        "less",
        "very",
        "also",
        "just",
        "able",
        "across",
        "about",
        "above",
        "below",
        "between",
        "within",
        "while",
        "which",
        "these",
        "those",
        "such",
        "etc",
        # Portuguese/Spanish high-frequency stopwords
        "para",
        "como",
        "esse",
        "essa",
        "isso",
        "aqui",
        "isto",
        "ser",
        "ter",
        "uma",
        "uns",
        "umas",
        "dos",
        "das",
        "que",
        "por",
        "pelo",
        "pela",
        "pelos",
        "pelas",
        "del",
        "los",
        "las",
        "una",
        "unos",
        "unas",
        "con",
        "sin",
        "sus",
    }
)


def _tokenize_jd_signal(jd_role: str | None, jd_description: str | None) -> list[str]:
    """Extract candidate keyword tokens from JD role + description.

    Used as a fallback signal for resume selection when jd.skills is empty
    (e.g., LLM extraction returned [] for a non-English or skill-sparse JD).

    Returns deduplicated lowercase tokens >= 4 chars, excluding common stopwords.
    """
    parts = []
    if jd_role:
        parts.append(str(jd_role))
    if jd_description:
        parts.append(str(jd_description))
    raw = " ".join(parts).lower()
    if not raw:
        return []
    tokens = re.findall(r"[a-zÀ-ſ][a-zÀ-ſ0-9+/\-]{2,}", raw)
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if len(tok) < 4 or tok in _JD_SIGNAL_STOPWORDS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def compute_keyword_overlap(
    jd_skills: list[str],
    tex_content: str,
    *,
    skill_index: dict[str, Any] | None = None,
    resume_name: str | None = None,
    fallback_signal: list[str] | None = None,
) -> float:
    """Compute fraction of JD skills found in resume text.

    If a skill_index is provided with a matching resume_name, uses
    index-based matching (synonym expansion + indexed skills) in
    addition to text-based matching. A skill counts as matched if
    either method finds it.

    When jd_skills is empty and fallback_signal is provided (tokens from
    jd.role + jd.description), score against the fallback tokens instead.
    Fallback scores are bounded to [0, 0.5] so they never beat a real
    skills-based match.
    """
    if not jd_skills:
        if not fallback_signal:
            return 0.0
        tex_normalized = _normalize_text(tex_content)
        matches = sum(1 for tok in fallback_signal if tok in tex_normalized)
        # Cap fallback at 0.5 so any genuine skills overlap from a non-empty
        # jd_skills run still wins. Inside the fallback regime this still gives
        # a deterministic ranking signal across templates.
        return min(0.5, matches / max(len(fallback_signal), 1))
    tex_normalized = _normalize_text(tex_content)

    # Load index data for this resume if available
    resume_skills: list[str] | None = None
    synonyms: dict[str, list[str]] = {}
    if skill_index and resume_name:
        resume_skills = skill_index.get("resumes", {}).get(resume_name)
        synonyms = skill_index.get("synonyms", {})

    def _matches(skill: str) -> bool:
        # Text-based matching (existing logic)
        if _skill_matches(skill, tex_normalized):
            return True
        # Index-based matching (additive)
        if resume_skills is not None:
            return _skill_matches_index(skill, resume_skills, synonyms)
        return False

    matches = sum(1 for skill in jd_skills if _matches(skill))
    return matches / len(jd_skills)


def select_base_resume(
    jd_skills: list[str],
    resumes_dir: Path,
) -> Path:
    """Select the best-matching base resume by keyword overlap."""
    best_path, _ = select_base_resume_with_score(jd_skills, resumes_dir)
    return best_path


def select_base_resume_with_score(
    jd_skills: list[str],
    resumes_dir: Path,
) -> tuple[Path, float]:
    """Select the best-matching base resume and return overlap score."""
    best_path, best_score, _details = select_base_resume_with_details(jd_skills, resumes_dir)
    return best_path, best_score


def select_base_resume_with_details(
    jd_skills: list[str],
    resumes_dir: Path,
    *,
    skill_index: dict[str, Any] | None = None,
    jd_role: str | None = None,
    jd_description: str | None = None,
) -> tuple[Path, float, dict[str, Any]]:
    """Select best resume with deterministic tie-breaking and provenance details.

    When jd_skills is empty, falls back to tokenizing jd_role + jd_description
    so we still get a ranking signal instead of every template scoring 0.0.
    Fallback scores are capped at 0.5 (see compute_keyword_overlap).
    """
    fallback_signal: list[str] = []
    if not jd_skills:
        fallback_signal = _tokenize_jd_signal(jd_role, jd_description)

    best_path: Optional[Path] = None
    best_score = -1.0
    candidate_scores: list[tuple[Path, float]] = []

    for tex_file in sorted(resumes_dir.glob("master_*.tex")):
        content = tex_file.read_text(encoding="utf-8")
        score = compute_keyword_overlap(
            jd_skills,
            content,
            skill_index=skill_index,
            resume_name=tex_file.name,
            fallback_signal=fallback_signal,
        )
        candidate_scores.append((tex_file, score))
        if score > best_score:
            best_score = score
            best_path = tex_file

    if best_path is None:
        raise FileNotFoundError(f"No master_*.tex files found in {resumes_dir}")

    jd_skills_clean = [s.strip() for s in jd_skills if s and s.strip()]
    # Use index-aware matching for diagnostics too
    chosen_text = best_path.read_text(encoding="utf-8")
    chosen_text_normalized = _normalize_text(chosen_text)
    resume_skills = (skill_index or {}).get("resumes", {}).get(best_path.name)
    synonyms = (skill_index or {}).get("synonyms", {})

    def _diag_matches(s: str) -> bool:
        if _skill_matches(s, chosen_text_normalized):
            return True
        if resume_skills is not None:
            return _skill_matches_index(s, resume_skills, synonyms)
        return False

    matched_skills = sorted([s for s in jd_skills_clean if _diag_matches(s)])
    missing_skills = sorted([s for s in jd_skills_clean if not _diag_matches(s)])

    top_candidates = [path.name for path, score in candidate_scores if score == best_score]
    tie_break_reason = (
        "highest_score_unique"
        if len(top_candidates) == 1
        else "highest_score_lexicographic_tie_break"
    )

    details: dict[str, Any] = {
        "selected_resume": best_path.name,
        "candidate_count": len(candidate_scores),
        "normalized_score": round(float(best_score), 6),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "tie_break_reason": tie_break_reason,
        "candidate_scores": [
            {"resume": path.name, "score": round(float(score), 6)}
            for path, score in sorted(candidate_scores, key=lambda x: x[0].name)
        ],
        "fallback_signal_used": bool(fallback_signal),
        "fallback_signal_count": len(fallback_signal),
    }
    return best_path, best_score, details


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
            "-output-directory",
            str(output_dir),
            str(tex_path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        # pdflatex writes errors to stdout, not stderr. Surface the first
        # actionable "! ..." line + a short tail so failures are debuggable.
        stdout = result.stdout or ""
        error_lines = [ln for ln in stdout.splitlines() if ln.startswith("!")]
        first_error = error_lines[0] if error_lines else ""
        tail = "\n".join(stdout.splitlines()[-15:])
        msg = f"pdflatex exited {result.returncode}"
        if first_error:
            msg += f" — {first_error}"
        raise RuntimeError(f"{msg}\n--- pdflatex tail ---\n{tail}")

    pdf_path = output_dir / tex_path.with_suffix(".pdf").name
    if not pdf_path.exists():
        raise FileNotFoundError(f"pdflatex succeeded but PDF not found at {pdf_path}")

    return pdf_path


# ── Page-count verification ───────────────────────────────────────


def get_pdf_page_count(pdf_path: Path) -> int:
    """Return the number of pages in a compiled PDF."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    return len(reader.pages)
