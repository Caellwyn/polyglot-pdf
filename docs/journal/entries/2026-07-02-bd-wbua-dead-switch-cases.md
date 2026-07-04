---
date: 2026-07-02
bead: polyglot-pdf-wbua
title: "Remove dead webFormConnection inbound cases (complete_section, ai_response)"
tags: [refactor]
---

## Trigger

The ceyt wire-contract sweep (PR #291) found two inbound switch cases in
frontend/src/webFormConnection.ts for message types no backend code sends and
ws-protocol.md does not document: complete_section (self-labeled DEPRECATED,
warn-only) and ai_response (no-op). Filed as bd polyglot-pdf-wbua.

## What shipped

Deleted both cases plus the commented-out handleCompleteSectionRequest stub
and its "kept for reference" docstring (git history is the reference).
Unknown inbound types fall through to the connection's default handling, so
behavior for these never-sent types is unchanged in practice.

Verified: repo-wide grep shows no remaining complete_section /ai_response
references in frontend/src (the distinct section_complete proactive event is
untouched); tsc clean; FE suite 493/493 green on this branch.

## Lessons

- (None new -- this is the ceyt contract tests doing their job: doc-vs-code
  diffs surfaced the dead receive arms within one session of landing.)

## Doc freshness

- No doc tracks these cases; ws-protocol.md never documented them (that
  absence is exactly what flagged them). Nothing to bump.

## Files touched

- frontend/src/webFormConnection.ts -- two dead cases + one commented-out
  stub removed (~20 lines).
