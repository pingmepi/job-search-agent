"""Tests for resume engine: editable regions, mutation bounds, compilation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agents.inbox.resume import (
    apply_mutations,
    compute_keyword_overlap,
    escape_latex_specials,
    find_blank_bullets,
    parse_editable_regions,
    replace_bullet_at,
    select_base_resume_with_details,
    select_base_resume_with_score,
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
        regions = parse_editable_regions(
            r"\documentclass{article}\begin{document}Hello\end{document}"
        )
        assert len(regions) == 0

    def test_region_has_line_numbers(self):
        regions = parse_editable_regions(SAMPLE_TEX)
        # Regions should track their start/end positions
        assert regions[0].start_line > 0

    def test_tagged_marker_sets_reference(self):
        tex = "%%BEGIN_EDITABLE[Miles Education]\n\\item bullet\n%%END_EDITABLE"
        regions = parse_editable_regions(tex)
        assert len(regions) == 1
        assert regions[0].reference == "Miles Education"

    def test_bare_marker_sets_reference_none(self):
        tex = "%%BEGIN_EDITABLE\n\\item bullet\n%%END_EDITABLE"
        regions = parse_editable_regions(tex)
        assert len(regions) == 1
        assert regions[0].reference is None

    def test_mixed_markers_each_get_correct_reference(self):
        tex = (
            "%%BEGIN_EDITABLE\n\\item summary\n%%END_EDITABLE\n"
            "%%BEGIN_EDITABLE[Miles Education]\n\\item miles bullet\n%%END_EDITABLE\n"
            "%%BEGIN_EDITABLE[upGrad]\n\\item upgrad bullet\n%%END_EDITABLE"
        )
        regions = parse_editable_regions(tex)
        assert len(regions) == 3
        assert regions[0].reference is None
        assert regions[1].reference == "Miles Education"
        assert regions[2].reference == "upGrad"

    def test_apply_mutations_regex_matches_tagged_marker(self):
        tex = "%%BEGIN_EDITABLE[Acme]\n\\item old bullet\n%%END_EDITABLE"
        mutations = [{"original": "old bullet", "replacement": "new bullet"}]
        result = apply_mutations(tex, mutations)
        assert "new bullet" in result
        assert "old bullet" not in result

    def test_apply_mutations_regex_matches_bare_marker(self):
        tex = "%%BEGIN_EDITABLE\n\\item old bullet\n%%END_EDITABLE"
        mutations = [{"original": "old bullet", "replacement": "new bullet"}]
        result = apply_mutations(tex, mutations)
        assert "new bullet" in result


class TestMutationBounds:
    def test_unlimited_mutations_allowed(self):
        """Mutations are no longer capped — model can make as many as needed."""
        # 5+ mutations should work fine (previously capped at 3)
        mutations = [
            {
                "original": "Built ML pipeline improving accuracy by 20\\%",
                "replacement": "Built ML pipeline improving accuracy by 30\\%",
            },
            {
                "original": "Led team of 5 engineers",
                "replacement": "Led cross-functional team of 5 engineers",
            },
            {
                "original": "Launched recommendation engine",
                "replacement": "Launched AI-powered recommendation engine",
            },
            {
                "original": "Managed product roadmap",
                "replacement": "Owned end-to-end product roadmap",
            },
            {
                "original": "Drove 15\\% increase in retention",
                "replacement": "Drove 15\\% improvement in user retention",
            },
        ]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "accuracy by 30" in result
        assert "cross-functional team" in result
        assert "AI-powered recommendation" in result
        assert "end-to-end product roadmap" in result
        assert "improvement in user retention" in result

    def test_zero_mutations_ok(self):
        result = apply_mutations(SAMPLE_TEX, [])
        assert "Built ML pipeline" in result

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
            [
                {
                    "original": "Built ML pipeline improving accuracy by 20\\%",
                    "replacement": "Built ML pipeline improving accuracy by 30\\%",
                }
            ],
        )

        # Non-editable summary line must remain unchanged.
        assert "\\section*{Summary}\nBuilt ML pipeline improving accuracy by 20\\%" in updated
        # Editable bullet should be updated.
        assert "  \\item Built ML pipeline improving accuracy by 30\\%" in updated

    def test_apply_mutations_deletes_full_item_for_empty_replacement(self):
        updated = apply_mutations(
            SAMPLE_TEX,
            [
                {
                    "original": "Led team of 5 engineers",
                    "replacement": "",
                }
            ],
        )

        assert "Led team of 5 engineers" not in updated
        assert "\\item \n" not in updated
        assert not find_blank_bullets(updated)

    def test_apply_mutations_rewires_payload_match_to_existing_item_line(self):
        updated = apply_mutations(
            SAMPLE_TEX,
            [
                {
                    "original": r"\item Led team of 5 engineers",
                    "replacement": "Led cross-functional product and engineering team",
                }
            ],
        )

        assert "Led cross-functional product and engineering team" in updated
        assert "Led team of 5 engineers" not in updated


class TestApplyMutationsDefensiveness:
    """Ensure apply_mutations handles malformed LLM output gracefully."""

    def test_skips_none_original(self):
        mutations = [{"original": None, "replacement": "something"}]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "Built ML pipeline" in result

    def test_skips_none_replacement(self):
        mutations = [{"original": "Built ML pipeline", "replacement": None}]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "Built ML pipeline" in result

    def test_skips_both_none(self):
        mutations = [{"original": None, "replacement": None}]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "Built ML pipeline" in result

    def test_skips_missing_keys(self):
        mutations = [{"replacement": "only replacement"}, {"original": "only original"}, {}]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "Built ML pipeline" in result

    def test_skips_empty_original(self):
        mutations = [{"original": "", "replacement": "injected"}]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "injected" not in result

    def test_valid_mutations_still_work(self):
        mutations = [
            {"original": None, "replacement": "bad"},
            {
                "original": "Built ML pipeline improving accuracy by 20\\%",
                "replacement": "Built ML pipeline improving accuracy by 30\\%",
            },
        ]
        result = apply_mutations(SAMPLE_TEX, mutations)
        assert "accuracy by 30" in result


class TestBulletRepairHelpers:
    def test_find_blank_bullets_detects_empty_item(self):
        tex = (
            "\n%%BEGIN_EDITABLE\n"
            "\\begin{itemize}\n"
            "  \\item Filled bullet\n"
            "  \\item   \n"
            "\\end{itemize}\n"
            "%%END_EDITABLE\n"
        )
        blanks = find_blank_bullets(tex)
        assert len(blanks) == 1
        assert blanks[0].bullet_index == 1

    def test_replace_bullet_at_preserves_item_prefix(self):
        tex = "\n%%BEGIN_EDITABLE\n\\begin{itemize}\n  \\item   \n\\end{itemize}\n%%END_EDITABLE\n"
        repaired = replace_bullet_at(
            tex,
            region_index=0,
            bullet_index=0,
            replacement="Recovered bullet text",
        )
        assert "  \\item Recovered bullet text" in repaired
        assert not find_blank_bullets(repaired)


class TestSkillMatchingImprovements:
    """Verify smarter skill matching: slash splitting, normalization, word boundaries."""

    def test_slash_splitting(self):
        score = compute_keyword_overlap(["AI/ML"], "We use machine learning and ai agents")
        assert score == pytest.approx(1.0)

    def test_hyphen_normalization(self):
        score = compute_keyword_overlap(
            ["Cross-functional Collaboration"],
            "Led cross functional collaboration across teams",
        )
        assert score == pytest.approx(1.0)

    def test_bidirectional_containment(self):
        score = compute_keyword_overlap(["Process Automation"], "Built workflow automation tools")
        assert score == pytest.approx(1.0)

    def test_short_token_word_boundary_no_false_positive(self):
        score = compute_keyword_overlap(["SQL"], "Handled employee dismissal cases")
        assert score == pytest.approx(0.0)

    def test_short_token_real_match(self):
        score = compute_keyword_overlap(["SQL"], "Proficient in SQL and Python")
        assert score == pytest.approx(1.0)

    def test_multi_word_token_fallback(self):
        score = compute_keyword_overlap(["Data Analytics"], "Built analytics dashboards")
        assert score == pytest.approx(1.0)

    def test_short_token_ai_not_in_maintain(self):
        score = compute_keyword_overlap(["AI"], "Help maintain the servers")
        assert score == pytest.approx(0.0)

    def test_slash_single_char_segments_no_false_positive(self):
        """A/B Testing should not match just because 'a' appears in text."""
        score = compute_keyword_overlap(["A/B Testing"], "This is a normal sentence")
        assert score == pytest.approx(0.0)

    def test_slash_single_char_matches_ab_testing(self):
        """A/B Testing should match when 'ab testing' or 'a/b testing' appears."""
        score = compute_keyword_overlap(["A/B Testing"], "We run A/B testing experiments")
        assert score == pytest.approx(1.0)

    def test_symbol_skill_cpp(self):
        """C++ should match even though + isn't a word character."""
        score = compute_keyword_overlap(["C++"], "Proficient in C++ and Java")
        assert score == pytest.approx(1.0)

    def test_symbol_skill_csharp(self):
        """C# should match via substring fallback."""
        score = compute_keyword_overlap(["C#"], "Experience with C# and .NET")
        assert score == pytest.approx(1.0)


