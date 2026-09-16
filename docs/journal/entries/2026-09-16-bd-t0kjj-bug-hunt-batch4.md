---
date: 2026-09-16
bead: polyglot-pdf-t0kjj
title: "Bug-hunt batch 4: dead-code assert, three stale doc citations, a docstring duplication"
tags: [testing, review]
---

## Trigger

Continuation of the open-ended bug-hunt mandate (self-select ready `sonnet`/
`haiku`-tier beads, fix and close as many as possible, re-tier and release
anything that turns out to touch multiple surfaces). Batches 2 and 3 already
shipped as PR #809 and PR #823. This is batch 4, picking up where batch 3's
own fresh-eyes review left off: `polyglot-pdf-t0kjj` was filed by that
review round per CLAUDE.md scar #8 ("enumerate the set before fixing any of
it") as a second instance of the same dead-code-assert shape `uyoi4` had
already fixed once in the same file.

## What shipped

Five beads closed, all `tier: sonnet`/`haiku`, all self-contained:

- **`t0kjj`** -- `test_no_real_firestore_guard.py`'s
  `test_get_db_is_still_caught_when_the_client_is_already_cached` had an
  `assert not isinstance(db, _FakeCachedClient)` INSIDE a `with
  pytest.raises(...)` block. That line could never execute either way: if
  `get_db()` raised as expected (the pass path), the `with` block exits on
  the exception before reaching the assert; if `get_db()` instead returned
  successfully, `pytest.raises` itself fails first with "DID NOT RAISE".
  Moved the assert outside the block. Mutation-verified per the bead's own
  exit criterion: removing the `fa_firestore.client` patch from
  `install_no_real_firestore_guard` now correctly reddens this exact test
  with a real "DID NOT RAISE" failure (previously it would have stayed
  green even with the guard defeated, since the file's other guarded
  assertions covered for it by coincidence).
- **`9utmk`** -- `docs/components/pdf-view.md` stated twice that
  `polyglot-pdf-1utg` (the edit-popover's value read defeating field-value
  aliasing) was an open "known gap". Verified against current code:
  `PDFViewer.tsx:159` already reads through `readFieldEntryWithAlias`, and
  bd `1utg` itself has been CLOSED since 2026-08-13. Rewrote both passages
  as a "Retired gap" note (matching the doc's existing convention for
  `polyglot-pdf-ks1y`) and bumped the stamp.
- **`6mfsi`** -- `admin-console/src/pages/FirmDetailPage.test.tsx`'s header
  comment cited a nonexistent file, `AlertRow.sharedImport.test.tsx`. The
  real file is `AlertRow.test.tsx`. Comment-only fix; verified via `grep -rn
  sharedImport admin-console/ docs/` returning zero matches afterward.
- **`hkmnq`** -- `docs/technical_guide.md`'s "single HTML entry" bullet
  cited `frontend/vite.config.ts` as the build config with no multi-page
  `rollupOptions.input`. Every actual deploy path (`npm run deploy`,
  `deploy-staging.sh`, `deploy-demo.sh`) builds with
  `vite.config.schema.ts` via `build:schema`/`build:schema:demo`, not the
  bare config `npm run dev` uses. The doc's CONCLUSION was right (single
  `main: index.html` entry) but its CITATION was wrong. Corrected to name
  the right config and the deploy scripts that prove it.
- **`q1s8y`** -- `backend/services/runtime_config.py`'s `KEY_TYPES` comment
  claimed to be "the ONE place a key's type is spelled out", while the
  module's own docstring restates every key's type in prose two sections
  above. Both were correct today; the comment's claim of uniqueness was
  not. Softened it to "the ONE AUTHORITATIVE place" and added a sentence
  naming the docstring as a second, unpinned, prose-only copy that
  `KEY_TYPES` governs -- rather than removing the docstring's useful
  "what moved and from where" narrative.

**Re-tiered, not fixed:** four separate beads (`gpu4v`, `5gzpp`, `kyrd4`,
`e7aa4`) were all found during investigation to describe the exact same
underlying problem in `docs/components/admin-service.md` -- a 1227-line
file with 15 stacked `*Last updated:*` stamp paragraphs that should be
collapsed into current-state prose (a `doc-architecture.md` section 3
violation), filed independently by different review passes at different
times. Collapsing that many historical entries into accurate current-state
prose across a large surface is genuine editorial judgment (verifying each
historical claim is still true, deciding what merges into body prose vs.
drops as redundant with the journal) -- not a mechanical find-and-replace,
and not something that fits the batch's sonnet/haiku self-contained-fix
model. Re-tiered all four to `opus` and released them unclaimed, with notes
on each cross-referencing the other three and recommending `kyrd4` (the
most complete -- it also specifies a regrowth-prevention rule for
`check_doc_freshness.py`) as the canonical bead to consolidate onto.

Fresh-eyes triage: no gaps found in a self-review pass covering the rubric
above; no out-of-scope findings surfaced beyond the four re-tiered beads
already described.

## Lessons

- The `t0kjj` shape (an assertion placed inside a `pytest.raises` block,
  where it can never execute in either branch) is now confirmed to recur --
  this is the SECOND instance in the same file (`uyoi4` was the first,
  batch 3). Worth a grep sweep of the rest of the test suite for the same
  `with pytest.raises(...):` + trailing `assert` shape if it turns up
  again.
- `closeout_prep.py`'s internal pytest subprocess run can legitimately take
  10-11 minutes under normal load but stalled far longer than that during
  this closeout under heavy concurrent-session contention on the same
  dolt-backed repo -- confirmed via direct process inspection (steadily
  growing memory, not a frozen process) rather than assuming a hang. A
  `subprocess.run(capture_output=True)` wrapper also buffers ALL output
  until the whole call finishes, so a redirected-to-file run showing zero
  bytes for a long stretch is not itself evidence of a hang -- distinguish
  the two by checking the underlying OS process, not the file.

## Doc freshness

Bumped `docs/components/pdf-view.md` (9utmk fix) and
`docs/technical_guide.md` (hkmnq fix) -- both files this branch's changes
directly touch. `closeout_prep.py`'s doc-freshness pass also flagged
numerous OTHER stale docs (`admin-service.md`, `config-deployment.md`,
`context-compression.md`, `jit-schema.md`, `tool-call-flow.md`,
`voice-ai.md`, `websocket-routing.md`, and most of `docs/standards/*.md`) --
all pre-existing staleness from other branches' recent work, none of it
touched by this branch's 5-file diff. Left as-is per the doc-freshness
triage rule (only fix staleness this branch's own changes caused).

## Files touched

- `backend/tests/unit/test_no_real_firestore_guard.py` -- t0kjj fix
- `docs/components/pdf-view.md` -- 9utmk fix
- `admin-console/src/pages/FirmDetailPage.test.tsx` -- 6mfsi fix
- `docs/technical_guide.md` -- hkmnq fix
- `backend/services/runtime_config.py` -- q1s8y fix
