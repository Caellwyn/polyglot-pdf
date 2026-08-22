# Sprint 21 -- Per-user identity for the schema editor

**Epic:** `polyglot-pdf-ijntk`
**Approved:** 2026-08-20

---

## Why

The editor API authenticates with exactly two shared secrets: everyone holding
the editor token is the same principal to the server, and likewise every author.
No user id, no session, nothing in any request that says WHO acted.

That costs four things, and they get worse as subcontractors are added:

1. **No editor-vs-editor anything.** The kit checkout lock (bd
   `polyglot-pdf-hqztg`) can only be ROLE-scoped, because the server can record
   "an editor holds this" but never "Maria holds this". Two subcontractors
   sharing one token collide exactly as they do today.
2. **No attribution.** Logs record `role=editor|author`, so an audit answers
   "an editor did it", never which one -- in a product whose whole point is a
   defensible record of who agreed to what.
3. **No revocation granularity.** Removing one subcontractor's access means
   rotating the shared token and redistributing it to everyone else.
4. **No per-user UI.** "Checked out by ..." cannot name anyone.

---

## The governing constraint

Maintainer, 2026-08-20, verbatim:

> "separating them fully right now is out of scope. That's its own epic. What I
> don't want is to create NEW dependencies that I will just need to unravel
> against later."

So the rule is **not** "separate everything now" and **not** "share freely" --
it is **do not deepen the coupling**:

- The editor gets its **own allowlist** and its **own role claim**, distinct
  from the voice app's `authorized_emails` / `firm_role`. A voice-app user has
  no editor access unless separately listed.
- The editor's sign-in code lives in `schema-editor/` and **imports nothing**
  from `frontend/`. Duplicate the pattern rather than share the component -- the
  editor folder stays liftable.
- **Do not** build a second Firebase project. **Do not** change how the voice
  app authenticates. That is the separate epic.

**Test for any choice in this epic:** *does this create a new thread a future
separation epic would have to cut?* If yes, do it differently.

The editor is already separable in the ways that matter -- its own Hosting
target (`editor` vs `app` in `firebase.json`), its own backend routes, its own
deploy script. The sign-in system is the only genuinely shared piece.

---

## Maintainer decisions

| # | Decision |
|---|----------|
| 1 | **Sign-in shape:** reuse the KIND of screen the voice app has (Google / email+password / reset). NOT email-link -- that exists nowhere in this codebase and would be new code on a path nothing else uses. |
| 2 | **Cutover, not transition:** "I have no live subcontractors, so now is a good time to cutover." No dual-auth path, no migration window. The shared tokens are REMOVED, not deprecated. |
| 3 | **Historical attribution:** nothing to backfill. No kit metadata carries an actor field (all 3 kits checked) and past editor actions live only in Cloud Logging, which a migration cannot rewrite. New actions are attributed; pre-identity history is explicitly unattributed. Inventing an owner field populated with an unverified claim would be wrong in a product whose value is a defensible record. |

---

## Exit rubric

| # | Criterion | Verify |
|---|-----------|--------|
| 1 | Two DIFFERENT editor users are distinguishable by the server: a mutating action records which one acted | Test: two users each perform a mutating action; the recorded actor differs |
| 2 | Revoking one user's access does not disturb any other user, with no shared-secret rotation | Revoke one user; a second signs in and completes a save. No env var changes |
| 3 | The checkout lock prevents editor-vs-editor stealing while preserving author preemption | Test both: editor B refused on editor A's lock (409); author takes it back (200) |
| 4 | An editor account grants no voice-app access, and a voice-app account grants no editor access | Test: a voice-app-only user is refused by an editor route; an editor-only user is refused by a voice route |
| 5 | Nothing under `schema-editor/` imports from `frontend/` | `grep -rn "from ['\"].*frontend/" schema-editor/src` returns nothing |

Criteria 4 and 5 are additions to the bead's original three, derived from the
separation constraint above.

---

## Bead tree

