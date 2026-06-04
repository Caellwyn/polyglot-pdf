---
date: 2026-06-04
bead: polyglot-pdf-bmz
title: "Add authorized_emails firestore rule + wire rules for deploy"
tags: [security, conventions]
---

## Trigger

`bd polyglot-pdf-bmz` (fresh-eyes finding on PR #40): `signUpWithEmail`
(`frontend/src/contexts/AuthContext.tsx`) queries the Firestore
`authorized_emails` collection while the user is still **unauthenticated**
(before `createUserWithEmailAndPassword`), to allowlist-gate email signup. But
the checked-in `firestore.rules` had **only** a `/users/{userId}` rule -- no
`authorized_emails` match -- so under Firestore default-deny that read fails with
a permission error instead of the intended "This email is not authorized"
message. README claimed the collection was "readable by unauthenticated users,"
but the repo didn't encode it. The bead asked: check the DEPLOYED rules; if
deployed has the rule, resync the repo; if not, add it + reconcile docs.

## What shipped

**Diagnosis (verified against deployed state via the Firebase MCP):** the demo
project `polyglot-demo-aa709` had **pure default-deny** deployed --
`match /{document=**} { allow read, write: if false }` -- with **no**
`authorized_emails` rule AND **no** `/users` rule. So this was the bead's "case
b": email signup is broken there, and the `users/{uid}` profile-doc sync
(`onAuthStateChanged`) is broken too. The repo `firestore.rules` (which had the
`/users` rule) was therefore NOT what's deployed -- and `firebase.json` had no
`firestore` config block at all, so the repo rules were never wired for
deployment (the repo was not the source of truth). Prod `polyglot-forms-919f2`
rules could not be read (403, and auto-mode blocked switching the active project
to prod -- a correct production guardrail), so prod's deployed state is
**unverified**; the deploy follow-up bead covers checking it.

**Repo changes (the deploy itself is the maintainer's -- NEVER-deploy rule):**
- `firestore.rules`: added
  `match /authorized_emails/{doc} { allow read: if true; allow write: if false; }`
  (unauthenticated read required for the pre-signup check; never client-writable,
  entries managed out of band). Kept the existing `/users/{userId}` rule.
  Validated clean via the Firebase rules checker (`OK: No errors detected`).
- `firebase.json`: added a `firestore.rules` block so the repo file is actually
  deployable. This makes `firebase deploy` (and `--only firestore:rules`) ship
  the repo rules -- the repo is now the source of truth.
- `README.md` + `docs/components/auth.md`: replaced the "rules gap (verify)"
  warning with the resolved current-state rule, and added a "deploy the rules per
  project" step (a project left on default-deny breaks both signup and profile
  sync).

**Deferred (filed `bd polyglot-pdf-8sn`, P1):** the actual `firebase deploy
--only firestore:rules` to demo + prod, plus verifying prod's pre-fix state.
That is a maintainer deploy action, gated by the NEVER-deploy rule.

## Lessons

"The repo file says X" is not evidence the deployed rules say X -- especially
when `firebase.json` doesn't even wire the rules file for deployment. For any
"repo config vs. live infra" bug, read the LIVE state (here via the Firebase MCP)
before deciding between "out of sync" and "actually broken." (Generalizes the
existing "verify claims against code, not the brief" lesson to "verify against
deployed state, not the repo file.")

## Doc freshness

`docs/components/auth.md` (Tracks `firestore.rules`, now also `firebase.json`)
and `README.md` updated to the resolved current state; auth.md `Last updated:`
bumped to 2026-06-04 pointing here. `config-deployment.md` and `technical_guide.md`
also Track `firebase.json` and were flagged stale, but both reference `firebase.json`
ONLY for the hosting `/api/**` -> Cloud Run rewrite (which this change did not
touch) -- the new `firestore` block doesn't alter what they document, and the
rules-deploy guidance lives in auth.md + README (the auth-surface docs). Reviewed
and left as-is; their stale flags are pre-existing backend-mtime noise unrelated
to this branch. No other doc references the rule gap.

## Files touched

- `firestore.rules` -- add `authorized_emails` read rule (write:false).
- `firebase.json` -- wire `firestore.rules` for deployment.
- `README.md` -- reconcile rule description + add deploy-rules checklist item.
- `docs/components/auth.md` -- resolve the rules-gap warning; bump Last updated;
  add `firebase.json` to Tracks.
