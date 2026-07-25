---
date: 2026-07-25
bead: polyglot-pdf-c6td
title: "V5 follow-ups: cross-family fixes through the pipeline + IRSN pin; w7-2 kit deleted"
tags: [extractor, conventions]
---

## Trigger

Two small whole beads bundled (bead/PR contract): `polyglot-pdf-c6td` (adopt
the 6 cross-family-confirmed translation fixes + pin IRSN as
do-not-translate, from the V5 audit) and `polyglot-pdf-r9a7` (delete the
redundant w7-2 kit -- a straight copy of w7 from the editor's prior
form-name render bug, maintainer directive 2026-07-25).

## What shipped

- **Glossary:** `IRSN` added to the do-not-translate list (retires the V5
  worklist's largest cluster, ~24 judge false-flags across 8 languages) and
  an afrikaans pin `middle name -> middelnaam` (the in-kit-consistent
  rendering the cross-family audit confirmed).
- **The 6 drifted strings, fixed through the pipeline (not hand-typed):**
  the drifted entries were deleted from the kits and re-baked via the
  normal only-missing bake with verify ON (live spend ~$0.15). Results:
  swedish "Hispanic or Latino" / "Not ..." now bake as
  "(Inte) Spansk/latinamerikansk harkomst" (ethnicity/descent -- the exact
  category fix), and the three w7 afrikaans middle-name fields bake as
  "Middelnaam" variants via the new pin; all five passed the verify loop
  clean. The sixth (portuguese hair-color "Sandy") is the one case the
  pipeline cannot settle: the forward translator reproduces "Loiro-escuro"
  and the reframed judge correctly flags it -- it ships UNRESOLVED-flagged
  on the human worklist instead of silently clean (recorded on the bead;
  fail-open by design, a Portuguese speaker's one-word call).
- **w7-2 deleted** (`git rm -r form-kits/w7-2`) with a full reference
  sweep: parametrize lists + per-kit tables in
  `test_form_models_v2` / `test_schema_lint` / `test_w7_field_widget_mapping`
  / `test_translation_lint` / `test_eval_extraction`, the
  `eval_extraction.py` benchmark entry (w7-2 duplicated w7's gold --
  nothing lost), and prose mentions in `form_models.py`, `schema_lint.py`,
  `extract_form.py`, `migrate_schema_v2.py`, `docs/components/pdf-view.md`
  (bumped). The machine-local gitignored `frontend/public/form-kits/w7-2`
  copy was removed too. The REMOTE kit store has no `w7-2` (its index
  lists only i-90); the unlisted `form`/`form-2` draft remnants there are
  the same-origin clutter, filed as `polyglot-pdf-tpvb` for maintainer
  review rather than deleted beyond this bead's scope.
- Lint sweep post-change: i-90 and w7 still 0 findings (the new IRSN DNT
  and middelnaam pin hold on the real kits).
- Fresh-eyes triage: (filled at closeout -- see PR.)

## Lessons

- A glossary pin is the right fix-vector for a repeated in-kit term: the
  re-bake honored `middelnaam` mechanically, no hand-editing, and the lint
  now enforces it forever.
- When the pipeline cannot settle a string (translator and judge deadlock),
  the honest ship is flagged-unresolved -- the V5 keep-rule design ending
  exactly as intended.

## Doc freshness

- `docs/components/pdf-view.md` -- bumped (w7-2 example generalized).
- No other tier-1/tier-2 doc tracks the touched files; reviewed and left.

## Files touched

- `form-kits/_translation/glossary.json` -- IRSN DNT + afrikaans middelnaam pin
- `form-kits/i-90/schema.json`, `form-kits/w7/schema.json` -- 6 entries re-baked
- `form-kits/w7-2/` -- deleted
- `scripts/authoring/eval_extraction.py` -- w7-2 benchmark entry removed
- `scripts/authoring/extract_form.py`, `scripts/migrate_schema_v2.py`,
  `backend/models/form_models.py`, `backend/services/schema_lint.py` -- prose
- tests: `test_form_models_v2.py`, `test_schema_lint.py`,
  `test_w7_field_widget_mapping.py`, `test_translation_lint.py`,
  `test_eval_extraction.py`
- `docs/components/pdf-view.md` -- example generalized + stamp
