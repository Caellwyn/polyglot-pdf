---
date: 2026-07-29
beads: [polyglot-pdf-anim]
tags: [schema-editor, review]
---

# bd anim: label swaps now flag -- the identity hash binds labels to values

Resolves the ONE open question from the handoff
(`2026-07-29-bd-anim-handoff.md`): a label SWAP between two options
("Married" and "Single" trading places, values staying put) hashed
identically under the sorted-bare-labels formula, so the one identity drift
that records a WRONG ANSWER on the form -- not merely stale wording -- never
raised the gate. Fixed by hashing each option as a sorted
`[label, spoken_label, value]` binding in `identity_payload`
(backend/services/guidance_contract.py). (spoken_label joined the binding in
the closeout Opus rounds: it OUTRANKS label as the voice join key, so a
spoken-label swap is the same hazard -- bd polyglot-pdf-w028.)

## Why "all six cases" was impossible, and which one was sacrificed

The handoff asked for a fix satisfying: reorder silent / swap flag / label
edit flag / add flag / remove flag / value-only rename silent. The last two
goals are mutually exclusive for ANY order-insensitive hash: a swap IS a
reorder composed with a value rename (swap two whole options back, then
rename the two values across them), so a hash blind to both operations is
necessarily blind to swaps. No payload cleverness escapes this -- the
handoff's untested hypothesis (sort pairs by value, emit labels only) fails
too: renaming a value can change the sort order and flag spuriously, just
less predictably.

So value-only renames now flag. Measured behavior (same probe style as the
handoff):

| edit | want (handoff) | shipped |
|---|---|---|
| no change | silent | silent |
| pure reorder | silent | silent |
| label swap | FLAG | FLAG |
| label edited | FLAG | FLAG |
| option added/removed | FLAG | FLAG |
| value-only rename | silent | FLAG (accepted tradeoff) |

## Why the sacrificed case costs ~nothing (the empirical grounding)

The editor CANNOT produce a value-only rename: option values are minted from
labels when an edit settles on blur, "never free-typed" (FieldEditor, bd
h76m.10), and the value chip is rendered read-only in the Advanced
disclosure. A value-only rename therefore only arises from out-of-band
script/JSON edits (e.g. a slug-repair pass re-minting values after a bake)
-- rare, deliberate, and arguably worth a human glance anyway. When it does
fire, the cost is ONE acknowledgment checkbox click, not an LLM re-author.
The maintainer's 2026-07-29 reorder decision ("harmless reshuffling must not
prompt") is preserved: a pure reorder moves whole options, each pair intact,
and the sorted-pair hash does not move.

Note the editor-mediated swap variant is also caught: swapping labels by
retyping them re-mints both values (with collision suffixes), so the pairs
change either way.

## Safety

Unchanged from the handoff's verified claim: shipped `form-kits/w7` carries
44 provenance records with ZERO `identity_sha1`, so the formula change
lights up nothing (pinned by
`test_a_kit_baked_before_identity_tracking_never_reads_stale` against the
real kit). Optionless fields hash identically under old and new formulas
(`[name, spoken, []]` either way); only option-bearing fields changed, and
none have shipped hashes.

## What changed

- `backend/services/guidance_contract.py` -- `identity_payload` emits sorted
  `[label, value]` pairs; docstring records both accepted tradeoffs and the
  impossibility argument.
- `backend/services/schema_lint.py` -- rule docs mention the binding; the
  human-facing message says "options changed" (covers swaps and value
  renames honestly).
- `schema-editor/src/utils/guidanceStaleness.ts` + `FieldEditor.tsx` --
  header comment and amber-banner wording follow suit (display text only; no
  gate logic changed -- the editor consumes backend findings and never
  computes hashes).
- `backend/tests/test_schema_lint.py` -- new pins: the swap case, and the
  value-rename-flags tradeoff (with a pointer at the swap test for anyone
  tempted to re-exclude values). Full backend suite 2315 passed; editor tsc
  clean; editor vitest unchanged by construction (display strings only, no
  test references them) and re-run by CI on the PR.
