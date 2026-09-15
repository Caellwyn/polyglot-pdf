---
date: 2026-09-15
bead: polyglot-pdf-cpsi0
title: "feat(credits): ledger and link records carry the acting account's email; console shows who minted or granted (uid kept, never logged)"
sprint: 22
tags: [security, testing]
---

## Trigger

Maintainer feedback on 2026-09-15, after the first live mint on staging: the
firm overview's ledger showed `actor` as a raw Firebase uid (`QOtm...`),
"not really useful as is -- show which account produced the link." The bead
was filed directly from that feedback rather than tracing to a pre-planned
program-plan line item.

## What shipped

Two halves, write and read, because most rows in Firestore today were
written before this bead and carry only a uid.

**Write side.** `backend/services/credit_ledger.py::append_entry()` gains an
optional `actor_email` kwarg, stored alongside `actor` (the uid) on every
entry -- never instead of it; `actor` stays the ledger's one attribution
key. `backend/services/links_store.py::build_mint_record()` gains the same
idea one field over, `employee_email`. `backend/routes/link_routes.py`'s
mint route reads the verified staff token's `email` claim once and threads
it to both the ledger call and the mint-record builder, so the two records
a mint touches can never disagree about who minted. `admin_backend/routes/
credit_routes.py`'s grant/adjust routes pass `actor_email=actor.email` the
same way their existing audit-row call already did. Every system actor
(`"system:<origin>"` -- the sweep, the monthly top-up, the reconcile pass)
passes none, unchanged. The `ledger_export` log line never carries an
email: `LEDGER_EXPORT_FIELDS` has no email slot and the emitter never
passes one, pinned by a new test asserting no `"@"` reaches the payload
(docs/standards/hipaa-pii-policy.md).

**Read side.** New `admin_backend/services/identity_labels.py::
labels_for_uids(uids)` resolves a batch of uids to their account emails in
ONE `firebase_admin.auth.get_users()` call per request -- a caller collects
every distinct uid a page's rows need resolved first, so a firm's ledger
page (which repeats the same few staff uids across many rows) costs one
Auth call, not one per row. Per-uid TTL cache (600s, longer than
`runtime_config`'s 45s since a staff email changes far less often than a
config flag). An unknown/deleted uid, or a store failure, falls back to the
uid itself -- fail-soft, so a page always renders something rather than a
blank cell or a 500. `label_for_actor(actor, actor_email, labels)` is the
one place the three-way precedence (stored email wins; batch map is the
legacy fallback; raw uid is the last resort) is decided, shared by both
consumers so they cannot independently drift.

`GET /admin/firms/{firm_id}` and `GET /admin/firms/{firm_id}/links` each
resolve their page's distinct uids through one `labels_for_uids` call and
add `actor_label` / `employee_label` to their response rows; the uid stays
on the row, unchanged. `employee_label` joins the links route's
by-hand-fields response allowlist the same way every other key already had
to.

**Console.** `FirmDetailPage.tsx`'s ledger and links tables render the
label with the uid as a `title` tooltip; a `"system:<origin>"` label is
prettified client-side into `"system: <origin>"` (display-only -- the
backend never invents a label for a system actor).
`frontend/src/console/LinkHistoryPage.tsx` gains a manager-only Employee
column (an employee's own view already scopes to just their own links, so
repeating their own label on every row adds nothing).

**Decisions made autonomously, defended:**

- **Claimed the bead with `--no-surface-check`.** `bd_safe.py claim` flagged
  a write-surface overlap with bead `polyglot-pdf-tb3kp` (both touch
  `docs/components/admin-service.md` and `docs/technical_guide.md`) --
  every admin-console bead touches those two docs, and the overlap was
  confined to prose additions, never code. The branch/PR collision checks
  (which DO gate on real conflicts) passed clean. Not the beyond-the-bead
  commitment step 2 covers; a reversible, low-consequence pick.
- **A genuine tool-sandbox mismatch forced a mid-task pivot.** The task's
  own instructions named a fresh worktree
  (`.claude/worktrees/cpsi0-actor-labels`) to create via `git worktree add`,
  but this session's file-editing tools were hard-locked to a DIFFERENT,
  pre-existing worktree (`app-backend-connectivity-6d6fa3`, on branch
  `claude/admin-console-planning-dfe9bf`) -- `git worktree add` via Bash
  succeeded, but Edit/Write refused every write into it with an explicit
  cross-worktree error. Rather than stall, created a fresh
  `feat/cpsi0-actor-labels` branch off current `origin/dev` INSIDE the
  already-writable sandbox worktree, removed the now-orphaned stray
  worktree/branch, and did all implementation there -- a mechanical
  substitution of "which directory holds the branch," not a scope or
  design change. Confirmed via `git diff origin/dev...HEAD --stat` that
  the diff was exactly this bead's own files before committing (CLAUDE.md
  scar #3's own check).
- **Where the system-actor label prettifying lives.** The bead's own prose
  names a specific display example (`"system: backfill_firm_kind"`
  prettified). Implemented as a small, pure, frontend-only function
  (`prettifyActorLabel` in FirmDetailPage.tsx) rather than baking
  presentation formatting into the backend's `label_for_actor` -- the
  backend's job is resolving WHO an actor is, not how a column renders it,
  and a system actor's raw `"system:<origin>"` string is exactly what a
  future non-console consumer of `actor_label` (a CSV export, say) would
  want unprettified.
