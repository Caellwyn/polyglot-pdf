---
date: 2026-09-23
bead: polyglot-pdf-2cot
title: "The third, fourth and fifth ways through one contract test"
tags: [testing, conventions, schema-editor]
---

## Trigger

Bug-hunt continuation. Two beads, both holes in
`schema-editor/src/utils/markerNames.contract.test.ts` -- the only thing that
couples the schema editor's handshake-marker filenames across the
TypeScript/Python boundary.

The stakes are why this test exists at all. If the browser writer and the
server reader disagree on the marker filename, the reader finds nothing, which
is indistinguishable from "wrong folder" -- so the editor permanently refuses a
folder that actually agrees, and Repair-all, Regenerate-divisions,
Rewrite-guidance and the widget picker all switch off **with no error
anywhere**. Nothing in either type system couples the two sides: the Vite
plugin is outside the `src/` tsconfig scope, and the backend is Python.

## What shipped

**bd `polyglot-pdf-2cot` -- the capture stopped at the first closing quote.**
A declaration written as a concatenation whose leading segment was unchanged
compared equal on the shared prefix. Reproduced before fixing:

```
formKitDirectory.ts   HANDSHAKE_FILE  = '.editor-store-check.json' + ''
editor_kit_routes.py  _HANDSHAKE_FILE = ".editor-store-check.json" + ".TOTALLY-BROKEN"
```

Suite **green 4/4** while the browser wrote one filename and the backend read
another. The literal must now be the WHOLE right-hand side -- only a
semicolon, trailing whitespace or a trailing comment may follow.

**bd `polyglot-pdf-o6io` -- relocation, not renaming.** The scrape pins a
declaration at a fixed PATH. Moving a constant into a shared module makes the
scrape fail *loudly* ("not found"), so this was never silent -- but the natural
repair is to repoint the test's path constant, and nothing then checks that the
scraped file is the one the runtime reader actually imports. The test would pin
a stale literal at the old path while production used a different value.

Closed by requiring each scraped constant to also be USED (non-declaration,
non-comment) in the file it is scraped from. A relocation can no longer be
repaired by repointing the path alone: the constant and its consumer must move
together, and the failure message says so.

## Lessons

**A guard that cannot evaluate an expression must REFUSE, not approximate.**
The 2cot capture tried to be lenient -- take the first string literal and
compare it. Leniency is what made it wrong: comparing a *fragment* and calling
it agreement is worse than not comparing at all, because the green tick is
read as proof. The fix makes any computed right-hand side (concatenation,
template literal, f-string, call) fail loudly via the existing
exactly-one-match guard. That looks like a limitation and is actually the
correct posture: this test reads source text, it cannot run it, so the only
honest answers are "these two literals are identical" or "I cannot tell".

**Count the ways through, not the times you fixed it.** This file's own
docstring already recorded two prior defeats -- a comment satisfying the
pattern, and a duplicate declaration -- each found by review and each fixed.
These beads are the third and fourth. A FIFTH arrived during this very PR:
the use-site guard I added for o6io excluded comments by testing whether a
line STARTED with `//`, `*` or `#`, which missed a block-comment
continuation and a mention inside a string -- so a relocated constant could
satisfy its own pin with any prose mention. Fresh-eyes caught it, and the
structural strip that replaced it then had its own ordering bug (a `#`
inside a string ate the rest of the line, deleting a real use), caught on
the next round.

That is the honest shape of this file: five holes, two of them mine, each fix
correct and none final. The pattern is that a *scraping* guard has an
open-ended attack surface -- every syntactic form the language permits is
another way for the source text to say something the regex reads differently.
The useful response is not to keep patching in silence but to write each
defeat into the docstring as it happens, which this file does, so the next
reader sees the shape of the problem rather than a pile of
unrelated-looking conditions.

**When tightening a guard, verify the protection it ALREADY gave.** It is easy
to narrow a pattern and silently lose an existing catch. I re-ran the original
drift scenario (a plain value rename -- the verification recipe from the bead
that created this test) and confirmed it still fails. Three mutations in total:
the concatenation now fails where it passed, the relocation now fails, and the
plain rename still fails. The pin is tightened, not traded.

## Doc freshness

No tracked docs affected: this diff touches one test file and nothing under
`docs/`. The test's own docstring is updated in place, which is where this
file's history of defeats is deliberately recorded.

No CLAUDE.md changes.

## Files touched

- `schema-editor/src/utils/markerNames.contract.test.ts` -- whole-RHS anchor on
  the declaration capture (2cot); new case requiring each scraped constant to
  be used in its own file (o6io); that case's comment-exclusion rewritten from
  a line-prefix test to a structural strip (fresh-eyes round 1), then the strip
  reordered so strings go before line comments and made escape-aware, since a
  `#` inside a string was eating a real use (bd `polyglot-pdf-k0qh9`, round 2);
  docstring extended with the third defence and the reproduction that motivated
  it.
