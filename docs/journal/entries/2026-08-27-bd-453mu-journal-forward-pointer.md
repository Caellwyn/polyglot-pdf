---
date: 2026-08-27
bead: polyglot-pdf-453mu
title: "docs(journal): 0dsv4 journal entry restates the retired 'temporary until firm auth' firm_id framing"
tags: [doctrine]
---

## Trigger

`docs/journal/entries/2026-08-22-bd-0dsv4-durable-acceptance.md` said
`firm_id` is written `None` because "this route carries no auth... needs
no migration when firm auth lands" -- the same temporary-compromise
framing bd `polyglot-pdf-g3kui` later corrected (in
`confirmation_logger.py` and `confirmation-and-audit.md`) to
"PERMANENTLY None, by design; not a stopgap pending firm auth."

## What shipped

Added a forward-pointer immediately after the original framing, noting
the later correction and pointing at
`standards/confirmation-and-audit.md`, rather than rewriting the
historical text.

## Lessons

**Tier-3 exists precisely so a correction doesn't require editing
history.** The journal is the chronological record, append-only at the
corpus level -- a later bead correcting an earlier bead's framing is
itself a fact worth recording, not a reason to retroactively edit what
the earlier entry said. A forward-pointer preserves both facts: what was
believed then, and what is true now.

## Files touched

- `docs/journal/entries/2026-08-22-bd-0dsv4-durable-acceptance.md` --
  forward-pointer added
