# Sprint 1 — Harness tuning: reduce token burn, increase bounded autonomy

*Active sprint plan. Lives at `docs/` root while active; archived to `docs/archive/`
at sprint closeout (see [`doc-architecture.md`](../doc-architecture.md) §sprint-archive).
This is the maintainer-approved plan of record for this sprint — per the
plan-traceability goal (R3 below), every bead in this sprint should trace back to a
section here. Owning epic: `polyglot-pdf-hrn` (harness near-term);
roadmap epic: `polyglot-pdf-h2r`.*

> **Note on tier-1 status.** The longer-term goal (R3) is to make the active sprint
> plan a formally always-loaded tier-1 doc so every orchestrator shares current scope.
> That doctrine change (adding sprint plans to `TIER1_DOCS` + the doc-architecture
> rules) is itself a bead under R3. Until it lands, this plan is reached via the
> "Active sprint plans" row in [`INDEX.md`](../INDEX.md).

---

## Context

A fresh-eyes review of the agentic coding harness (beads + closeout +
fresh-eyes/Copilot review loop + deterministic scripts) targeting three goals:
**reduce token burn**, **reduce babysitting**, and a **roadmap** toward bounded
autonomy. This plan is advisory + experimental-design + roadmap. All changes are to
`.claude/`, `scripts/`, and `docs/` — **no product code.**

### The north-star flow (the organizing principle everything serves)

The orchestrator does the **grunt work of implementing the maintainer's choices** — it
never *owns* the project:

> Maintainer creates a plan → AI breaks the plan into beads → AI completes beads,
> **spawning new beads** when a bead's scope suggests splitting, when bugs arise,
> when nits are suggested, or **when worthwhile work runs beyond a bead's scope**
> (file a bead rather than ask or silently expand — *unless* the out-of-scope item
> is itself a decision the maintainer must make, which escalates instead) → AI
> **reports the choices it
> made** → AI **auto-records scar-tissue** for minor gotchas → AI **escalates the
> calls that are genuinely the owner's** (a product/direction/scope call; a
> **longer-term commitment the bead doesn't call for** — a new contract, a new
> operational/cost/security dependency, a broken documented invariant, or an
> architectural change *bigger than the small obvious one serving the bead*; an
> ambiguous/untenable bead) → when a plan is **complete or proves untenable, AI
> stops and pings** the maintainer for new instructions.

The human gate moves from "merge to `dev`" up to **merge to `main` + regular audit
reports**. Autonomy is for *implementing the maintainer's plan and addressing
bugs/nits* — including the implementation and small bead-serving architecture
decisions, which are the orchestrator's. It is **never** for inventing features,
making product/direction judgment calls, or longer-term commitments a bead doesn't
authorize. The full rule (the 3-step decision procedure, the NEVER list, and the
defended-decision merge report) is the **Escalation vs. autonomy** section of
[`CLAUDE.md`](../../CLAUDE.md) (`polyglot-pdf-hrn.11`).

### What the review found (the system is already good — don't regress these)

> **Note (post-sprint):** `copilot_watch.py` was later renamed to
> `pr_review_watcher.py` and generalized to `--reviewer copilot|codex`
> (bd `polyglot-pdf-hrn.10`). This plan's prose keeps the original name as the
> point-in-time record; the live script is `scripts/pr_review_watcher.py`.

- **Mechanical work is deterministic / zero-token** (`bd_safe.py`,
  `closeout_housekeeping.py`, `check_doc_freshness.py`, `journal_scaffold.py`,
  `copilot_watch.py`). Tokens are spent only on judgment.
- **`copilot_watch.py` is the model win to replicate** — it turned a
  3–10 poll-turns-per-round loop into one background wakeup with a pre-classified
  verdict and distinct exit codes.
- **Round-1 review is parallel** (Copilot on PR-open ‖ fresh-eyes Sonnet subagent);
  the no-draft rule structurally prevents a redundant second Copilot review.
- **Beads is a real, collision-safe system-of-record** with pull/push bracketing.

### Constraints verified against Claude Code docs

