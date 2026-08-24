---
date: 2026-08-22
bead: polyglot-pdf-evkzi
title: "docs(technical_guide): fix stale kit_gates.py citations in Surface contracts entry 7"
tags: [conventions, review]
---

## Trigger

Surface contracts entry 7 ("Firm-scoped kit visibility") cited
`kit_gates.py` and neighboring files by line number. bd polyglot-pdf-xg0pm
had already swept section 1's citations, but section 7 was never touched,
and the later `z6bk9` firm-retire diff shifted the file further.

## What shipped

Enumerated every citation in section 7 -- 17 distinct sites, not just the
four the bead named -- and checked each against the real current line by
reading the file, not by trusting either the bead's own "actual" numbers
(several had drifted again since it was filed) or a first-pass script that
mishandled bare filenames.

7 sites were genuinely stale and got replaced with symbol names
(`kit_gates.py`'s `load_live_metadata`/`kit_visibility`/
`firm_allowed_kits`/`require_visible`, `form_kits.py`'s
`normalize_manifest` and `LocalFormKitStore.load_manifest`,
`firms.py`'s `get_allowed_kits`, `form_kit_routes.py`'s `list_form_kits`
and the `FormKitInfo` model, `SchemaFormDemo.tsx`'s manifest mapping) --
the durable fix bd evkzi's own criterion offered as an alternative to
re-verifying line numbers forever.

5 sites were verified still accurate and left untouched
(`pdf_fill_routes.py:82`, `form_kit_routes.py:293`, `usePDFDocument.ts:60`,
`pdfFiller.ts:59`, `:117`).

## Lessons

**A symbol-name citation isn't automatically unambiguous.**
`load_manifest` exists as three separate implementations
(`FormKitStore`'s abstract base, `LocalFormKitStore`, `GCSFormKitStore`) --
the same base/Local/GCS pattern `put_schema` uses elsewhere in this file.
Citing the bare method name would have been just as fragile as a line
number, in a different way: correct today, silently wrong the moment a
reader assumes the wrong implementation. Qualified as
`LocalFormKitStore.load_manifest` once the ambiguity was checked for.

**Re-enumerating catches drift the original bead's own numbers didn't
have.** The bead named four stale citations with specific "actual" line
numbers; three of those four had ALREADY moved again by the time this fix
landed (`firms.py:55` -> real 56, not the bead's cited replacement;
`form_kit_routes.py`'s three citations were off by 3-89 lines from what
the bead's own investigation found). A "fix the four the report names"
approach would have re-shipped stale numbers under a green PR.

## Doc freshness

- `docs/technical_guide.md` -- no stamp (PR #622 removed it; freshness is
  git-log-derived now). Doc conventions clean; routes-table pinning test
  unaffected (it doesn't cover Surface contracts prose).

## Verification command

For the next sweep, to re-enumerate every citation in this section:

```
python -c "
import re, io
doc = io.open('docs/technical_guide.md', encoding='utf-8').read()
start = doc.index('### 7.'); end = doc.index('\n### 8.', start)
print(sorted(set(re.findall(r'([\w./-]+\.(?:py|ts|tsx)):(\d+)', doc[start:end]))))
"
```

## Files touched

- `docs/technical_guide.md` -- 7 stale citations replaced with symbol
  names, 5 accurate citations left as-is, one ambiguous symbol
  disambiguated
