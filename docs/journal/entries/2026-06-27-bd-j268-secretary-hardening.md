---
bead: polyglot-pdf-j268
beads_closed: [polyglot-pdf-j268]
date: 2026-06-27
tags: [hotfix, review]
---

# Secretary hardening: apology fail-open UX + lite-only fallback + ERROR logging

## Trigger

Three issues the maintainer flagged reviewing the just-merged secretary backend
(jnjj.45, PR #257), filed as a separate bead per scope-creep doctrine (jnjj.45 was
already closed/shipped):

1. **Bad fail-open UX.** On a secretary timeout/error the tool told the live model
   to "ask the user directly," which made it parrot the user's own question back
   after a multi-second wait -- "What WAS your previous last name?" -- a knock-knock
   joke. It needs an apology for an internal error instead.
2. **A possibly-invalid model id** in the fallback chain (`gemini-flash-lite-latest`).
3. **Missing visibility:** are 4xx / outage errors actually logged (PII-free)?

## What shipped

1. **Fail-open UX = APOLOGY, not a re-ask.** `_handle_ask_secretary_tool`'s
   fallback instruction now tells the live model to apologize for an internal
   error ("I'm sorry, due to an internal error I wasn't able to look that up") and
   EXPLICITLY not to repeat the user's question back. The genuine "they haven't
   answered that yet" case is unaffected -- that is a real prose answer with
   `available=True`, not the failure path.

2. **Lite-only fallback chain.** `gemini-flash-lite-latest` was confirmed NOT a
   valid model string (checked against the live Gemini model docs: the only
   `-latest` rolling aliases are `gemini-flash-latest` / `gemini-pro-latest`;
   there is no `flash-lite-latest`, so it would 404 if reached) and REMOVED from
   `DEFAULT_FALLBACK_MODELS`. It was NOT replaced with the real `gemini-flash-latest`
   -- that is the full Flash model and is too expensive; the secretary is the cheap
   tier and the fallback must stay lite-tier (maintainer cost directive). The chain
   is now `gemini-2.5-flash-lite` -> `gemini-3.1-flash-lite`; on exhaustion it logs
   and fail-opens, never escalating to a pricier model.

3. **ERROR-level logging (PII-free).** `_generate` now logs `text_ai_generate_failed`
   (model + status code + chain_exhausted flag, NO content) when a non-transient
   4xx OR a full lite-chain exhaustion is about to re-raise. The handler logs
   `ask_secretary_failed` / `ask_secretary_unavailable` at ERROR (were warnings) so
   a secretary outage is VISIBLE to us, not silently absorbed by the fail-open.

This was a latent-bug fix (the invalid model id came from jnjj.42) plus two
maintainer-requested UX/observability improvements. The invalid-model issue is a
good reminder that the fallback chain's third entry had never actually been
exercised (the first two models essentially never both fail), so the 404 hid.

**Pre-PR assess:** rubric all 3 criteria PASS (see PR body). Fresh-eyes (Sonnet,
1 round) scored all PASS but found 2 gaps, both adopted: (1) it caught this very
journal placeholder shipping unfilled -- filled now; (2) a real observability bug
-- on a handler EXCEPTION the code logged TWO ERROR events for one failure (the
except block's `ask_secretary_handler_error` plus the empty-answer branch's
`ask_secretary_failed`), which would double the secretary error rate for the
exception case. Fixed with an `already_logged` flag so exactly one ERROR fires per
failure, and added a `capture_logs` test asserting the single-error invariant.
A low-confidence finding 3 (the no-handler fail-open test didn't assert the
apology wording) was also adopted -- strengthened that test. Full suite re-run
green after the fixes.

## Lessons

- **Verify model id strings against the live model list, not memory.** A fallback
  model that "looks right" (`gemini-flash-lite-latest`) was never a real id; only
  the docs settle it. Recorded to memory [[secretary-fallback-stays-in-lite-tier]].
- **A cost-cheap path must keep its fallbacks cheap.** Escalating a lite-tier
  model to full Flash on an outage silently multiplies cost; the fix on an
  exhausted lite chain is to log + fail-open, not climb the price ladder.

## Doc freshness

- `docs/standards/validation-delegation.md` (Tracks text_ai_gemini.py) -- updated
  the fallback-chain description: lite-only, the removed invalid id, and the new
  ERROR logging on 4xx / exhaustion. Stamp bumped.

## Files touched

- `backend/adapters/text_ai_gemini.py` (lite-only chain + ERROR logging on failure)
- `backend/services/callback_handler.py` (apology fail-open + ERROR logging)
- `backend/tests/test_text_ai_fallback.py` (2-model chain + 4xx/exhaustion log tests)
- `backend/tests/test_callback_handler.py` (apology-wording assertions)
- `docs/standards/validation-delegation.md` (fallback-chain current state)
