---
date: 2026-08-27
bead: polyglot-pdf-5pyk0
title: "docs(editor): document bootstrap_editor_user.py, fix stale shared-secret runbook"
tags: [doc-freshness]
---

## Trigger

bd `polyglot-pdf-hn0jq` replaced the shared `SCHEMA_EDITOR_TOKEN` /
`SCHEMA_AUTHOR_TOKEN` secrets with per-person Firebase custom claims
(`scripts/bootstrap_editor_user.py`), but nothing documented the new
script, and `deploy-editor.sh`'s ONE-TIME setup runbook still instructed
operators to create the two dead secrets and attach them via
`--set-secrets`. An operator following the runbook exactly would stand
up an editor surface nobody could sign in to.

## What shipped

- `scripts/README.md`: new "Schema Editor Access" section documenting
  `bootstrap_editor_user.py` (grant/`--revoke`/`--list`), matching the
  existing `bootstrap_firm.py` entry's style.
- `deploy-editor.sh`: rewrote setup step 3 to require
  `bootstrap_editor_user.py` instead of the dead secrets.

## Lessons

**A "verify by following the runbook" exit criterion is a real
end-to-end check, not a formality -- it caught three real inaccuracies
across three review rounds, each introduced by the PREVIOUS round's own
fix:**

1. Round 1 added a precondition ("the target needs an existing Firebase
   account") but said nothing about how to satisfy it.
2. Round 2's fix for that ("have them sign in once, they'll see the
   403") assumed a sign-in screen that doesn't exist yet -- the hosted
   editor's actual gate, `AccessCodeGate.tsx`, is a free-text access-code
   field with no Firebase client SDK behind it at all (confirmed via
   `grep firebase schema-editor/package.json` -- zero hits). The
   sign-in-screen bead (`polyglot-pdf-yswp3`) is still open.
3. Round 3 caught that even the ORIGINAL, unchanged "every account
   403s" framing was imprecise: a real Firebase token with no role
   claim gets 403, but the shipped access-code UI sends a non-JWT
   string that fails token verification and gets 401 instead (pinned
   by `test_a_malformed_token_is_401_never_a_500` in
   `test_editor_identity.py`) -- it never reaches the 403 branch.

Each fix was independently plausible and each was wrong in a way only
caught by re-deriving the actual behavior from the real auth code and
the real frontend component, not by re-reading the prose in isolation.
**A documentation fix that describes a flow is itself a claim about the
system, and needs the same "read the actual code path" verification as
a behavioral change** -- restating a wrong assumption more confidently
is not the same as correcting it.

## Files touched

- `scripts/README.md` -- new section
- `deploy-editor.sh` -- setup step 3 rewritten
