---
date: 2026-08-26
bead: polyglot-pdf-x8r78
title: "docs(technical_guide): route row for /api/disclaimer-acceptance omits the g3kui dedupe + field caps"
tags: [doctrine]
---

## Trigger

`docs/technical_guide.md`'s POST `/api/disclaimer-acceptance` route row
and Surface contracts entry 6 (the `confirmation_events` collection
contract) both described this route's write path in detail -- durable
sink, fail-open, `firm_id` always `None`, safe-path-segment validation --
but predated bd `polyglot-pdf-g3kui` and so mentioned neither control
that bead added: the one-acceptance-per-`form_session_id` in-process
dedupe, or the Pydantic field caps that reject an oversized body with
422. Nothing in either row was wrong -- an omission, not a false claim --
but entry 6 is specifically the collection contract a reviewer consults
for blast radius, and a reader there could not tell a duplicate POST is
silently dropped.

## What shipped

Added the dedupe + field-caps mention to both the route row and the
contract-6 entry, each pointing at
`standards/confirmation-and-audit.md` for the full placeholder-carve-out
rationale rather than duplicating it. Verified every factual claim
against the current code before writing anything:
`confirmation_logger._claim_first_acceptance`,
`_NON_UNIQUE_SESSION_IDS`, and `disclaimer_routes.py`'s four field caps
(`form_session_id` 128 / `language` 64 / `user_agent` 512 /
`script_version` 64) all exist exactly as the bead described. Used
symbol-name citations rather than line numbers, per this session's own
recent scar tissue on line-citation drift.

## Doc freshness

`closeout_prep.py` flagged `docs/technical_guide.md` stale from many
unrelated files (other concurrent sessions' work: `config.py`,
`websocket_routes.py`, etc.) plus the one file this bead's own trigger
names (`disclaimer_routes.py`). Left the doc's `*Last updated:*` stamp
alone rather than bumping it: bumping would misleadingly claim review of
all the OTHER triggers this diff never touched, when only the one
relevant to this bead was actually addressed.

## Files touched

- `docs/technical_guide.md` -- dedupe + field-caps mention added to the
  route row and Surface contracts entry 6
