# Bead tiers -- routing work to the right model

**Tracks:** .claude/agents/ .claude/skills/next-bead/SKILL.md scripts/next_bead.py

*Last updated: 2026-08-05. See [../journal/entries/2026-08-05-bd-1bsx-bead-tier-routing.md](../journal/entries/2026-08-05-bd-1bsx-bead-tier-routing.md) for closeout details.*

Every bead carries two metadata keys saying **which model tier should pick it up**
and **what class of work it is**. They exist so a cheap session can query the
tracker for work sized to it -- batching a handful of documentation nits into one
Sonnet run instead of letting them interrupt an expensive session -- and so the
expensive sessions stay on the work only they can do.

This is the bead-level expression of the model-tiering rule in
[`../doctrine/planning.md`](../doctrine/planning.md#model-tiering): expensive models
at decision gates, never bug-hunting or grepping.

## The two keys

Both go in the bead's `metadata` JSON, alongside `surfaces`:

```bash
bd create --title="..." --description="..." --type=task \
  --metadata '{"surfaces":["docs/foo.md"],"tier":"haiku","work_class":"docs-nit"}'
```

> **`--metadata` REPLACES the entire object.** It does not merge. Writing
> `--metadata '{"tier":"haiku"}'` on a bead that already declared `surfaces`
> **wipes the collision guard**. Always pass every key in ONE object. (Same trap
> warned about in [`../../.claude/skills/next-bead/SKILL.md`](../../.claude/skills/next-bead/SKILL.md).)

## `tier` -- a CLOSED enum

**Exactly one of: `haiku` | `sonnet` | `opus` | `fable`.** Not free text. A value
outside this list breaks the batching query that drains the queue, which is worse
than no value at all -- the bead becomes invisible to the runner instead of
mis-sorted.

**This is not a difficulty ladder with `fable` on top.** Three of the four are a
capability ordering; `fable` is a **different job**.

| `tier` | The job | Typical work |
|--------|---------|--------------|
| `haiku` | Mechanical, fully specified, no judgment. | Renames across known files, deterministic script runs, doc typos, a stale cross-reference. |
| `sonnet` | **The default.** Execution and local correctness -- build the change, get the diff right. | Scoped beads, docs nits, comment/naming alignment, local bug fixes, the inner review pass. |
| `opus` | Judgment across surfaces, and delegation. Equally good at code as analysis -- **Opus writes code.** | Cross-surface work, the outer review, ambiguous fixes needing a design call. Opus **delegates non-cross-surface subtasks to Sonnet subagents** rather than doing them itself. |
| `fable` | **Long-horizon planning and delegation. Fable should NEVER write code.** | Epic scoping, multi-week decomposition, research-then-plan work, deciding *what* to build and in what order. If the deliverable is a plan or a decision -- not a diff -- it is `fable`. |

**The mistake this table prevents:** filing `fable` because a bead is *hard*. Hard
code is **`opus`**. A `fable` bead that hands back a diff was mis-tiered; a hard
cross-surface refactor filed as `fable` sits in the wrong queue and stalls.

**Quick disambiguation** -- ask *"what does done look like?"* A merged diff ->
`haiku`/`sonnet`/`opus` by blast radius. An approved plan, a decomposition, or a
research conclusion -> `fable`.

## `work_class` -- also a CLOSED enum

**One of: `docs-nit` | `comment-align` | `cross-surface` | `local-bug` |
`needs-plan` | `mechanical`.**

| `work_class` | Means | Usual `tier` |
|--------------|-------|--------------|
| `docs-nit` | Prose, a stale reference, a doc that disagrees with the code. | `haiku` / `sonnet` |
| `comment-align` | A comment, docstring, or name that no longer matches its code. | `sonnet` |
| `local-bug` | A defect contained to one surface. | `sonnet` |
| `cross-surface` | Touches contracts more than one surface depends on. | `opus` |
| `needs-plan` | Underspecified; the deliverable is a decision, not a diff. | `fable` |
| `mechanical` | Fully specified, no judgment required. | `haiku` |

**On `comment-align`: verify which side is wrong first.** If the CODE is wrong and
the comment described the intent correctly, it is a `local-bug`, not a
`comment-align` -- and it is a blocker, not a nit. (See the nit-vs-blocker rule in
[`../doctrine/review-flow.md`](../doctrine/review-flow.md): "a comment that
contradicts its code is NOT a nit -- it is evidence the CODE is wrong.")

The pairings above are the common case, not a constraint. A `docs-nit` spanning
twelve files with contradictory claims can be `sonnet`; a `cross-surface` bead whose
fix is one obvious line can be `sonnet` too. Tier by the **judgment required**, not
by the label.

## Draining the queue

`bd list` filters on metadata natively -- no `jq` needed:

```bash
bd list --metadata-field tier=sonnet --metadata-field work_class=docs-nit --status=open
```

`--metadata-field key=value` is repeatable (AND semantics). Related:
`--has-metadata-key tier` finds beads carrying the key at all -- useful for spotting
untagged beads -- and `--json` emits full metadata for scripting.

**The batch pattern this enables:** a cheap session claims 4-5 `docs-nit` beads,
fixes them together, and ships them as ONE PR through a single closeout. That is
explicitly allowed -- the bead/PR contract in
[`../../CLAUDE.md`](../../CLAUDE.md) permits a PR to bundle several whole beads when
each is too small to warrant its own cycle. Docs-only PRs get the cheap adversarial
review (see the three-way gate in [`../doctrine/review-flow.md`](../doctrine/review-flow.md)),
so the whole loop stays cheap.

## Escalation: release WITH NOTES, and bump the tier

An agent that claims a bead and finds it **above its tier** -- a "minor docs update"
that turns out to unravel a real contract, a single-surface fix with cross-surface
consequences -- should **stop, not grind**.

1. Write what you found and why it is above tier into the bead (`bd update <id>
   --notes "..."`).
2. **Bump `tier`** to the right level (remember: full metadata object).
3. Release the claim so the right tier can pick it up.

**A bare unclaim is not enough** -- with the tier unchanged, the next same-tier
runner simply re-claims it and hits the same wall. The note is what stops the
ping-pong.

## De-escalation is NOT a release

An agent that finds a bead **below** its tier should **just do it**, or delegate it
to a cheap subagent. Do not release it, do not re-tier it, do not write a
calibration note.

The reason is sunk cost: by the time you know the bead is easy, you have already
loaded its context. Releasing it throws that away and makes a cheaper session
re-derive it -- which usually costs more than just finishing. Administration that
outweighs the saving is not a saving.

## Reclassification to epic scale must be LOUD

If work uncovers something genuinely epic-scale -- needing major rewrites, new
features, or a research plan rather than a fix -- re-tier it to `fable`, and:

- **Do not halt** if the finding is non-blocking; finish what you can.
- **Do return it to your orchestrator**, which **MUST surface it emphatically in its
  end-of-session summary** -- as its own flagged item, never buried in the defended-
  decision list.

This is the one reclassification the maintainer always wants to hear about. It maps
onto the existing step-2 escalation trigger in
[`../../CLAUDE.md`](../../CLAUDE.md) ("proves the bead's original direction
impossible"); the tier bump is the tracker's record of it, not a substitute for
telling someone.

## Who sets these

- **At creation** -- `/plan-epic`, `/next-bead`, and any `bd create` (including the
  ones the review agents run when filing findings) set both keys.
- **Reviewers** -- [`fresh-eyes-reviewer`](../../.claude/agents/fresh-eyes-reviewer.md),
  [`cross-surface-reviewer`](../../.claude/agents/cross-surface-reviewer.md), and
  [`docs-reviewer`](../../.claude/agents/docs-reviewer.md) all file pre-existing and
  out-of-scope findings as beads, and set the tier on what they file.
- **Retrofit is not required.** Beads created before 2026-08-05 have no `tier`; they
  are not broken, just invisible to the batching query. Tag them when touched.
