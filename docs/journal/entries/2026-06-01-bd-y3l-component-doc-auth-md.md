---
date: 2026-06-01
bead: polyglot-pdf-y3l
title: "Component doc: auth.md"
tags: [conventions]
---

## Trigger

`bd polyglot-pdf-y3l`, the last writing child of the docs-reorg epic
`polyglot-pdf-gfb`. Write `docs/components/auth.md` and absorb the
`AUTH_AND_PROFILES_PLAN.md`. Dep `cg7` already closed → unblocked.

Bundled in: a stale-tracker cleanup that surfaced when the maintainer noticed three
beads sat `in_progress` with no session working them (see below), plus a one-line
INDEX de-stale.

## What shipped

`docs/components/auth.md` — verified against the **code**, because the source plan
(`AUTH_AND_PROFILES_PLAN.md`, dated Jan 2026) is mostly unchecked boxes and its
details had drifted. The plan-vs-reality corrections were the substance:

- **Firestore is the DEFAULT database**, not the named `polyglotusers` DB the plan
  assumed (`getFirestore(app)` with no name in `frontend/src/firebase/config.ts`).
- **`authorized_emails` allowlist** — `signUpWithEmail` blocks email signup unless the
  address is pre-registered in the `authorized_emails` collection. This real
  access-control gate wasn't in the plan; **Google sign-in is not gated by it.**
- **Profile `users/{uid}`** writes `role: 'user'` (plan omitted it) and `merge`-updates
  `lastLogin` on return logins.
- **Backend gate** — `verify_token` (ADC-init Firebase Admin) runs on the **`token`
  query param** of `/ws/fill` **before `accept()`**; failure closes with **code
  1008**, not the plan's 4001/4003. `VFF_DISABLE_AUTH` dev bypass documented.
- Frontend config is fully `VITE_FIREBASE_*`-env-driven; `AuthContext` also has
  `resetPassword` (plan omitted). No frontend auth tests exist (noted).

Cross-links: stateless-architecture (stateless-backend tie-in), config-deployment
(projects + `VFF_DISABLE_AUTH`), websocket-routing (handshake), testing.

INDEX: auth row de-`(planned)`-ed; **also** dropped the now-false "skeleton — being
populated under gfb.2" annotation on the `technical_guide.md` row (gfb.2 shipped and
merged — see the audit below).

### Stale-tracker audit (this session)

The maintainer flagged that 3 beads were `in_progress` with no active session. Audited
each against merged PRs + current code rather than assuming live work — all four
turned out to be **stale-open** (work merged 2026-05-30 under the old
"hold `in_progress` until maintainer merge" pattern, never flipped closed):

| Bead | Deliverable | Evidence | Closed |
|------|-------------|----------|--------|
| `gfb.2` | `technical_guide.md` | PR #17 merged; doc populated, 0 placeholders | ✓ |
| `m3f` | `terminology.md` | PR #18 merged; doc + INDEX + CLAUDE.md canon + `gfb.4` filed | ✓ |
| `pki` | `stateless-architecture.md` | PR #20 merged; doc + INDEX link | ✓ |
| `hjo` (P1 security) | PII/PHI log redaction | PR #26 merged; leaks gone+redacted; `test_no_pii_logging.py` passes 3/3 | ✓ |

This removed the recurring "SLIP-FOUND — 4 stale beads" noise that hit every closeout,
and the docs-reorg epic jumped 14→17/20.

### Review triage (PR #<TBD>)

_To be filled after round-1 triage._

## Lessons

A "plan" doc is not a source of truth for a current-state component doc — the auth
plan's named-DB / status-code / field-list details had all drifted from what shipped.
Verifying every claim against code surfaced an undocumented access-control gate
(`authorized_emails`) the plan never mentioned. Generalizes the existing
[[verify-claims-against-code-not-brief]] habit to absorbed planning docs.

Process: a bead parked `in_progress` "pending merge" is a lifecycle trap — once the PR
merges, nothing flips it, so it masquerades as active work forever. Closing at
PR-handoff (what `/closeout` does now) avoids this; the four cleaned up here were
pre-`/closeout` holdovers.

## Doc freshness

- `docs/components/auth.md` — created, stamped `2026-06-01`, passes the checker
  (worktree script copy).
- `docs/INDEX.md` — auth row de-`(planned)`-ed; technical_guide row de-staled.
- No other docs flagged for this branch's changes.

## Files touched

- `docs/components/auth.md` — new tier-2 component doc.
- `docs/INDEX.md` — auth link + technical_guide annotation fix.
- `docs/journal/entries/2026-06-01-bd-y3l-component-doc-auth-md.md` — this entry.
