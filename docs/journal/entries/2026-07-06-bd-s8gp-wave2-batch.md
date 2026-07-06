---
date: 2026-07-06
bead: polyglot-pdf-s8gp
title: "Wave-2 five-bead batch (s8gp, 5jvn, 6oe6, k726, jh2k)"
tags: [hotfix, harness]
---

## Trigger

Maintainer directive: keep clearing low-risk beads independently, parallelize
what can run in tandem. Five open beads across disjoint surfaces, implemented
by three parallel Sonnet subagents (backend / frontend-validation+nav /
frontend-switch) plus orchestrator-owned infra (the hooks fix); bundled into
one PR per the bead/PR contract.

## What shipped (per bead)

- **s8gp** (backend/models/form_models.py): FormSection.show_if now runs
  through BOTH the v2 rule checker and the reference auditor. `_collect_v2_problems`
  iterates `schema.sections` and reuses the existing `_v2_condition_problems`
  helper against each section's show_if, building a `sections[i] (id=...)`
  path; `validate_all_references` walks section.show_if atoms via the same
  `iter_condition_atoms` fields use, so a ghost field ref in a section
  condition is now reported. FormSection.show_if is model-typed
  `Optional[ConditionalDisplay]` (atomic only -- sections cannot carry a v2
  composite on the wire today), so only the atomic path was needed; widening
  the model would be an out-of-scope wire change. 4 new tests (2 v2-violation
  cases naming the section path, 2 negative cases proving no over-rejection);
  all shipped kits still validate.
- **5jvn** (frontend/src/schema-forms/utils/validation.ts): checkbox-group
  enum/option-membership validation no longer requires `group_kind` (which no
  shipped kit sets). `isStringEnumField`'s checkbox branch now uses a shared
  `isCheckboxGroupField()` (options.length>0 OR group_kind==="checkbox"),
  matching canonicalizeAiCheckboxGroupValue / the CheckboxField renderer. Two
  wrinkles the trace surfaced beyond the bead text: (1) validateOptionMembership's
  OWN internal group flag was also group_kind-only and needed the same
  alignment, else a valid array value for a real group (i-90 p3_race) would be
  wrongly rejected; (2) a boolean-intent carve-out in validateField's enum gate,
  because the real standalone checkbox p2_checkbox3 carries a one-element
  options array (its single PDF widget) and would otherwise start failing valid
  true/false fills -- mirrors canonicalizeAiCheckboxGroupValue's existing
  boolean-intent exclusion. Now an AI-invented race option is REJECTED at the
  client boundary (routed back to the model) instead of silently dropped at
  PDF-fill time. Tests at both the validation-unit and applyAiValueWithValidation
  end-to-end layers.
