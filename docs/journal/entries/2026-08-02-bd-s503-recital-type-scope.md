---
date: 2026-08-02
bead: polyglot-pdf-s503
title: "fix(voice): scope option recital to checkbox/radio groups -- selects ask directly"
tags: [conventions, testing]
---

## Trigger

Maintainer directive on merging the option-recital fix (bd polyglot-pdf-6bq8,
PR #531): "let's start this just for checkbox and radio groups for now.
definitely not US states. I think your 20 option limit is reasonable for now.
we may need to tune that later." The shipped fix keyed the read-ALL imperative
on option COUNT alone, which also captured selects/dropdowns (the 50-state
lists were covered by the count carve-out, but the height feet/inches selects
were not -- bd polyglot-pdf-e5a7).

## What shipped

`render_field_guidance` now branches on field TYPE before count
(`RECITAL_OPTION_TYPES = {radio, checkbox, checkbox_group}`,
`backend/services/ai_context.py`):

- **select / any non-recital type** -> `Options (N -- standard list; ask
  directly and offer to read all N aloud): [...]` at EVERY count. Covers the
  50-state lists and the height feet/inches numeric selects.
- **radio/checkbox groups, <= 20 options** -> the read-ALL imperative
  (unchanged).
- **radio/checkbox groups, > 20 options** -> the `long standard list` marker
  (unchanged backstop; threshold maintainer-reviewed as reasonable for now,
  may be tuned later).

The DTI SI's PRESENTING OPTIONS exception and both initiating templates
generalize their carve-out phrase from "long standard list" to "standard
list" -- a substring of both non-recital markers, so one phrase keys both.
All options still ride the injection in every branch; only the ask style
changes.

This resolves bd polyglot-pdf-e5a7 (numeric-range selects force-recited),
closed with this PR.

**Live verification (local voice harness, Vertex 2.5 native-audio):** the
I-90 mailing-state select (50 options), reached via the resume path, asked
"What is the mailing state you'd like to select? I can read the full list for
you if you'd like." -- no recital; the W-7 reason checkbox_group still recited
all 8 options a-h in one ask.

## Lessons

- A count threshold is a proxy; the real distinction the product wanted was
  FIELD TYPE (a dropdown of standard values vs. a printed choice group). When
  a carve-out needs a second exception (heights) that the first (states)
  already hinted at, look for the underlying dimension instead of stacking
  thresholds.

## Doc freshness

- `docs/standards/si-reduction.md` -- bumped: per-field bullet and header now
  describe the type-scoped three-branch render.
- The pre-existing stale set flagged by the freshness checker (see the bd 6bq8
  entry) is unchanged by this diff and left as-is.

## Files touched

- `backend/services/ai_context.py` -- `RECITAL_OPTION_TYPES`; type-scoped
  Options branches.
- `backend/config.py` -- SI exception + both initiating templates: "standard
  list" carve-out phrase.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- select-always-asks-
  directly test (7/12/50 options), long-radio-group test, checkbox_group
  recital test, boundary test re-typed to radio, template/SI phrase pins.
- `docs/standards/si-reduction.md` -- freshness bump (above).
- `docs/journal/entries/2026-08-02-bd-s503-recital-type-scope.md` -- this
  entry.
