---
date: 2026-08-28
bead: polyglot-pdf-a372q, polyglot-pdf-digef
title: "docs(config): correct 3 stale SCHEMA_EDITOR_TOKEN/SCHEMA_AUTHOR_TOKEN descriptions"
tags: [docs, editor-auth]
---

## Trigger

`bd polyglot-pdf-hn0jq` replaced the schema editor's shared-secret gate
(`SCHEMA_EDITOR_TOKEN` / `SCHEMA_AUTHOR_TOKEN`) with per-person Firebase
identity (`backend/services/editor_auth.py`), but two docs still described
the retired mechanism as current, and `backend/config.py`'s own comment on
the settings never caught up either.

## What shipped

- `docs/components/config-deployment.md`: rewrote the schema-editor-access
  bullet (previously claiming a 503 fail-closed on unset tokens, which no
  longer happens) to describe the Firebase claim + `bootstrap_editor_user.py`
  enrolment path, and corrected two stale mentions of "access-code" in the
  deploy-editor.sh runbook summary a few paragraphs later.
- `backend/config.py`: the two settings' comment now says RETIRED and names
  what actually reads them today (nothing) and what removes them later
  (`bd polyglot-pdf-rhc2v`).

## Enumerate the set (CLAUDE.md scar tissue #7)

This doc drift had accumulated **five** open beads describing overlapping
pieces of the same underlying staleness (`polyglot-pdf-9rw0h`, `-rynbi`,
`-a372q`, `-w8e44` all describe the identical stale paragraph in
`config-deployment.md`; `-digef` covers `config.py`'s comment; `-w8e44`'s own
comment already flagged the overlap and recommended closing it once `-a372q`
landed). Rather than duplicate the fix once per bead, `-a372q` and `-digef`
were fixed together here; `-9rw0h`, `-rynbi`, and `-w8e44` close as
superseded by this same change once it merges.

A SIXTH, related-but-genuinely-separate issue surfaced during the audit:
`docs/technical_guide.md`'s `/api/editor/*` route table still labels ~17 rows
"Token-gated"/"Author token only" -- the `/session` row was already fixed
(bd `polyglot-pdf-yswp3`), the rest were not. This is a same-cause, larger
sweep (17 rows vs. one paragraph) explicitly out of scope for a doc-nit-sized
bead, so it was filed separately as `polyglot-pdf-rzk6p` rather than folded
in or silently left for someone else to re-discover.

## Lessons

Five beads independently reported variations of one paragraph's staleness
over several days -- a sign the underlying doc drift (not the beads
themselves) was the real problem. Fixing the paragraph once and closing the
duplicates against it is cheaper than working each bead separately, but the
audit only works if done BEFORE fixing (checking all five descriptions
against the live file) rather than after (fixing the first one found and
hoping the others match).

## Files touched

- `docs/components/config-deployment.md` -- schema-editor-access bullet
  rewritten; two stale "access-code" mentions corrected; Last-updated bumped.
- `backend/config.py` -- SCHEMA_EDITOR_TOKEN/SCHEMA_AUTHOR_TOKEN comment
  marked RETIRED with the real current gate named.

## Follow-up

`polyglot-pdf-rzk6p` filed for the `technical_guide.md` route-table sweep
(17 rows, out of this bead's scope). `polyglot-pdf-9rw0h`, `-rynbi`, and
`-w8e44` to be closed as superseded once this merges.
