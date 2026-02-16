"""Tests for resume engine: editable regions, mutation bounds, compilation."""

from __future__ import annotations

import pytest
from pathlib import Path

from agents.inbox.resume import (
    parse_editable_regions,
    EditableRegion,
    apply_mutations,
    select_base_resume_with_score,
    compute_keyword_overlap,
)


SAMPLE_TEX = r"""
\section*{Experience}

\textbf{Company A} \hfill 2022 -- Present

%%BEGIN_EDITABLE
\begin{itemize}
  \item Built ML pipeline improving accuracy by 20\%
  \item Led team of 5 engineers
  \item Launched recommendation engine
\end{itemize}
%%END_EDITABLE

\textbf{Company B} \hfill 2020 -- 2022

%%BEGIN_EDITABLE
\begin{itemize}
  \item Managed product roadmap
  \item Drove 15\% increase in retention
\end{itemize}
%%END_EDITABLE

\section*{Education}
"""


class TestEditableRegionParsing:
    def test_finds_two_regions(self):
        regions = parse_editable_regions(SAMPLE_TEX)
        assert len(regions) == 2

    def test_region_content(self):
        regions = parse_editable_regions(SAMPLE_TEX)
        assert "Built ML pipeline" in regions[0].content
        assert "Managed product roadmap" in regions[1].content

    def test_no_regions(self):
        regions = parse_editable_regions(r"\documentclass{article}\begin{document}Hello\end{document}")
        assert len(regions) == 0

    def test_region_has_line_numbers(self):
        regions = parse_editable_regions(SAMPLE_TEX)
        # Regions should track their start/end positions
        assert regions[0].start_line > 0
        assert regions[0].end_line > regions[0].start_line


class TestMutationBounds:
    def test_max_three_mutations(self):
        """Resume mutation should never produce more than 3 changes."""
        from agents.inbox.resume import validate_mutation_count
        # 3 should be fine
        validate_mutation_count(3)
        # 4 should raise
        with pytest.raises(ValueError, match="at most 3"):
            validate_mutation_count(4)

    def test_zero_mutations_ok(self):
        from agents.inbox.resume import validate_mutation_count
        validate_mutation_count(0)

    def test_apply_mutations_does_not_edit_outside_markers(self):
        tex = r"""
\section*{Summary}
Built ML pipeline improving accuracy by 20\%

%%BEGIN_EDITABLE
\begin{itemize}
  \item Built ML pipeline improving accuracy by 20\%
\end{itemize}
%%END_EDITABLE
"""
        updated = apply_mutations(
            tex,
            [{
                "original": "Built ML pipeline improving accuracy by 20\\%",
                "replacement": "Built ML pipeline improving accuracy by 30\\%",
            }],
        )

        # Non-editable summary line must remain unchanged.
        assert "\\section*{Summary}\nBuilt ML pipeline improving accuracy by 20\\%" in updated
        # Editable bullet should be updated.
        assert "  \\item Built ML pipeline improving accuracy by 30\\%" in updated


class TestResumeSelection:
    def test_compute_keyword_overlap(self):
        score = compute_keyword_overlap(["python", "sql", "ml"], "Python and ML systems")
        assert score == pytest.approx(2 / 3)

    def test_select_base_resume_with_score(self, tmp_path: Path):
        a = tmp_path / "master_a.tex"
        b = tmp_path / "master_b.tex"
        a.write_text("python sql ml", encoding="utf-8")
        b.write_text("excel operations", encoding="utf-8")

        best_path, score = select_base_resume_with_score(["python", "sql"], tmp_path)
        assert best_path.name == "master_a.tex"
        assert score == pytest.approx(1.0)
