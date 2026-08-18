# Documentation architecture: progressive discovery

*Last updated: 2026-08-18 (bd polyglot-pdf-lmcgz: the tier-2 row and the
`**Tracks:**` section now name `docs/doctrine/*.md` alongside components and
standards, matching `scripts/check_doc_freshness.py`'s DOC_DIRS and this
file's own line naming the scanned set elsewhere. Also current: the
current-state-only section's claim about the mechanical checker's regex
coverage -- it now catches `Prior:`/`Earlier:` too, not just `Previously:`
(bd polyglot-pdf-6dn2n).) This file documents the doc SYSTEM (current
state). It is a meta-doc about that system, not a doc about the product: it
sits outside the three product tiers below, is reached on demand via
[`INDEX.md`](INDEX.md), and carries no `**Tracks:**` line because it owns no
code path.*

This project organizes its docs for **progressive discovery**: a small always-loaded core points at on-demand docs, so an agent (or human) loads only what the task needs and context stays lean. This file explains the system and the discipline that keeps it from rotting. It is the most transferable artifact in the claude-swarm-kit -- the structure below works for any codebase.

## The three tiers

| Tier | What | Loaded |
|------|------|--------|
| **1 -- Always loaded** | `CLAUDE.md` (top-level rules + doc map) and `docs/INDEX.md` (the canonical map). | Auto, every session. Keep these LEAN -- they point, they don't duplicate. |
| **2 -- Easily reached** | `docs/components/<surface>.md` (one per user-facing surface or subsystem), `docs/standards/*.md` (cross-cutting rules: testing, security, performance, conventions, review), `docs/doctrine/*.md` (process/workflow rules: planning, review-flow, promotion tiers), `docs/technical_guide.md` (system-wide routes/endpoints/gotchas), and the **active sprint plans** `docs/sprint_<N>_<slug>_plan.md` (each sprint's maintainer-approved scope-of-record). | On demand, when that surface or concern is in scope. A "trigger read" in CLAUDE.md tells the agent when. Reach a plan via the "Active sprint plans" row in [`INDEX.md`](INDEX.md) or the owning epic's `plan:` metadata. |
| **3 -- Indexed / historical** | `docs/journal/entries/*.md` (one file per sprint/bead, YAML-frontmatter tagged), `docs/journal/TAGS.md` (the controlled tag vocabulary = the per-feature index), `docs/archive/` (completed plans). | On demand, when investigating "why was this built this way?" or "when did X change?" |

**The key move:** tier 1 stays small and stable; everything else is reached only when relevant. The agent never loads the whole corpus -- it loads CLAUDE.md + INDEX.md, then follows pointers. This is what keeps a large doc set from bloating every session's context.

## The discipline that prevents rot

Without active defense, tier-2/tier-3 docs drift out of sync with the code and become misleading. Four mechanisms keep them honest:

### 1. `**Tracks:**` lines map docs to code

Every `docs/components/*.md`, `docs/standards/*.md`, and `docs/doctrine/*.md` may declare, near the top, a line like:

```
**Tracks:** `src/auth/**/*.py`, `src/routes/login.py`
```

This is the doc's ownership claim: "I describe the current state of these code paths." `scripts/check_doc_freshness.py` parses these globs. Don't remove the line; widen the glob if the doc grows to cover more, narrow it if it shrinks.

### 2. Freshness stamps + the checker

Every tier-1/tier-2 doc carries a one-line stamp:

```
*Last updated: YYYY-MM-DD. See [docs/journal/entries/YYYY-MM-DD-bd-<code>-<slug>.md](...) for closeout details.*
```

`scripts/check_doc_freshness.py` compares each doc's stamp (treated as end-of-day UTC) against the `git log -1` commit time of every file its `**Tracks:**` globs cover. If tracked code is newer than the stamp, the doc is flagged STALE -- a signal to review and re-stamp (or confirm it's still accurate). Stamp with **today's UTC date** (`date -u +%F`); a local date in a UTC-ahead-of-local evening lags UTC and self-flags.

