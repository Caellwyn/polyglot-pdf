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
  `[label, spoken_label, value]` triples; the docstring records the accepted
  tradeoffs and the impossibility argument. (spoken_label joined during the
  closeout Opus rounds -- it outranks label as the voice join key, so its
  swap is the same hazard; bd polyglot-pdf-w028, closed in-PR.)
- `backend/services/schema_lint.py` -- rule docs name the bindings; the
  human-facing message says "options changed" (covers swaps and value
  renames honestly).
- `schema-editor/src/utils/guidanceStaleness.ts` + `FieldEditor.tsx` --
  header comment and amber-banner wording follow suit (the editor consumes
  backend findings and never computes hashes).
- `backend/tests/test_schema_lint.py` -- new pins: the label-swap case, the
  spoken-label-swap case, and the value-rename-flags tradeoff (with a
  pointer at the swap test for anyone tempted to re-exclude values).

## The closeout assess loop (what it caught after the fix "worked")

The measured six-case table above was green before any review ran. The
closeout loop still found eleven real gaps across seven rounds -- on a
feature whose failure mode is silently telling a reviewer something is
fine, this is the part of the record worth reading.

Fresh-eyes inner loop (Sonnet): round 1 found the kit-wide "% complete"
figure blind to the gate (a gated kit could read 100%) and FieldEditor's
stale-finding lookup unscoped by field id; round 2 found
`withReviewStatus`/`withReviewNote` silently DROPPING a just-recorded ack on
the ordinary ack-then-sign-off flow (the fourth instance of the pin-to-a-
value-that-does-not-move family); round 3 cleared.

Opus clearing rounds: round 1 found the bake's `identity_sha1` WRITER had
zero test coverage (deleting it disabled the whole feature with every test
green -- the lint rule is deliberately silent without a hash), an
unparseable-identity deadlock (a checkbox that could record nothing on a
permanently amber row -- now fails OPEN everywhere), stale display copy, and
the un-resolved handoff entry; round 2 found the counters aggregation had
missed the fail-open guard (fixed by DELEGATING it to the row gate so the
two can never split) and that its own test was vacuous (non-hex identity
literals never parse); round 3 added spoken_label to the binding and an
isinstance guard on the unmatched-ids counter (model junk under a
hallucinated id crashed the whole apply AFTER the metered model run); round
4 demanded rendered-component pins for the blocking wiring itself (mutation
check: deleting the gate argument out of FieldList had left the suite
green) and the doc sweeps in this entry; round 5 cleared.

Beads: polyglot-pdf-2onl (catalogue scan % stays gate-blind -- no lint
findings at scan time), polyglot-pdf-ug5n (Repair-all value re-mint
manufactures ack prompts; needs a design call), polyglot-pdf-w028 (filed by
a reviewer, closed in-PR -- the formula stops being freely changeable once
a kit ships with baked hashes). Pre-existing: polyglot-pdf-l7u0
(FieldOverlay ignores lint + gate).

Final state: full backend suite 2316 passed; editor suite green (the
worktree full-run exit-1 is fork-startup noise -- counts are authoritative
locally, Linux CI authoritative overall); tsc clean.
