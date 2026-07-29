---
date: 2026-07-29
beads: [polyglot-pdf-anim]
tags: [handoff, editor, guidance, review-gate]
---

# HANDOFF: bd anim (guidance staleness gate) -- one open decision

Written at maintainer request when the session's context filled. The work is
**committed, green, and coherent**; it is NOT merged and has ONE unresolved
design question that needs a fresh look. Branch:
`feat/anim-instructions-staleness-gate` (worktree
`.claude/worktrees/vibrant-kepler-4acabb`), HEAD `cad162f8`, tree clean.

## What the feature does (plain language)

Authored field guidance (`help.instructions` / `help.details`) is written
against a field's **voice-facing identity**: its name, spoken name, and option
labels. If a human later renames the field or relabels options, the guidance
may no longer match what the assistant actually says. But a trivial rename
must NOT cost an LLM re-author (maintainer design, 2026-07-27), so:

1. The bake records `identity_sha1` in
   `_bakeoff.authoring.instructions_enrich.provenance[fieldId]`.
2. The **backend** lint recomputes it and emits `guidance-identity-stale`
   (WARNING) whose **path** carries the CURRENT identity
   (`fields (id=X).help[identity:<hash>]`).
3. The **editor** highlights Instructions, shows a "these are still correct"
   checkbox, and blocks the field from reading green -- demoting even an
   explicit `reviewed_correct` to amber -- until a human ticks it.

Human review is always the last step. The gate informs; it never blocks the
kit publish gate (that is ERROR-only, and this is a WARNING).

## State: done and verified

- All 3 exit criteria met, including the component test criterion 1 demanded.
- 148 backend tests, 837 editor tests, `tsc` clean.
- 4 fresh-eyes rounds + 2 outer-review rounds. Outer review cleared all four
  design decisions (backend-owns-hashing, path-carried identity, amber/
  non-blocking, identity scope).

### The bug that kept recurring (worth knowing)

The SAME conceptual error appeared in **three layers** and each review round
found the next one: pinning the acknowledgment to the hash frozen at BAKE
time, which does not move when a human edits. Effect: drift -> ack -> drift
again left the gate silently satisfied (a permanent waiver). Fixed in the
write path, then the row gate, then -- worst -- the FieldEditor's own render,
where the checkbox rendered ALREADY TICKED for content the reviewer had never
seen. All three now use `isAcknowledged(field, currentIdentity(...))`.

## THE OPEN QUESTION (this is the handoff)

`identity_payload` (backend/services/guidance_contract.py) currently hashes
option labels as a **sorted bare list**. That was a deliberate maintainer
decision on 2026-07-29: *pure reorders must not prompt* (the assistant says
the same words; needless prompts train editors to click through the gate).

**The consequence nobody intended:** a label **SWAP** between two options --
"Married" and "Single" trading places while their `value`s stay put -- yields
an IDENTICAL hash, so nothing flags. The form would then record `value=m`
(now labelled "Single") for someone who said "married". Verified:

```
label SWAP flags? False   # currently MISSED
```

Maintainer asked for a recommendation and the session ran out of room. My
recommendation, for the record: **fix it.** Prompting slightly more often is
cheap; a wrong answer on an immigration form is not. It also honours what the
reorder decision actually meant ("don't nag me about harmless reshuffling") --
a swap is not harmless reshuffling.

### What I tried, and the trap in it

The obvious fix is to bind each label to its option `value` and sort the
pairs. That correctly makes reorder silent and swap flag. BUT emitting the
value in the payload also makes a **value-only rename** flag -- and the
docstring explicitly promises value edits are invisible (values are internal
slugs the assistant never says). I had that contradiction half-written when
the session ended; **it is reverted, not committed.** Measured behaviour of
that attempt:

| edit | want | that attempt gave |
|---|---|---|
| pure reorder | silent | silent OK |
| label swap | FLAG | FLAG OK |
| label edited | FLAG | FLAG OK |
| option added/removed | FLAG | FLAG OK |
| **value-only rename** | **silent** | **FLAG (wrong)** |

A next session should be able to get all six right -- e.g. sort pairs by value
but emit only labels (order derived from the binding, content from labels
alone), then check the value-rename case explicitly. I did not verify that
variant; it is a hypothesis, not a recommendation.

## Safety check already done (do not redo)

Changing the hash formula invalidates every hash already baked. **The shipped
`form-kits/w7/schema.json` carries 44 provenance records with ZERO
`identity_sha1`** (it predates the feature), and the rule is deliberately
silent without a recorded hash -- so no mass false alarm, and the formula is
still free to change. This is pinned by
`test_a_kit_baked_before_identity_tracking_never_reads_stale`, which lints the
REAL kit. Once a kit ships WITH identity hashes, that freedom ends.

## Deferred, already filed

- **bd polyglot-pdf-l7u0** -- `FieldOverlay` ignores both lint errors and this
  gate, so the PDF overlay can show green while the field list shows amber.
  Pre-existing shape (the overlay never received lint findings); fixing means
  threading props from App.
- Outer review also noted the warning message does not distinguish
  label-edit vs option-added. Judged low value; not filed.

## Also open from earlier in the session (maintainer decisions)

- **AI Studio credits for 3.1 Live** -- three diagnostic spikes remain blocked
  until credits exist or Vertex ships a 3.1 id. They now say so plainly
  instead of failing cryptically (bd kbi1, merged as PR #504).
- **I-90 refresh** -- all 132 fields are human-authored prose, so the
  ownership guard protects them all; re-enriching needs an explicit
  force-overwrite decision (bd wsao.7).
- **bd w99b** -- fleet-wide Vertex sweep; scope was CORRECTED mid-session to
  "pin Vertex as the default, KEEP the AI-Studio opt-out" (the maintainer may
  buy 3.1 credits later). Do not delete those routes.
