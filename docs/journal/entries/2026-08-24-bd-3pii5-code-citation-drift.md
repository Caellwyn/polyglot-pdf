---
date: 2026-08-24
bead: polyglot-pdf-3pii5
title: "docs(technical-guide): pdf_fill_routes line citations are ~15 lines stale (pre-existing drift)"
tags: [testing, doctrine]
---

## Trigger

`docs/technical_guide.md`'s contract-5 (PDF fill) block cited line numbers
into `backend/routes/pdf_fill_routes.py` that were stale by ~15 lines --
already wrong on `origin/dev` before bd `polyglot-pdf-xddtl`/`7hicd`'s
fixes, which shifted every citation by +27 to compensate for a guard
insertion. That shift was arithmetically correct (old line N and new
line N+27 held byte-identical content) but preserved the pre-existing
drift underneath it rather than fixing it -- the citations still pointed
at the wrong code, just at a different wrong line than before.

## What shipped

1. Every stale `pdf_fill_routes.py:<N>` citation in the contract-5 block
   re-anchored to a symbol name (`class PDFFillRequest`, `fill_pdf`,
   `fill_widget`, `fit_comb_value`, `get_button_on_state`, the
   `field_type` dispatch branches, the field-fill loop's `None`/`""`
   guard, the `need_appearances_skipped` log site) or a role-based
   description where no stable symbol name exists.
2. `scripts/check_doc_freshness.py` gained a fourth warn-only check,
   `check_code_citations()`: resolves `file.py:N`/`file.py:N-M` doc
   citations against `git ls-files` and flags any whose line number has
   run past the cited file's current EOF. Wired into `main()`'s existing
   sweep via `report_code_citations()`, gated by a real-repo CI test
   (`TestCurrentRepoHasNoOutOfBoundsCodeCitations`) mirroring the sibling
   `check_doc_conventions()` CI gate.

## Lessons

**A full "does this citation match the construct its prose names" checker
was the wrong thing to build, and recognizing that early saved a much
bigger, riskier bead.** The bead's own exit criterion 2 offered two
options -- eliminate line numbers, or add a check that verifies the
citation. The second option, taken literally, needs to infer WHAT a
citation claims from surrounding natural-language prose and then verify
the cited line contains that specific construct. That is exactly the
over-general-checker trap this repo's own scar tissue names (a checker
that infers a claim from text must scope the evidence region to exactly
the claim -- prose is not a reliable scoping signal). Building the narrower,
purely mechanical version instead -- "is the cited line number still
within the file's bounds at all" -- gives up catching every drift shape in
exchange for zero false positives. Both real limits of that narrower
check surfaced during review and are now explicitly documented rather than
silently accepted:
- it cannot see a citation shifted (not shrunk) by an insertion above it
  -- the MORE common real-world drift shape, and the reason symbol-name
  anchors, not a smarter citation checker, remain the durable fix;
- it is structurally blind to the doc's own `(:N)` shorthand-continuation
  citations (bare `:N` meaning "same file as the last full citation") --
  filed separately as `polyglot-pdf-oyjbx` rather than expanding this
  bead's scope to also parse that convention.

**Basename ambiguity made "resolve a bare filename citation" a real risk,
not a hypothetical one.** 21 basenames collide across this repo's tracked
tree, including two cited in the very doc block this bead touches
(`form_models.py`, `secretary_context.py`). A checker that resolved a bare
`foo.py:N` citation by guessing among same-named files would be doing
exactly what bd `polyglot-pdf-abn4o` did three times (shorthand resolved
against the wrong scope) -- so an ambiguous or untracked basename is
silently SKIPPED here, never guessed at. Mutation-verified: weakening the
ambiguity guard to accept any match count produced a real wrong-file
false-positive in the test suite, not just a theoretical one.

**A vacuous test survived a first mutation pass because the "wrong"
outcome and the "right" outcome were indistinguishable.** The
untracked-file test originally cited an IN-BOUNDS line against a
10-line untracked file; whether the checker correctly skipped it
(untracked) or incorrectly resolved it (in bounds either way), the
assertion `findings == []` passed identically. Only mutation-testing the
test itself (widening `git ls-files` to include untracked files) exposed
that it proved nothing -- fixed by citing an out-of-bounds line instead,
so a wrong resolution and a correct skip diverge.

**The first fresh-eyes pass caught the bead's own dangling self-reference.**
`report_code_citations()`'s docstring named a CI test
(`test_no_out_of_bounds_code_citations`) before that test was actually
written -- a documentation claim about test coverage that was false the
moment it was committed. Fixed by writing the real test with that exact
name rather than editing the claim down; the fix and the reference now
agree.

## Scoping note

The outer cross-surface review filed two further, genuinely separate
findings rather than folding them in here: `polyglot-pdf-82rzp` (the
script's own docstring paragraph miscounts its checks -- pre-existing on
`origin/dev`, this bead's docstring edit only widened the existing
mismatch) and `polyglot-pdf-oyjbx` (the bare `:N` continuation-citation
blind spot noted above).

## Doc freshness

No stale-doc findings traced to this diff; `docs/technical_guide.md` and
`docs/components/pdf-filling.md` both report `OK`.

## Files touched

- `docs/technical_guide.md` -- 8 citations across the contract-5 block
  re-anchored to symbol names
- `scripts/check_doc_freshness.py` -- new `check_code_citations()` +
  `report_code_citations()`, wired into `main()`
- `tests/test_doc_freshness.py` -- 6 new tests (5 synthetic-repo,
  1 real-repo CI gate) plus one existing pin's anchor string updated
