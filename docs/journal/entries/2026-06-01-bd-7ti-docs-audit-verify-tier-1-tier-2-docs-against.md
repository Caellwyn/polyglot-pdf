---
date: 2026-06-01
bead: polyglot-pdf-7ti
title: "Docs audit: verify tier-1 + tier-2 docs against current code, fix drift"
tags: [review, conventions, security]
---

## Trigger

Maintainer asked for a full docs audit against the active codebase: confirm the
tier-1 + tier-2 docs actually describe the code that runs today. The mechanical
`check_doc_freshness.py` only compares a doc's `*Last updated:*` stamp against its
`**Tracks:**` files' git mtimes — it can't see *content* drift (a renamed method, a
removed message type, a "being fixed" section for already-closed work). This audit
filled that gap.

## What shipped

A 17-agent audit (one auditor per doc) cross-checked every concrete, checkable
claim in CLAUDE.md, `docs/INDEX.md`, all six `docs/components/*.md`, all eight
`docs/standards/*.md`, and `docs/technical_guide.md` against the code each one
`Tracks`. Result: **11 of 17 docs fully accurate**; 10 findings across 6 docs,
all fixed in this PR. No code changed — docs only.

Fixes by severity:

- **major** — `standards/hipaa-pii-policy.md`: deleted the "Known leaks (being
  fixed)" section. The leaks it described were already remediated under
  `polyglot-pdf-hjo` (PR #26, merged 2026-05-30) — a current-state-only violation.
  Replaced with the now-real enforcement: the static CI guard
  `backend/tests/test_no_pii_logging.py`. Widened the doc's `Tracks:` glob to cover
  the enforced files (`pdf_fill_routes.py`, `live_ai_gemini.py`, the guard test).
- **major** — `components/websocket-routing.md`: the `section_switched` payload was
  documented with a `section_id` key the backend never sends (it sends
  `section_number`/`total_sections`/`section_label`,
  `form_filling_service.py:564`). And section-completion was attributed to a
  `section_completed` message no client emits — the real mechanism is
  `manual_section_switch` / `onFormComplete` (`webFormConnection.ts:911`). The
  `section_completed` backend handler exists but is legacy/unsent.
- **minor** — `components/voice-ai.md`: tool-routing list named 2 of 5 routed
  tools; added `get_form_status`, `switch_section`, `get_field_value`.
- **minor** — `components/auth.md`: `ProtectedRoute` is wired in
  `schema-forms/main.tsx`, not `SchemaForm.tsx`.
- **minor** — `components/schema-forms.md`: added the `makes_optional`
  `ConditionalControl` capability and the legacy `conditional_logic` unlock alias.
- **minor** — `INDEX.md`: indexed the orphaned `schema_format.md`; disambiguated
  the two branch-protection docs (doctrine = this repo's rulesets, root = generic
  template).
- **nit** — `standards/stateless-architecture.md`: scoped `section_id` /
  `initial_field_hint` to the explicit section-switch handshake (not warm
  reconnect).

Deferred / filed (not fixed here, out of audit scope):

- `polyglot-pdf-rt4` (new) — `check_doc_freshness.py`'s sprint-archive regex
  expects the INDEX "Active sprint plans" row to *start* with the literal
  `sprint_<N>_<slug>_plan.md` cell; the row starts with `**Active sprint plans**`,
  so the checker always warns. Pre-existing, unrelated to this branch.
- Existing beads already cover README/model-pricing drift the audit did not need
  to re-surface (`polyglot-pdf-4ok`, `-2hy`, `-bmz`).

## Lessons

The freshness checker is a *staleness* tripwire, not an *accuracy* checker: two
docs it flagged STALE this session (`schema-forms.md`, `confirmation-and-audit.md`)
were content-accurate — the flag was only a `config.py`/`schema.ts` mtime newer
than the stamp. Conversely, the worst finding (the HIPAA "being fixed" section)
sat in a doc the checker reported **OK**. Mechanical freshness and content
accuracy are independent; a real audit has to read the tracked code, not just the
stamps. (No new standards/* one-liner — this is already implied by
`doc-architecture.md`'s "re-stamp to confirm still accurate" guidance.)

## Doc freshness

Bumped to 2026-06-01: `components/websocket-routing.md`,
`components/schema-forms.md`, `standards/hipaa-pii-policy.md`,
`standards/confirmation-and-audit.md`. Already at 2026-06-01 (content edited, no
bump needed): `components/voice-ai.md`, `components/auth.md`,
`standards/stateless-architecture.md`, `INDEX.md` (tier-1, no stamp). After the
fixes, `check_doc_freshness.py` reports no STALE docs and clean conventions; the
only remaining warning is the pre-existing sprint-row regex quirk (filed as
`polyglot-pdf-rt4`).

## Files touched

- `docs/INDEX.md` — indexed schema_format.md; disambiguated branch-protection docs
- `docs/components/auth.md` — ProtectedRoute wiring location
- `docs/components/schema-forms.md` — makes_optional + conditional_logic alias; stamp
- `docs/components/voice-ai.md` — full 5-tool routing list
- `docs/components/websocket-routing.md` — section_switched payload + completion mechanism; stamp
- `docs/standards/confirmation-and-audit.md` — stamp bump (content reviewed, accurate)
- `docs/standards/hipaa-pii-policy.md` — removed stale "known leaks"; added CI-guard enforcement; widened Tracks; stamp
- `docs/standards/stateless-architecture.md` — handshake key scoping
- `docs/journal/entries/2026-06-01-bd-7ti-docs-audit-verify-tier-1-tier-2-docs-against.md` — this entry