class TestSkillIndexMatching:
    """Verify skill index integration with synonym expansion."""

    SAMPLE_INDEX = {
        "version": 1,
        "synonyms": {
            "sdlc": ["software development lifecycle"],
            "ci/cd": ["continuous integration", "continuous deployment"],
            "llms": ["large language models", "llm"],
        },
        "resumes": {
            "master_ai_pm.tex": [
                "ai",
                "ml",
                "llm",
                "python",
                "sql",
                "product management",
                "automation",
                "analytics",
                "crm",
                "cross functional",
            ],
        },
    }

    def test_index_matches_skill_not_in_text(self):
        """Index-based match when text doesn't contain the skill."""
        score = compute_keyword_overlap(
            ["Python"],
            "No python mentioned here at all",
            skill_index=self.SAMPLE_INDEX,
            resume_name="master_ai_pm.tex",
        )
        # "python" is in the index even though text says "No python mentioned"
        # — wait, "python" IS in the text as substring. Use a cleaner example:
        score = compute_keyword_overlap(
            ["Python"],
            "This resume has no programming languages listed",
            skill_index=self.SAMPLE_INDEX,
            resume_name="master_ai_pm.tex",
        )
        assert score == pytest.approx(1.0)

    def test_synonym_expansion_matches(self):
        """SDLC should match via synonym 'software development lifecycle'."""
        index = {
            "version": 1,
            "synonyms": {"sdlc": ["software development lifecycle"]},
            "resumes": {
                "test.tex": ["software development lifecycle"],
            },
        }
        score = compute_keyword_overlap(
            ["SDLC"],
            "no sdlc text here",
            skill_index=index,
            resume_name="test.tex",
        )
        assert score == pytest.approx(1.0)

    def test_no_index_falls_back_to_text(self):
        """Without index, only text matching is used."""
        score = compute_keyword_overlap(
            ["Python"],
            "This resume has no programming languages listed",
        )
        assert score == pytest.approx(0.0)

    def test_unknown_resume_falls_back_to_text(self):
        """If resume isn't in index, only text matching is used."""
        score = compute_keyword_overlap(
            ["Python"],
            "This resume mentions Python explicitly",
            skill_index=self.SAMPLE_INDEX,
            resume_name="unknown_resume.tex",
        )
        assert score == pytest.approx(1.0)  # matched via text

    def test_combined_text_and_index(self):
        """Skills matched by either text or index count."""
        score = compute_keyword_overlap(
            ["Python", "Docker"],  # Python in index, Docker not in text or index
            "No skills mentioned here",
            skill_index=self.SAMPLE_INDEX,
            resume_name="master_ai_pm.tex",
        )
        assert score == pytest.approx(0.5)  # Python via index, Docker misses


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

    def test_select_base_resume_with_details_is_deterministic_on_tie(self, tmp_path: Path):
        a = tmp_path / "master_a.tex"
        b = tmp_path / "master_b.tex"
        a.write_text("python", encoding="utf-8")
        b.write_text("python", encoding="utf-8")

        best_path, score, details = select_base_resume_with_details(["python"], tmp_path)
        assert best_path.name == "master_a.tex"
        assert score == pytest.approx(1.0)
        assert details["tie_break_reason"] == "highest_score_lexicographic_tie_break"
        assert details["selected_resume"] == "master_a.tex"
        assert details["matched_skills"] == ["python"]


