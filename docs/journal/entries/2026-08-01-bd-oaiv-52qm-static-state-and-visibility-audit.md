---
date: 2026-08-01
bead: polyglot-pdf-oaiv
title: "W-7 audit round 1: the checkbox rejection was not what it looked like, and three static-state gaps"
tags: [voice, schema, testing, cost]
---

## Trigger

The W-7 kit shipped to the demo bucket earlier the same day, and the post-deploy
voice test surfaced one live failure: with the section-1 `reason` checkbox_group
active, the model called `update_form_fields` and the backend answered
`success=false / applied_count=0 / unknown_count=1`. That became bd
`polyglot-pdf-oaiv` (P1) and, with the maintainer's go-ahead, the wider audit
epic `polyglot-pdf-52qm` -- the new schema format (runtime-translated spoken
names and option labels, thorough `help.instructions`, secretary-only expanded
`details`, the consult path, conditional visibility, static field states) had
never been systematically tested against the live voice model.

This entry covers the first working round: oaiv's root cause, plus beads `.7`
(static states) and `.4` (visibility boundary), both of which are payload-capture
work and cost nothing to run.

## oaiv: the hypothesis was wrong, and that is the finding

The bead was filed suspecting the SI or schema failed to teach the model what
payload shape a grouped control takes. That is **refuted**. Measured against the
shipped schema:

- `checkbox_group` `reason` accepts the option value as a scalar, a list, or CSV.
- `radio` `application_type` accepts a scalar and correctly refuses a list.
- `render_field_guidance` already emits `"<label>" (use value: <value>)` for every
  option, and every one of those values is accepted by the validator.

So neither validation nor the SI has a gap. The rejection was `unknown_count=1`
with `error_count=0` -- an **id** rejection, not a value one. In DTI strict mode
only an exact match against the active field counts, and the upstream coercion
deliberately does *not* re-point an id that resolves to some other real field (bd
`8vy3`: blanket re-pointing corrupted legitimate late corrections). A sibling id
therefore lands as unknown, which is the designed behavior.

What remains is model behavior on that turn, and the logs could not say which id
was sent -- the rejection path logged only a count. That observability gap is why
this needed a code read instead of a log read, so the fix landed here:
`validate_field_updates` now records `unknown_field_ids` (schema field ids;
values still never logged, asserted by test). One live re-run with the new
logging will name the id and decide the fix. The bead carries the three
candidate outcomes and an explicit "do NOT loosen validation to fuzzy-match" --
that is the PR #251 mis-fill trap this design exists to avoid.

## Three static-state gaps (bead .7)

W-7 is the first kit to exercise all three states: 7 Acceptance-Agent fields are
`hidden:true` + `read_only:true` with no `show_if`, and one `_ignored_fields`
entry parks a field that still owns a PDF widget.

1. **`hidden`/`read_only` are dropped by `build_fields_from_schema`.** `FormField`
   models both, but a field the schema marks true comes back `False`. Nothing
   downstream can honor them.
2. **A hidden + read_only field accepts a voice write.** There is no read-only
   guard in validation. The near-miss worth recording: `agent_phone` with
   `'555-1234'` *is* rejected -- for a tel **format** error, not a guard. A
   format-valid value applies cleanly with zero errors. Testing the first value
   would have produced a false all-clear.
3. **The completion denominator counts hidden fields.** `VoiceOverlay.tsx` uses
   `schema.fields.length` at four sites with no filter, while navigation
   elsewhere correctly uses `!f.hidden && shouldShowField(...)`. On W-7 that is 53
   counted vs 46 fillable: progress **caps at 87%** and the form never reads
   complete. This is visible on the live demo as "0 of 53 fields".

Clean, and pinned so a future edit cannot quietly change it: `_ignored_fields`
never becomes a live field, and its widget (`f1_02[0]`) is claimed by no live
field, so it stays blank on a filled PDF. The hidden fields *do* appear in the
secretary catalog, which is correct -- that surface lists every field with `shown`
applicability; it answers questions, it does not fill.

All three gaps are left **unfixed on purpose**. They are pinned as
characterization tests that assert current behavior and name the target
assertion, so the fix lands as its own reviewable change with the tests flipping
in the same commit.

## The visibility boundary holds (bead .4)

The expensive assertion first: `form_metadata.details` -- the 9,487-char booklet
-- appears in **zero** of the 53 per-field voice guidance blocks, and does appear
in the secretary catalog. Since per-turn text-in SI is 95-98% of session cost, a
leak there would have been a cost bug, not a tidiness one.

Measured: secretary static catalog ~142.6k chars (~35.7k tokens, the cacheable
byte-stable prefix on the cheap text model); largest single voice block `reason`
at 6,906 chars (~1.7k tokens) against a 20,000-char inline clamp, so nothing
ships truncated and the enrichment authored to fit. Worst-case voice block is
>4x smaller than the whole-form catalog -- the delegation's economic premise
holds. Exclusions verified on both surfaces: no `pdf_field_name`, `pdf_position`,
`validation.pattern`, `label_translations`, `spoken_name_translations`, `_review`.

`docs/standards/schema-key-visibility.md` is the new home for this contract, one
row per schema key with its code path, registered in `docs/INDEX.md`. Still owed
for the bead's second criterion: a live wire capture of a per-turn SI. The
numbers above come from the same renderers the session uses, but they are not a
capture -- pair that with `.1`'s live re-run rather than spending separately.

## Notes

- The maintainer relaxed `required` on four W-7 fields and bumped one
  `max_length` mid-session. `required` does reach the voice model (it renders as
  `Required: true`), so it is not inert for this audit even though it does not
  change the gaps above.
- The observability test initially used `structlog.testing.capture_logs`, which
  passed alone and failed under full-suite ordering -- the exact trap already
  documented in `test_callback_handler.py`. Switched to patching the module
  logger's `.warning` directly, per that precedent.