- **6oe6** (frontend/src/navigation.ts): computeNextField's Priority-1
  (filled-unconfirmed) has-value check now mirrors handleConfirmFieldRequest's
  hasUsableValue exactly -- `'' on an optional field counts as usable` -- so an
  optional field the model filled with `''` (the "does not apply -> update ''
  then confirm" SI flow) is offered for CONFIRM, not re-offered as empty-to-fill.
  Confirmed to manifest in practice (the optional-cleared-field flow is real).
  Priority-2 (required empty -> fill) untouched. Missing navigation-confirmation
  test added (+a contrast test proving required-empty still routes to fill).
- **k726** (frontend/src/webFormConnection.ts): handlePrepareSectionSwitchRequest,
  when an AI switch arrives while a client auto-advance is parked on the
  validator gate, CANCELS the parked switch (resolving its gate cancelled=true so
  proceedSectionSwitch returns without a reconnect/throw). This holds for BOTH a
  matching and a mismatching AI target: an AI switch to an unrelated section M has
  authoritatively relocated the session, so the parked N->N+1 boundary is now
  STALE and running it later would pull the user OUT of M. (See the fresh-eyes
  section: an earlier "preserve on mismatch" cut had a stale-reconnect hazard;
  cancel-in-both-cases is correct.) Regression tests: an AI switch to unrelated s3
  cancels the parked s1->s2 switch cleanly; and the adverse ordering (AI switch
  COMPLETES before the parked gate resolves) does NOT reconnect-switch to the
  stale s2.
- **jh2k** (.claude/settings.json + scripts/block_admin_merge_hook.py):
  ALL FOUR hook commands (PreToolUse admin-merge guard, SessionStart bootstrap
  + bd_prime, PreCompact bd_prime) used cwd-RELATIVE `python scripts/...` paths.
  Because the Bash tool's cwd persists between calls, any command ending inside
  a subdirectory (e.g. `cd frontend && vitest`) made the next hook fail
  "can't open file" and bricked all subsequent Bash calls (this bit the bo4m
  session). Fixed to absolute `python "${CLAUDE_PROJECT_DIR}/scripts/..."` --
  Claude Code substitutes ${CLAUDE_PROJECT_DIR} (guaranteed set for all hook
  types, points at the project root) as a plain string before the shell runs,
  and Git Bash handles the Windows path natively (verified via claude-code-guide
  against the official hooks docs). Kept shell-form (not exec form) to preserve
  the `|| true` on the bootstrap hook. Also converted the hook script's module
  docstring to a raw string (r""") -- the `--ad\min` example was an invalid
  `\m` escape firing a SyntaxWarning on every hook run.

## Verification

Combined suites after all five: backend+harness 1588 passed / 3 skipped,
frontend 749 passed (37 files, default pool). jh2k verified by MECHANISM (this
session cannot reload its own hooks): simulated Claude Code's substitution
(${CLAUDE_PROJECT_DIR} -> repo root) and ran the hook FROM a subdirectory --
the absolute path is found, `gh pr merge --admin` is still DENIED
(permissionDecision deny, exit 0), a normal `--squash` merge is ALLOWED (exit 0
no output), and `-W error::SyntaxWarning` no longer raises.

## Fresh-eyes findings (all adopted)

The pre-PR Opus assess found ONE blocking gap + two supporting findings, all
correct:

- **k726 (blocking) -- stale reconnect after AI switch completes.** My first
  cut LEFT the parked switch intact on a target mismatch. The reviewer traced a
  worse bug than the original: once the AI switch COMPLETES (clears
  switchInFlight), the parked gate's fail-OPEN timer resolves past the
  post-await switchInFlight re-check (which only guards while the AI switch is
  in flight) and runs doSectionSwitch on the STALE target -- reconnecting the
  user OUT of the section the AI just moved them to. Resolution: the bead's
  premise ("the dropped switch was a valid advance") was itself wrong -- once
  the AI relocates the session, the parked N->N+1 boundary is STALE. So the
  correct behavior is to CANCEL the parked switch in BOTH match and mismatch
  cases (cancel cleanly resolves its gate). This is close to the original
  unconditional cancel, but now with correct justification and a test for the
  adverse ordering the agent's original test missed (AI switch completes BEFORE
  the parked gate resolves). NOTE: this means k726's literal exit criterion
  ("mismatched AI switch preserves the parked client switch") was superseded --
  the review proved that behavior buggy; the delivered behavior is the correct
  one the criterion was reaching for (don't strand the session), reached by
  cancel-not-preserve.
- **5jvn (supporting) -- boolean-intent carve-out too broad.** The `"true"`/
  `"false"` string carve-out fired on ANY checkbox, so `"true"` on a real
  multi-option group (p3_race) skipped the enum check -- reopening the exact
  silent-drop 5jvn closes. Fixed by scoping the STRING carve-out to
  SINGLE-option checkboxes (option count <= 1 -- the load-bearing distinction,
  since isCheckboxGroupField is true for both the one-option standalone
  p2_checkbox3 AND real groups). Actual boolean values stay broad. +test: "true"
  rejects on p3_race, still passes on p2_checkbox3.
- **k726 (supporting) -- misleading "deferred" comment.** The mismatch comment
  said the boundary was "deferred", but the code dropped it. Moot after the
  cancel-in-both-cases fix; the comment now states the cancel reasoning.

## Doc freshness

No tier-1/2 doc tracks the touched surfaces in a way this batch changes. (The
hooks live in settings.json, documented behaviorally in CLAUDE.md scar tissue
and the memory files, which describe the footgun -- now fixed -- generically.)

## Notes for the maintainer

- jh2k touched `.claude/settings.json`: the orchestrator CAN edit hook `command`
  strings (the auto-mode restriction is specifically on `permissions.allow`
  rules, which this did not touch). The change is behavior-preserving for the
  hooks' matcher/type/exit-code contract -- only the script path became absolute.
