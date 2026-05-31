---
date: 2026-05-31
bead: polyglot-pdf-b11
title: "Standards docs: logging/PII/audit batch (b11 + gbn + m8s)"
tags: [security, conventions]
---

# polyglot-pdf-b11 (+gbn, +m8s): logging/PII/audit standards docs

One PR bundling three tightly-coupled tier-2 standards docs from the docs-reorg
epic (`polyglot-pdf-gfb`). They share the same logger surface
(`log_schemas`/`structured_logger`, `confirmation_logger`, `token_file_logger`)
and cross-link each other, so they are one reviewable unit.

## Trigger

The gfb epic decomposes the canonical docs into tier-2 component/standards docs.
b11 (hipaa-pii-policy), gbn (confirmation-and-audit), and m8s (logging-and-cost)
are the cross-cutting logging/cost/privacy concerns. Batched per the maintainer's
"draft several, then review-batch" call for this run.

## What shipped

Three new docs under `docs/standards/`, each verified line-by-line against the
**dev-branch** code (not the bead text), plus three `docs/INDEX.md` rows flipped
from `_(planned)_` to live links:

- **hipaa-pii-policy.md** — the never-log/always-safe rule + a per-surface status
  table. Enforcement is **by-construction/convention** (no runtime scrubber
  exists); `dev_file_logger` is the one PHI sink, gated by `backend/.env.DEV`
  existence. Known code leaks tracked under `polyglot-pdf-hjo` (P1).
- **confirmation-and-audit.md** — `confirm_field` workflow (enum exactly
  `["verbal","manual"]`), `log_field_confirmation` event shape (field_id + method,
  never the value), `CONFIRMATION_LOG_DIR` env override, liability rationale.
- **logging-and-cost.md** — `GEMINI_PRICING_BY_FAMILY` + `model_family()` /
  `get_pricing_for_model()`; adapter cost calc + session accumulation;
  `TokenFileLogger` (caller supplies costs, not-prod); structured event schemas
  defined-but-not-emitting; phased roadmap migrated from `TODO.md` with bead refs.

Fresh-eyes triage (round 1): **5 adopted, 0 deferred, 1 skipped.** Adopted — H1:
confirmation JSON example showed an enriched `field_name` the code never emits
(caller passes `None` → equals `field_id`); fixed example + prose. M1: added
`structured_logger.py` to logging-and-cost Tracks. M2: softened "→ BigQuery"
present-tense to note Phase 5. M3: noted `log_form_session_start/end` are
defined-but-uncalled. L1: cited the ~25 tok/sec source. Skipped — L2 (INDEX short
label vs doc H1; INDEX uses short labels by convention). The reviewer
independently re-verified the factual core (no `strip_forbidden`; dead
`structured_logger` import; enum `verbal/manual`; family-keyed pricing; dev gate)
all correct.

## Lessons / surprises

- **Branch base is load-bearing.** The session opened a worktree off `main`, but
  the doctrine requires branching off `dev` (which was ~66 commits ahead). My
  first drafts described `main`'s stale code (flat mislabeled `GEMINI_PRICING`,
  hardcoded confirmation-log dir). Caught only because the code didn't match what
  I was writing. Re-cut off `origin/dev` and redrafted. The repo's git *default*
  branch is the legacy `shared-audio-stream`, so `EnterWorktree`'s "fresh" base is
  wrong here — branch off `origin/dev` explicitly.
- **Write from the code, not the bead.** The bead text and my own priors had me
  invent a `strip_forbidden`/`_FORBIDDEN_KEYS` enforcement layer that does not
  exist, the wrong confirmation enum (`ai_voice` vs the real `verbal`), and a
  family-keyed token logger (the family logic is in `config.py`, not the logger).
  Each was corrected by reading the actual file.
- **Imports ≠ usage.** `structured_logger` is imported by `live_ai_gemini.py` but
  never called (dead import); `StructuredLogger` emits nothing yet. The doc says
  "defined, not emitting" rather than "wired."

## Doc freshness

`check_doc_freshness.py`: the three new docs carry `**Tracks:**` + a
`*Last updated: 2026-05-30*` stamp; `tests/test_doc_freshness.py` (38) green;
doc-conventions clean (no `Previously:` chains, no history sections). The
same-day stale flag on two docs is the documented end-of-day-UTC vs today-commit
artifact (warn-only) — content was verified against that exact code today.

## Files touched

- `docs/standards/hipaa-pii-policy.md` — new (b11)
- `docs/standards/confirmation-and-audit.md` — new (gbn)
- `docs/standards/logging-and-cost.md` — new (m8s)
- `docs/INDEX.md` — three standards rows → live links
- `docs/journal/entries/2026-05-31-bd-b11-...md` — this entry
