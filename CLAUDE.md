# CLAUDE.md -- <PROJECT NAME>

**Project-specific instructions for AI assistants. Read this before making any changes.**

> This file is the tier-1, always-loaded doc. Keep it lean: it should point at
> the on-demand docs (tier 2 + 3), not duplicate them. See
> [`docs/INDEX.md`](docs/INDEX.md) for the canonical doc map and
> [`docs/doc-architecture.md`](docs/doc-architecture.md) for the progressive-
> discovery system this file sits at the top of.

---

## What this is

<One paragraph: what the product does, the stack, the entry point. Replace this.>

---

## Doc map (read these on demand)

This file (CLAUDE.md) is auto-loaded every session. Everything else is on-demand.
**Always start by reading [`docs/INDEX.md`](docs/INDEX.md)** -- it's the canonical map.

| Tier | Where | Load when |
|------|-------|-----------|
| **1 -- Always loaded** | This file + [`docs/INDEX.md`](docs/INDEX.md) | Auto |
| **2 -- Easily reached** | [`docs/components/<surface>.md`](docs/components/) (per surface) + [`docs/standards/*.md`](docs/standards/) (cross-cutting rules) + [`docs/technical_guide.md`](docs/technical_guide.md) | When that surface or concern is in scope |
| **3 -- Indexed / on-demand** | [`docs/journal/entries/`](docs/journal/entries/) (per-file, frontmatter-tagged) + [`docs/journal/TAGS.md`](docs/journal/TAGS.md) | When investigating "why was this built this way?" |

**Trigger reads:** Before changing code in a surface, read the matching
`docs/components/<surface>.md`. If the doc is wrong, fix the doc first as a
separate commit. (Add your own surface-specific trigger reads here.)

---

## Top scar tissue (always-relevant lessons)

<Numbered list of the lessons that have been re-learned more than once. Each
cites a journal entry for incident detail. Start small; grow as you learn.
The claude-swarm-kit ships a starter set in docs/standards/ and docs/doctrine/
-- promote the ones that bite repeatedly up to here.>

1. **Beads is the system of record for "what to do next."** Resume work via
   `bd ready` / `bd show <id>`, not by reading a plan file. Pull before reads,
   push after every write. See [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).
2. **Every PR goes feature-branch -> fresh-eyes review (parallel with Copilot)
   -> normal PR -> maintainer merges.** No draft PRs. See
   [`docs/doctrine/review-flow.md`](docs/doctrine/review-flow.md).
3. **In a worktree, run every git command via `git -C <worktree-path>`** --
   the shell cwd resets between tool calls; a chained `cd <main-repo> && git ...`
   silently operates on the main checkout.

---

## Critical rules

<The rules that override default behavior. The kit's doctrine docs supply a
starter set for beads, review flow, promotion tiers, and doc maintenance --
copy the load-bearing ones up here and add your product-specific ones.>

### Task tracking
- Beads (`bd`) is the canonical tracker. Pull-before-read, push-after-write.
  Full cadence: [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).

### Deployment / promotion
- feature branch -> `dev` (staging) -> `main` (prod). Details:
  [`docs/doctrine/promotion-tiers.md`](docs/doctrine/promotion-tiers.md).

### Doc maintenance
- Tier-1 and tier-2 docs are CURRENT STATE ONLY -- no `Previously:` chains, no
  history sections. The journal is the chronological record. Mechanically
  enforced by `scripts/check_doc_freshness.py`. Full rules:
  [`docs/doc-architecture.md`](docs/doc-architecture.md).

---

## Sprint closeout

Run the `/closeout` skill at the end of every bead. It encodes the checklist:
beads housekeeping, doc-freshness, journal entry, tests, then a normal PR with
parallel Copilot + fresh-eyes review, looped to clean, then ping to merge. See
[`.claude/skills/closeout/SKILL.md`](.claude/skills/closeout/SKILL.md).
