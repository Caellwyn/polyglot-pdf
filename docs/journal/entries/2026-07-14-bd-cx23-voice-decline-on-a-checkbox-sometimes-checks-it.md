---
date: 2026-07-14
bead: polyglot-pdf-cx23
title: "Voice-loop robustness: declined checkbox, secretary metadata waste, switch_to_field grounding, non-Anglo name spelling"
tags: [hotfix, review, testing]
---

## Trigger

Four voice-loop bugs from the full-form stress-test epic (polyglot-pdf-00pt), plus
one product directive, bundled into one PR (each too small for its own cycle):

- **cx23** (P1): declining an optional checkbox ("no accommodation") sometimes made
  the live model write `"true"` via update_form_fields -- CHECKING a box the user
  explicitly declined. Nondeterministic (~1 in 3 runs); a checked accommodation box
  on a printed I-90 is a substantive wrong answer.
- **2af7**: in a clean continuous run the model called ask_secretary 10 times,
  unprompted, once per field, to fetch each field's spoken NAME -- a blocking
  per-field lookup for metadata the guidance already carries (+~1.5min, +$0.13/session
  at 113 fields).
- **3vby**: on "go back to X", switch_to_field resolved in only 1 of 4 scenarios --
  the model guessed id variants that failed the exact-only resolver, and the
  unknown_field ack was a bare failure with no candidates.
- **5roy**: non-Anglo names spoken naturally were transcribed to Anglo defaults
  ("Nguyen" -> "Smith"), a plausible wrong legal name that survives a casual read-back.

## What shipped

All four fixes are SI/tool-description wording plus one frontend helper -- no change
to any data contract. The maintainer accepted cx23/2af7/3vby's code + deterministic
unit tests in lieu of a live stress-harness run, and directed the 5roy mitigation
directly.

- **cx23**: a DECLINED CHECKBOX rule in both the live DTI SI and the legacy baseline
  SI -- declining an optional checkbox -> value `""` (unchecked), then confirm
  normally; NEVER `"true"`/`"false"`. The client already renders `""` as unchecked
  and cannot distinguish a decline from an intentional check, so the fix is
  model-side.
- **2af7**: reworded `render_section_metadata` so completed-field names are listed
  inline (not framed as secretary-fetched); added a DTI SI line forbidding
  ask_secretary metadata lookups; and -- caught by the fresh-eyes review as the
  strongest lever -- NARROWED the ask_secretary tool description (and the sibling
  switch_to_field description that said "after ask_secretary names the field") so no
  tool text invites field-metadata lookups. The 1/10 in-session implicit-cache hit
  rate (vs 96-98% offline) was diagnosed as cache-TTL expiry between the
  widely-spaced per-field asks + 2.5->3.1 lite-fallback namespace mixing -- NOT a
  byte-instability bug (the prefix is stable); eliminating the redundant asks removes
  the exposure. Documented in `scripts/spikes/secretary_cache_miss_2af7_findings.md`.
- **3vby**: steered switch_to_field to pass the exact SPOKEN NAME for back-navigation
  (never a reconstructed id), and made the unknown_field ack carry nearest navigable
  candidates (id + spoken name). Candidate ranking is whole-word overlap + document
  order -- a SUGGESTION list only; resolution stays EXACT (`resolveFieldForNavigation`
  unchanged), so the lt9z fuzzy-match mis-fill trap is avoided. Mirrored in the stress
  harness so the E4 nav micro-suite exercises the same path.
- **5roy** (maintainer directive): a NAMES block in both SIs -- for a person's-name
  field the model now leads with "How do you spell your <name>?" as the PRIMARY ask
  (not "What is your <name>?"), fills the exact spelling letter for letter, and
  verifies by reading the SPELLING back ("N-G-U-Y-E-N, Nguyen -- did I get that
  right?"), never a guessed spelling.

Filed this sprint: **cfm3** (cross-script names -- what to fill when a name's native
script differs from the form's fill language, e.g. a Latin name on a Mandarin form; a
product/legal call the maintainer flagged).

## Lessons

- **Tool descriptions and the SI must agree -- a contradiction between them silently
  defeats an SI fix.** The 2af7 SI prohibition against fetching field metadata from
  the secretary was undermined by two tool descriptions (ask_secretary's own, and
  switch_to_field's "after ask_secretary names the field") still advertising exactly
  that. The fresh-eyes review caught both across two rounds. Tool-declaration text is
  weighted as heavily as prose SI by the model; pin it with a test that reads the
  declaration, not just the SI string.
- **Offering candidates is not fuzzy matching.** The banned trap (lt9z) is fuzzy
  RESOLUTION that auto-fills the wrong field. Returning a ranked SUGGESTION list the
  model then picks from -- with resolution still strictly exact -- grounds the model
  without any mis-fill risk.

## Doc freshness

The doc-freshness checker flagged ~25 docs STALE, all already stale from prior-session
commits or tracking files whose CURRENT-STATE prose this branch's SI/wording changes
do not alter (voice-ai.md, tool-call-flow.md, terminology.md do not document the
specific SI clauses added here). No current-state doc needed a content update; left
as-is per the doc-maintenance rule for docs tracking otherwise-unchanged behavior.

## Files touched

- `backend/config.py` -- DECLINED CHECKBOX + NAMES SI blocks (both SIs); DTI SI ask_secretary-metadata prohibition; narrowed ask_secretary + switch_to_field tool descriptions.
- `backend/services/ai_context.py` -- render_section_metadata reworded (names inline, ask_secretary = answers only).
- `backend/services/callback_handler.py` -- unknown_field ack surfaces candidate spoken names; message steers to spoken name, not a guessed id.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- suggestNavigationCandidates (visible-only, word-overlap ranked, exact-resolvable).
- `frontend/src/webFormConnection.ts` -- unknown_field ack carries candidates.
- `scripts/spikes/measure_form_session_costs.py` -- harness mirror of the candidate ack.
- `backend/tests/unit/test_tool_contract_static.py` -- static pins for all four SI/tool changes.
- `backend/tests/unit/test_switch_to_field_tool.py` -- candidate-listing + spoken-name-steer tests.
- `frontend/src/__tests__/switch-to-field-pin.test.ts` -- suggestNavigationCandidates + ack-candidate tests.
- `scripts/spikes/secretary_cache_miss_2af7_findings.md`, `scripts/spikes/nonanglo_name_transcription_5roy_findings.md` -- diagnosis + mitigation records.