The checker is **warn-only** as a pre-commit hook and a **CI gate** via `tests/test_doc_freshness.py`. Wire the hook in your project (see the kit README).

### 3. Current-state-only rule

Tier-1 and tier-2 docs describe CURRENT STATE ONLY:
- No `Previously: <date>` chains on stamps -- and no synonym chains either
  (`Prior:`, `Earlier:`, stacked prior-update summaries). The stamp is ONE
  line; the mechanical checker's regex catches the `Previously:`/`Prior:`/
  `Earlier:` spellings (plus their `,`-separated variants) followed by a
  date, `Sprint NN`, "same day/week", or a bead-id reference, but the rule
  covers the pattern, not the keyword set -- a synonym chain not yet in the
  regex is still a violation to file (bd polyglot-pdf-6dn2n/riffn widened
  the regex from `Previously:`-only after finding four docs whose
  `Prior,`/`Earlier,`/`Earlier:` chains had passed it silently).
- No `## Update history` / `## Recent sprint history` / `## Changelog` sections.
- No "Sprint NN did X" narrative threaded through body prose.

Chronological history lives in the **journal** (tier 3), which is append-only at the corpus level (write a new entry file; never edit an old one). The checker's regexes (`PREVIOUSLY_CHAIN_RE`, `HISTORY_HEADING_RE`) flag violations; the CI test fails on them. **Prune-on-bump:** when you update a stamp, replace the old content, don't append.

**Sprint plans are exempt from this rule.** A `docs/sprint_<N>_<slug>_plan.md` is a tier-2 doc (reachable on demand) but a **chronological plan of record** -- it legitimately sequences a sprint (R1 -> R2 -> R3 ...) and records A/B notes. So the current-state-only convention does NOT apply to plans, and `check_doc_freshness.py` deliberately does not convention-scan them (they sit outside the scanned set: `TIER1_DOCS` + `docs/components/*` + `docs/standards/*` + `docs/doctrine/*`). Plans are intentionally **not tier-1 (not always-loaded)**: with several sprints in flight in parallel, a session loads only the plan its bead traces to, not all of them.

### 4. Trigger reads bake review into the work

CLAUDE.md lists "before changing code in surface X, read `docs/components/X.md`" rules. This makes doc-review part of the work cadence, so it doesn't depend on a separate "doc gardening" pass. If the doc is wrong, fix the doc FIRST as a separate commit.

## The journal (tier 3) in detail

Each sprint/bead produces one file: `docs/journal/entries/YYYY-MM-DD-bd-<code>-<slug>.md` with YAML frontmatter (`date`, `bead`, `title`, `tags` required; `sprint`, `pr` optional) and five body sections: **Trigger / What shipped / Lessons / Doc freshness / Files touched**. `scripts/journal_scaffold.py` emits the skeleton; the agent fills the prose. Tags come verbatim from `docs/journal/TAGS.md` -- adding a tag is a deliberate edit to that file, never an ad-hoc invention. The tag set IS the per-feature index: "every entry touching billing" = `grep -l 'billing' docs/journal/entries/*.md`.

When a journal lesson **generalizes** (applies anywhere), promote a one-liner up to the relevant `docs/standards/*.md` (and, if it bites repeatedly, to CLAUDE.md's "scar tissue" list), citing the entry.

## Setting this up in a new project

1. Keep the directory skeleton this template ships: `docs/INDEX.md`, `docs/components/`, `docs/standards/`, `docs/journal/entries/`, `docs/journal/TAGS.md`, `docs/archive/`, `docs/technical_guide.md`.
2. Give each component/standard doc a `**Tracks:**` line and a `*Last updated:*` stamp.
3. List your tier-1 docs in `scripts/check_doc_freshness.py`'s `TIER1_DOCS`.
4. Wire `check_doc_freshness.py` as a pre-commit hook + run `tests/test_doc_freshness.py` in CI.
5. Use `/closeout` -- it runs the checker and scaffolds the journal entry every sprint, so the discipline is automatic, not aspirational.