| Child | Scope | Surfaces | Inherits |
|-------|-------|----------|----------|
| **1. Server-side identity** | The editor verifies per-user Firebase ID tokens and reads its OWN role claim; a bootstrap script stamps that claim, mirroring `scripts/bootstrap_firm.py` rather than extending it. `require_editor_role`/`require_author_role` return an actor object; the ~5 helpers that consume the role adapt. | `backend/routes/editor_kit_routes.py`, `backend/routes/editor_readiness_routes.py`, `backend/services/editor_auth.py` (new), `scripts/bootstrap_editor_user.py` (new) | 1, 2, 4 |
| **2. User-scoped locking** | `editing_lock` records a person, not a role. Same-role stealing refused; author preemption preserved. `heldBy` names a person. | `backend/routes/editor_kit_routes.py` (lock helpers + response models) | 3 |
| **3. Editor sign-in screen** | Its own sign-in screen under `schema-editor/`, its own allowlist, importing nothing from `frontend/`. Replaces `AccessCodeGate.tsx`. | `schema-editor/src/components/`, `schema-editor/src/utils/remoteKitStore.ts` | 2, 5 |
| **4. Remove the shared tokens** | Delete `SCHEMA_EDITOR_TOKEN` / `SCHEMA_AUTHOR_TOKEN` and the `X-Editor-Token` path outright. Clean cutover -- no live subcontractors. | `backend/config.py`, `backend/routes/editor_kit_routes.py`, `deploy-editor.sh`, `deploy-demo.sh` | 1 |

**Ordering.** Child 1 lands first -- it fixes the real problem and is testable
with no UI change. Children 2 and 3 have disjoint surfaces and no ordering edge
between them, so they are **parallelizable** once 1 is in. Child 4 is last, once
the replacement is proven.

**Surface overlap note.** Children 1, 2 and 4 all touch
`editor_kit_routes.py`. They are deliberately SEQUENCED rather than parallel for
that reason -- 1 -> 2 -> 4, with 3 free to run alongside 2. The collision guard
will enforce this.

---

## Research findings that shaped this

- `backend/services/auth.py` already verifies Firebase ID tokens and returns
  decoded claims -- but `editor_kit_routes.py` does not use it at all. The
  editor is on an entirely separate shared-token path today.
- The `firm_id`/`firm_role` custom-claim pattern is **shipped, not
  speculative**: `scripts/bootstrap_firm.py` stamps claims via
  `set_custom_user_claims` (merging over existing claims, pinned by a test),
  read off the decoded token. A directly reusable **template** -- copy the
  pattern, do not extend the firm one.
- `require_editor_role`/`require_author_role` return a plain `str`. 26 call
  sites: ~10 use the value in real logic, ~16 are gate-only or log-only. The
  logic uses funnel through ~5 helpers (`_require_edit_lock`, `_lock_refusal`,
  `_lock_after_transition`) plus 2 response models
  (`EditorSessionResponse.role`, `KitLockResponse.heldBy`). So `str` -> object
  is a ~5-helper edit, not a 26-site churn.
- `editing_lock` is stored per-kit in `metadata.json` as `{"role": "editor"}`.
  The code comments already name `ijntk` as the bead that re-scopes it.
- Email-link sign-in exists **nowhere** in this codebase (0 hits in
  `frontend/src` and `schema-editor/src`; an earlier count of 289 was
  `node_modules`, the Firebase SDK's own definitions).

---

## Out of scope

- A second Firebase project, or full auth separation between the editor and the
  voice app. **That is its own epic**, and this one must not add threads it
  would have to cut.
- Any change to how the voice app authenticates.
- Backfilling existing kits or records with an owner (see decision 3).
- A request queue or "checked out by" UI beyond naming the holder.

---

## Noted at planning time

Child 3 (the sign-in screen) is the bulk of the work and the least essential:
the collision actually biting today is fixed by child 1. Cutting child 3 and
keeping the shared token for LOGIN while the SERVER tracks identity is a
coherent stopping point if this needs to be smaller.
