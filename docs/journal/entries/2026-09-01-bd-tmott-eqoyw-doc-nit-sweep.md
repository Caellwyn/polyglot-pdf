---
date: 2026-09-01
bead: polyglot-pdf-tmott, polyglot-pdf-eqoyw
title: "docs-nit sweep: notice-route doc pointer + a false computeNextField claim"
tags: [docs]
---

## polyglot-pdf-tmott

`docs/technical_guide.md`'s route table row for `POST /api/tts/notice`
pointed at `components/voice-ai.md`, which contains zero mentions of
"notice" -- a dead end for a reader following the surface-contract map.
Found while cross-surface-reviewing bd `polyglot-pdf-see5j` (the
notice-route caching fix, PR #700).

Fixed by pointing the row at `backend/services/notice_tts.py` directly
(the route's own service module, which thoroughly documents its
contract), matching the convention the sibling `/api/tts/intro` row
already uses (it points at `backend/services/intro_tts.py`, not a
`components/` doc). Also added a short summary of the cache/304 behavior
`see5j` just shipped, since the row previously said nothing about it.

## polyglot-pdf-eqoyw

`schemaFormState.ts`'s `extractSectionFields` docstring claimed:

    - computeNextField() which skips locked/hidden fields for next_field_hint
    - Backend validation which rejects updates to locked fields with helpful error

Both bullets are wrong about the shipped code, verified directly:
- `navigation.ts` has zero occurrences of `read_only`; `computeNextField`
  filters purely on `shouldShowField` (confirmed by grep across every
  filter site in the file) -- a locked field CAN be offered as
  `next_field_hint`.
- The locked-field refusal is a CLIENT-side gate
  (`webFormConnection.handleFieldUpdate` checks `isFieldReadOnly`), not
  backend validation.

This was pre-existing on `origin/dev` (not caused by any change in this
sweep) -- a stale comment that actively misleads a reader into believing
a read_only field can never surface as the next field. Fixed the
docstring to describe the actual shipped behavior. Grepped the rest of
`frontend/src` for the same claim shape; no other comment repeats it.

## Also touched, then reverted

Claimed `polyglot-pdf-9pj13` (a docs-nit claiming bd `cke6v` had landed
frontend handling for `budget_exhausted` WebSocket closes) but its
premise turned out to be FALSE: `cke6v` is still `IN_PROGRESS`
(unmerged), and grepping `frontend/src` for `budget_exhausted` on current
`dev` returns zero hits. Released the bead without any diff and left a
comment explaining why, rather than writing a doc "fix" for a feature
that hasn't shipped yet.

Also verified `polyglot-pdf-hnrbg` (a docstring citation in
`backend/services/link_budget.py`) was already resolved by an unrelated
earlier PR (#693) -- closed with no diff needed.

## Testing

Both fixes are comment/doc-only, no behavioral change, no tests to run.
Verified `scripts/check_doc_freshness.py`'s code-citation check stays
clean, and confirmed (via grep) that the false claims fixed here have no
other instance in the codebase.