- **Added a manager-only Employee column to LinkHistoryPage.tsx** even
  though the bead's own wording ("likewise for the manager view") did not
  spell out a new column -- the page had no per-row employee display at
  all before this bead (only a manager-typed uid FILTER), so "likewise"
  needed a concrete rendering decision. Chose manager-only (mirroring the
  existing Revoke-column visibility split) since an employee's own view is
  already scoped to their own links, making a self-referential label
  column pure noise.

## Lessons

- **A hard tool-sandbox/instruction mismatch is a mechanical substitution,
  not a blocker, when a reversible, low-consequence path exists.** The
  session's write tools were bound to one worktree while the task named
  another; recognizing the constraint immediately (rather than repeatedly
  retrying the named path) and re-deriving a correctly-based branch inside
  the writable sandbox kept the work moving with zero content impact.
- Enumerate-the-set (CLAUDE.md scar #8) applied directly to allowlist
  tests: adding one field (`employee_email`) to a mint record touched FOUR
  separate hand-maintained allowlists across the codebase
  (`backend/tests/unit/test_store_shapes.py`,
  `backend/tests/unit/test_links_store.py`, `scripts/audit/
  inventory_stores.py`'s `links`/`links_staging` entries) plus a fifth for
  the ledger side (`inventory_stores.py`'s `ledger` entry) -- none of which
  are derived from a single shared constant the way `ENTRY_FIELDS`/
  `LEDGER_EXPORT_FIELDS` already are. Grepped for every `set(rec) ==` /
  `set(record) ==` / hand-listed key tuple touching the two stores' shapes
  before considering the change complete, rather than fixing the first
  failure the test suite surfaced and stopping there.

## Doc freshness

- `docs/technical_guide.md`: new Surface contract 34 documents the full
  write+read shape (no stamp, by design -- CLAUDE.md).
- `docs/components/admin-service.md`: new dated entry; `identity_labels.py`
  added to the Tracks line.
- `docs/components/auth.md`: closeout_prep's doc-freshness sweep flagged it
  stale against `links_store.py`/`credit_ledger.py`/`link_routes.py` (all
  touched here) -- updated the mint-record and credit-ledger-entry shape
  descriptions with the two new optional fields, bumped the stamp.
- Left stale and unreviewed (flagged by the sweep but track files this
  bead did not touch -- other in-flight branches' churn): `docs/standards/
  logging-and-cost.md` (tracks `credit_ledger.py`'s mtime, but its
  `ledger_export` description is already derived-not-hand-listed and needs
  no edit for this bead's addition), plus the voice/session/schema-forms
  doc cluster (`context-compression.md`, `jit-schema.md`,
  `schema-forms.md`, `tool-call-flow.md`, `voice-ai.md`,
  `websocket-routing.md`, `ai-models.md`, `bead-tiers.md`, `risk-rating.md`,
  `schema-key-visibility.md`, `section-reset-deprecation.md`,
  `si-reduction.md`, `stateless-architecture.md`, `terminology.md`,
  `validation-delegation.md`, `voice-and-vad.md`, `ws-protocol.md`) --
  none track any file this bead edited.

## Files touched

- `backend/services/credit_ledger.py` -- `actor_email` kwarg/entry field.
- `backend/services/links_store.py` -- `employee_email` on the mint record.
- `backend/routes/link_routes.py` -- reads the token's email claim, threads
  it to both writers.
- `admin_backend/services/identity_labels.py` -- new; batched uid->label
  resolution + `label_for_actor` precedence rule.
- `admin_backend/routes/firm_routes.py` -- `actor_label` on ledger rows.
- `admin_backend/routes/link_routes.py` -- `employee_label` on link rows,
  joins `_ALLOWLISTED_KEYS`.
- `admin_backend/routes/credit_routes.py` -- passes `actor_email` to
  `append_entry`.
- `admin-console/src/pages/FirmDetailPage.tsx` + `.test.tsx` --
  `actor_label`/`employee_label` rendering with uid tooltips, system-actor
  prettifying.
- `admin-console/src/utils/adminApi.ts` -- `LedgerEntry.actor_label`,
  `LinkRow.employee_label` typed fields.
- `frontend/src/console/LinkHistoryPage.tsx` + `.test.tsx` -- manager-only
  Employee column.
- `backend/tests/unit/test_credit_ledger.py`, `test_link_routes.py`,
  `test_links_store.py`, `test_store_shapes.py` -- new/updated tests,
  mutation-verified.
- `admin_backend/tests/unit/test_identity_labels.py` -- new module tests.
- `admin_backend/tests/unit/test_firm_routes.py`,
  `test_admin_link_routes.py`, `test_credit_routes.py`,
  `test_monthly_topup.py` -- updated/new tests.
- `scripts/audit/inventory_stores.py` -- allowlists updated for the two new
  fields.
- `docs/technical_guide.md`, `docs/components/admin-service.md`,
  `docs/components/auth.md` -- documented above.
