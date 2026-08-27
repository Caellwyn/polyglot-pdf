---
date: 2026-08-22
bead: polyglot-pdf-7hicd
title: "fix(pdf-fill): /fill-pdf passes body kit_id + pdf_filename to the store unsanitised"
tags: [security, testing]
---

## Trigger

Found while tracing bd polyglot-pdf-xddtl's store-level `snapshot_id` guard
out to its siblings: `/fill-pdf` is the ONE client-tier kit read that never
resolves `pdf_filename` through the manifest allowlist. Every other
`{kit_id}` route gets its schema/pdf filename from `_resolve_kit_filenames`
or `_resolve_meta_names`, both of which call `form_kits.safe_filename` on a
manifest-derived value at write time. `PDFFillRequest.pdf_filename` comes
straight off the client's POST body, and `kit_id` here arrives in JSON
rather than a URL path segment -- unlike a GET route's path segment (which
the test client resolves before the handler ever sees a `..`), a raw `..`
in a POST body reaches the handler as a literal string untouched.

Verified before the fix, against a REAL `LocalFormKitStore` (not a fake --
the existing `_TwoKitStore` test double in `test_http_route_auth.py` checks
`pdf_filename == "REAL"` and can't demonstrate a real escape at all): a
traversing `kit_id` or `pdf_filename` made `load_pdf_bytes` read a decoy PDF
planted outside the store root, and the route filled + served it back as a
`200` -- `fitz.open()` opened attacker-planted bytes as real PDF input, not
merely a wrong-file read.

## What shipped

`kit_id` and `pdf_filename` are sanitised at the top of the handler, before
either gate or the store is touched -- `kit_id` via the existing
`_safe_kit_id` (same as every other route), `pdf_filename` via a new
`_safe_pdf_filename` sharing `form_kits._SAFE_FILENAME_RE`'s charset but
RAISING 400 rather than degrading to a default (there is no legitimate
default here -- the caller asked for a specific file). Enumerated the
complete set of unsanitised path-joining store readers (grep of
`_kit_dir(kit_id) /` and `_build_blob_path(kit_id, ...)`): every other call
is either a fixed literal or an already-`safe_filename`'d value;
`load_pdf_bytes` via `/fill-pdf` was the only one carrying a raw value.
Two new parametrized tests in `test_http_route_auth.py`.

## Lessons

**A fake store that only checks `pdf_filename == "REAL"` cannot prove a
traversal guard does anything.** `_TwoKitStore.load_pdf_bytes` (used by most
of this file's other fill-pdf tests) never actually reads a path -- any
string that isn't the literal `"REAL"` trivially "fails" the fill for
reasons having nothing to do with sanitisation. Testing a path-traversal
fix needs the real store, planted files, and the guard genuinely absent to
prove anything -- same lesson as bd xddtl, applied to a second call site in
the same session.

**Same depth-counting trap as xddtl, twice, in two DIFFERENT directions.**
The two traversal cases in this bead's test escape to different depths
relative to `tmp_path` (one hop above it for `kit_id="../../outside_secret"`
via `kits_root/../../...`; zero hops -- still inside `tmp_path` -- for
`pdf_filename="../../outside_secret/..."` via `kits_root/w7/../../...`,
because the extra `/w7` segment absorbs one `..` before any climbing
starts). Verified both with `os.path.normpath` against the literal join
each store method performs before writing either the test or its
docstring, not by intuition -- xddtl's own test got exactly this wrong
once already in the same session, caught only by mutation-testing it.

**A fake byte-string decoy proves less than mutation-testing needs.** The
first version of this bead's test used `b"%PDF-DECOY-SECRET"` as the decoy
payload; with the guard removed the traversal DID succeed, but `fitz.open()`
choked on the non-PDF bytes and the route 500'd -- a failure indistinguishable
from any other bug, not the "the decoy was actually served" proof the test
needs to claim. Switched to a real minimal PDF (`fitz.open(); doc.new_page();
doc.tobytes()`), which makes an unguarded route genuinely return 200 with
the decoy's bytes filled and served -- the unambiguous mutation-test outcome
(confirmed via captured logs: `pdf_loaded pages=1`, `pdf_generated`).

**Fixing one staleness set surfaced a SECOND, older one -- correctly left
separate.** This fix's ~27-line insertion shifted every downstream line
citation into `pdf_fill_routes.py` inside `docs/technical_guide.md` (8
citations across 6 doc lines, enumerated by grep, fixed by verifying each
old-cited line's exact content against the new file rather than assuming a
flat offset). The outer reviewer then found the ORIGINAL (pre-this-diff)
citations were already ~15 lines imprecise on `origin/dev` -- a
pre-existing drift this diff's shift preserved rather than caused. Correct
call: fix what this diff broke, file the older, unrelated imprecision
separately (`polyglot-pdf-3pii5`) rather than silently expanding this PR's
scope to re-anchor citations that were never this bead's problem.

## Scoping note

`load_schema`'s own posture (no internal guard) was NOT touched: tracing
every call site (`editor_kit_routes.py`, `form_kit_routes.py`,
`kit_gates.py`) confirmed all of them pass an already-`safe_filename`'d
value via `_resolve_meta_names`/`_resolve_kit_filenames` -- `load_schema`
has zero unguarded callers today, so adding a guard there would be
gratuitous (CLAUDE.md's caution against unscoped over-fixing).

## Doc freshness

`docs/components/pdf-filling.md` -- step 3 of the request flow updated to
note the new guard; stamp bumped. `docs/technical_guide.md` -- 8 stale line
citations fixed (see Lessons above); a second, pre-existing ~15-line
imprecision filed separately as `polyglot-pdf-3pii5`, not fixed here.

## Files touched

- `backend/routes/pdf_fill_routes.py` -- `_safe_kit_id` + new
  `_safe_pdf_filename` guard at the top of `fill_pdf`
- `backend/tests/unit/test_http_route_auth.py` -- two mutation-verified
  parametrized tests, real `LocalFormKitStore`, real PDF decoy
- `docs/components/pdf-filling.md`, `docs/technical_guide.md` -- doc
  accuracy fixes described above
