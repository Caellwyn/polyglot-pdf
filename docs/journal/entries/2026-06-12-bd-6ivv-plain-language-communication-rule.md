---
date: 2026-06-12
bead: polyglot-pdf-6ivv
title: "Add plain-language communication rule for maintainer messages"
sprint: 4
tags: [conventions, docs]
---

## Trigger

Maintainer feedback during a session: status updates, questions, and PR
descriptions were too dense and jargon-heavy to parse when context-switching
across multiple active sessions. Specific complaint: bead IDs like "zun.4"
appear without context, internal shorthand like "F1" and "geometric-sweep"
require knowing the session's experiment history, and the reports assume the
reader has been following along.

## What shipped

A new **`### Communication with the maintainer`** section in CLAUDE.md under
"Critical rules", between "Escalation vs. autonomy" and "Task tracking". Three
rules:

1. Lead with context -- what triggered this, why it matters, then the question
   or status in one sentence.
2. Spell out bead IDs with a plain-English label, and replace domain jargon /
   experiment shorthand / metric names with plain explanations.
3. Don't sacrifice clarity for brevity -- but don't pad either.

Includes a Bad/Good example pair from a real session demonstrating rule 2: the
"bad" version uses opaque ML experiment shorthand; the "good" version explains
what was tested, what was found, and what numbers support the trade-off, so the
maintainer can decide without a follow-up.

## Fresh-eyes findings addressed

Two rounds of fresh-eyes ran before the PR opened. Round 1 found four gaps:

- "Internal shorthand" was too vague -- replaced with concrete categories
  (bead IDs, domain jargon, experiment shorthand, metric names).
- The "Good" example dropped the numbers from the bad example, making it
  harder to decide -- numbers added back (~2%, roughly 2x duplicate fields).
- Rule 3 had no floor against over-padding -- added "if two sentences is clear,
  two sentences is right."
- Section claimed broad scope but only covered in-session messages -- title and
  intro now scoped to "in-session messages and questions" with a pointer to the
  merge-report guidance above.

Round 2 confirmed all four gaps closed, no further findings.

## Pre-existing warnings noted

Closeout prep flagged:
- Three stale in-progress beads (b6k4, 0tgc, kl26) -- these belong to other
  active sessions and were not touched here.
- Five stale docs (beads-remote-bootstrap.md, pdf-filling.md,
  websocket-routing.md, stateless-architecture.md, voice-and-vad.md) -- all
  track files changed by other sessions (webFormConnection.ts, pdfFiller.ts,
  bd_prime.py), not by this branch. Reviewed: none of the staleness relates to
  CLAUDE.md or this change.
