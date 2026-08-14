---
tags: [bug-hunt, testing, schema-editor, authoring, auth, docs]
beads: [polyglot-pdf-8bjdx, polyglot-pdf-6p0z, polyglot-pdf-8lh77, polyglot-pdf-qs7m6, polyglot-pdf-yb41u, polyglot-pdf-fzt0a]
surfaces: [schema-editor, scripts/authoring, backend/routes, docs/components]
---

# Bug-hunt round 8: the complete options-consumer set, review-id squatting, a stale docstring, and an unpinned auth set

Eighth round of the ongoing bug-hunt bead roundup (rounds 1-7: PRs #573,
#576, #578, #581, #583, #585, #587). SIX beads -- four planned, plus two
(`yb41u`, `fzt0a`) that the two review layers surfaced and this branch then
fixed -- three of them "enumerate the set" fixes rather than
single-instance ones.

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
   four routes gated in code, three listed in three docs.
5. **`ConditionBuilder`'s trigger predicate had the same truthy-length
   trap** (bd yb41u) -- filed by the review as pre-existing, then fixed
   here once the widened set-guard started pointing at it.
6. **My own normalizer treated a LEGACY option shape as malformed** (bd
   fzt0a) -- found by the Opus outer review tracing the new helper out
   to the other three surfaces.

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

- **8bjdx**: the bead named 2 sites. My first enumeration found 9
  across 5 files -- and was still incomplete, because it anchored on the
  literal `field.options` and so could not see a consumer that names the
  same object `trigger` (see the evasion-surface note below). The
  discriminator for WHICH reads are dangerous did hold up once measured
  in node rather than reasoned about: `.length` and truthiness checks are
  SAFE on both malformed shapes (a string has a `.length`; an array with
  nulls has a `.length`), while every array METHOD throws. That
  measurement separated real offenders from ~15 benign reads a textual
  grep flags identically -- but it says nothing about reads the SEARCH
  never reached, which is the failure that actually happened.
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

### The review found TWO regressions this branch itself introduced

Both came from the same decision: `safeOptions` (drops malformed entries)
and `safeOptionsPreservingArity` (keeps them as `null`) are near-identical
in shape, and I picked between them per call site.

In `FieldEditor` I picked BOTH -- arity-preserving for `optionValues` (which
feeds the lint-finding anchor map) and dropping for the option-row render
loop. Those are two different index spaces over one array. With
`options=[null, a, b]`, a finding anchored to option 'a' (raw index 1) was
looked up at 'b's row, and an edit to 'a' spliced position 0. The tell was
sitting in my own comment: `optionValues` is annotated "arity preserved
because the values are matched positionally against the option rows below"
-- and I then changed those rows to the other view, invalidating the stated
invariant without re-reading it.

The second was subtler and shows the limit of the crash-shaped fix: the
`atFloor` guard ("a choice field needs >= 2 real options before Remove is
allowed") reads `field.options.length`. `.length` NEVER THROWS on either
malformed shape -- that is exactly the fact that made the crash enumeration
tractable -- so this site was invisible to both the crash hunt and the
source-scan guard, while still being wrong: 2 real options plus 1 malformed
entry counts as 3, Remove stays enabled, and one click yields the
single-option choice field the backend rejects.

Lesson: a bug class defined as "throws" and a bug class defined as "reads
the wrong count" overlap on the same lines but not on the same set of them.
Fixing the first does not sweep the second, and the guard built for the
first cannot see the second.

### A set-guard is only as good as its evasion surface

The first `optionsConsumerSet.test.ts` anchored on the literal
`field.options`. The reviewer broke it three ways in node -- alias
(`const o = field.options; o.map(...)`), destructure, and a differently-named
receiver -- and the third was not hypothetical: `ConditionBuilder.tsx` calls
the trigger field `trigger`, which is precisely why my "mechanical
enumeration" missed it and why the journal's original "9 consumers across 5
files" claim was wrong.

Widening the receiver pattern immediately surfaced two genuinely unguarded
sites (`ConditionBuilder` and `App.tsx`'s option drag-drop). The cost is
false positives on safe locals, which now carry documented exemptions -- and
the exemption mechanism needed its own hardening: matching a fragment with a
`>= 1` check meant a NEW call sharing common text like `.map((opt, idx) =>`
would silently inherit an exemption written for a different call's
reachability argument. It now pins an exact occurrence count.

### The outer review's whole job, demonstrated: my normalizer disagreed with three other surfaces

The inner review cleared at zero gaps. The outer review then traced
`safeOptions` OUT of the diff and found it contradicting every other
surface that reads `options`.

`"options": ["A", "B", "C"]` -- a bare list of strings -- is not malformed.
It is a DOCUMENTED accepted input: `FormField.normalize_options` coerces it
(`[FieldOption(value=opt, label=opt) for opt in v]`, docstring: "Accepts
both List[str] and List[FieldOption] formats"), the voice frontend's
`optionValue()` takes it, and `schema_lint`'s `ref-option-value` rule builds
its legal-value set INCLUDING `isinstance(o, str)` entries. My helper
classified it as junk and dropped it.

The consequence was worse than the crash the helper was written to prevent.
A string-option field rendered zero option rows, so FieldEditor's Options
panel fell to its EMPTY-STATE branch -- whose "+ Add Option" *overwrites*
`options` rather than appending. One click destroyed every option, silently,
and invisibly: the rows whose absence would have warned the author were
precisely the ones not rendering. Separately, `isChoiceTrigger` went false,
so ConditionBuilder offered a free-text box for values the publish gate
constrains -- inviting the exact `ref-option-value` ERROR the gate raises,
which is the editor/backend parity break bd 93p8 and wjes exist to end.

The general lesson is about what "malformed" means. I derived that
definition from ONE surface's crash behavior -- "what makes an array method
throw" -- and never checked it against what the other surfaces consider
VALID. Those are different questions, and the gap between them is where a
crash-safety fix turns into data loss. A normalizer is a contract, not a
local convenience, and its definition of "bad input" has to be reconciled
with every producer and consumer of that input, not just the one that
crashed.

Worth noting for calibration: the reviewer FILED rather than blocked,
because no shipped kit reproduces it (1377 option entries scanned across
`schema-editor/public/schemas` and `form-kits`, zero non-dict). That was a
defensible call. I fixed it anyway -- the editor opens ARBITRARY kits
through three raw-`JSON.parse` paths with no normalization, and silent data
loss is the wrong thing to leave armed against the day someone opens a
legacy kit.

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
- One review cycle, five gaps, three blocking -- and the two most
  serious were self-inflicted by this branch rather than pre-existing.
  Every finding was reproduced in node before being fixed.
- The outer review's second pass also established something the first
  could not: the coercion is a net IMPROVEMENT over `dev` at the one place
  it changes persisted data. On `dev`, "+ Add Option" on a string-option
  kit wrote `["A", "B", {label:"", value:"option"}]` -- a MIXED array the
  Pydantic publish gate rejects outright. The new code writes all-dicts.
  So the pre-fix editor was already corrupting these kits; it just did it
  one option at a time instead of all at once.
- Beads filed rather than folded in, all genuinely out of scope:
  `polyglot-pdf-teizj` (a doc with no `Tracks:` line silently opts out of
  the freshness gate), `polyglot-pdf-9jc53` (a finding anchored to an
  all-malformed options block is counted but unreachable), and
  `polyglot-pdf-r771m` (`FormField.normalize_options` decides the legacy
  shape from `v[0]` alone, so a MIXED string/dict list lints clean on
  every surface and then dies at the publish gate -- pre-existing on
  `dev`, and unreachable from the editor, whose write paths all rebuild
  `options` as all-dict).
- Two review layers, two cycles at the inner and two at the outer;
  the inner found 5 gaps (2 self-inflicted), the outer found 2 more that
  only a cross-surface trace could see (1 self-inflicted). Every finding was reproduced
  before being fixed.
- Total across rounds 1-8: 44 beads closed over 8 PRs.
