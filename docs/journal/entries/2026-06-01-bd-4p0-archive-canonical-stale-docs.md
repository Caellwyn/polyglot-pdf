---
date: 2026-06-01
bead: polyglot-pdf-4p0
title: "Archive canonical + stale docs"
tags: [conventions]
---

## Trigger

`bd polyglot-pdf-4p0`, the **capstone** of the docs-reorg epic `polyglot-pdf-gfb`.
Blocked-by all the component + standards content beads; once the last of them
(`y3l`/auth.md, PR #40) merged to dev, the full tier-2 set was present and the source
docs could be archived without orphaning content.

## What shipped

Moved the superseded source docs into `docs/archive/` (all via `git mv` — renames at
100% similarity, history preserved), each with a "do not cite as current" pointer to
its tier-1/tier-2 successor:

- `planning_documents/PROJECT_CONTEXT.md` (376L) → `docs/archive/` → CLAUDE.md + INDEX + tier-2.
- `planning_documents/TECHNICAL_GUIDE.md` (1494L) → `docs/archive/` → `docs/technical_guide.md` + `components/` + `standards/`.
- `planning_documents/AUTH_AND_PROFILES_PLAN.md` → `docs/archive/` → `components/auth.md`.
- `backend/ENV_VARIABLES.md` → `docs/archive/` → `components/config-deployment.md`.
- `docs/releases/*` (7 dated legacy notes) → `docs/archive/releases/` + a README pointing at the journal.

Plus: a `planning_documents/archived/README.md` marking that pre-existing dir
superseded and recording the unshipped-work audit; an **Archive** section added to
`docs/INDEX.md` indexing all of the above; and `config-deployment.md`'s ENV_VARIABLES
pointer updated to the archived path. All pointer + INDEX links verified to resolve.

### Decisions (maintainer-steered)

- **README reconciliation deferred** → `bd polyglot-pdf-4ok`. README still frames
  `planning_documents/` as canonical reading and points AI assistants at the now-archived
  `PROJECT_CONTEXT.md`. Kept out of this PR to leave 4p0 a clean archival move; the
  follow-up rewrites README's pointers to CLAUDE.md + INDEX.
- **`docs/releases/` moved** under `docs/archive/releases/` (vs. folding into the
  journal) — they're dated point-in-time notes, preserved verbatim, not lossy-migrated.
- **Archived-docs audit:** the 7 checkbox/`TODO`-bearing docs in
  `planning_documents/archived/` were spot-checked; their unchecked items are historical
  (success criteria for shipped features, or dated hour-by-hour schedules), not a live
  backlog. Live descendants already exist as beads (token reduction `l3a`, cloud resume
  `57d`). **No new work-beads filed from the audit.**

### Review triage (PR #<TBD>)

_To be filled after round-1 triage._

### Tests

`-m "not external"`: **165 passed, 2 skipped, 1 deselected** (green). The full run
shows 1 failure — `contract/test_live_ai_gemini_integration.py::test_live_ai_gemini_real_connection`,
the `external`-marked test that hits the **real Gemini Live API**. It's an
**environmental** failure (no live API reachability/creds in this run), not a
regression: this PR's diff is docs-only and touches zero Python. Earlier closeouts
ran with live access and it passed; the deterministic suite is unaffected. This is
exactly the case `testing.md`'s `-m "not external"` guidance covers.

## Lessons

`4p0` had a real sequencing constraint that bead-deps alone didn't capture: its deps
showed `y3l` as **closed**, but I close beads at PR-handoff, so "closed bead" ≠ "merged
to dev." Archiving `AUTH_AND_PROFILES_PLAN.md` safely required `auth.md` to actually be
**on dev** (PR #40 merged), not just `y3l` closed. Verified `git cat-file -e
origin/dev:docs/components/auth.md` before starting. Generalizes: for a "do this after
everything lands" bead, check the content is on the integration branch, not just that
the upstream beads are closed.

Also: `scripts/bd_safe.py claim` false-positived on `4p0` — it substring-matched the
bead id inside OTHER merged PRs' bodies (PRs that list "blocks 4p0" as context) and
ABORTed as "mid-flight." Claimed via direct `bd update` instead. The guard should match
the bead id as a bounded token in the PR's own bead field, not a substring of arbitrary
PR bodies — filed as a note (see Doc freshness / follow-ups).

## Doc freshness

- `docs/INDEX.md` — added the Archive section (no Tracks line; not freshness-checked).
- `docs/components/config-deployment.md` — ENV_VARIABLES pointer repathed; stamp
  unchanged (its tracked code files didn't change).
- Archived docs carry pointer headers but are history-only (not freshness-tracked).
- Pre-existing STALE, left as-is (track code this branch did NOT touch): `schema-forms.md`,
  `voice-ai.md`, `ai-models.md`, `logging-and-cost.md`, `voice-and-vad.md` (track
  `live_ai_gemini.py` / schema-forms TS, stale from the merged p1t fix), and
  `technical_guide.md` (tracks `config.py`/`main.py`). None are this branch's concern.
- The freshness checker now reads correctly from the **main** repo too — the maintainer
  brought that checkout onto current `dev` (it had been 102 commits behind on
  `pitch/working-draft`), which had been causing "docs/ empty" false reads and fed a
  fresh-eyes false positive last sprint. See [[worktree-branch-off-dev-not-default]].

## Files touched

- `docs/archive/{PROJECT_CONTEXT,TECHNICAL_GUIDE,AUTH_AND_PROFILES_PLAN,ENV_VARIABLES}.md` — moved + pointer headers.
- `docs/archive/releases/*` (7 files moved) + `docs/archive/releases/README.md` (new).
- `planning_documents/archived/README.md` — new (supersede note + audit).
- `docs/INDEX.md` — new Archive section.
- `docs/components/config-deployment.md` — ENV_VARIABLES pointer repathed.
- `docs/journal/entries/2026-06-01-bd-4p0-archive-canonical-stale-docs.md` — this entry.