- Subagent `model:` accepts `haiku|sonnet|opus|<full-id>|inherit` (default `inherit`).
  `CLAUDE_CODE_SUBAGENT_MODEL` is a highest-precedence session-wide override — the
  **A/B control arm**. ([model-config](https://code.claude.com/docs/en/model-config))
- **PreCompact fires near context-fill and already runs a script** (`bd_prime.py`)
  with **zero extra model turns** — this is the handover trigger, no transcript-watching
  needed. ([hooks](https://code.claude.com/docs/en/hooks))
- **`Stop` hook can gate end-of-response** — the lever for "finish bead, then cease."
- **Background tasks DO re-invoke this harness on completion** (why `copilot_watch.py`
  works). We keep that pattern.
- **No native per-turn token telemetry in hooks** — cost data lives in the transcript
  JSONL (`~/.claude/projects/<uuid>/*.jsonl`); a script must parse it.
- **No built-in "retire orchestrator → spawn successor" pattern** — but "retire" =
  *finish cleanly and stop* is trivial (just don't claim another bead). Spawning the
  successor is the only scripted-later piece.

---

## Ranked opportunities

Vectors: **Cost / Err(or-reduction) / Indep(endence) / Speed**. ★ strong, ☆ mild.

| # | Change | Cost | Err | Indep | Speed | Effort | Risk |
|---|--------|:----:|:---:|:-----:|:-----:|:------:|:----:|
| 1 | **Harness cost telemetry** (parse transcript → per-bead ledger + experiment counter) | ★ (enables all) | ☆ | ☆ | · | low | very low |
| 2 | **Diff-size fresh-eyes tiering + Haiku self-escalation** | ★ | ☆ | · | ☆ | low | low |
| 3 | **Orchestrator-judged bounded Copilot loop** (defer nits to beads, ambiguous=blocker) | ★ | ☆ | ★ | ★ | low | low–med |
| 4 | **`closeout_prep.py`** — collapse closeout steps 0/1/2/4 into one script → structured TODO | ★ | ☆ | ☆ | ★ | med | low |
| 5 | **File/function risk-rating discipline** (doc high/med/low; feeds #2's cheap model) | · | ★ | · | ☆ | med | low |
| 5b | **Autonomous merge-conflict resolution** (resolve mechanical inline; escalate only structural) | · | ☆ | ★ | ★ | low | med |
| 6 | **`/next-bead` + change-surfaces field** — candidates + **hard write-overlap block** | · | ★ | ★ | ★ | med | med |
| 7 | **PreCompact-triggered clean drain/handover** (finish bead → closeout → stop) | ☆ | ☆ | ★★ | · | med | med |
| 8 | **Sprint-plan-as-tier-1-doc + escalation-by-traceability** (prereq for real autonomy) | · | ★ | ★★ | · | med | med |
| 9 | **Guarded auto-merge to `dev`** + audit reports (human gate → `main`) | · | ✗-risk | ★★ | ★ | med | high |

**Near-term (this sprint): #1, #2, #3** (+ #4, #5, #5b fold in as supporting work).
**Roadmap: #6 → #7 → #8 → #9**, gated on #1's numbers. Successor-spawn for #7 is left
**conceptual** — goals only: maximize autonomy, work-vs-burn efficiency, hard bounds
against runaway; leaning bounded-pool/budget; the 5-hour quota is the existing backstop.

---

## Near-term proposal (build this sprint)

### Change #1 — Harness telemetry + experiment counter (`scripts/harness_ledger.py`)

Deterministic, zero-token script that parses the session transcript JSONL and appends
a per-session row to `docs/journal/harness_ledger.jsonl`. Each row records:
- **tokens** — input/output, split by phase (review / triage / fix) and by actor
  (**orchestrator vs subagent**, so you see *where* an arm actually saves);
- **time** — wall-clock PR-open → CLEAN;
- **Copilot rounds/PR**;
- **maintainer touchpoints/closeout** (the thing we're trying to reduce);
- **deferred-nit count/closeout** (denominator for the nit-turned-blocker rate);
- **Haiku-escalation events** (diagnostic, NOT failure — how tightly diff-length and
  true severity overlap, for later threshold tuning);
- **errors-shipped** (see audit below);
- a **`cost_category`** tag per row: `production` vs `audit/overhead`. **Fairness
  rule:** measurement/cross-arm bug-reporting work is bucketed `audit`, **never charged
  to the arm doing it** — else the experiment penalizes whichever arm runs when an old
  bug surfaces.

**Bead provenance + nit-turned-blocker audit.** Every spawned bead is tagged with the
**arm that generated it** (`A`/`B`/`C`/`BC`). A bead labeled a **nit** that later proves
a **blocking bug** is reported to the tracker and **counted against the arm that
deferred it** — a measurable failure rate, not anecdote. (Pre-production, low stakes:
recorded number, not a kill-switch.)

**Experiment-state counter** (`.beads/experiment_state.json`): `baseline_A`, `arm_B`,
`arm_C`, `arm_BC` counts + phase. The bead-picker / closeout prints the directive:
- `baseline_A <= 15` → "Phase A: run as-is, just measure."
- `> 15` → "Phase A done — start B/C toggling."
- `arm_B > 10 and arm_C > 10` → "Independent arms done — report; if both adopted, run BC."
- `arm_BC > 10` → "Combined arm done — final report."

**Files:** new `scripts/harness_ledger.py`; closeout Step 7 documents the telemetry row
(written by `closeout_finish.py` in Step 6); allowlist entry;
fixture-based unit test (like `tests/test_doc_freshness.py`).

### Change #2 — Diff-size tiering + Haiku self-escalation

- **Routing is purely mechanical:** `scripts/pick_review_model.py` reads
  `git diff --shortstat origin/dev...HEAD` → prints `haiku` for small diffs (≤ ~80
  changed lines), `sonnet` otherwise. **No risk judgment in the script** (that would
  force an extra expensive orchestrator turn on small diffs).
- **Fresh-eyes prompt gains a self-escalation clause:** when running as Haiku, if the
  change touches a function/class **imported elsewhere**, spans **multiple surfaces**,
  or touches **Gemini / `google-genai` wiring**, it **stops and recommends a Sonnet
  re-review** rather than rendering a verdict. The judgment happens inside a turn that
  was going to happen anyway, by the cheap model.

**Files:** new `scripts/pick_review_model.py` (+ unit test); edit fresh-eyes agent
prompt; edit Step 6.3 of `SKILL.md`; allowlist entry.

### Change #3 — Orchestrator-judged bounded Copilot loop

`copilot_watch.py` keeps doing only what it's good at — detect terminal state and
**extract comment bodies**. The **orchestrator** judges (a script can't reliably tell a
nit from a blocker):
- **Address-and-loop** on anything that is — or *might be* — a blocker. **Ambiguous =
  blocker** (safe default).
- **File remaining true nits as one follow-up bead and proceed to closeout.** These
  deferred-nit beads are **prime candidates for a later multi-bead cleanup PR**.
- **Hard ceiling** (e.g. 3 loops) → escalate to maintainer rather than loop forever.
  (SUPERSEDED 2026-07-04, bd `polyglot-pdf-16pj`: the hard round ceiling is retired
  in favor of an outcome-based loop-stop — loop while findings are correct blockers,
  stop when they are incorrect or nit-file-able. See
  [`review-flow.md`](../doctrine/review-flow.md) + the closeout skill.)

So #3 is **decision-rule prose in the skill** + the deferred-nit bead convention, not a
new classifier script.

**Files:** edit Step 7 of `SKILL.md`; document the deferred-nit → cleanup-PR convention;
loop-ceiling constant.

### Supporting work that folds in

- **#4 `closeout_prep.py`** — collapse closeout Steps 0/1/2/4 (preconditions, beads
  housekeeping, doc-freshness, tests) into **one script run** returning a single
  structured TODO. Build alongside #1 (both pure scripting).
- **#5 file/function risk-rating discipline** — tag files (and key functions)
  **high/med/low risk**, especially anything exporting to other files, core functions,
  and **all `google-genai`-touching code**. Static signal Haiku leans on in #2's
  self-escalation. Seed from the `RISKY_GLOBS` intuition (`live_ai_gemini.py`,
  `websocket_routes.py`, `pdf_fill_routes.py`).
- **#5b autonomous merge-conflict resolution** — when the closeout loop finds the merge
  conflict-blocked, the orchestrator **resolves mechanical/ordering conflicts inline**
  (journal/doc ordering, changelog interleaving) and **escalates only on genuine
  structural incompatibility**. Added as a Step-7 loop step with that explicit boundary.

---

## A/B testing strategy (parallel independent arms, then a combined arm)

**Unit = one closeout (one PR).** ~10–15 closeouts/day, so this runs in days.

- **Phase A (baseline):** land #1 (+#4, #5) only; run as-is until `baseline_A > 15`.
- **Phase B/C (parallel, independent vs A):** toggle **B = fresh-eyes tiering** and
  **C = bounded loop** independently. Controls: `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`
  forces B-off; `CLOSEOUT_LOOP_MODE=zero|blockers` forces C-off. Counter alternates
  until `arm_B > 10 and arm_C > 10`, then reports.
- **Phase BC (combined — confirm, don't assume):** **if both B and C are adopted**, run
  a combined arm (>10) and measure efficiency + error rate vs A.
- **Adoption rule:** adopt either/both of B/C that beat A on cost/speed/touchpoints
  **without** a worse error-shipped rate; the combined arm validates B+C > A.

**Guardrail metric — record and report, do NOT abort.** The error-shipped rate is a
*tracked number per arm*, not a kill-switch (can't be known until after a session ends;
pre-production; data-gathering is the point). Haiku-escalation frequency is tracked the
same way — diagnostic, not failure.

**Metrics (all from #1's ledger):** tokens/closeout (per phase AND
orchestrator-vs-subagent); wall-clock PR-open→CLEAN; Copilot rounds/PR; **maintainer
touchpoints/closeout**; deferred-nit count; Haiku-escalation events; errors-shipped (by
arm); all bucketed by `cost_category`.

---

## Longer-term roadmap (sequenced; gated on #1's numbers)

**R1 — `/next-bead` self-selection + change-surface collision guard.** "Top ready bead"
is a **judgment call** (continue an epic vs. **bundle nits into one cleanup PR** vs.
avoid write-collisions). Two pieces:
- **Beads gain a "change-surfaces" field** — files the bead is expected to **modify**
  (e.g. `[gemini.py, VAD.js]`). **"Change," not "touch"** — reads don't collide, writes
  do. Stored as a **structured `bd` field** (via `--metadata` if the schema supports
  it; fall back to a parseable `Surfaces:` body line). Added at creation + the spawn
  convention.
- **`/next-bead` surfaces candidates + enforces a hard write-overlap block** —
  cross-references each ready bead's change-surfaces against active claims and
  **hard-blocks** any intersecting claim. **No orchestrator override** — two processes
  writing `websockets.py` is a conflict regardless of intent. The orchestrator judges
  the non-blocked candidates (epic-continuation vs nit-bundling).

Touches only *claiming*, never *merging* — safe first autonomy step. Complements the
existing same-bead claim collision-check.

**R2 — PreCompact-triggered clean drain / handover.** No watchdog, no transcript-burn:
PreCompact already fires near context-fill and runs a script. Extend `bd_prime.py` (or
a sibling hook) to set a **"drain" flag**; on seeing it the orchestrator finishes the
current bead, closes out, **writes any spawned beads + a handover note**, pings the
maintainer, and **stops** (claims no new bead). The successor's existing `bd prime`
SessionStart rehydrates from `bd ready` + the handover note. **Spawning the successor is
left unspecified** — conceptual goals only (maximize autonomy, work-vs-burn efficiency,
hard bounds against runaway; leaning bounded-pool/budget; 5-hour quota = backstop).
Revisit after A/B produces real token curves.

**R3 — Sprint-plan-as-tier-1-doc + escalation-by-traceability** (autonomy prerequisite).
Escalation rule = **plan-traceability**: every action must trace to a maintainer-approved
plan that spawned the beads; **if a decision isn't derivable from the plan, escalate.**
- **Promote the active sprint plan to a tier-1 always-loaded doc** (add to
  `TIER1_DOCS` + the doc-architecture rules) so every orchestrator shares current scope.
  Persist approved plans, link each to the beads it spawned.
- **Add an escalation checkpoint to the skill** — before any action not derivable from
  the linked plan, stop and ping. Makes "implement the maintainer's choices, never
  invent" mechanically enforceable. Must be solid before R4.

**R4 — Guarded auto-merge to `dev` + audit reports** (highest autonomy; do last). Move
the human gate to **merge-to-`main`**; require **regular auto-generated audit reports**
("what changed and why" per merged PR). Auto-merge to `dev` ONLY when: Copilot CLEAN,
fresh-eyes no high-confidence findings, no risky-rated files touched, tests green, bead
traces cleanly to its plan, below a size/priority threshold; **everything else still
pings.** Per-PR `allow_auto_merge` flip, never a blanket ruleset change. `dev`→`main`
stays forever-manual. Earn this only after R1–R3 + the A/B work show acceptably low
post-merge defect rate.

---

## Verification

- **#1 ledger / counter:** run against a known past session's transcript JSONL; eyeball
  vs `/usage`. Unit test on a fixture JSONL asserts parsed totals, `cost_category`
  bucketing, provenance tagging (A/B/C/BC), counter transitions (A→B/C→BC→report).
  Confirm it appends at closeout Step 7 (via `closeout_finish.py` in Step 6) without
  erroring on worktree/resumed-session transcript paths.
- **#4 `closeout_prep.py`:** run on the current branch; confirm its TODO matches the
  manual Steps 0/1/2/4 (same stale docs, orphans, test result).
- **#5b conflict resolution:** stage a synthetic mechanical conflict (reordered journal
  entries) → confirm inline resolution; stage a structural conflict → confirm escalation.
- **#2 router + escalation:** unit-test `pick_review_model.py` on synthetic shortstats;
  run one closeout per arm; confirm the spawned fresh-eyes used the chosen model (ledger
  subagent-model column) and that a cross-file Haiku-arm change triggers self-escalation.
- **#3 bounded loop:** run one closeout in `blockers` mode with a planted nit-only
  Copilot comment; confirm one deferred-nit bead is filed and the loop exits; confirm an
  ambiguous comment is treated as a blocker.
- **A/B:** at the report threshold, the ledger JSONL is the dataset — compute mean
  cost/speed/rounds per arm + list every deferred-nit bead for the guardrail audit. No
  arm adopted until its rule is met on real data.

All new scripts follow existing conventions: deterministic, distinct exit codes, read
config from `swarm.config.json`, resolve paths via the git-common-dir (worktree-safe),
added to the permissions allowlist.

---

## Bead tree

Two epics. Each child's `surfaces` metadata declares the files it will **modify** (the
R1 change-surfaces field, used early). The A/B arms and the whole roadmap are gated on
**#1 telemetry** (`hrn.1`) — `bd ready` surfaces #1 + the independent supporting work
first; #2/#3 and R1–R4 unblock once #1 lands.

**`polyglot-pdf-hrn` — Harness tuning (near-term)** [epic, P1]
- `hrn.1` — **#1** Harness cost telemetry + experiment counter (P1) — *ready; enables all A/B*
- `hrn.2` — **#4** `closeout_prep.py` one-shot structured TODO (P2) — *ready*
- `hrn.3` — **#5** File/function risk-rating discipline (P2) — *ready*
- `hrn.6` — **#5b** Autonomous merge-conflict resolution (P2) — *ready*
- `hrn.4` — **#2** Diff-size fresh-eyes tiering + Haiku self-escalation (P1, arm B) — *blocked by `hrn.1`*
- `hrn.5` — **#3** Orchestrator-judged bounded Copilot loop (P1, arm C) — *blocked by `hrn.1`*

**`polyglot-pdf-h2r` — Harness autonomy roadmap (R1–R4)** [epic, P2] — *all gated on `hrn.1`*
- `h2r.1` — **R1** `/next-bead` + change-surface collision guard (P2) — *blocked by `hrn.1`*
- `h2r.2` — **R2** PreCompact-triggered clean drain / handover (P3) — *blocked by `h2r.1`*
- `h2r.3` — **R3** Sprint-plan-as-tier-1-doc + escalation-by-traceability (P3) — *blocked by `h2r.1`*
- `h2r.4` — **R4** Guarded auto-merge to `dev` + audit reports (P4) — *blocked by `h2r.3`*

Resume work with `bd ready` / `bd show <id>`; this section is a snapshot, the tracker is
the source of truth.
