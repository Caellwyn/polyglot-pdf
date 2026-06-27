---
date: 2026-06-27
bead: polyglot-pdf-1ac3
title: "Static DTI SI constant (zero placeholders, generic tool protocol)"
sprint: 7
tags: [refactor, conventions, testing]
---

## Trigger

Child A of the fully-static DTI system-instruction epic (polyglot-pdf-13w7;
plan of record `docs/sprint_7_static-si_plan.md`, on branch
`claude/fervent-agnesi-e3b020`, not yet merged to dev). The epic root-causes the
DTI field_id hallucination (jnjj.46): the DTI system instruction (SI) was never
actually static -- it interpolated 12 form/session placeholders, most damagingly
a `CURRENT FIELD:` block built from field 1 at connect that never updated
mid-section. Fields 2..N's exact ids arrived only inside `confirm_field` tool
results, so the model reconstructed wrong ids for them from field 1's exemplar.
Child A's job is the first step: make the constant itself fully static.

## What shipped

Rewrote `Settings.DTI_SYSTEM_INSTRUCTION` (`backend/config.py`) to a
zero-placeholder constant. The change:

- **Deleted the crux.** Removed the `CURRENT FIELD:\n{current_field_guidance}`
  block and the "use the exact field_id from schema" line.
- **Added a static current-field rule.** A new "CURRENT FIELD -- READ THIS FIRST"
  block tells the model that the field it is filling now -- including its exact
  field_id -- is ALWAYS in the most recent injected guidance block (the
  initiating message at session/section start, then the next-field guidance after
  each confirm); to act on the LATEST block, copy the field_id verbatim, and
  NEVER invent, reconstruct, guess, abbreviate, or pattern-match an id from
  another field; and to fall back to a status lookup or asking the user if there
  is no current guidance block (e.g. after a reconnect).
- **Genericized the tool prose.** Replaced the per-tool catalog (a "TOOLS:" list
  naming update_form_fields / confirm_field / get_form_status / etc.) with a
  tool-agnostic "TOOL PROTOCOL:" section that states protocol rules only (use the
  tool whose declared purpose matches your intent; fill one field per call;
  confirm before advancing; pass args as declared; act on what the tool returns).
  Tool names/params/returns already live in the SDK tool declarations, so the
  coming validator/assistant tools need no SI edit.
- **Stripped all remaining placeholders** (`{fill_language}`, `{form_title}`,
  section/progress metadata, `{section_list}`, `{confirmation_policy}`, etc.) to
  satisfy epic criterion 1 (zero `{`). Delivering those values back via the
  dynamic injection is epic children B and C; A+B alone is what the jnjj.46 fix
  needs, and the metadata move (C) is a fast-follow.

The `.format(...)` call in `ai_context.py` (DTI branch) still passes its 12
kwargs; with no placeholders left, `.format()` is a verified safe no-op. Cleaning
up that call is Child C's scope.

**Tests.** Two DTI unit tests asserted field-1 guidance lived in the SI
(`test_dti_branch_carries_current_field_guidance`,
`test_dti_current_field_is_client_selected_field_zero`) -- behavior the epic
intentionally removes. Rewrote both to assert the new static-SI invariants:
`test_dti_si_is_static_carries_no_field_guidance` (no `ID:`/field guidance in the
SI) and `test_dti_si_is_fully_static_zero_placeholders` (zero `{` in the rendered
SI and in the constant; verbatim-copy + never-invent instruction present). Full
backend suite: 436 passed, 2 skipped, 3 deselected (run from the worktree).

**Exit-criteria scorecard (Assess, Step 5.5.a):**
1. Zero `{` in `DTI_SYSTEM_INSTRUCTION` -- PASS (verified `'{' not in si`; both
   the constant and the rendered SI; `.format()` is a no-op).
