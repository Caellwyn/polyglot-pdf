---
tags: [editor, local-dev, testing, stale-bead, enumerate-the-set, scar-tissue]
beads: [polyglot-pdf-borq]
surfaces: [tests, scripts, schema-editor]
---

# A P1 bug that was already fixed, and the guard that was missing instead

bd `borq` said the local schema editor was unusable: the launcher started
uvicorn with no editor token, so every `/api/editor` call 503'd. It was a
detailed, well-evidenced bead -- line numbers, a TestClient reproduction, both
halves of the failure traced.

It was also stale. bd `cpiw` (PR #522) rewrote the launcher months later and
fixed both halves.

## Checking before building

The bead's evidence was specific enough to be worth trusting, which is exactly
why it was worth checking. Reading `run-schema-editor.sh` took a minute:

```sh
if [ -z "$SCHEMA_AUTHOR_TOKEN" ]; then
    SCHEMA_AUTHOR_TOKEN="$(... secrets.token_urlsafe(24) ...)"
fi
```

...then handed to the backend, and the SAME value baked into the vite bundle
as `VITE_EDITOR_TOKEN`. Both halves the bead called broken.

Confirmed by execution rather than by reading, since that is the standard this
repo keeps re-learning: TestClient with the launcher's env shape returns 401
without the token and 200 with it.

Had I started from the bead's instructions I would have "fixed" a working
launcher -- and the diff would have looked plausible.

## The real gap was criterion 2, which nobody had done

The bead's second exit criterion asked for a test pinning that the launcher's
two sides agree. That was genuinely missing, and it is the more valuable half,
because the credential crosses FOUR links in three languages:

    run-schema-editor.sh   mints + exports SCHEMA_AUTHOR_TOKEN
      -> exports the same value as VITE_EDITOR_TOKEN
        -> remoteKitStore.ts reads import.meta.env.VITE_EDITOR_TOKEN
          -> sends it as the X-Editor-Token header
            -> require_editor_role reads that header

**The failure mode is what makes it worth a test.** Break any link and local
mode does not error -- the editor loads, the panel renders, and lint returns
nothing. To an author that reads as "no problems found", not "auth failed".
There is no toast and no red state. A findings-free panel and a clean schema
look identical.

## Testing the guard found two holes in the guard

Both are the same mistake wearing different clothes, and both were found by
mutating rather than trusting.

**Hole 1: I asserted against prose.** The first cut checked that
`VITE_EDITOR_TOKEN` appeared anywhere in `remoteKitStore.ts`. Renaming the live
read left the suite green, because two DOC COMMENTS still spell the old name.
A guard whose whole job is catching drift between code and its description was
itself reading the description. Fixed by stripping comment lines.

**Hole 2: my mutation was too gentle.** I renamed
`VITE_EDITOR_TOKEN` -> `VITE_EDITOR_TOKEN_V2`, which is the friendliest
possible version of that edit -- and the old name is a PREFIX of the new one,
so a substring check matches it. The guard passed again. Fixed with a word
boundary, then verified against BOTH a suffixed and a clean rename.

The second hole is the more interesting one. A mutation that is too polite
does not just fail to prove the guard works -- it actively certifies a guard
that does not. I would have shipped hole 2 believing hole 1 was the whole
story, because the mutation I chose could not tell the difference.

**The rule that generalizes:** pick the mutation a real author would make, and
when a guard survives, ask whether the mutation was strong enough before
concluding the guard is.

## Process notes

- The bead is RESCOPED, not closed-as-invalid. Criterion 1 was met by shipped
  code; criterion 2 is what this delivers. Both findings are recorded on the
  bead so the next reader sees why a P1 "bug" produced a test-only diff.
- No production file is touched. That is the honest shape of the work: the
  code was right and the safety net was missing.
