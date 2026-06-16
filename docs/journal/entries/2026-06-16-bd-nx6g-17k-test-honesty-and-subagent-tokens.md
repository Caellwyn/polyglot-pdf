---
date: 2026-06-16
beads: [polyglot-pdf-nx6g, polyglot-pdf-17k]
pr: TBD
tags: [testing, harness]
---

# nx6g + 17k: honest formatter/routing test labels + subagent-token recovery

Two unrelated quality fixes bundled (backend test honesty + a harness-telemetry
bug). Different surfaces, both self-contained.

## nx6g -- tests that mocked the unit-under-test

The uov.16 re-audit found backend tests asserting a VALIDATOR outcome while
replacing the validator with a MagicMock, so they tested only the response
formatter yet were named as if they covered validation -- they'd stay green if the
real validator were deleted.

- `test_field_validation_responses.py`: four classes inject
  `handle_update_fields=<MagicMock>` with a hardcoded return, so the asserted
  value/pattern strings come from the FIXTURE, not from validating the input. Rather
  than rewrite working tests, I RELABELED them honestly (the bead's second option):
  they ARE real coverage of the CallbackHandler response-shaping (success flag,
  applied/unknown fields, the `ERRORS:` envelope) -- just not of the validator.
  Renamed to `TestUpdateResponseShaping_Valid/_Invalid/_SingleField` +
  `TestUpdateErrorMessageFormatting`, with a module docstring stating the real
  validator is covered by `TestANumberNormalization` (same file, calls
  `validate_updates` directly) + `test_d24n_dict_option_validation.py`. The
  mislabeled `TestMultiFieldRejection.test_multiple_fields_rejected_with_clear_message`
  (it sends ONE field + asserts the happy path -- there is no multi-field path,
  `update_form_fields` takes a single field) became
  `TestUpdateResponseShaping_SingleField.test_single_field_update_shapes_success_response`.
- `test_jit_schema_loading.py`: relabeled `TestCallbackHandlerJITIntegration` as
  handler<->getter ROUTING (the JIT getter is mocked; the real schema BUILD is
  covered by the `TestJITSchemaLoading` class that calls the real
  `get_next_field_schema`). Rewrote the tautological
  `test_validation_error_does_not_call_jit`: `_handle_update_form_fields_tool` NEVER
  calls the JIT getter on ANY path (JIT delivery is on the `confirm_field` path,
  `callback_handler.py:556-557`), so `assert_not_called()` held by construction --
  true even on a successful update, proving nothing. It now asserts only the real
  thing (a validation failure shapes a `success:false` response with no
  `next_field_schema`); the structural "update never JITs" fact is covered
  meaningfully by `test_update_does_not_include_next_field_schema`.

## 17k -- subagent tokens read 0 in the harness ledger

`scripts/harness_ledger.py` splits tokens orchestrator-vs-subagent on each record's
`isSidechain` flag IN THE MAIN TRANSCRIPT -- but a spawned subagent (fresh-eyes, any
Agent/Task call) does NOT write its turns into the main JSONL. It writes its OWN
transcript under `<main-stem>/subagents/agent-<id>.jsonl`. So the main transcript has
zero subagent rows and the `subagent` bucket read 0 -- defeating the whole arm-B
point (seeing where a cheaper subagent model saves).

**Empirically confirmed** before fixing (the bead's investigate-first ask): this
session's main transcript has 0 `isSidechain:true` rows, while its
`subagents/` dir holds 10 `agent-*.jsonl` sidecars, each with 29-152
`isSidechain`-tagged usage rows.

Fix: a `discover_subagent_transcripts()` helper globs
`<main-stem>/subagents/agent-*.jsonl`, and `parse_transcript` folds those records in.
The sidecar rows already carry `isSidechain:true`, so the existing actor rule buckets
them as `subagent` automatically. The session id + wall-clock span stay anchored to
the MAIN transcript only (an `anchor_meta` flag) -- a subagent's own session id or a
late-finishing subagent must not redefine them. Verified on a REAL session (161k
subagent output tokens recovered, `models.subagent` correctly shows
`claude-sonnet-4-6`) plus 3 unit tests (folding, meta-anchoring, no-subagents-dir).

Note: 17k's comment also recorded a SEPARATE failure mode (transcript discovery keys
off cwd, breaking when run from a different worktree -- workaround `--transcript`).
That is a discovery bug, distinct from the subagent-bucket bug this PR fixes; left
for a follow-up if it recurs (the `--transcript` workaround holds).

## Pre-PR fresh-eyes

Sonnet, 1 round -> both criteria PASS; the real-validator coverage claim verified
(TestANumberNormalization + test_d24n both call validate_updates for real), the
sidecar path + meta-anchoring confirmed. Two test-coverage gaps on 17k's
"orchestrator unaffected" prong, both fixed -- and the P1 was fixed in the CODE, not
just tested: sidecar records now force-bucket to subagent (a row in subagents/ IS a
subagent turn), so a sidecar assistant row lacking isSidechain cannot leak into the
orchestrator bucket. Added a test for that leak case + an orchestrator==1 assertion
to the meta-anchoring test, and documented the no-double-count assumption.

## Closeout notes

- **Tests:** 72 affected tests pass (the 2 backend files + the harness-ledger
  suite); full backend 363 pass.
- **Doc-freshness:** the usual 10 voice-path tier-2 docs flagged STALE from other
  merged work; none track `scripts/harness_ledger.py` or `backend/tests/unit/*`
  (test files + a script are not tier-2 tracked surfaces). Nothing this PR is to
  bump.
- **Beads slip:** the orphan audit flagged `a079` -- a FALSE POSITIVE: it
  substring-matched the unrelated telemetry commit `aa079964` ("a079" in "aa079964").
  a079 is the maintainer's freshly-created (2026-06-16) in-progress bead (re-attempt
  of the demo->Vertex switch that was reverted by 5oq/zm4); not mine, not actually
  orphaned, left untouched. The stale `hrn`/`jf6w` in-progress beads belong to other
  sessions; left.