2. No field guidance / no `ID:` line; copy-id-verbatim-from-latest-injection
   rule present -- PASS (no field guidance block; new "CURRENT FIELD -- READ THIS
   FIRST" block instructs verbatim copy and "NEVER invent, reconstruct, guess").

Fresh-eyes adversarial assess (Sonnet, arm B picker -> sonnet on a 152-line
diff): NO-GAPS in round 1. Both criteria met; `.format()` verified safe with zero
placeholders; ASCII-only confirmed; no load-bearing static behavior dropped; both
rewritten tests confirmed non-tautological. It filed one out-of-scope bead,
polyglot-pdf-39ik (a stale `render_field_guidance` docstring + a `{next_field_hint}`
mention in an `ai_context.py` comment -- Child C territory, the .format() cleanup).
It also noted the now-vestigial stale comment in the unchanged
`test_dti_si_size_is_independent_of_section_size` (untouched lines, left for the
epic). Adopt: 0 inline fixes needed. Reject: 0. Defer: 1 bead (39ik).

Codex outer review (PR #252, round 1): COMMENTS -- 4 P1 inline findings, all the
SAME class of true-but-out-of-scope observation: removing a placeholder from the
SI removes information the model needs, and Child A does not restore it. Each maps
1:1 to an already-filed dependent child bead, so nothing is lost and none is a
Child-A blocker:
- Field-1 guidance/field_id no longer reaches the model (Codex's sharpest, and
  correct: `send_initiating_message` strips the field_id) -> **j748** (B),
  which DEPENDS ON 1ac3 and exists precisely to deliver field 1 via the injection.
- `fill_language` lost -> **uogm** (C): fill_language becomes a render_field_guidance param.
- End-of-section confirmation policy lost -> **uogm** (C): confirmation_policy via
  render_section_metadata.
- Section-lookup context (section_list / previous_spoken_names) lost -> **uogm**
  (C): same render_section_metadata block.
Critically, `USE_DTI` defaults to **false** (config.py:128; no `.env` override),
so the affected DTI path is experimental + off in the default/production config --
this PR regresses no live or default behavior. The approved plan structures A/B/C
as sequential children (j748 depends on 1ac3), and the bead/PR contract is one
bead = one PR, so Child A ships as its own PR that lands before B/C. Codex
disposition: deferred to existing dependent beads (j748/uogm), NOT looped (a
re-review with no code change would re-report the same inherent-to-design findings
and burn a round). Recorded for the maintainer's merge decision.

## Lessons

Run backend tests from the WORKTREE, not the main checkout. An early
verification run with cwd in the main repo (`PYTHONPATH=.`) imported main's
unedited `config.py` and reported "15 passed" against the OLD SI -- a false green.
Re-running with cwd + `PYTHONPATH` at the worktree surfaced the two real
failures. This is the existing scar (run-backend-tests-from-worktree-not-main);
it bit again here because the SI constant is read indirectly via `get_settings()`,
so the wrong-checkout import is invisible in the test output.

## Doc freshness

Reviewed the doc-freshness flags. My branch touched only `backend/config.py` and
`backend/tests/unit/test_dti.py`. The freshness gate flagged many tier-2 docs as
stale-and-tracking-config.py, but on inspection none contain current-state prose
that THIS change makes false:
- `docs/standards/si-reduction.md` (the frozen SI-shape contract) documents only
  the Legacy and JIT templates and their placeholder sets -- it never described
  the DTI template at all (DTI shipped under jnjj.22, after this doc's
  2026-06-17 stamp). So it was already stale w.r.t. DTI mode existing; my change
  to the DTI SI does not invalidate its documented Legacy/JIT contract. Bolting a
  partial DTI section onto a frozen-contract doc is beyond this one-file bead; the
  static-SI epic (13w7) is the natural owner of refreshing the SI-shape contract
  to cover the now-static DTI template. Reviewed and left.
- `docs/components/jit-schema.md` mentions DTI only in passing ("DTI rides the
  next field's client-supplied guidance in the confirm_field response and keeps
  the principal SI tiny") -- which this change makes MORE true, not false. Left.
- The other flagged docs are stale because of other recent commits to files my
  branch did not touch (live_ai_gemini.py, callback_handler.py, frontend, etc.) --
  they were stale before this branch. Left.

No CLAUDE.md change.

## Files touched

- `backend/config.py` -- rewrote `DTI_SYSTEM_INSTRUCTION` to a fully static
  zero-placeholder constant (static current-field rule + generic tool protocol);
  updated the constant's leading comment.
- `backend/tests/unit/test_dti.py` -- replaced the two field-1-in-SI assertions
  with two static-SI invariant tests.
