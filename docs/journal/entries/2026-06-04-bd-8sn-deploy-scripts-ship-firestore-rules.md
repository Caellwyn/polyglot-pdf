---
date: 2026-06-04
bead: polyglot-pdf-8sn
title: "deploy-demo.sh / deploy-production.sh now ship Firestore rules"
tags: [deployment, security, conventions]
---

## Trigger

`bd polyglot-pdf-8sn` (follow-up to `bmz`): bmz made the repo `firestore.rules`
correct (`users/{uid}` + `authorized_emails` unauth-read / `write:false`) and
wired it into `firebase.json`, but left the actual deploy as a maintainer action.
Readiness check for a demo (staging) smoke test surfaced the real gap: the deploy
scripts never shipped the rules. `deploy-demo.sh` and `deploy-production.sh` both
delegate frontend deploy to `deploy-all.sh`, which runs `firebase deploy --only
hosting` (deploy-all.sh:246) -- **hosting only, no firestore**. So a normal demo
deploy would leave the project on its current pure default-deny rules, and email
signup (the unauth `authorized_emails` read) plus the `users/{uid}` profile sync
would both still permission-deny after deploy -- defeating the smoke test.

## What shipped

The fix makes a normal deploy self-sufficient: ship the rules alongside the
frontend, so no separate manual `firebase deploy --only firestore:rules` step is
needed for a clean deploy.

- **`deploy-demo.sh`**: added a Stage 2b inside the existing `DEPLOY_FIREBASE`
  block -- after `./deploy-all.sh --frontend`, run
  `firebase deploy --only firestore:rules --project "$FIREBASE_PROJECT"`. Rules
  ride with the frontend; `--backend`/`--form-kits`-only runs skip them (they
  don't enter the Firebase block).
- **`deploy-production.sh`**: same rules deploy after `./deploy-all.sh "$@"`,
  guarded by a `DEPLOY_RULES` flag that is true only when no args / `--all` /
  `--frontend` is passed -- so a backend-or-form-kits-only prod run does not touch
  rules. Targets `polyglot-forms-919f2`.
- **Docs reconciled to current state** (tier-2 = current-state-only): `README.md`
  (Firestore Security Rules paragraph + deploy checklist item) and
  `docs/components/auth.md` (deploy note) now say the deploy scripts ship the
  rules automatically on any frontend/full deploy, with the standalone
  `firebase deploy --only firestore:rules` noted as the manual fallback. The
  auth.md note dropped the now-historical "as of this fix the demo project had
  default-deny... until deployed" wording per the no-history doc rule.

Both scripts pass `bash -n`. `firebase.json` confirmed to carry the
`firestore.rules` block in the working tree, so the deploy command resolves the
rules file.

## Why this is in 8sn's scope (not a separate bead)

8sn is the deploy bead (maintainer-only action). Folding the rules deploy into
the existing scripts is the small, obvious change in direct service of that
deploy -- it does not alter the wire format, the stateless contract, or the
architecture; it just makes the maintainer's single `./deploy-demo.sh` run ship
what the smoke test needs. The deploy itself remains the maintainer's (NEVER-deploy
rule); this change only makes that one command sufficient.

## What still needs the maintainer

The actual deploy. From a `dev` checkout with `firebase use` on the target:
`./deploy-demo.sh` now ships frontend + rules to `polyglot-demo-aa709` in one run.
Smoke test: non-allowlisted email signup shows "not authorized" (not a permission
error); fresh login writes `users/{uid}`; a Gemini Live voice session fills a
field end-to-end. Prod (`polyglot-forms-919f2`) deployed rule state is still
unverified from bmz -- the prod deploy now ships rules too, which resolves it
forward regardless.

## Doc freshness

- `docs/components/config-deployment.md` (Tracks the deploy scripts + `firebase.json`):
  added a Firestore-rules bullet to the deploy section and bumped both
  `Last updated:` lines to 2026-06-04 pointing here.
- `docs/components/auth.md`: deploy note rewritten to current state; `Last updated:`
  pointer repointed from the bmz entry to this one.
- `docs/technical_guide.md` was flagged stale (Tracks the deploy scripts) but
  references them only as the one-line "local/manual deploy" mechanism, which this
  change does not alter -- reviewed, left as-is. Its remaining stale flag is
  pre-existing `backend/config.py` / `firebase.json` mtime noise unrelated to this
  branch.
- All other STALE entries from `check_doc_freshness.py` (voice-ai, websocket-routing,
  ai-models, hipaa-pii-policy, logging-and-cost, risk-rating, stateless-architecture,
  voice-and-vad, schema-forms, confirmation-and-audit) track backend/frontend files
  this branch does not touch -- pre-existing mtime noise, not introduced here.

## Files touched

- `deploy-demo.sh` -- Stage 2b: deploy firestore rules after frontend.
- `deploy-production.sh` -- deploy firestore rules after deploy-all, guarded to
  frontend/full runs.
- `README.md` -- rules paragraph + checklist item reflect script-shipped rules.
- `docs/components/auth.md` -- deploy note rewritten to current state.
