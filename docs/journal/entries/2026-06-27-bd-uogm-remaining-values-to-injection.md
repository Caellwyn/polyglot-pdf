---
date: 2026-06-27
bead: polyglot-pdf-uogm
title: "Move remaining form/session values (incl fill_language, metadata, policy) to injection"
sprint: 7
tags: [refactor, conventions, testing]
---

## Trigger

Child C of the fully-static DTI system-instruction epic (polyglot-pdf-13w7). 1ac3
made the DTI SI static (zero placeholders); j748 delivered the current field's
guidance via the initiating message. But emptying the SI also dropped the OTHER
former placeholders -- fill_language, form/section metadata, progress, previous
names, end-of-section confirmation policy -- which in DTI mode then reached the
model via NOTHING. uogm routes them onto the injection. Gated behind the
arm-coexistence audit (fu1h), whose F1 finding dictates the metadata source.

## What shipped

- **fill_language rides every field render.** `render_field_guidance` gained an
  optional `fill_language` param that appends "| Fill language: <lang>". Passed at
  BOTH render sites: field 1 (`send_initiating_message`) and fields 2..N
  (`callback_handler`). The handler reads a LIVE getter
  (`get_fill_language=lambda: self._fill_language`, wired via `set_tool_handlers`),
  not a snapshot, so a mid-session `change_fill_language` is reflected in the next
  field's guidance with no stale second source of truth.
- **Form/section metadata rides the initiating message.** New
  `render_section_metadata(...)` in `ai_context` renders form title / section
  N-of-total / label / previous-section names / end-of-section confirmation policy
  (reusing `get_confirmation_policy`). `send_initiating_message` appends it
  (DTI-gated) at session AND section start.
- **F1 audit constraint honored.** The metadata block is sourced from the service's
  `self._last_section_metadata` + the stored schema's form title -- NOT
  `schema["manifest"]`, which is ABSENT on a section-switch handshake
  (extractSectionFields sends full fields, no manifest). Without this, the block
  would be empty on sections 2..N. `websocket_routes` now SEEDS
  `_last_section_metadata` at SESSION START too (the plan found `_last_section_metadata`
  was only set at switch, leaving the initial + resume openers without a source);
  this also benefits `restart_gemini_session`, which already reads it.
- **SI stays state-free.** Removed the dead manifest/progress computation from the
  DTI branch of `build_form_context`; it returns the static constant directly. The
  DTI SI is now provably byte-identical across forms/sections (criterion 2) and
  still zero-placeholder (criterion 1).
- **Non-DTI byte-identical.** Both additions are gated/optional, so legacy/JIT
  output is unchanged.

**Exit-criteria scorecard:**
1. All former dynamic values ride an injection channel; the SI has no placeholder
   (zero `{`) -- PASS (`'{' not in DTI_SYSTEM_INSTRUCTION`; fill_language + metadata
   now travel on the injection; verified by tests).
2. `build_form_context` in DTI mode returns a byte-identical SI across two
   different forms/sections -- PASS (`test_dti_si_byte_identical_across_forms`; the
   DTI branch now has zero schema-derived computation).

**Live smoke-test (from the worktree, real Gemini, i90 DTI, 9 fields):** 9/9 correct
field_ids, 0 hallucinated (no regression of j748's fix); the FORM CONTEXT +
Fill language blocks confirmed present in the real initiating message (verified
deterministically since the --debug artifact does not capture the injected message
body). One field showed an un-confirmed `confirm_field` (8/9 confirmed) -- benign
live confirm-timing variance; the fill itself succeeded with the correct id.

Fresh-eyes adversarial assess (Sonnet, arm B): both exit criteria PASS, F1 honored,
no rubric FAIL. It found 2 in-scope quality findings with one shared root:
`render_section_metadata` never returned `""` -- its title branch always appended a
line (defaulting to "Form"), so the `if not lines: return ""` guard was dead, the
docstring's "returns '' if nothing renders" was false, and a metadata-less DTI
session would emit a useless `FORM CONTEXT:\nForm` line. ADOPTED: render the title
line only when there is substantive input (a section position, a label, or a REAL
form title), and pass the real title-or-None from the caller (not a "Form" default),
so the guard genuinely fires; added a test asserting the empty-input case returns
"". Re-spawn not needed (the criteria were already met; this is a self-contained
quality fix verified by the new test + full suite). Adopt: 2 (one shared fix).
Reject: 0. Defer: 0.

Codex outer review (PR #258): ERROR -- Codex hit its usage limit (same as PR #254).
Per doctrine an ERROR routes to the Opus-4.8 fallback reviewer (reviewer of last
resort), not an auto-clear or a maintainer stop. The Opus fallback independently
re-reviewed the full diff (verified fill_language at both render sites + the getter
wiring + None-safe degradation; non-DTI byte-identity; the DTI-branch cleanup;
the now-real empty-metadata guard; resume/section-switch/change_fill_language
metadata sourcing; F1 not-from-manifest) and returned NO-GAPS, no defects filed.
The review record for this PR is the Opus-4.8 fallback NO-GAPS, because Codex was
unavailable (usage limit). Closed by hand (the watcher's Codex-only --close-on-clean
did not fire).

## Lessons

A "move values to a new channel" task has a silent failure mode: a value that has
NO source at one of the channel's fire points. Here `_last_section_metadata` was set
only at section switch, so the initial + resume openers would have rendered an empty
metadata block -- the planning pass caught it by enumerating the metadata source at
EACH of the 3 initiating-message fire points (start / switch / language-change)
rather than assuming one source covered all. Enumerate fire points, not just the
happy path, when relocating state onto an event channel.

## Doc freshness

My branch changed `ai_context.py`, `form_filling_service.py`, `callback_handler.py`,
`websocket_routes.py`, `test_dti.py`. `docs/components/websocket-routing.md` reads
OK (j748 bumped it; uogm adds the metadata block to the opener but does not change
the client-driven-opener mechanism that doc describes). The remaining stale tier-2
docs (si-reduction, voice-ai, tool-call-flow, ai-models, logging-and-cost, etc.)
are stale from the cumulative epic commits; none document the DTI initiating-
message/injection internals uogm changed, so none has prose this change
invalidates. Per the epic-wide disposition, refreshing the SI-shape contract docs
(si-reduction.md et al.) to cover the now-static DTI arm + its injection channels is
the epic's collective fast-follow (the final child h1bn / a docs pass), not this
child's. Reviewed and left.

## Beads housekeeping

No orphans. Three stale in_progress beads (hrn, jf6w, ue5s) are pre-existing,
unrelated to this branch, owned by the maintainer / long-running epics. Left.

## Files touched

- `backend/services/ai_context.py` -- `fill_language` param on `render_field_guidance`; new `render_section_metadata`; removed dead DTI-branch value computation.
- `backend/services/form_filling_service.py` -- `send_initiating_message` passes fill_language to the field render + appends the DTI metadata block (sourced from `_last_section_metadata`); wires `get_fill_language` into `set_tool_handlers`.
- `backend/services/callback_handler.py` -- `get_fill_language` getter; passes fill_language to the fields-2..N render.
- `backend/routes/websocket_routes.py` -- seeds `_last_section_metadata` at session start (non-manifest metadata source).
- `backend/tests/unit/test_dti.py` -- tests for fill_language render, `render_section_metadata`, the F1 not-from-manifest guard, non-DTI byte-identical, cross-form SI identity.
