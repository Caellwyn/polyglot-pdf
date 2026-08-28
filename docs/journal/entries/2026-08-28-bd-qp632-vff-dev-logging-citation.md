---
date: 2026-08-28
bead: polyglot-pdf-qp632
title: "docs(config-deployment): re-anchor a stale callback_handler.py:466 citation"
tags: [docs, config-deployment]
---

## Trigger

Found during independent review of an unrelated PR (beads
polyglot-pdf-vuxco/-w85gd/-in8il's citation-drift fixes in
docs/technical_guide.md and docs/standards/ws-protocol.md): a repo-wide grep
for `callback_handler.py:[0-9]+` turned up a citation in a THIRD doc file
those beads didn't cover -- `docs/components/config-deployment.md:251`, still
citing `callback_handler.py:466` for the VFF_DEV_LOGGING dead-config comment.
That line is now inside `on_tool_call`'s function signature, not the comment;
the real comment is at line 491.

## What shipped

Re-anchored the citation to name `on_tool_call`'s "LOGGING POLICY" comment
block by symbol/heading rather than a raw line number, matching the
convention `bd polyglot-pdf-vdcm4` established for this repo's citations.

Swept the rest of `docs/components/config-deployment.md` for other
`callback_handler.py:N` / any `*.py:N` citations while here (CLAUDE.md scar
tissue #7) -- found one other (`main.py:10`), verified still accurate,
left untouched.

## Files touched

- `docs/components/config-deployment.md` -- one citation re-anchored.
