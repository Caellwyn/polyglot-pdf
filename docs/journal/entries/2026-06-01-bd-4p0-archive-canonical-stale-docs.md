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

### Also: default native model → 3.1 (folded in)

This PR also flips `USE_PREMIUM_MODEL`'s default from `false` → **`true`** in
`config.py`, making **`gemini-3.1-flash-live-preview`** the default native-audio model
(2.5 becomes the cheaper opt-in). Reason: the 2.5 native-audio *preview* is
intermittently silent on the audio path (no-audio turns; `bd polyglot-pdf-daa`),
whereas 3.1 is stable there, and 3.1 is only modestly pricier (text-out 4.50 vs
2.00 /1M; audio in/out identical). Updated to match: `standards/ai-models.md` (tier
table default + the `USE_PREMIUM_MODEL` default + a why-3.1 note),
`components/config-deployment.md`, and the config.py tier comments.

**What this investigation surfaced (verified live):** 3.1 and 2.5 are **not
config-compatible**. 3.1 (`-live-preview`) *rejects* the smoke test's minimal
`{response_modalities:[AUDIO], system_instruction}` config with `1007 invalid
argument` (every run; TEXT-only → 1007 "invalid combination of modalities" too). It
only works through the fuller config the real adapter builds (tools +
`realtime_input_config` + transcription) — which is how the tak spike billed 3.1
cleanly. So the default flip is correct for the **app** (real adapter path), but the
hand-rolled smoke test can't simply switch models.

### The smoke test (deferred — `bd polyglot-pdf-a7k`)

Left as-is on this PR. It still pins 2.5 and is flaky (~2/5 isolation runs return no
audio → `AssertionError: No audio response received`); it can't be repointed at the
new 3.1 default without sending the adapter's full config (the 1007 above). Reworking
it to drive the real adapter config against `get_settings().MODEL_NATIVE` (+ optional
retry) is filed as `a7k`. It's `external`/flaky and already out of the closeout gate
(`bnt`), so it doesn't block.

### Review triage (PR #41)

- **Copilot (1) — adopted.** No test pinned the *bare default* (only explicit-flag
  paths), so a future accidental flip back to 2.5 wouldn't be caught. Added
  `test_default_resolves_to_3_1_premium` (asserts `Settings(MODEL_NATIVE="")` →
  premium/3.1; skips if the env explicitly sets `USE_PREMIUM_MODEL`, since the field
  default is import-time-frozen).
- **Fresh-eyes (4):**
  - F1 (high) — adopted. `config.py:373` comment still said "2.5 is the current default
    (MODEL_NATIVE)" — false after the flip. Reworded: 2.5 is the pricing fallback for
    *unrecognized* names, NOT the runtime default (which is now 3.1).
  - F2 (med) — adopted. The smoke-test comment "the model we actually run" was now
    false; updated it to note 2.5 is no longer the default and point at `a7k` (the
    mechanical rework stays deferred; only the misleading comment was fixed here).
  - F3, F4 (low) — left as-is. Both confirmed correct/resolving (the INDEX
    `../planning_documents/archived/` link is intentional — that dir lives outside
    `docs/`; the two TECHNICAL_GUIDE copies are accurately described). Navigation/clarity
    observations, not bugs.
- Fresh-eyes correctly did **not** re-flag the deferred 3.1/2.5 smoke-test
  incompatibility (`a7k`), and read the worktree (not the stale main checkout) — no
  repeat of last sprint's false positive.

### Tests

Deterministic suite (`-m "not external"`): **165 passed, 2 skipped, 1 deselected**
(green, stable), including the model-selection + health unit tests after the
config-default flip (they pass `USE_PREMIUM_MODEL` explicitly, so the default change
doesn't perturb them). The one `external` live-Gemini test is excluded as above.

> **Process note:** the closeout checklist runs the FULL `backend/tests/`, which
> includes the flaky live-API test — so closeout can intermittently go red on an
> unrelated API hiccup. The deterministic gate should be `-m "not external"`. Filed as
> `bd polyglot-pdf-bnt`.

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

The `config.py` edit (3.1 default) touched a file tracked by several docs, so beyond
the archival doc edits I reconciled the model-default claims and bumped stamps:

- `docs/standards/ai-models.md` — **content updated** (tier-table default → 3.1,
  `USE_PREMIUM_MODEL` default `true`, why-3.1 note) + stamp → 2026-06-01.
- `docs/technical_guide.md` — **content fix** (line 29 `USE_PREMIUM_MODEL` default was
  `false`, now `true`) + stamp → 2026-06-01.
- `docs/components/config-deployment.md` — `USE_PREMIUM_MODEL` default cell → `true`;
  ENV_VARIABLES pointer repathed to `archive/`. (Stamp already 2026-06-01.)
- `docs/standards/logging-and-cost.md` — **review-and-bump** (tracks `config.py`; the
  model-default flip doesn't change logging/cost mechanics) → stamp 2026-06-01.
- `docs/INDEX.md` — added the Archive section (no Tracks line; not freshness-checked).
- Archived docs carry pointer headers but are history-only (not freshness-tracked).
- Still STALE, **left as-is** — track files this branch did NOT touch (`live_ai_gemini.py`
  / schema-forms TS, stale from the merged p1t fix), not this branch's concern:
  `schema-forms.md`, `voice-ai.md`, `voice-and-vad.md`.
- The freshness checker now reads correctly from the **main** repo too — the maintainer
  brought that checkout onto current `dev` (it had been 102 commits behind on
  `pitch/working-draft`), which had been causing "docs/ empty" false reads and fed a
  fresh-eyes false positive last sprint. See [[worktree-branch-off-dev-not-default]].

## Files touched

- `docs/archive/{PROJECT_CONTEXT,TECHNICAL_GUIDE,AUTH_AND_PROFILES_PLAN,ENV_VARIABLES}.md` — moved + pointer headers.
- `docs/archive/releases/*` (7 files moved) + `docs/archive/releases/README.md` (new).
- `planning_documents/archived/README.md` — new (supersede note + audit).
- `docs/INDEX.md` — new Archive section.
- `backend/config.py` — `USE_PREMIUM_MODEL` default `false` → `true` (3.1 default) + tier comments.
- `docs/standards/ai-models.md` — tier-table default → 3.1, flag default, why-3.1 note + stamp.
- `docs/technical_guide.md` — `USE_PREMIUM_MODEL` default cell fixed + stamp.
- `docs/standards/logging-and-cost.md` — stamp bump (review-only).
- `docs/components/config-deployment.md` — `USE_PREMIUM_MODEL` default cell + ENV_VARIABLES pointer repathed.
- `docs/journal/entries/2026-06-01-bd-4p0-archive-canonical-stale-docs.md` — this entry.
