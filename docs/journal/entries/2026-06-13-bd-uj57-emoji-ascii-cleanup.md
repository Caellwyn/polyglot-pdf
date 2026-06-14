---
date: 2026-06-13
beads: [polyglot-pdf-uj57]
pr: TBD
tags: [conventions]
---

# uj57: emoji -> ASCII in webFormConnection.ts (+ abuk investigation, released)

## Trigger

A third "keep knocking these down" pass, constrained to beads outside the
Gemini-API / reconnection / test-coverage surfaces other sessions own.
`uj57` was filed by fresh-eyes during the PR #187 review (pre-existing emoji it
spotted but correctly held out of scope). Bundled with an investigation of `abuk`
(a dual-key sessionStorage bug); the abuk investigation did not yield a safe fix
and was released (see below), so this PR carries `uj57` alone.

## What shipped

`webFormConnection.ts` had 16 distinct emoji (29 occurrences) in `console.log`
string literals and comments -- accumulated as the auto-section-switch feature
grew -- violating the ASCII-only source rule (CLAUDE.md scar #6; a consistency
rule for TS, a correctness rule for Python). Replaced each with a short ASCII tag
(`[OK]`, `[reconnect]`, `[send]`, `[recv]`, `[check]`, `[stop]`, `[done]`, `[X]`,
`[warn]`, `[plug]`, `[timer]`, `[wait]`, `[door]`, `[NEW]`, `[wave]`) and dropped
the bare U+FE0F variation selectors. Console-string + comment text only -- no logic
change. Applied via a deterministic UTF-8-in/UTF-8-out replacement script, then
verified the bead's exact exit criterion (`grep -Pn '[^\x00-\x7F]'` returns zero).
`tsc` clean for the file; full frontend suite green (364 passed).

### abuk -- investigated, released (not in this PR)

`abuk` (manual-editing a field twice writes both `p1_line1_aliennumber` and
`p1_line1_aliennumber[1]` to sessionStorage). Timeboxed static trace findings,
recorded on the bead:

- All `fieldValues` writes funnel through `SchemaFormStateManager.updateField`
  (`schemaFormState.ts:234`), which writes `[fieldId]: fieldValue` with the
  fieldId AS PASSED -- no key canonicalization.
- DOM fields render with `id={field.id}` AND `name={field.id}` (the schema id,
  never a widget id), which contradicts the first-pass "an element carries the
  widget id" hypothesis. The AI-update path also always pushes `field.id`.
- The true origin of the `[1]`-suffixed, schema-id-cased key (matching neither the
  schema id nor `pdf_field_name` `[0]`) was NOT located statically; it needs live
  browser repro with a breakpoint in `updateField` to capture the write's call
  stack.

Released to OPEN with those notes + a caution: schema field IDs **legitimately**
contain brackets (`p1_checkbox4[0]`; terminology.md L68-77 says keep them), so a
naive "strip `[N]`" fix would corrupt bracketed fields and is wrong. The fix should
resolve the incoming key to a canonical schema id by lookup, not by bracket
surgery.

## Lessons

A timeboxed investigation that does not find a safe fix is a legitimate outcome:
recording the narrowed static trace + the specific next step (live repro) + the
correctness trap to avoid (bracket preservation) leaves the next session far ahead
of where this one started, without shipping a speculative fix that could regress a
documented invariant.

## Doc freshness

No tracked tier-1/tier-2 doc describes `webFormConnection.ts`'s console-log text;
the change is cosmetic-string-only. Doc-freshness gate result recorded at closeout.

## Files touched

- `frontend/src/webFormConnection.ts` -- emoji -> ASCII in console logs + comments (uj57)
