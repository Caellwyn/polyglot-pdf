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

## What was done

Every flagged doc was verified claim-by-claim against the code that changed
since its stamp (not just date-bumped): the changed commits were inspected, the
current code read for every claim about those files, and real drift fixed in
the doc text. Six parallel reviewer agents each owned a cluster of related
docs; tier-1 (CLAUDE.md, docs/INDEX.md) was reviewed by hand.

Substantive corrections (the rest were verified accurate, stamp-only):

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
- **components/config-deployment.md** -- the env-flag list and feature-flag
  table omitted the live `USE_DTI` flag; added.
- **standards/validation-delegation.md** -- Frozen Contract 5 showed only
  `ITextAI.validate()`; the port also declares `ask()` (secretary, jnjj.45).
  Updated; drifted line-number pointers replaced with symbolic references;
  `backend/ports/text_ai_port.py` added to Tracks.
- **standards/hipaa-pii-policy.md** -- the `GUARDED_FILES` enumeration listed
  3 of the 6 files actually guarded by `test_no_pii_logging.py`; fixed. Added
  the DTI current-field-id coercion note (confirm logs can carry the coerced
  `current_field_id`, not the raw model arg). Tracks line gained the 3
  missing guarded files.
- **standards/confirmation-and-audit.md** -- removed a "Prior:" history chain
  from the stamp; documented the DTI confirm-field-id coercion.
- **standards/logging-and-cost.md** -- folded the `gemini_go_away_received`
  structlog event into the body (was only in the stamp blob). Measured cost
  invariant left untouched (empirical, not code-derivable).
- Remaining per-doc corrections (voice-ai, tool-call-flow,
  context-compression, websocket-routing, ws-protocol,
  stateless-architecture, voice-and-vad, schema-forms, jit-schema,
  terminology) are listed in the PR body for bd polyglot-pdf-mpoe.

## Convention change folded in

Stamp lines had accreted multi-paragraph "Prior:" history blobs (voice-ai.md's
was ~20 lines). Per `docs/doc-architecture.md` the stamp is ONE line pointing
at a journal entry; history lives in the journal. All refreshed docs now carry
a single-line stamp pointing here. Any still-true current-state fact found
only in an old stamp blob was folded into the doc body before the blob was
dropped.
