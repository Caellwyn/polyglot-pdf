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
- **2af7**: the measured waste was the model asking the secretary for the CURRENT
  field's spoken name -- metadata already in guidance. The FIRST fix over-reached
  with a blanket "do not ask_secretary for a field's name/id" ban; **maintainer
  feedback corrected it**: the secretary is BY DESIGN the voice model's "which
  field does the user mean" resolver for navigation (the model cannot hold other
  fields' ids -- tight compression window). The corrected fix (a) reworded the SI +
  both tool descriptions to forbid only the CURRENT field's metadata while
  ALLOWING the nav-identification use, and (b) WIRED the secretary's `sourced_from`
  field ids -- previously DISCARDED at the adapter -- through to the ask_secretary
  tool response as a `fields` list of {field_id, spoken_name}, so the "secretary
  names a field -> switch_to_field navigates to it" flow (designed in jnjj.36) now
  actually returns a usable identifier. `TextAIGemini.ask()` changed from `-> str`
  to `-> (answer, sources)`, threaded through the handler's status dict and the
  callback dispatch (surfaced only when non-empty and well-formed; async-deliver
  path stays prose-only). The 1/10 in-session implicit-cache hit rate (vs 96-98%
  offline) was diagnosed as cache-TTL expiry between the widely-spaced per-field
  asks + 2.5->3.1 lite-fallback namespace mixing -- NOT a byte-instability bug (the
  prefix is stable). Documented in `scripts/spikes/secretary_cache_miss_2af7_findings.md`.
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

- **The secretary IS the voice model's field-navigation resolver -- do not tell the
  model to stop using it for field identification.** The model cannot hold other
  fields' ids (tight compression window), so "which field does the user mean?" is a
  legitimate, designed ask_secretary use. The 2af7 fix's first cut wrongly banned it
  wholesale; the correct line is narrow: forbid only the CURRENT field's own
  metadata (redundant), keep the nav-identification use. Underneath, the secretary's
  `sourced_from` field ids had been DISCARDED at the adapter since jnjj.45, so the
  jnjj.36-designed "secretary names a field -> switch_to_field" flow had never
  actually returned a usable id -- a designed-but-unwired path. Wiring it
  (`ask()` -> `(answer, sources)` -> tool response `fields`) is what makes the
  navigation work.
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

- `backend/config.py` -- DECLINED CHECKBOX + NAMES SI blocks (both SIs); DTI SI current-field-metadata prohibition + nav-identification allowance; reworded ask_secretary + switch_to_field tool descriptions (two uses: recall answer / identify field for nav).
- `backend/services/ai_context.py` -- render_section_metadata reworded (names inline).
- `backend/adapters/text_ai_gemini.py` -- ask() -> (answer, sources); _resolve_sources resolves sourced_from ids to {field_id, spoken_name} (deduped, capped 8).
- `backend/ports/text_ai_port.py` -- ITextAI.ask() contract updated to the (answer, sources) tuple.
- `backend/services/form_filling_service.py` -- handle_ask_secretary unpacks + carries `sources`; async-deliver path unpacks the tuple.
- `backend/services/callback_handler.py` -- unknown_field ack surfaces candidate spoken names; ask_secretary dispatch surfaces resolved `fields`; messages steer to spoken name, not a guessed id.
- `frontend/src/schema-forms/state/schemaFormState.ts` -- suggestNavigationCandidates (visible-only, word-overlap ranked, exact-resolvable).
- `frontend/src/webFormConnection.ts` -- unknown_field ack carries candidates.
- `scripts/spikes/measure_form_session_costs.py` -- harness mirror of the candidate ack.
- `backend/tests/unit/test_tool_contract_static.py` -- static pins for all SI/tool changes (incl. the nav-identification allowance).
- `backend/tests/unit/test_switch_to_field_tool.py` -- candidate-listing + spoken-name-steer tests.
- `backend/tests/unit/test_text_ai_gemini.py` -- ask() tuple return, _resolve_sources dedup/cap/skip-unknown tests.
- `backend/tests/unit/test_ask_secretary_handler.py` -- handler `sources` propagation across the deadline/detach paths.
- `backend/tests/test_callback_handler.py` -- ask_secretary dispatch surfaces `fields`; omits it when no sources.
- `frontend/src/__tests__/switch-to-field-pin.test.ts` -- suggestNavigationCandidates + ack-candidate tests.
- `scripts/spikes/secretary_cache_miss_2af7_findings.md`, `scripts/spikes/nonanglo_name_transcription_5roy_findings.md` -- diagnosis + mitigation records.
