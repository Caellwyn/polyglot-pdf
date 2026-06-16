---
date: 2026-06-16
beads: [polyglot-pdf-ux15]
pr: TBD
tags: [testing, review]
---

# ux15: defensive duplicate-FunctionResponse dedup + parts-path integration test

Split from `pen` (PR #121 deferred fresh-eyes findings). Item (1) (the None-coordinator
guard) was adopted in a later cleanup; the two remaining items were deferred because
neither was a cheap win. Both are now actionable.

## (2) Why the dedup was investigation-gated, and why it can ship now

`live_ai_gemini.py`'s receive loop handles BOTH tool-call shapes per event -- the
`model_turn.parts[].function_call` path and the `event.tool_call.function_calls`
path -- and each appends to the SAME per-event `responses` list, flushed once. If one
event ever carried the same call in BOTH shapes, Gemini would receive TWO
`FunctionResponse`s for one call id -- a protocol violation.

The bead deferred the fix until a live-log confirmed whether both shapes can co-occur.
That investigation HAPPENED (bd ux15 notes, 2026-06-11): 3 instrumented native-audio
2.5 runs showed every tool call arrived via `event.tool_call` ONLY -- no
`model_turn.parts` co-occurrence, no duplicate responses. So the dual-path defect is
real-but-unrealized; the dedup is pure DEFENSIVE hardening (a no-op today), which is
cheap and safe to ship now that the gate is satisfied.

`_dedupe_responses_by_id` (module-level, testable) keeps the first response per call
id and drops later duplicates; id-less responses (the rare genuinely-id-less call)
can't be a duplicate-by-id so are always kept. It runs right before the flush and
returns the dropped ids so the caller logs a PII-free `duplicate_tool_response_dropped`
(COUNT only, no ids/bodies) -- the "never co-occurs" assumption stays observable if a
future SDK/model change ever makes it fire. If `polyglot-pdf-tks` later consolidates
the two paths to the single SDK-canonical `event.tool_call` one, this dedup becomes
redundant and can be removed with that change.

## (3) Parts-path coverage through a REAL CallbackHandler

The existing PR #121 regression tests inject a BARE `on_tool_call` lambda, so they
lock the adapter's append/echo logic but bypass `CallbackHandler`. The new
`test_adapter_parts_path_integration.py` drives a REAL `CallbackHandler` (its
`on_tool_call`, with a mocked coordinator + tool handlers) and runs the result through
the adapter's actual wire-build (`_build_function_response` + `_dedupe_responses_by_id`)
-- the exact tail the `model_turn.parts` path runs. It locks the
adapter -> CallbackHandler -> coordinator -> response-body -> FunctionResponse chain:
the call id is echoed (bd 0ux), the body is well-formed, an unknown tool still gets a
response (tks invariant), and no duplicates slip through. Plus 4 `_dedupe_responses_by_id`
unit tests (dup dropped keep-first, distinct kept, id-less kept, empty safe).

## Scope note (not a Gemini behavior change)

The "be wary of the Gemini API" reserved zone is about BEHAVIOR changes to the
adapter. This is neither: the dedup is a no-op on the observed wire traffic (it only
fires on a duplicate that does not occur), and the test locks EXISTING behavior. No
change to what Gemini receives in any real run.

## Verification + closeout

- 6 new tests pass; 64 adapter + callback-handler tests pass (no regression); full
  backend 369 pass.
- **Doc:** `tool-call-flow.md` tracks `live_ai_gemini.py` and documents the two
  tool-call paths + the every-call-gets-a-response invariant; bumped it with the
  dedup-before-flush behavior (a genuine addition on a tracked surface).
- **Stacking note:** this branch also carries the unmerged nx6g+17k commits (PR #221).
  The ux15 PR is opened AFTER #221 merges + a rebase, so its diff is ux15-only.
- **Beads slip:** the recurring `hrn`/`jf6w` stale in-progress beads belong to other
  sessions; left.
