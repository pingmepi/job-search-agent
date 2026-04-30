# Docs Review — job-search-agent

**Date:** 2026-04-30
**Repo HEAD:** `69ebd60` (branch `fix/out-of-scope-gate`)
**Scope:** All markdown docs in repo root + `docs/` + `interview-prep/`. Goes beyond the alignment scan ([docs-alignment-report.md](docs-alignment-report.md)) — covers structural issues, content quality, redundancy, and decisions to make.
**Companion artifact:** This is a one-shot review. Drift findings (stale instructions, removed APIs) live in [docs-alignment-report.md](docs-alignment-report.md). Anything that's already there is referenced, not re-described.

---

## Summary

| Severity | Count |
|----------|-------|
| 🔴 Critical (will actively mislead a reader)  | 5 |
| 🟠 Structural (file-level org / boundary)     | 7 |
| 🟡 Stale (was true, now outdated)             | 5 |
| 🟢 Suggestions / nice-to-haves                | 5 |
| ⚖️ Decisions to make                          | 6 |

**Bottom line:** The doc surface is broadly accurate but is starting to fragment along three axes: (a) a dual "what is this project" set (README.md vs docs/RUNBOOK.md vs docs/PROJECT_OVERVIEW.md), (b) AGENT_HANDOFF.md drifting from "short-lived handoff" to "incident archive," and (c) several files with explicit `Last updated:` headers that have stopped being maintained. Most fixes are 5-30 minutes each.

---

## 🔴 Critical Findings

### C1 — `AGENTS.md` is not documentation

**File:** [AGENTS.md](AGENTS.md) (66 lines)

**What it says:** Wrapped entirely in `<claude-mem-context>...</claude-mem-context>` tags. The body is a memory observation timeline ("S150 6:05p 🔵 Bulk GitHub Clone…", "S153 🟣 bullet_bank.json Updated…"). The closing line is `Access 551k tokens of past work via get_observations([IDs])`.

**Why it misleads:** The filename strongly implies it documents the agents in this system (Inbox, Profile, Follow-Up, Article). A new contributor or agent landing on the repo will open `AGENTS.md` first and find a memory tooling artifact. There's also no link to it from anywhere — strong signal it's an accidental commit.

**Fix:**
- **Option A (delete):** `git rm AGENTS.md` — it's not load-bearing; the actual agent docs are in [docs/PROJECT_OVERVIEW.md §2](docs/PROJECT_OVERVIEW.md) and [PRD.md §2](PRD.md).
- **Option B (repurpose):** Replace with a real ~80-line "Agents in this system" summary — purpose, entry point, tools, where to find tests for each. Worth doing if you want a single-page agent map separate from the longer PROJECT_OVERVIEW.

**Recommended:** Option A. The PROJECT_OVERVIEW already covers it.

---

### C2 — `docs/decisions.md` has duplicate ADR-14

**File:** [docs/decisions.md:244,282](docs/decisions.md)

**Evidence:**
```
ADR-14: Telegram Inbox Submissions Are Treated as Manually Vetted   (line 244)
ADR-14: Pre-Commit Hooks Over CI-Only Checks                        (line 282)
ADR-15: Agent Run Logging — Match Inbox Agent Observability         (line 303)
ADR-16: LLM Outputs as Untrusted Data                               (line 321)
ADR-17: Graceful Degradation with Visibility                        (line 345)
```
File header claims to track "every significant decision" with "cross-references" — but the second ADR-14 has no unique ID, so any external citation of "ADR-14" is ambiguous. There are 18 entries with 17 unique numbers.

**Fix:** Renumber `Pre-Commit Hooks Over CI-Only Checks` to `ADR-15`, then push subsequent entries to ADR-16, ADR-17, ADR-18. Add a one-line note at the top: "Renumbered 2026-04-30 to fix duplicate ADR-14." Internal references in BUILD_LOG.md / AGENT_HANDOFF.md should be grep-checked — ADR-12 is already referenced in [docs/decisions.md:24](docs/decisions.md), but I didn't find any ADR-14/15/16/17 cross-references in the repo.

---

### C3 — `AGENT_HANDOFF.md` "Known Risks / Gaps" is stale; the persona-mutation incident is buried

**File:** [AGENT_HANDOFF.md:36-39](AGENT_HANDOFF.md)

**What it says:**
> ## Known Risks / Gaps
> - Follow-Up Agent adapter only shows status list via `/status` — never generates or shows drafts to user.
> - URL ingestion behavior is incomplete relative to PRD expectations.
> - LOW-severity code smells from audit: unbounded JD cache, Image.open without `with`, singleton thread safety.

