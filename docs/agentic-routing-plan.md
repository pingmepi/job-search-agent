# Agentic Routing — Design Plan

**Status:** Proposed (2026-05-05)
**Author:** Karan M (with Claude)
**Related:** PR #31 (out-of-scope gate), [core/router.py](../core/router.py), [agents/inbox/adapter.py](../agents/inbox/adapter.py)

## Background

The current router in [core/router.py](../core/router.py) is deterministic — pure regex/keyword matching with six rules. It misroutes in two well-understood ways:

1. **URL force-route to inbox** ([router.py:125-131](../core/router.py#L125-L131)): any URL is treated as a job listing sight-unseen, so articles shared as links (Medium, Substack, blog posts) get pushed through the JD pipeline.
2. **JD-keyword false positives** ([router.py:146-158](../core/router.py#L146-L158)): the JD indicator list contains phrases (`"responsibilities"`, `"qualifications"`, `"requirements"`, `"you will"`, `"must have"`, `"years of experience"`) that appear constantly in career/leadership/AI articles. Two matches → forced to inbox. The article-detection branch is also gated on `jd_score == 0`, so a single JD-ish phrase permanently blocks the article route.

A third failure mode exists for **images**: `has_image=True → INBOX` is unconditional, so screenshots of articles, notes, or anything non-JD get the same treatment.

### Confirmed bug from production runs

Two consecutive runs in the Railway DB on 2026-05-05 (16:31 UTC):

| | run-179a5325d173 | run-61771d31a05c |
|---|---|---|
| agent | inbox | inbox |
| input_mode | text (no URL) | text (no URL) |
| jd_extract result | `company=Unknown, role=Unknown, skills=[]` | same |
| resume_select | failed: out_of_scope, fit=0.0 | same |
| duration | 6.4s | 5.9s |

Both runs fed the same article body as text. The deterministic router matched ≥2 JD indicators, forced INBOX, and the LLM `jd_extract` correctly identified it as not-a-JD (empty skills, Unknown role) — but the pipeline kept marching to `resume_select`, which tripped PR #31's out-of-scope gate. User got a confusing error instead of an article summary.

## Goal

Replace the deterministic router with an LLM-driven classifier that reads the message and reasons about intent. Keep deterministic rules as a fast-path / safety fallback, not the primary brain. Handle all input modalities (text, URL, image) with the **same text-only classifier**, using OCR and URL-fetch as preprocessors.

## Non-goals

- Not changing the downstream agents (inbox, article, profile, followup) — only how messages get routed to them.
- Not adding a multimodal LLM call. OCR is cheap and preserves the cost profile; multimodal Haiku per-message was rejected on cost grounds.
- Not removing PR #31's out-of-scope gate — it remains the safety rail for genuine but sparse JDs.

## Constraints

- **Latency budget**: routing is currently ~0ms; new flow can spend ~300–600ms (Haiku 4.5) on the hot path. URL fetches and OCR add their own time on top — acceptable since both already happen in the inbox path today.
- **Cost**: ~one classifier call per inbound message. `claude-haiku-4-5`, JSON output, ~150-token completion. Prompt caching on the system prompt (5-min TTL).
- **Failure isolation**: classifier error / timeout → fall back to deterministic rules. Never block a user message on classifier outage.
- **Telemetry**: every routing decision logs `route_method`, `route_confidence`, `ocr_used`, classifier latency and tokens, into `runs` / `run_steps` for offline eval.

## Pipeline shape

```
        ┌────────────────────────────────┐
input → │ preprocess (text-ify)          │ → text → classifier → route
        │  • text  → pass through        │           (Haiku 4.5,
        │  • URL   → fetch_url_text      │            JSON out,
        │  • image → tesseract OCR       │            ~150 toks)
        └────────────────────────────────┘
```

Cost split: cheap path for everyone (Tesseract + Haiku, ~$0.0005/msg). Expensive vision-LLM extraction only runs in the inbox JD pipeline **after** the classifier confirms it's a JD — same as today, just gated on a real signal instead of "has_image → blind inbox."

## Key design decision: Phase 1 (post-extract reroute) is rejected

An earlier draft proposed short-circuiting after `jd_extract` returns empty skills — reroute to article agent instead of letting `resume_select` fail. **This conflicts with PR #31** and is unsafe as a standalone fix.

PR #31's out-of-scope gate exists to handle the "input was *intended* as a JD but is too weak/garbled to act on" case. It persists a Run record with `out_of_scope=true` and an explicit error so the user knows why nothing came back. A post-extract reroute collapses two distinct user intents:

| User actually sent... | jd_extract returns | Phase-1 reroute | What user wanted |
|---|---|---|---|
| An article | `skills=[], role=Unknown` | reroute → article ✅ | summary + signals |
| A real but sparse JD | `skills=[], role=Unknown` (LLM is conservative) | reroute → article ❌ | "couldn't get enough signal" |
| A garbled JD copy-paste | same | reroute → article ❌ | same as above |

`skills==[]` is **not** a clean signal of "this isn't a JD" — it can mean "extractor found no skills" for either reason. The clean fix is structural: classify *before* `jd_extract` runs, so the article path is never entered for genuine JDs and the JD path is never entered for articles. PR #31's gate stays intact for the case it was designed for (sparse JD recognized as a JD by the classifier).

## Phases

### Phase A — OCR utility

**New file:** [core/ocr.py](../core/ocr.py)

- `ocr_image(image_bytes_or_path) -> OCRResult(text, char_count, confidence)` using `pytesseract`.
- Preprocess: convert to grayscale, threshold for screenshot text. Tesseract handles printed text well, struggles on stylized/dark-mode UI — acceptable for routing (we only need keyword density, not perfect transcription).
- If `char_count < 50` → return `OCRResult.empty()` and let classifier handle empty-text path (likely → `AMBIGUOUS_NON_JOB` "couldn't read your image, paste the text").

**Dependencies:**
- [Dockerfile](../Dockerfile): `apt-get install -y tesseract-ocr`.
- [pyproject.toml](../pyproject.toml): add `pytesseract>=0.3.10`. (Pillow is likely already a transitive dep — verify.)

### Phase B — URL fetch hoisted ahead of routing

In [agents/inbox/adapter.py](../agents/inbox/adapter.py) around line 470 (just before `route()` is called), move `fetch_url_text` to run **before** routing for URL-only messages. Pass extracted text into the classifier instead of the raw URL.

- Fetch failure → keep existing `URL_FALLBACK_PROMPT` behavior.
- The "🔗 Fetched job URL successfully…" user-facing message becomes generic ("Fetched URL content…") since we don't yet know it's a JD at fetch time.

### Phase C — LLM classifier

**New file:** [core/router_llm.py](../core/router_llm.py)

- Single function `classify(text) -> RouteResult`. No image param — all image handling done via OCR upstream.
- Haiku 4.5, temp 0, JSON-mode response:
  ```json
  {
    "target": "inbox|profile|followup|article|ambiguous_non_job|clarify",
    "confidence": 0.0-1.0,
    "reason": "<one sentence>",
    "signals": {
      "is_jd": bool,
      "is_article": bool,
      "asks_about_karan": bool,
      "asks_about_followups": bool
    }
  }
  ```
- Prompt-cache the system prompt (rules + 6–8 few-shot examples covering today's failure cases — including the two real-world misrouted articles from the Railway DB).
- `confidence < 0.6` → `CLARIFY`. Better to ask than misroute.
- Failure modes (timeout, JSON parse, API error) → fall back to existing deterministic `route()`. Never block the user message.

### Phase D — Wire everything in [core/router.py](../core/router.py)

- Keep deterministic `route()` as `_route_deterministic()` — used as fallback only.
- New `route()` becomes: `(preprocess if needed) → classify_llm → (deterministic fallback on error)`.
- Behind a feature flag `ROUTER_USE_LLM` (env var, default `false`) so we can ship code first, flip on after evals pass.
- Image input arriving with `has_image=True` no longer hard-routes — caller (adapter.py) is responsible for OCR'ing and passing text. If OCR yielded nothing, classifier sees empty text and returns `AMBIGUOUS_NON_JOB`.

### Phase E — Eval harness

**New files:** [evals/router_eval.jsonl](../evals/), [evals/run_router_eval.py](../evals/)

~40 cases across categories:
- Real JDs (text, URL-extracted, screenshot-OCR'd) — should → `inbox`
- Articles (text, URL-extracted, screenshot-OCR'd) — should → `article`
- **Today's two failed runs from the Railway DB — regression cases, must → `article`**
- Profile/Karan asks → `profile`
- Follow-up checks → `followup`
- Garbage / greetings / empty OCR → `ambiguous_non_job` or `clarify`

Runner compares deterministic vs LLM, prints confusion matrix + per-class accuracy.

**Pass bar:** ≥95% on JD/article disambiguation, 100% on profile/followup. Cost & latency budget assertions too.

### Phase F — Telemetry

Additive columns on `runs` ([core/db.py](../core/db.py)):
- `route_method` — `deterministic` | `llm` | `llm_fallback_to_deterministic`
- `route_confidence` — float, nullable
- `ocr_used` — bool
- `preprocess_text_chars` — int, nullable

Per-call `run_steps` entry for the classifier itself: `input_hash`, output JSON, latency, model, tokens.

This must land **early** (alongside Phase A) so even the deterministic baseline emits the new fields. Gives us data to mine for Phase E and a baseline to compare against once the LLM router flips on.

## Files touched

| File | Change | Phase |
|---|---|---|
| [core/ocr.py](../core/ocr.py) | NEW — pytesseract wrapper | A |
| [Dockerfile](../Dockerfile) | apt install tesseract-ocr | A |
| [pyproject.toml](../pyproject.toml) | + pytesseract | A |
| [agents/inbox/adapter.py](../agents/inbox/adapter.py) | OCR images, fetch URLs before route | A, B |
| [core/router.py](../core/router.py) | Refactor: deterministic = fallback | D |
| [core/router_llm.py](../core/router_llm.py) | NEW — Haiku classifier | C |
| [core/db.py](../core/db.py) | Additive route columns | F |
| [evals/router_eval.jsonl](../evals/) | NEW — eval set | E |
| [evals/run_router_eval.py](../evals/) | NEW — runner | E |
| [tests/test_router.py](../tests/) | Extend; mock LLM | C, D |
| [tests/test_ocr.py](../tests/) | NEW — OCR unit tests | A |

## Risks

1. **OCR dep on Railway.** Tesseract is a system binary — needs to land in Dockerfile and survive Railway's build. Low risk (Tesseract is in standard Debian repos, used widely in Railway deployments) but worth verifying with one no-op deploy before plumbing the rest.

2. **OCR quality on real Telegram images.** Compressed screenshots, dark mode, mobile UI chrome, stylized fonts. We don't need perfect text — keyword density is enough for the classifier. But there's a long tail where Tesseract returns gibberish and the classifier confidently misclassifies on noise. Mitigation: log `preprocess_text_chars` and OCR confidence; sample low-confidence cases offline; the `confidence < 0.6 → CLARIFY` floor catches most of these.

3. **Cold-cache latency.** First message after deploy pays full system-prompt cost (~1500 tokens). Anthropic prompt caching's 5-min TTL keeps the hot path cheap during active sessions. Acceptable.

4. **Eval set is the bottleneck**, not the code. Phase E must land before flipping `ROUTER_USE_LLM=true` in prod. Without it we're swapping one set of false positives for another and won't know.

5. **Classifier vs PR #31 interaction.** A genuinely sparse JD that the classifier correctly identifies as `inbox` will still hit `jd_extract` returning `skills=[]` and PR #31's gate will trip. That's correct behavior — the user gets the explicit out-of-scope error rather than a wrong-shaped response. Document this in the runbook so future-Karan doesn't re-discover it.

## Execution order

1. **Phase A** (OCR + Dockerfile) — verify Tesseract works on Railway with a no-op deploy.
2. **Phase F** (telemetry) — go in early so even the deterministic baseline gets logged. Gives us data to mine for Phase E.
3. **Phase E** half 1 — build eval set from Railway `runs` table while it's fresh.
4. **Phase C + D + B** behind `ROUTER_USE_LLM=false`.
5. **Phase E** half 2 — run evals against both routers, tune classifier prompt.
6. Flip `ROUTER_USE_LLM=true`, watch telemetry for a day.

Estimated effort: 2–3 focused days.

## Open questions

- Where does the Haiku call live — `core/llm.py` (existing wrapper) or its own client? Default to existing wrapper for retry/usage-tracking consistency unless there's a reason to bypass.
- Should the classifier prompt include the user's recent message history (last N turns)? Argues for: better disambiguation of "yes" / "the second one" follow-ups. Argues against: more tokens, more cache invalidation. Default off for v1; revisit if eval shows context-free errors.
- OCR fallback policy if Tesseract returns <50 chars: ask user, or burn one multimodal Haiku call as escape hatch? Default to ask-user (cheaper, clearer UX); revisit if user-friction is high in telemetry.
