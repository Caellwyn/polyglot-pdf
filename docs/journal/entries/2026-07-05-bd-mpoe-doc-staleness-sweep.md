---
date: 2026-07-05
bead: polyglot-pdf-mpoe
title: "Tier-1/2 doc staleness sweep: 19 flagged docs verified against code and refreshed"
tags: [conventions, doctrine]
---

## Trigger

The maintainer asked for a review + refresh of the tier-1 and tier-2 docs:
`scripts/check_doc_freshness.py` flagged 19 of 23 tier-2 docs STALE (8 of 10
`docs/components/`, 11 of 12 `docs/standards/`) -- tracked code had newer
commits than each doc's `*Last updated:*` stamp.

## What shipped

Every flagged doc was verified claim-by-claim against the code that changed
since its stamp (not just date-bumped): the changed commits were inspected, the
current code read for every claim about those files, and real drift fixed in
the doc text. Six parallel Sonnet reviewer agents each owned a cluster of
related docs; tier-1 (CLAUDE.md, docs/INDEX.md) was reviewed by hand.

Substantive corrections (the rest verified accurate, stamp-only):

- **CLAUDE.md** -- scar #5 still claimed the `part` wire-format drift was
  "sequenced under polyglot-pdf-zun"; zun shipped (token-log key is
  `section_id`, the handshake-manifest rename was frontend-internal). Reworded
  to the current state: the one remaining `part` holdout is the deliberately
  deferred backend-internal `manifest_service.py`/`ai_context.py` SI-text
  path. Also dropped "tier-2 docs are being populated under `gfb`" (epic
  closed; the set exists).
- **docs/INDEX.md** -- removed the stale "(planned)" row boilerplate; archived
  the shipped sprint plans 2, 3, 4 (all referenced epics/beads closed) to
  `docs/archive/` with rows in the new `docs/archive_completed_plans.md`;
  active list now carries sprints 1, 5, 6, 7 with open-work pointers.
- **components/voice-ai.md + tool-call-flow.md** -- tool count was stale
  ("five tools"; `TOOL_DECLARATIONS` has six -- `ask_secretary`, jnjj.45);
  `set_callbacks` enumeration was missing `on_user_activity` +
  `on_processing_done` (wpw.5); `send_client_content()` now returns `bool`
  (jnjj.17) -- all added.
- **components/context-compression.md** -- broken link to the sprint-4 plan
  (archived this sweep); now points at the archive copy + the go/no-go brief.
- **components/config-deployment.md** -- env-flag list and feature-flag table
  omitted the live `USE_DTI` flag; added.
- **components/jit-schema.md** -- undocumented `full_schema` handshake field
  (secretary, p68s/jnjj.45d) noted; stale Gap-P line citations refreshed;
  `callback_handler.py` + `config.py` added to Tracks.
- **components/websocket-routing.md** -- `confirm_field_response` row gained
  the `section_complete` sub-flag (njvh) the backend reads at section
  boundaries.
- **standards/voice-and-vad.md** -- the doc said the shipped VAD knobs are
  `LOW`/`LOW`/500ms/500ms; `config.py` says `VAD_START_SENSITIVITY` defaults
  `HIGH` (4sv7). Corrected; native-VAD `input_transcription` signal and the
  mic-energy/send-gate relationship folded into the body.
- **standards/validation-delegation.md** -- Frozen Contract 5 showed only
  `ITextAI.validate()`; the port also declares `ask()` (secretary). Updated;
  drifted line-number pointers replaced with symbolic references;
  `text_ai_port.py` added to Tracks.
- **standards/hipaa-pii-policy.md** -- `GUARDED_FILES` enumeration listed 3 of
  the 6 files actually guarded by `test_no_pii_logging.py` (uov.15); fixed.
  DTI confirm-field-id coercion (h1bn) noted; 3 missing guarded files added
  to Tracks.
- **standards/confirmation-and-audit.md** -- "Prior:" history chain removed
  from the stamp; DTI confirm-field-id coercion documented.
- **standards/logging-and-cost.md** -- `gemini_go_away_received` structlog
  event folded into the body (was only in the stamp blob). Measured cost
  invariant left untouched (empirical, not code-derivable).
- **standards/ws-protocol.md** -- ~50 line-number citations corrected for code
  growth; no semantic drift (type names / keys / unions all still match).
- **standards/stateless-architecture.md** -- secretary request-use-discard
  pattern folded into the Rules section; invariant claims verified unchanged.
- Verified accurate with stamp-only bumps: auth.md, schema-forms.md (+2 Tracks
  additions), terminology.md, testing.md (stray duplicate stamp removed),
  ai-models.md, risk-rating.md.

Fresh-eyes assess: see the PR body scorecard; outcome recorded in the merge
ping.

## Lessons

- Stamp lines accrete history: several docs carried multi-paragraph "Prior:"
  blobs inside the `*Last updated:*` line (voice-ai.md's was ~20 lines) that
  the conventions checker doesn't catch because they're one physical line. The
  stamp is ONE line pointing at a journal entry; still-true facts found only
  in a stamp blob were folded into the doc body before the blob was dropped.
- Precise `file.py:NNN` citations in tier-2 docs drift within weeks; symbolic
  references (function/flag names) survive code growth. ws-protocol.md and
  validation-delegation.md were converted where drift had already happened.

## Doc freshness

This sweep IS the doc-freshness work: 19 flagged docs verified + re-stamped;
checker now reports zero STALE, sprint-archive protocol clean, conventions
clean. The 4 unflagged tier-2 docs (pdf-filling, si-reduction,
beads-remote-bootstrap, technical_guide) were stamped after their tracked
code last changed and were not re-verified (recent closeouts already reviewed
them).

## Files touched

CLAUDE.md; docs/INDEX.md; docs/archive_completed_plans.md (new);
docs/archive/sprint_{2,3,4}_*.md (moved from docs/); all 19 flagged docs under
docs/components/ + docs/standards/; this journal entry. No code files.
