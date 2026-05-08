# Bullet Bank Per-Region Scoping — Implementation Plan

**Status:** Ready to implement (2026-05-07)
**Author:** Karan M (with Claude)
**Branch to cut from:** `main`

---

## The Bug

`profile/bullet_bank.json` contains bullets tagged with a `reference` field — the past employer or project where that work was done (e.g., `"Miles Education"`, `"upGrad"`, `"AlmaBetter"`, `"MyThirdPlace"`). The resume has named experience sections, each with its own `%%BEGIN_EDITABLE` / `%%END_EDITABLE` region.

**Today:** `select_relevant_bullets()` scores all bullets purely on JD-skill overlap with no filter on `reference`. The LLM receives a single flat pool of 12 bullets and can — and does — place a Miles Education bullet under the upGrad section, or an upGrad bullet under the AlmaBetter section. Cross-employer attribution. False work history implied.

**Root cause confirmed in code:** [agents/inbox/bullet_relevance.py:63-68](../agents/inbox/bullet_relevance.py#L63-L68) loops over all bullets unconditionally. `reference` is never read.

---

## Architecture Decisions (all locked, no need to re-ask)

| Decision | Choice |
|---|---|
| How regions declare their company | **Explicit marker tag**: `%%BEGIN_EDITABLE[Miles Education]`. Edit all 5 master_*.tex files. Backwards-compatible — bare `%%BEGIN_EDITABLE` (no tag) → `reference=None`. |
| Non-experience regions (Summary, Projects) | Use **full unscoped bullet bank**. `role_family` drives relevance. `reference` can also hold project/product names (e.g., `"MyThirdPlace"`) — these match tagged Project regions. |
| Prompt structure | **Per-region blocks** in the LLM user message: each region rendered separately with its own scoped bullet pool (not a flat 12-bullet list). |
| No feature flag | Ship as default. Bug is severe enough to not gate behind a flag. Prompt v3 stays in tree for rollback; new behaviour is v4. |

---

## What Is Already Implemented (do not re-do)

The following code was already written and tested (28/28 passing) in the current branch:

**[agents/inbox/bullet_relevance.py](../agents/inbox/bullet_relevance.py)**
- `_normalize_company(name)` — case-fold + trim + strip corporate suffixes (`Corporation`, `Incorporated`, `Limited`, `Company`, `Corp`, `Ltd`, `LLC`, `Inc`, `Co`). Longer forms listed first so `"Acme Corporation"` strips fully.
- `select_relevant_bullets(..., target_reference: str | None = None)` — when `target_reference` is set, pre-filters bullets to those where `_normalize_company(bullet["reference"]) == _normalize_company(target_reference)`. Falls back to unscoped bank on zero matches (logs info). `target_reference=None` → existing behaviour unchanged.

**[tests/test_bullet_relevance.py](../tests/test_bullet_relevance.py)**
- `TestNormalizeCompany` — 7 tests covering suffix stripping, case-fold, whitespace.
- `TestTargetCompanyFilter` — 6 tests covering filter, fallback, empty-string as None.

> **Note on param naming:** the param was previously called `target_company` and has been renamed to `target_reference` because the `reference` field can hold project/product names, not just companies. Ensure any new code uses `target_reference`.

---

## Ground-Truth File Map

| File | Role | Key lines |
|---|---|---|
| [profile/bullet_bank.json](../profile/bullet_bank.json) | Data — array of `{id, role_family, tier, reference, needs_review, bullet, review_note, tags}` | Full file |
| [agents/inbox/bullet_relevance.py](../agents/inbox/bullet_relevance.py) | Scoring + filter primitive — already updated | 8-44 (helpers), 52-118 (selector) |
| [agents/inbox/resume.py](../agents/inbox/resume.py) | `EditableRegion` dataclass + `parse_editable_regions()` | 22-81 |
| [agents/inbox/executor.py](../agents/inbox/executor.py) | `_handle_resume_mutate()` — the mutation driver | 707-870 |
| [agents/inbox/executor.py](../agents/inbox/executor.py) | `_load_relevant_bullet_bank_values()` helper | 365-375 |
| [agents/inbox/executor.py](../agents/inbox/executor.py) | `apply_mutations` regex | 211 |
| [agents/inbox/executor.py](../agents/inbox/executor.py) | `_run_hard_evals()` | 1343-1379 |
| [core/prompts/resume_mutate_v3.txt](../core/prompts/resume_mutate_v3.txt) | Current LLM prompt — REWRITE/SWAP/GENERATE ops | 1-57 |
| [evals/hard.py](../evals/hard.py) | `check_forbidden_claims_per_bullet` — existing hard eval | Full |
| [evals/logger.py](../evals/logger.py) | `log_run()` — writes to PostgreSQL + JSON artifact | Full |
| [evals/report.py](../evals/report.py) | `_extract_metrics()` — trend table for `eval-report` CLI | Full |
| [resumes/master_product.tex](../resumes/master_product.tex) | 8 editable regions | See marker map below |
| [resumes/master_ai_pm.tex](../resumes/master_ai_pm.tex) | 9 editable regions | — |
| [resumes/master_agentic_ai.tex](../resumes/master_agentic_ai.tex) | 8 editable regions | — |
| [resumes/master_founders_office.tex](../resumes/master_founders_office.tex) | 6 editable regions | — |
| [resumes/master_technical_pm.tex](../resumes/master_technical_pm.tex) | 7 editable regions | — |

### master_product.tex region→company map (confirmed from source)

| Region line | Section | Tag to add |
|---|---|---|
| 27 | Summary | *(no tag — unscoped)* |
| 35 | Tribeca Developers / Turing | `[Tribeca Developers]` |
| 44 | Miles Education | `[Miles Education]` |
| 56 | AlmaBetter | `[AlmaBetter]` |
| 67 | upGrad | `[upGrad]` |
| 76 | Capgemini | `[Capgemini]` |
| 85 | MyThirdPlace (project) | `[MyThirdPlace]` |
| 93 | *(check — likely another project)* | *(check source)* |

> Do the same mapping for the other 4 tex files before annotating them. Read each file and map `\textit{Company | Location}` lines to the following `%%BEGIN_EDITABLE` region.

---

## Implementation Steps

### Step 1 — Marker parser ([agents/inbox/resume.py](../agents/inbox/resume.py))

**Add `reference` field to `EditableRegion`:**
```python
@dataclass
class EditableRegion:
    content: str
    start_line: int
    end_line: int
    reference: str | None = None   # NEW — value from %%BEGIN_EDITABLE[Name]
```

**Update `parse_editable_regions` to parse the bracket:**
```python
_BEGIN_MARKER_RE = re.compile(r"^%%BEGIN_EDITABLE(?:\[([^\]]+)\])?$")

# In the loop, replace the stripped == _BEGIN_MARKER check with:
m = _BEGIN_MARKER_RE.match(stripped)
if m:
    in_region = True
    region_start = i + 1
    region_lines = []
    pending_reference = (m.group(1) or "").strip() or None

# In the append:
regions.append(
    EditableRegion(
        content="\n".join(region_lines),
        start_line=region_start,
        end_line=i - 1,
        reference=pending_reference,   # NEW
    )
)
```

**Update `apply_mutations` regex at [executor.py:211](../agents/inbox/executor.py#L211):**
```python
# Old:
pattern = re.compile(r"(%%BEGIN_EDITABLE)(.*?)(%%END_EDITABLE)", re.DOTALL)
# New (captures optional bracket payload, ignored for apply purposes):
pattern = re.compile(r"(%%BEGIN_EDITABLE(?:\[[^\]]*\])?)(.*?)(%%END_EDITABLE)", re.DOTALL)
```

**Tests to add (new `TestEditableRegionParsing` class in [tests/test_resume.py](../tests/test_resume.py) or new `tests/test_resume_parser.py`):**
- `%%BEGIN_EDITABLE[Miles Education]` → `region.reference == "Miles Education"`
- Bare `%%BEGIN_EDITABLE` → `region.reference is None`
- Mixed markers in same file → each region gets correct reference
- `apply_mutations` regex still matches both forms

---

### Step 2 — Executor: per-region pools + prompt restructure ([agents/inbox/executor.py:741-778](../agents/inbox/executor.py#L741-L778))

Replace the current flat-pool + flat-content block with per-region building:

```python
bullet_bank_raw = json.loads(ctx.settings.bullet_bank_path.read_text(encoding="utf-8"))

# Build per-region pools
region_blocks = []
all_bullet_values: list[str] = []
bullets_per_region: dict[int, int] = {}

for i, region in enumerate(regions):
    pool = select_relevant_bullets(
        bullet_bank_raw,
        jd.skills,
        jd.description,
        top_n=8,  # per region, not 12 for the whole resume
        target_reference=region.reference,
    )
    bullets_per_region[i] = len(pool)
    all_bullet_values.extend(b["bullet"] for b in pool if b.get("bullet"))

    label = region.reference or f"region-{i+1}"
    bullets_fmt = "\n".join(
        f"[{b.get('id','?')}] (tags: {', '.join(b.get('tags', []))}) {b.get('bullet','')}"
        for b in pool
    )
    region_blocks.append(
        f"=== Region {i+1} ({label}) ===\n"
        f"Current content:\n{region.content}\n\n"
        f"Available bullets for this region:\n{bullets_fmt or '(none — use REWRITE or GENERATE only)'}"
    )

bullet_bank_values = list(dict.fromkeys(all_bullet_values))  # dedup, preserve order
editable_content_structured = "\n\n".join(region_blocks)
```

Update the user message (lines 771-778):
```python
user_msg = (
    f"JD:\n{json.dumps({'company': jd.company, 'role': jd.role, 'skills': jd.skills, 'description': jd.description})}\n\n"
    f"Current editable regions (each with its own bullet pool):\n{editable_content_structured}\n\n"
    f"Current bullet count: {current_bullet_count}. "
    f"Do NOT exceed {current_bullet_count} total bullets — the resume must fit on 1 page.\n\n"
    f"Profile context:\n{profile_context}"
)
```

Update audit blob to include per-region counts:
```python
audit_blob = {
    ...existing fields...,
    "bank_bullets_per_region": bullets_per_region,
}
```

Also update `_load_relevant_bullet_bank_values` helper at line 365 — it's used elsewhere and still passes `target_reference=None` (unscoped), which is intentional for that call path. Leave it as-is.

---

### Step 3 — Scope-violation hard eval ([evals/hard.py](../evals/hard.py))

Add a new function alongside `check_forbidden_claims_per_bullet`:

```python
def check_scope_violations(
    mutations: list[dict],
    regions: list["EditableRegion"],
    bullet_bank: list[dict],
) -> list[dict]:
    """Return a list of SWAP mutations where the placed bullet's reference
    doesn't match the region it was placed in. Deterministic — no LLM."""
    bank_by_id = {b["id"]: b for b in bullet_bank if b.get("id")}
    violations = []
    for mutation in mutations:
        if mutation.get("type") != "SWAP":
            continue
        source = mutation.get("source", "")
        bullet_id = source.replace("bank:", "").strip()
        bullet = bank_by_id.get(bullet_id)
        if not bullet:
            continue
        bullet_ref = _normalize_company(bullet.get("reference"))
        # Find which region this mutation's original bullet lives in
        original = mutation.get("original", "")
        for region in regions:
            if original in region.content:
                region_ref = _normalize_company(region.reference) if region.reference else None
                if region_ref and bullet_ref and bullet_ref != region_ref:
                    violations.append({
                        "bullet_id": bullet_id,
                        "bullet_reference": bullet.get("reference"),
                        "placed_in_region": region.reference,
                        "original_bullet": original[:80],
                    })
                break
    return violations
```

Call it in `_handle_resume_mutate` after applying mutations, store in `ctx.last_step_audit["scope_violations"]` and `ctx.mutation_summary["scope_violations"]`.

---

### Step 4 — Prompt v4 ([core/prompts/resume_mutate_v4.txt](../core/prompts/resume_mutate_v4.txt) NEW)

Copy `resume_mutate_v3.txt` verbatim. Add one rule to the CONSTRAINTS block:

```
10. SCOPE LOCK — each region is labelled with its employer or project (e.g., "Miles Education", "upGrad"). You may only SWAP in a bullet from the pool shown for that region. NEVER place a bullet from one region's pool into a different region. REWRITE and GENERATE are region-neutral (they operate on existing content). Cross-region bullet placement is a hard failure.
```

Update `_record_prompt_version(ctx, "resume_mutate", 4)` and `load_prompt("resume_mutate", version=4)` in `_handle_resume_mutate`.

---

### Step 5 — Tex annotations (5 files, 38 markers total)

For each file:
1. Read the file.
2. Find each `%%BEGIN_EDITABLE` and the `\textit{...}` line that precedes it.
3. Extract the company/project name from `\textit{Name | Location}` (first `|`-delimited token).
4. Replace `%%BEGIN_EDITABLE` with `%%BEGIN_EDITABLE[Name]`.
5. Leave Summary and any unattributable regions bare.

> **Important:** Do all 5 files in one pass. Do NOT partially annotate — a mix of tagged and untagged experience regions would make the scoping inconsistent.

---

### Step 6 — Eval report wiring ([evals/report.py](../evals/report.py))

In `_extract_metrics`, add:
```python
"scope_violations": er.get("mutation_summary", {}).get("scope_violations_count", 0),
```

Add a column to the markdown table in the report renderer.

---

## Eval + Monitoring Summary

| Check | Type | When it runs | Where result lands |
|---|---|---|---|
| Marker parser tests | Unit (pytest) | CI | `tests/test_resume_parser.py` |
| `TestTargetCompanyFilter` | Unit (pytest) | CI | `tests/test_bullet_relevance.py` — already written |
| `check_scope_violations` | Deterministic hard eval | Every prod run | `ctx.mutation_summary["scope_violations"]` → `eval_output.json` → PostgreSQL `eval_results` column |
| `python main.py eval-report` | Trend table | On-demand | Terminal markdown, reads `runs/artifacts/*/eval_output.json` |
| Railway query | Ad-hoc SQL | On-demand | `SELECT run_id, eval_results->>'scope_violations_count' FROM runs WHERE (eval_results->>'scope_violations_count')::int > 0` |

For continuous improvement: any run with `scope_violations_count > 0` surfaces concrete `{bullet_id, placed_in_region, bullet_reference}` triples. These are either (a) a missing/wrong tag in a tex file — fix the marker, or (b) the LLM ignoring the per-region prompt constraint — strengthen constraint 10 in v4 with a few-shot example.

---

## Constraints and Gotchas

- **`_normalize_company` must be imported in `evals/hard.py`** if you use it in `check_scope_violations`. It lives in `agents/inbox/bullet_relevance.py`.
- **`top_n=8` per region** (not 12) keeps total prompt size manageable. A 6-region resume with 8 bullets each = 48 bullet strings in the prompt. If this bloats the context, reduce to 5.
- **The `apply_mutations` regex change (Step 1) must land before Step 5** otherwise the tex template changes break region replacement.
- **Don't change the SWAP output format** — the LLM still emits `"source": "bank:ai-001"`. The scope checker reads this `id` to look up the bullet's `reference` post-hoc.
- **Fallback for untagged experience regions:** if a tex file has a bare `%%BEGIN_EDITABLE` for an experience section (forgot to tag it), `region.reference=None` → unscoped full bank → old behaviour. This is safe, not a crash. Fix the tag afterward.
- **`_load_relevant_bullet_bank_values` at executor.py:365** is a separate helper used by the swap-bullet path. Do NOT add `target_reference` there — it's intentionally unscoped (called without region context). Leave it unchanged.

---

## Files Changed (summary)

| File | Change |
|---|---|
| [agents/inbox/resume.py](../agents/inbox/resume.py) | Add `reference` field to `EditableRegion`; update `parse_editable_regions` regex |
| [agents/inbox/executor.py](../agents/inbox/executor.py) | Update `apply_mutations` regex; restructure `_handle_resume_mutate` for per-region pools; add scope-violation check |
| [agents/inbox/bullet_relevance.py](../agents/inbox/bullet_relevance.py) | Already done — `target_reference` param + suffix-aware filter |
| [core/prompts/resume_mutate_v4.txt](../core/prompts/resume_mutate_v4.txt) | NEW — v3 + scope constraint |
| [evals/hard.py](../evals/hard.py) | Add `check_scope_violations()` |
| [evals/report.py](../evals/report.py) | Add `scope_violations` column to trend table |
| [tests/test_bullet_relevance.py](../tests/test_bullet_relevance.py) | Already done — `TestNormalizeCompany`, `TestTargetCompanyFilter` |
| [tests/test_resume_parser.py](../tests/tests/) | NEW — marker parser tests |
| [resumes/master_product.tex](../resumes/master_product.tex) | Annotate 8 markers |
| [resumes/master_ai_pm.tex](../resumes/master_ai_pm.tex) | Annotate 9 markers |
| [resumes/master_agentic_ai.tex](../resumes/master_agentic_ai.tex) | Annotate 8 markers |
| [resumes/master_founders_office.tex](../resumes/master_founders_office.tex) | Annotate 6 markers |
| [resumes/master_technical_pm.tex](../resumes/master_technical_pm.tex) | Annotate 7 markers |