class TestEscapeLatexSpecials:
    def test_escapes_all_five_specials(self):
        assert escape_latex_specials("a&b") == r"a\&b"
        assert escape_latex_specials("10%") == r"10\%"
        assert escape_latex_specials("$1M") == r"\$1M"
        assert escape_latex_specials("#1") == r"\#1"
        assert escape_latex_specials("snake_case") == r"snake\_case"

    def test_does_not_double_escape(self):
        assert escape_latex_specials(r"20\%") == r"20\%"
        assert escape_latex_specials(r"a\&b") == r"a\&b"

    def test_leaves_backslash_commands_alone(self):
        assert escape_latex_specials(r"\textbf{bold}") == r"\textbf{bold}"

    def test_empty_and_none_safe(self):
        assert escape_latex_specials("") == ""
        assert escape_latex_specials(None) is None

    def test_preserves_math_mode_pair_around_command(self):
        # $\sim$20% — the outer $ delimiters are intentional math mode.
        # Only the % should be escaped; the $s around \sim must stay.
        assert escape_latex_specials(r"improved by $\sim$20%") == r"improved by $\sim$20\%"

    def test_preserves_rightarrow_and_times(self):
        assert escape_latex_specials(r"NLP $\rightarrow$ SQL") == r"NLP $\rightarrow$ SQL"
        assert escape_latex_specials(r"$\sim$2$\times$ growth") == r"$\sim$2$\times$ growth"

    def test_still_escapes_stray_dollar(self):
        # Not a math-mode pair — should be escaped.
        assert escape_latex_specials("$1M revenue") == r"\$1M revenue"
        assert escape_latex_specials("cost is $30") == r"cost is \$30"

    def test_apply_mutations_escapes_unescaped_specials(self):
        tex = (
            "\n%%BEGIN_EDITABLE\n"
            "\\begin{itemize}\n"
            "  \\item placeholder\n"
            "\\end{itemize}\n"
            "%%END_EDITABLE\n"
        )
        mutations = [
            {"original": "placeholder", "replacement": "Drove $1M & 20% growth in Q1"},
        ]
        result = apply_mutations(tex, mutations)
        assert r"\$1M" in result
        assert r"\&" in result
        assert r"20\%" in result