**Reality (per AGENT_HANDOFF.md:57-144 of the same file):** The dominant risk is the persona-mutation incident family (run-144b1afaef4a, run-d8c3e572aded), 5 missing pipeline gates, and the soft-eval parser fragility (which silently scored every historical run at 0.0 — see [memory 594](memory)). Three of the five gates have shipped (gates 1, 2, 5); gate 4 was rediscovered and fixed.

**Why it misleads:** A reader skimming the top-of-file "Known Risks" section will think the system is healthy modulo a Follow-Up UX gap. They'd need to read 40+ lines further to see the actual production incident. Anyone hand-offing under context pressure will hit the wrong picture.

**Fix:** Promote the incident summary to "Known Risks." A reasonable rewrite:

```
## Known Risks / Gaps
- **Out-of-scope JDs:** persona-mutation incident (run-144b1afaef4a) drove a 5-gate plan;
  gates 1, 2, 4, 5 shipped on `fix/out-of-scope-gate`; gate 3 (JD-role allowlist) not yet built.
  See "Persona-mutation incident & pipeline gate gaps" handoff entry below.
- **Eval artifact persistence:** evals/report.py reads local `runs/artifacts/*` — these
  vanish on every Railway redeploy. Needs DB-backed read path. (Static-analysis finding 475.)
- **Follow-Up Agent UX gap:** adapter only shows status list via `/status`, never drafts.
- LOW-severity code smells from 2026-04-08 audit: unbounded JD cache, Image.open without
  `with`, singleton thread safety. Tracked but not actively breaking.
```

---

### C4 — `AGENT_HANDOFF.md` self-contradicts on Gate #4

**File:** [AGENT_HANDOFF.md:88](AGENT_HANDOFF.md) vs [AGENT_HANDOFF.md:114-144](AGENT_HANDOFF.md)

**What it says (line 88):** Lists "Soft-eval hard floor" as a missing gate (#4 of 5).

**What's also in the same file (line 114+, "Regression soft-score floor + soft-eval parsing hardening" entry):** Documents that the soft-eval floor was found to *exist* but be silently broken (fenced JSON parser bug → all soft scores 0.0); fix landed in commit `69ebd60`. So gate #4 was implemented earlier but invisible due to the parser bug, and is now actually working.

**Fix:** Update the gate-4 bullet on line 88 to:
> 4. **Soft-eval hard floor post-`eval_log`** — ✅ implemented; was silently broken by a fenced-JSON parsing bug; fixed in commit `69ebd60` (2026-04-30). `SOFT_RELEVANCE_FLOOR=0.4` is hardcoded in `executor.py` eval assembly.

---

### C5 — Test baseline `251 passed, 37 skipped` is wrong in three places

**Files:** [AGENT_HANDOFF.md:12](AGENT_HANDOFF.md), [AGENT_HANDOFF.md:53](AGENT_HANDOFF.md), [TRACKER.md:15](TRACKER.md)

**Reality:** Commit `69ebd60` (2026-04-30) confirms `318 passed, 41 skipped`. The alignment scan ([docs-alignment-report.md:30-33](docs-alignment-report.md#L30-L33)) flagged this as MED on 2026-04-30 morning with a one-shot `pytest` re-run as the fix; the fix didn't land.

**Fix:** Run `.venv/bin/pytest -q -m "not live"`, copy the count, replace all 3 instances. While there, mention test baseline ownership ("update this when you add tests" or remove the count entirely and link to a CI badge).

---

## 🟠 Structural Findings

### S1 — `docs/execution_plan` lacks a file extension

**File:** [docs/execution_plan](docs/execution_plan) (314 lines, plain markdown content)

**Why it matters:** Most markdown renderers (VSCode preview, GitHub web UI, link checkers, MkDocs) gate behavior on the `.md` extension. The file is currently treated as plain text. There are no links to it from any other doc — discoverability is zero.

**Fix:** Rename to `docs/execution_plan.md` (or move under `docs/decisions.md` if redundant — review content first). One-line `git mv`.

---

### S2 — No `CHANGELOG.md`

**Reality:** There's [BUILD_LOG.md](BUILD_LOG.md) (dev-internal narrative) and [docs/decisions.md](docs/decisions.md) (architecture decisions), but no user/operator-facing changelog. With no version tags either, the only way for someone external to see "what changed last week" is `git log`.

**Fix options:**
- **Lightweight:** add a `CHANGELOG.md` at root, manually entered on each significant PR.
- **Generated:** wire the `changelog-generator` skill (available in this Claude Code env) to auto-extract from commits. Suggested cadence: regenerate on every push to `main`.
- **Punt:** if there's no external audience, skip and link to `BUILD_LOG.md` from README.

**Recommended:** Lightweight `CHANGELOG.md` keyed off Linear ticket IDs (KAR-XX). It pays off the moment you onboard another contributor.

---

### S3 — Three overlapping "what is this project" surfaces

| File | Length | Apparent role |
|------|--------|---------------|
| [README.md](README.md) | 99 lines | Root, runbook-flavored quickstart |
| [docs/RUNBOOK.md](docs/RUNBOOK.md) | 438 lines | Deep runbook (setup, env vars, webhook setup) |
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | 378 lines | Architecture + history + metrics |

**Why it matters:** A new reader doesn't know which is canonical. Some content is duplicated (env-var lists exist in both README.md and docs/RUNBOOK.md), some is contradictory (README.md:49 has stale DATABASE_URL form per [docs-alignment-report.md](docs-alignment-report.md) MED finding).

**Fix — recommended boundary:**
- **README.md (root):** elevator pitch + quickstart + link map only. ~60 lines.
- **docs/RUNBOOK.md:** the canonical operational runbook (env, setup, deploy, ops). Keep length.
- **docs/PROJECT_OVERVIEW.md:** architecture + decisions + history. Already plays this role.

Add a "Where to look" section at the top of root README pointing into the other two.

---

### S4 — Two `README.md` files in the repo

**Files:** [README.md](README.md), [docs/RUNBOOK.md](docs/RUNBOOK.md) (renamed from `docs/README.md`)

**Why it matters:** GitHub auto-renders the root one only. Search engines and AI agents indexing the repo can still find multiple top-level "overview-like" docs with overlapping scope.

**Fix:** Rename `docs/README.md` → `docs/RUNBOOK.md` (completed) and keep a clear boundary banner/link map in root README.

---

### S5 — `AGENT_HANDOFF.md` has outgrown its stated purpose

**File:** [AGENT_HANDOFF.md:5-6](AGENT_HANDOFF.md)

**What it says:** "This file is the short-lived operational handoff between sessions/windows when context gets full. Keep it concise and current."

**Reality:** 144 lines, two embedded RCAs (run-144b1afaef4a + soft-eval parser hardening), 22 days of "What Was Just Completed" entries (2026-04-08 → 2026-04-30), and a "Quick Start For New Agent" section that duplicates README.md content.

**Fix options:**
- **Truly short-lived:** prune to the most recent handoff entry only; archive prior entries to BUILD_LOG.md.
- **Rename to honest scope:** rename to `INCIDENTS.md` or `SESSION_LOG.md` — that's what it actually is.
- **Status quo + cap:** add a "Last 7 days only" rule and rotate entries out manually.

**Recommended:** Rename to `SESSION_LOG.md`. The current content has become valuable institutional memory; calling it "handoff" undersells it.

---

### S6 — `BUILD_LOG.md` is frozen at 2026-04-08

**File:** [BUILD_LOG.md:5](BUILD_LOG.md)

**What it says:** `Last updated: 2026-04-08`. File timeline ends at "Operations Fixes (2026-04-02)".

**Reality:** Missing 22 days of work — the 2026-04-23 application reports milestone, the 2026-04-29 persona incident, the 2026-04-30 soft-eval hardening. PR #30 (docs alignment) and PR #31 (out-of-scope gate) are both invisible.

**Fix options:**
- **Catch up:** add three entries for 2026-04-23 (application reports + integrity tooling), 2026-04-29 (persona incident discovery + 5-gate plan), 2026-04-30 (gates 1,2,4,5 shipped + soft-eval parser fix). ~20 minutes.
- **Freeze + successor:** rename to `BUILD_LOG_2026-Q1.md`, start `BUILD_LOG.md` fresh.
- **Replace with CHANGELOG:** see S2.

**Recommended:** Catch up. The history is valuable; the gap only gets harder to close.

---

### S7 — Project name inconsistency: `inbox-agent` vs `job-search-agent`

**Files:**
- [PRD.md:15](PRD.md) — `Project Name: \`inbox-agent\``
- [README.md:1](README.md) — `# Job Search Agent`
- Repo dir / pyproject / Linear project / Railway service — all `job-search-agent`

**Why it matters:** The PRD is a decision-record artifact; calling the project by an old name in the canonical PRD is confusing for anyone using PRD.md as ground truth.

**Fix:** Update [PRD.md:15](PRD.md) to `Project Name: \`job-search-agent\` (formerly \`inbox-agent\`)` or just `\`job-search-agent\``.

---

## 🟡 Stale Findings (was true, now outdated)

### St1 — `TRACKER.md` "Latest Progress (2026-04-23)" is now a week old

**File:** [TRACKER.md:20](TRACKER.md)

Add a 2026-04-30 entry: persona-incident discovery, gates 1/2/4/5 shipped on `fix/out-of-scope-gate`, soft-eval parser hardening (commit `69ebd60`).

---

### St2 — `Active issue: KAR-62` framing is stale

**Files:** [AGENT_HANDOFF.md:14,30](AGENT_HANDOFF.md), [TRACKER.md:18](TRACKER.md)

[PRD.md:554-558](PRD.md) shows KAR-62 as 3 Done / 2 Todo (Portal scanner + Operator dashboard remain). Real focus this past week has been the persona-incident gates, not KAR-62. "Active issue" should reflect lived reality.

**Fix:** Replace with `Active focus: \`fix/out-of-scope-gate\` branch (PR #31) — pipeline gates for out-of-scope JDs. KAR-62 paused (3/5 done; scanner + dashboard pending).`

---

### St3 — `docs/decisions.md` "Last updated: 2026-04-23" predates the 5-gate decisions

**File:** [docs/decisions.md:5](docs/decisions.md)

Missing decisions worth ADRs (each is genuinely a "we considered X, chose Y, here's why"):
- **Out-of-scope as a pipeline-level concern, not a prompt concern** — `OutOfScopeError` raised before any LLM sees the input. Considered: prompt-level "refuse if outside scope" (didn't hold under adversarial JDs); chose pipeline-level gate.
- **Mode-aware fit-score floor (`FALLBACK_MIN_SCORE = 0.075`)** — single threshold can't satisfy both primary-mode (skills-based) and fallback-mode (token-based) scoring; chose mode-aware threshold at 15% of fallback ceiling.
- **Soft-eval hardening — fenced-JSON recovery** — chose `extract_first_json_object` fallback over forcing prompt re-instruction. Note that all historical soft scores were silently 0.0 ([memory 594](memory)).
- **Regression dataset enrichment with `min_soft_resume_relevance` floors** — chose to assert soft-score floors on happy-path cases, not just structural assertions.

---

### St4 — `docs/PROJECT_OVERVIEW.md` "Current metrics (2026-04-08)"

Already covered as LOW in [docs-alignment-report.md](docs-alignment-report.md). Re-run `python main.py ci-gate` and refresh, or relabel as a snapshot.

---

### St5 — `docs/webhook-service*.md` duplication

**Files:** [docs/webhook-service.md](docs/webhook-service.md) (156 lines) and [docs/webhook-service-instructions.md](docs/webhook-service-instructions.md) (39 lines)

Names suggest the same scope but different sizes. Confirm whether the 39-line file is a stub, a quickstart, or vestigial. If vestigial, delete; if a quickstart, link the two and add a banner.

---

## 🟢 Suggestions

### Sg1 — Add `docs/INDEX.md` (or a "Docs map" section in root README)

A single one-page index telling readers "PROJECT_OVERVIEW = architecture, decisions = ADRs, setup-and-test = onboard, troubleshooting = ops, BUILD_LOG = history" removes ~80% of the "which doc is canonical" tax.

---

### Sg2 — Add cross-link footers

Most top-level docs ([AGENT_HANDOFF.md](AGENT_HANDOFF.md), [BUILD_LOG.md](BUILD_LOG.md), [TRACKER.md](TRACKER.md)) don't link to each other or to PROJECT_OVERVIEW. A 4-line footer per doc:
```
## See also
- [PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — architecture
- [decisions.md](docs/decisions.md) — ADRs
- [BUILD_LOG.md](BUILD_LOG.md) — dev history
```

---

### Sg3 — Promote `interview-prep/` or move it

[interview-prep/](interview-prep/) currently has two role-tailored FAQ docs (`ai-product-builder.md`, `ai-engineer-llm.md`) with no link from README. Either:
- Add a one-line README pointer ("Interview prep: see [interview-prep/](interview-prep/)"), or
- Rename to `docs/role-faqs/` to live alongside other docs, or
- If they're personal artifacts, add to `.gitignore` and remove from tracking.

---

### Sg4 — Wire `changelog-generator` for auto-changelogs

Available skill; could regenerate `CHANGELOG.md` on PR merge or branch push. Pairs with S2.

---

### Sg5 — Add a release-status badge to README

A CI-status / test-pass badge at the top of [README.md](README.md) reduces the staleness of inline test counts (covered in C5). The badge always tells the truth; the inline count rots.

---

## ⚖️ Decisions to Make

These are open questions that will keep generating doc-churn until decided. Listing as choices, not recommendations — these are yours to call.

### D1 — `AGENTS.md`: delete or rewrite?

- **Delete:** content is a memory artifact; no other doc depends on it. Cleanest.
- **Rewrite:** real "agents in this system" overview, ~80 lines. Useful if you want a single agents-focused doc separate from PROJECT_OVERVIEW §2.

---

### D2 — Adopt `CHANGELOG.md`?

- **Yes:** lightweight or auto-generated; helps future contributors and your own future-you.
- **No:** rely on `git log` and BUILD_LOG.md; fewer surfaces to keep current.

---

### D3 — How to fix the duplicate ADR-14?

- **Renumber forward** (14b → 15, 15 → 16, 16 → 17, 17 → 18). Cleanest. Risk: any external citation breaks (none found in repo).
- **Renumber backward** (rename old 14 → 13b). Less disruption but uglier.
- **Live with it:** mark one of them ADR-14a / ADR-14b explicitly. Pragmatic.

---

### D4 — Reframe `AGENT_HANDOFF.md` scope?

- **Keep "short-lived":** prune to last entry only; archive elsewhere.
- **Rename to `SESSION_LOG.md`:** acknowledge what it's become.
- **Status quo:** accept the drift, document the rule somewhere.

---

### D5 — `BUILD_LOG.md`: catch up, freeze, or replace?

- **Catch up:** ~3 new timeline entries; valuable history preserved.
- **Freeze + successor:** rename `BUILD_LOG_2026-Q1.md`; new file going forward.
- **Replace with CHANGELOG:** if S2 lands.

---

### D6 — `inbox-agent` (PRD) vs `job-search-agent` (everywhere else)

- **Pick `job-search-agent`:** matches dir, package, Linear, Railway. Update PRD §0/§1.
- **Live with it:** annotate PRD with "renamed to job-search-agent."

Recommended: pick `job-search-agent` everywhere.

---

## Quick-Fix Punch List (in order, 1-2 hour total)

1. ✅ Delete or rewrite [AGENTS.md](AGENTS.md). (C1) — 2 min
2. ✅ Renumber the second ADR-14 in [docs/decisions.md](docs/decisions.md). (C2) — 5 min
3. ✅ Update test baseline in [AGENT_HANDOFF.md](AGENT_HANDOFF.md) and [TRACKER.md:15](TRACKER.md) from a fresh local run. (C5) — 3 min
4. ✅ Promote persona-incident summary into [AGENT_HANDOFF.md "Known Risks"](AGENT_HANDOFF.md#L36). (C3) — 10 min
5. ✅ Update Gate #4 bullet to "✅ shipped, was broken via parser bug, fixed 69ebd60." (C4) — 2 min
6. ✅ `git mv docs/execution_plan docs/execution_plan.md` (or delete if vestigial). (S1) — 2 min
7. ✅ Add 3 new ADRs in [docs/decisions.md](docs/decisions.md): out-of-scope gate, mode-aware fit-score floor, soft-eval parser hardening. Refresh "Last updated" date. (St3) — 25 min
8. ✅ Catch up [BUILD_LOG.md](BUILD_LOG.md) with 3 entries (Apr 23, Apr 29, Apr 30). (S6) — 20 min
9. ✅ Add 2026-04-30 progress entry to [TRACKER.md](TRACKER.md). (St1) — 5 min
10. ✅ Reframe `Active issue: KAR-62` → `Active focus: out-of-scope-gate` in [TRACKER.md:18](TRACKER.md), [AGENT_HANDOFF.md:14,30](AGENT_HANDOFF.md). (St2) — 3 min
11. ✅ Update [PRD.md:15](PRD.md) project name. (S7) — 1 min
12. ✅ Reconcile [docs/webhook-service.md](docs/webhook-service.md) vs [docs/webhook-service-instructions.md](docs/webhook-service-instructions.md). (St5) — 10 min

The remaining (S2/S3/S4/S5, Sg1-5, D1-6) are decisions or larger refactors — not quick fixes.

---

## What This Review Did NOT Cover

- **Code/docs alignment drift** — handled by [docs-alignment-report.md](docs-alignment-report.md).
- **Spelling, grammar, prose tightening** — manual pass not done.
- **Internal accuracy of long files** — I sampled key sections. A line-by-line audit of [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) (378 lines) and [PRD.md](PRD.md) (565 lines) wasn't in scope.
- **`docs/setup-and-test.md`, `docs/troubleshooting-and-debugging.md`, `docs/google-oauth-setup.md`** — opened but not read in depth. Worth a separate pass.

If you want any of those expanded, point at the file and I'll do a targeted review.
