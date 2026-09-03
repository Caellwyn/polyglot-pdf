---
date: 2026-09-03
bead: polyglot-pdf-inrrn
title: "feat(pdf-fill): a select fills from pdf_on_value -- PR 1 of the g2fpr epic, and the hole that was still open"
tags: [pdf-filling, schema-lint, pdf-view, testing, review]
---

## Trigger

PR 1 of five under epic `polyglot-pdf-ps4hf` (plan approved 2026-09-03: "the full
solution, don't skimp"). A dropdown's `option.value` was the PDF export code because
the filler had no select branch -- it wrote `str(value)` verbatim into the combobox.
Every other choice type carries a slug in `value` and its widget identity in
`pdf_on_value`; selects never got the second channel. PyMuPDF does not validate
against `/Opt`, so a slug was accepted silently and printed clipped.

## What shipped

- `pdf_fill_routes.resolve_select_fill_value`: resolve the stored value to its
  option; if it carries `pdf_on_value`, that STRING goes into `fill_widget`'s
  existing text branch; else the value, verbatim, so a not-yet-migrated kit keeps
  working. A value matching no option is written verbatim and logged loudly,
  never with the value.
- `schema_lint` rules (a) and (b), evidence-based via `pdf_choice_values`: an
  option WITH `pdf_on_value` must have a slug value and a code the widget declares;
  a SLUG value not in `/Opt` with no `pdf_on_value` is an ERROR.
- `valuePainting.ts` paints `pdf_on_value ?? raw` for a select -- the overlay
  mirrors the filler in both shapes.
- `test_select_on_value_consumers.py`: every shipped file touching `pdf_on_value`
  (21 of them), derived from the tree and asserted against a reviewed list with a
  verdict per entry. An unlisted reader or a stale verdict fails CI.

## Lessons

**The hole was still open, and the carve-out could not see it.** The 4we6j
exemption fires only when a value is NOT slug-shaped. So a select authored as
`'alabama'` with no `pdf_on_value` lints clean, publishes clean, and prints
`'alabam'` -- the exact c5r8 defect that produced the old i-90 kit. Rule (b)
closes it. A carve-out that exempts the good case leaves the bad case invisible
by construction; the test that pins it asserts the PREMISE first (the slug rule
does not fire) before asserting the new finding.

**A combobox is not a radio.** The tempting move was to copy the radio branch's
xref `/AS` write. A combobox is one widget with an `/Opt` array and a plain
`/V`; the right mechanism is to substitute the string and let the text branch
write it. Stated in the code so the next reader does not "unify" the two.

**A set-pin caught its own author.** My first scan matched exclusion parts
against the ABSOLUTE path -- and a worktree lives under `.claude/worktrees/`, so
every file was excluded and the derived set was empty. The floor
(`assert derived`) caught it. Relative parts now. A derived set with no
non-vacuity floor is a list that can quietly become empty.

**An existing set-pin caught the thing I did not know existed.** I grepped for
a lint rule catalogue, found none, and added three rule ids. The full suite then
failed `test_lint_rule_parity`: the module docstring and the editor's
`RULE_LABELS`/`RULE_REMEDIES` must list every rule the backend emits. That is
what a set-pin is for -- it turned a review round into a red test.

**Fresh-eyes executed the shipped functions instead of reading them, and found
two gaps my mutations could not.** (1) A junk value carrying `pdf_on_value` got
two ERRORs with opposite remedies ("do NOT regenerate from the label" and
"regenerate from the label"); my comment claimed the scoping was handled, but
only rule (b) had it. (2) The filler matched dict options only, so a select in
the legacy PLAIN-STRING option shape fired the stale-session warning on every
fill while printing correctly -- a regression invisible to any fill assertion.
Both fixed, each pinned by a test that reddens under the reverting mutation.

**The consumer-set pin caught its own author, one commit later.** Round 1's fix
reworded an editor remedy to say the code "lives in `pdf_on_value`" -- prose,
not a read. The scanner does not know the difference: the file now mentioned
the token, had no verdict, and the pin went red on the full suite. I had run the
editor's own `lintFindings` test after the reword and read that as coverage; the
Python pin is the one that governs the set. That is the guard doing exactly its
job -- against me. The verdict entry says how the file got there.

**A fix can introduce an order dependency the original bug did not have.** The
string-option match returned on the first string hit, so a mixed list resolved
differently depending on element order. A mixed-shape list is already anomalous,
but a resolver whose answer depends on order is wrong regardless of who produces
the list. One full pass, dict match preferred; pinned in both orders.

**`structlog.testing.capture_logs` is unreliable under the full suite.** The warn
test passed alone and failed in-suite because an earlier test configures a
cached logger the capture processor never sees. Recording by replacing the
module logger is deterministic. Green-alone / red-in-suite is the tell.

**Found along the way:** `migrate_schema_v2.py:306` already writes
`{value: slug, pdf_on_value: code}` for selects built from the dump. The c5r8
kit had the channel all along; the filler never read it. PR 3a (`g2fpr.3`) can
reuse that shape rather than invent one.

## Named blind spot (not fixable here)

`value: '5'`, `pdf_on_value: '6'`, both legal `/Opt` codes: zero findings. The
dump yields the legal code SET, not a label-to-code correlation, so no
evidence-based rule can catch a semantically wrong pairing. Recorded so no one
later reads "both directions" as "every direction".

## Files touched

- `backend/routes/pdf_fill_routes.py` -- the select resolution
- `backend/services/schema_lint.py` -- rules (a)/(b), the remedy, the docstring list
- `frontend/src/pdf-view/valuePainting.ts` -- paints what prints
- `schema-editor/src/utils/lintFindings.ts` -- labels + remedies for the three rules
- tests: `test_pdf_fill_select_on_value.py` (new), `test_select_on_value_consumers.py`
  (new), `test_schema_lint.py`, `valuePainting.test.ts`
