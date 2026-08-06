---
date: 2026-08-05
bead: polyglot-pdf-n18q
title: "Surface contracts: the code-derived cross-surface data-contract map"
tags: [docs, architecture, review-harness]
---

## Trigger

Kickoff of the maintainer-directed docs audit (2026-08-05). The outer
cross-surface reviewer needs a single source of truth for where this app's
surfaces actually meet; the only "verified architecture" reference was the
2026-05-30 reorientation brief -- a tier-3 journal entry, dated history not
maintained current state. technical_guide.md already indexed endpoints and
gotchas but described ROUTING (which URL resolves where), not PAYLOAD SHAPE
(which keys both legs must agree on).

## What shipped

A `## Surface contracts` section in docs/technical_guide.md: six contract
chains (kit schema editor->store->voice/UI; WS handshake; WS control messages
both directions; backend<->Gemini tool coupling; the sessionStorage ->
/api/fill-pdf -> AcroForm round trip; the confirmation audit trail), every
entry citing producer and consumer file:line plus the silent failure mode
when they disagree. Derived by three parallel Explore tracers reading the
code (not prior docs), with the load-bearing citations spot-verified by the
orchestrator before publishing.

The doc's `Tracks:` line was widened from backend/main.py + config + routes
to include the contract-bearing files: form_models.py, form_kits.py,
callback_handler.py, request_coordinator.py, live_ai_gemini.py,
webFormConnection.ts, schemaFormState.ts. Mutation-verified: with the stamp
set to 2026-07-01, check_doc_freshness.py flags technical_guide.md STALE on
all seven newly-tracked files, none of which the old line covered.

Also fixed two drift spots in the same file: the sections/parts gotcha still
said the wire/log rename was "deferred to polyglot-pdf-zun" (zun shipped;
token-log is section_id; manifest.parts stays by design, carrying
section-shaped entries), and the brief-as-architecture citation now points
at the contract map instead.

## Notable findings baked into the map

- Almost no cross-surface contract is pinned by a shared type: both WS legs
  and the fill payload are hand-typed dicts/object literals; renames fail
  silently at runtime.
- FormSchema validation runs ONLY at the editor publish gate; draft saves and
  every read path stream raw dicts.
- /api/fill-pdf fills from the CLIENT-submitted schema (never cross-checked
  against the kit store or the extraction acroform.json ledger), and
  unwrapFieldValue strips confirmed/skipped flags -- a deliberate skip is
  indistinguishable from never-asked in the artifact.
- Dead frontend consumer: `case "field_update"` in webFormConnection.ts has
  no live producer (updates ride `form_updated` with a different shape).
- The `switch_to_field` tool deliberately maps to the `switch_field` wire
  type; `change_spoken_language` is a wire-compat misnomer.

## Follow-on

polyglot-pdf-wtte (blocked on this bead) wires the map into closeout
freshness and the outer-review prompt. The broader docs audit continues as
polyglot-pdf-2zk3.
