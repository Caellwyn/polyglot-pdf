---
tags: [bug-hunt, testing, schema-editor, authoring, auth, docs]
beads: [polyglot-pdf-8bjdx, polyglot-pdf-6p0z, polyglot-pdf-8lh77, polyglot-pdf-qs7m6]
surfaces: [schema-editor, scripts/authoring, backend/routes, docs/components]
---

# Bug-hunt round 8: the complete options-consumer set, review-id squatting, a stale docstring, and an unpinned auth set

Eighth round of the ongoing bug-hunt bead roundup (rounds 1-7: PRs #573,
#576, #578, #581, #583, #585, #587). Four beads, three of which are
"enumerate the set" fixes rather than single-instance ones.

1. **Malformed `options` still threw across the schema-editor** (bd
   8bjdx). Round 7's bd 93p8 guarded ONE consumer
   (`reviewStatus.ts`'s `hasUncoveredStructuralError`); this is the
   remainder -- `checkFieldComplete` plus the whole render and edit
   chain.
2. **A real form part could squat on the review part id** (bd 6p0z).
   `derive_sections`' section-id path guarded the well-known review
   prefix; its part-id path did not, and precedence ran backwards.
3. **`collect_markers`' docstring stated the pre-round-7 rule** (bd
   8lh77), contradicting the code directly beneath it.
4. **The `require_auth` route enumeration omitted a route** (bd qs7m6):
   four routes gated in code, three listed in two docs.

## Scar tissue

### The mutation-verify caught a VACUOUS test that a reading would not have

The 8bjdx tests were written, run, and passed: 49 green. Then the
mutation-verify -- reverting `checkFieldComplete` to genuinely pre-fix
code -- **also passed, all 49.** The tests were exercising nothing.

The cause is worth recording because it is invisible on inspection. The
options branch is nested two levels deep:

```python
if isChoice and options.length > 0:      # outer
    if not field.pdf_field_name:         # inner  <-- the short-circuit
        unmapped = options.filter(...)   # the throwing line
```

The test file's own `field()` helper defaults `pdf_field_name: id` --
sensible, since most fixtures want a well-formed field. That default
satisfied the INNER guard, so every malformed-options case returned
before ever reaching the `.filter` that was supposed to throw. The
fixtures looked correct, the assertions looked correct, and the whole
construction was inert.

Two lessons. First, the one already in CLAUDE.md scar #8 -- proving a
test can fail is the author's job -- held up exactly as advertised; a
reviewer would otherwise have paid for this round. Second, and newer:
**when the code under test has a nested guard, the fixture's DEFAULTS
are part of the test's reachability**, and a shared helper tuned for
well-formed cases is precisely the wrong default for a degradation
test. The fix carries a comment saying so, because the next person
adding a case to that block will reach for the same helper.

Also worth noting: the first mutation attempt was itself too weak. It
reverted the `options` binding but kept the `o?.pdf_field_name`
optional-chaining added in the same commit, and that chaining alone
defeats the null-entry case. Only reverting to the *actual* pre-fix
source (recovered via `git show origin/dev:<file>`) produced a real
signal -- and then each of the two malformed shapes had to be mutated
SEPARATELY (drop the null-filter -> 12 red; remove the `Array.isArray`
guard -> 12 red) to show that neither was riding on the other's guard.

### Three of four beads were "one more instance," and the set was bigger every time

8bjdx, 6p0z and qs7m6 are all the same shape: a rule correctly applied
in one place and silently missing in its siblings.

- **8bjdx**: the bead named 2 sites. Mechanical enumeration found **9**
  iterating consumers across 5 files. The discriminator turned out to
  be crisp once measured in node rather than reasoned about: `.length`
  and truthiness checks are SAFE on both malformed shapes (a string has
  a `.length`; an array with nulls has a `.length`), while every array
  METHOD throws. That one measurement separated real offenders from
  ~15 benign reads that a textual grep flags identically.
- **6p0z**: the guard existed 15 lines above the missing one, in the
  same function.
- **qs7m6**: three routes had individual 401 tests; the fourth had
  none, and the docs enumerated exactly the three that had tests. The
  test coverage and the prose drifted together, which is why neither
  caught the other.

Each fix therefore pins the SET rather than the instance:
`optionsConsumerSet.test.ts` scans source for unguarded `field.options`
iteration (with a staleness-checked exemption list, so a stale
exemption cannot silently whitelist whatever moves into that
file+fragment later), and
`test_the_complete_require_auth_route_set_is_pinned` derives the gated
routes from the live FastAPI dependant graph and names both doc sites
in its failure message.

### A set-guard needs its own mutation-verify, and mine found a real bug

`optionsConsumerSet.test.ts` passed on first run -- which proves
nothing, since a guard that finds zero offenders and a guard that is
broken look identical. Reverting `PreviewPane`'s fix to the classic
`(field.options || []).filter(...)` idiom made it fail and name
`PreviewPane.tsx:210` exactly.

The companion "exemptions are live" test earned its keep immediately:
it failed on the first run against a real mismatch. My path handling
split on `[\\/]` in one test and used a different basename derivation
in the other, so on Windows the exemption matched in one place and not
the other. A hand-checked exemption list would have absorbed that
silently.

## Process notes

- Recon correctly flagged `8bjdx` as claimed-by-another-session; it was
  claimed by THIS session minutes earlier (claimed before spawning
  recon, so it had already dropped out of `bd ready`). No collision --
  but the agent was right to surface it rather than assume.
- Recon also found that `polyglot-pdf-a5mjw`, carried forward in my own
  notes from round 5 as an open follow-up, **does not exist** under
  that id. The underlying defect is real and was re-verified here
  (`schema-key-visibility.md` is the only standards doc with no
  `Tracks:` line, so `check_doc_freshness.py` returns `[]` and skips it
  silently -- a doc with a WRONG Tracks line gets flagged, but one with
  NO Tracks line looks permanently healthy). Re-filed as
  **`polyglot-pdf-teizj`**, scoped to pin the set (every tier-2 doc has
  a Tracks line or an explicit exemption) rather than just patching the
  one file.
- Four beads cleared, none touching a runtime request path; the only
  behavioral changes are in the schema-editor UI, an authoring script,
  and two test files.
- Total across rounds 1-8: 42 beads closed over 8 PRs.
