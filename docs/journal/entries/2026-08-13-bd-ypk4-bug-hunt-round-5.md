---
tags: [bug-hunt, testing, websocket, deploy, schema-lint, confirmation-audit, schema-forms]
beads: [polyglot-pdf-ypk4, polyglot-pdf-d7hy, polyglot-pdf-5ry1, polyglot-pdf-8x56, polyglot-pdf-kbkd, polyglot-pdf-n2awd, polyglot-pdf-ez7n4]
surfaces: [backend/services, backend/utils, backend/routes, frontend/schema-forms, frontend/demo, scripts, schema-editor]
---

# Bug-hunt round 5: legacy handshake crash, deploy bucket defaults, to-review double-report, edition fingerprint, VoiceOverlay progress

Fifth round of the ongoing bug-hunt bead roundup (rounds 1-4: PRs #573, #576,
#578, #581). Five beads, later joined by two more the outer cross-surface
review found and folded in.

1. **A client WS handshake whose `form_metadata` is a non-dict crashed the
   session** (bd ypk4). `websocket_routes.py`'s legacy (non-JIT) branch
   validates only that `schema` itself is a dict, never the nested
   `form_metadata` key -- so a malformed client handshake reached an
   unguarded `.get().get()` chain and dropped the connection on the very
   first handshake of a session. Enumerated and fixed every reachable site in
   the same client-schema call chain (3 in `form_filling_service.py`, plus
   `ai_context.build_form_context` and `secretary_context._render_form_reference`,
   found by a dedicated reachability-tracing subagent).
2. **Two GCS bucket defaults for the same purpose disagreed** (bd d7hy, later
   n2awd). The schema-editor's deploy-kit endpoint defaulted to the demo
   bucket; `scripts/deploy-form-kit.sh` defaulted to the PROD bucket. Fixed
   the script's default to match, then the outer review caught a THIRD
   caller (`deploy-all.sh`, the script that actually performs the upload)
   still on the prod default -- an incomplete first enumeration, fixed in a
   follow-up commit on the same PR.
3. **A non-string field id caused a false double-report** (bd 5ry1).
   `schema_lint.py`'s to-review-pending section-level check only tracked
   str-typed ids, so a field with e.g. an int id sitting in a to-review
   section tripped a SECOND, false finding claiming its id "names no field
   at all."
4. **The edition-marker fingerprint ignored answerable constraints** (bd
   8x56). `resolve_edition_marker`'s fallback fingerprint hashed only field
   id + type + option values -- missing validation rules, `required`, and
   `pdf_field_name`. A real revision (a tightened validation rule, a flipped
   required flag, a remapped PDF widget) could fingerprint identically to the
   version before it.
5. **VoiceOverlay's progress counters used the wrong denominator** (bd
   kbkd). 3 live call sites computed completion from raw
   `schema.fields.length` instead of the visible-field-aware
   `SchemaFormStateManager.getProgress` -- the exact bug class bd 52qm.7
   already fixed in the shared state manager, never migrated onto these call
   sites. Factored a shared `getProgressCounts()` helper and wired all 3
   sites onto it.

## Scar tissue

### The outer review's own gap-hunting found a 4th caller the first
### enumeration missed -- twice removed from the original finding

The `d7hy` fix's own commit message said the new bucket default matched
"every other caller in this repo," naming two files. It was wrong: a THIRD
script (`deploy-all.sh`) also carried a bare `${FORM_KITS_BUCKET:-...}`
default, still pointing at prod -- and it's the one script that actually
performs the GCS upload, so it was the highest-consequence miss of the
three. This was caught not by the bead's own scope, not by the inner
fresh-eyes review, but by the OUTER cross-surface review specifically
tracing the changed bucket-default contract into every consumer. Restated
lesson (CLAUDE.md scar #7): "enumerate the set" doesn't mean "grep until the
bead's own repro passes" -- it means grep for the actual pattern
(`FORM_KITS_BUCKET:-`) across the whole repo, not just the files a bead
happens to name. The fix's own test now encodes the complete set as an
`it.each` allowlist rather than a single hardcoded check, so the next
omission fails a parametrized test instead of a third review round.

### A reachability trace is worth delegating, not eyeballing

The `ypk4` fix started from one crash site (`form_filling_service.py:317`)
the bead named directly. Rather than grep-and-guess for sibling sites, a
dedicated Explore-style subagent was asked to trace the SAME client-schema
call chain (not just any `.get("form_metadata")` in the codebase) forward
through every function it reaches, and separately classify every OTHER
`form_metadata` read in the backend as client-reachable or server-only. This
found 2 more genuine crash sites the naive "grep for the same string" pass
would have missed (they read a DIFFERENT variable name derived from the same
schema, several function calls downstream) while correctly ruling out ~10
other sites as server-side/already-guarded. Both the inner and outer review
independently re-verified this classification rather than trusting it, and
both confirmed it held.

### A doc's own missing `Tracks:` line let a stale claim survive a Haiku-
### tier freshness check

`docs/standards/schema-key-visibility.md` had no `**Tracks:**` line, so
`check_doc_freshness.py` silently skips scanning it for staleness against
the files it documents. Its claim about VoiceOverlay's raw-count sites
(accurate when written, made false by this round's own kbkd fix) would have
shipped unnoticed if the outer review hadn't cross-checked the doc's prose
against the actual current source rather than trusting the freshness
checker's silence. Filed `polyglot-pdf-a5mjw` to add the missing `Tracks:`
line so future drift in this doc surfaces mechanically instead of needing a
human-tier catch again.

## Process notes

- Five rounds now closed: 20 beads across PRs #573, #576, #578, #581, plus
  this round's 7 (5 original + 2 folded in from outer review), for 27 total.
- The outer review's first pass found 3 gaps: 2 were folded into this same
  PR (bd n2awd, ez7n4 -- both direct completions of this round's own
  enumeration), 1 was correctly left as a separate filed bead (bd jt9l4 --
  a genuinely deeper fix on a disjoint surface: the archive-sibling
  re-derivation path for `resolve_edition_marker`'s widened fingerprint,
  zero live impact today since no shipped kit reaches the fallback tier).
  A second, narrower outer-review pass then confirmed both folded-in fixes
  actually closed the gaps (mutation-verified) before this PR proceeded to
  closeout.
