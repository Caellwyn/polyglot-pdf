# Review-flow doctrine: pre-PR adversarial assess + ONE outer review (Opus for source, Haiku for docs), looped to clean

*Last updated: 2026-08-18 (bd polyglot-pdf-riffn: pruned a stamp chain -- no
content change; the full rationale for the current shape lives in "Why each
choice" below. Current state: the outer review is a THREE-way fork (bd
`polyglot-pdf-saxh`) -- a source diff gets the ONE Opus cross-surface pass, a
docs-only diff gets ONE adversarial Haiku review (`docs-reviewer`), and only a
genuinely trivial diff skips adversarial review. The inner fresh-eyes loop
scores the rubric, gets the local diff right, and ENUMERATES every changed
contract; the outer pass takes that enumeration and follows each contract OUT
into consumers in untouched files -- the hard-gated mandate that caught bd
`polyglot-pdf-bo4m`. External model reviewers remain retired: the
maintainer's Codex (OpenAI) subscription ended 2026-07-08 and the repo uses
NO external reviewer.)*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

Review is **two layers, both Claude, BOTH run BEFORE the PR opens, and they have
DIFFERENT JOBS** (flow change 2026-07-08; layers differentiated 2026-08-05): an
**inner** adversarial fresh-eyes loop (Sonnet/Haiku) that scores the local diff
against the bead's exit-criteria rubric, hunts in-diff bugs, and **enumerates every
changed contract**; then ONE **outer** adversarial pass on the same local branch.
**Which outer reviewer runs depends on the diff type** (the three-way gate, bd
`polyglot-pdf-saxh`): a **source** diff gets the Opus-5 `cross-surface-reviewer`,
which takes that enumeration and **follows each contract out into consumers in files
the diff never touched**; a **docs-only** diff gets the Haiku `docs-reviewer`, an
adversarial *prose* review (claims vs. the code they document, stale refs,
doc-vs-doc conflict) since there is no runtime contract to trace; only a genuinely
**trivial** diff gets no outer pass. Fresh-eyes is the gap-exhaustion assessor for
the local diff; the outer pass is the independent adversarial backstop (a fresh
subagent, no shared context). There is NO external reviewer. The PR
opens only AFTER both loops clear -- so opening the PR, closing the bead(s), and the
merge decision are the final steps, not a review surface.

**The split is the point.** Before 2026-08-05 both layers ran the SAME prompt, so
the expensive model re-hunted local bugs the cheap loop had already cleared -- three
serial Opus passes minimum, each re-run on every fix. Now the cheap tier owns local
correctness and the expensive tier owns the one job it alone can do: interaction
bugs the diff cannot show.

## The flow

```
clean tree
  -> score the exit-criteria rubric       [orchestrator: PASS/FAIL each criterion + evidence; any FAIL -> fix]
  -> INNER LOOP -- GET THE LOCAL DIFF RIGHT:   [ALWAYS, review-worthy or not; haiku/sonnet by diff size]
       spawn fresh-eyes (criteria passed in, ADVERSARIAL): score the rubric, hunt
         in-diff bugs, and ENUMERATE every changed contract (do NOT trace them out)
         -> fix gaps / file pre-existing + non-blocking as beads -> re-spawn
       ... until NO-GAPS (loop while gaps are correct blockers; no round cap)
       -> that verdict is TERMINAL at the routed model; no Opus round here
  -> judge the diff TYPE                  [orchestrator: source / docs-only / trivial -- a THREE-way fork]
  -> OUTER LOOP -- ONE adversarial pass, model by diff type, on the LOCAL branch:
       SOURCE diff -> cross-surface-reviewer (model: opus), handed the inner loop's
         `## Changed contracts` list: trace each contract into its consumers in
         UNTOUCHED files; may not clear without naming them
       DOCS-ONLY diff -> docs-reviewer (model: haiku): adversarial PROSE review --
         claims vs the code they document, stale refs, doc-vs-doc conflict,
         date-bump-without-review. No contract trace (nothing changed to trace).
       TRIVIAL diff -> no adversarial pass; the inner NO-GAPS is the record.
         -> fix -> re-spawn ... until NO-GAPS (loop while findings are correct blockers)
       -> ONE NO-GAPS = the adversarial clear. Only a BEHAVIORAL fix voids it.
  -> open a NORMAL (non-draft) PR + close the bead(s)   [one closeout_finish.py run; scorecard in the PR BODY; no external-reviewer trigger]
  -> CI re-runs the test suite                [a cheap triple-check -- NOT a warrant for a thinner LLM gate]
  -> merge decision: [auto-merge if routine/low-risk & clean | else ping the maintainer]
```

The final gate is the **merge decision** (autonomy increase 2026-07-04, bd
`polyglot-pdf-16pj`): once review is CLEAN (both pre-PR loops cleared) and checks are
green, a PR that is NOT consequence-bearing is **merged autonomously**
(`gh pr merge`); a consequence-bearing PR (affects operational cost / user-facing
features / downstream disruption / an approved plan / needs substantial
multi-surface rework) is **pinged to the maintainer**. Same line as the step-2
escalation triggers; when unsure, ping. A **docs-only** change runs the inner
fresh-eyes loop plus ONE adversarial **Haiku** review (`docs-reviewer`) rather than
the Opus cross-surface loop; a **trivial** change gets no adversarial pass at all
and the last fresh-eyes `NO-GAPS` is its record. **Neither is auto-merge-eligible
today** -- the auto-merge condition names the Opus gate specifically -- so both
ping. (Whether a Haiku-cleared docs PR should become auto-merge-eligible is an open
question for the maintainer, deliberately left undecided by bd
`polyglot-pdf-saxh`.) Force-push and `bd dolt push --force` stay barred throughout.

## The Assess layer (inner loop, pre-PR)

The SPEAR Assess gate runs in `/closeout` Step 5.5, BEFORE the PR opens:

- **Rubric scorecard.** The orchestrator scores each of the bead's `## Exit
  criteria` PASS/FAIL with one line of evidence. Any FAIL is fixed before the PR
  opens; a legacy bead with no rubric gets a retrospective one (and a journal
  note that it was reconstructed at closeout). **The scorecard is written into the
  PR body under an `## Exit criteria` section** -- the self-demonstrating record
  the maintainer scans.
- **Adversarial fresh-eyes, looped.** Fresh-eyes is the Assessor; it is passed the
  rubric and its mandate is gap-exhaustion ("find every place the changes do NOT
  meet the criteria"), never approval. Each pass ends with a gap verdict --
  `NO-GAPS` (terminal **at whatever model the diff-size router picked** -- there is
  no Opus round in this loop) or `GAPS-FOUND (n)`. On `GAPS-FOUND`, the orchestrator
  fixes the correct blockers, commits, and re-spawns; the loop runs -- with **no
  round cap** -- until every remaining gap is incorrect (refuted), **pre-existing**
  (reproduces unchanged on `origin/dev` -> filed as a bead), or a true nit (also
  filed), which is `NO-GAPS`. Any correct blocker means fix-and-re-spawn, however
  many rounds it takes (maintainer directive 2026-07-04, bd `polyglot-pdf-16pj`); a
  gap that can be neither fixed nor honestly refuted/deferred escalates, never a
  round count. A subagent TIMEOUT/ERROR surfaces to the orchestrator -- silence is
  never read as `NO-GAPS`.
- **The inner loop ENUMERATES, it does not TRACE.** Its output carries a
  `## Changed contracts` block listing every value, format, wire/message key,
  config/schema key, signature, return shape, enum, and coupled constant the diff
  changed -- without following them out. That list is the handoff the outer pass
  starts from, so an omission there becomes an untraced contract downstream.
- **Out-of-scope bugs are filed, not escalated.** Fresh-eyes files a genuine bug
  outside the current bead's criteria as a NEW bead itself (it has `Bash`; the bead
  body carries >= 1 exit criterion + `surfaces` metadata) and lists the filed IDs
  in its output. The executor is not interrupted for out-of-scope finds.
- **The outer review: ONE looped Opus-5 cross-surface review.**
  For a review-worthy change, closeout spawns the `cross-surface-reviewer` agent
  (`model: opus`) on the LOCAL diff (`origin/dev...HEAD`), BEFORE the PR opens,
  handing it the inner loop's `## Changed contracts` list. Its job is the **blast
  radius**, not the local diff: follow each contract into consumers in files the diff
  never touched. It **may not render `NO-GAPS` until it has traced every entry and
  named the consumer files it opened** -- a hard gate, so a skipped trace is visible
  in the output rather than silent. A single `NO-GAPS` is the **adversarial clear**:
  it closes the bead and feeds the merge decision (auto-merge a routine low-risk PR,
  else ping the maintainer). **Only a BEHAVIORAL fix voids that clear** -- filing a
  bead, editing a comment or docstring, docs-only prose, a journal entry, or a
  `.beads/` sync leaves it standing. A **docs-only** PR runs this same loop with the
  Haiku `docs-reviewer` in the outer slot; only a **trivial** PR has no outer loop at
  all, and there the last fresh-eyes `NO-GAPS` is the record.

## Why each choice

- **The OUTER reviewer MUST trace changed values into their consumers in untouched
  files (bd dgoa, retained + hardened 2026-08-05).** The costliest miss is an
  *interaction* the diff can't show: the
  changed code is correct in isolation but breaks a downstream reader in a file
  the diff never touched. bd `polyglot-pdf-bo4m` appended text after a
  `(field_id: ...)` marker in a voice hint; an untouched backend stripper was
  end-anchored on that marker being LAST, so it silently stopped stripping and the
  raw field_id was spoken aloud again -- a clean `NO-GAPS` from two Sonnet rounds
  that read only the diff. So the outer mandate requires, for every changed
  string/format/wire-shape/signature/contract, grepping for its consumers (which
  are NOT in the diff), opening them, and confirming each still works against the
  new shape -- BEFORE rendering `NO-GAPS`, **naming the consumer files opened**. See
  `.claude/agents/cross-surface-reviewer.md`. **This is why cutting Opus passes did
  not weaken the gate:** the trace moved from one bullet among many in a shared
  general-purpose prompt to the *entire stated purpose* of a dedicated agent, with
  the enumeration handed to it so the list to trace is never left underived.
- **The guaranteed-Opus INNER round is retired (2026-08-05, supersedes bd dgoa
  safeguard 2).** It re-ran the rubric-and-local-bugs pass at the highest price
  immediately before the outer review did its own pass -- two near-identical
  back-to-back Opus spawns separated only by the review-worthiness gate. The
  cross-file class it existed to catch is now the sole, explicit, hard-gated mandate
  of the outer pass, so the inner loop's verdict is terminal at its routed model.
- **ONE Opus outer pass, not two (2026-08-05, supersedes bd dgoa safeguard 3).** The
  duplicate confirming pass doubled the most expensive step *and* re-ran on every
  fix, for a marginal catch rate: two runs of the identical prompt at the identical
  model on the identical diff are independent in *context* but not in *perspective*,
  so they share blind spots. What actually mattered -- independence from the author's
  framing (a fresh subagent, no shared context, reading the real diff) -- is fully
  preserved by one pass. Measured cost of the old gate: 14 hours across 9 review
  cycles in a single day, with token burn quadrupled. **Residual risk, stated
  honestly:** a single reviewer's blind spot is no longer covered by a second
  opinion. Accepted deliberately, and partially offset by the hardened trace gate and
  by CI -- but see the CI bullet below for what CI does *not* cover.
- **CI is a cheap triple-check, NOT a warrant for a thinner LLM gate.** The suite
  re-runs on every PR and should always come up clean. It catches environment skew
  and lockfile drift; it does **not** catch what the review gate exists for. The
  motivating bo4m regression had **green tests throughout** -- cross-file interaction
  bugs are precisely the class tests usually do not cover. Never reason "CI will
  catch it" to justify skipping the trace.
- **External model reviewers are retired (2026-07-08).** The repo previously ran
  OpenAI Codex (`chatgpt-codex-connector[bot]`) as the outer review -- itself the
  successor to GitHub Copilot (bd hrn.8/hrn.9) after the prepaid Copilot credits
  were exhausted. The maintainer's Codex subscription has now ended, so the repo
  uses NO external reviewer at all. The Opus review that already existed as the
  fallback for when Codex was unavailable is now the ALWAYS-ON primary outer review
  (the maintainer's framing: "Codex will always be unavailable, so the fallback
  becomes the primary; that is the only change"). The Codex-specific machinery --
  the `@codex review` trigger comment, the `pr_review_watcher.py` bot watcher, the
  👍/eyeballs reaction signals, the `requested_reviewers` API, the AGENTS.md
  reviewer-etiquette section -- is dead path and is never invoked; it is retained in
  the scripts only as inert history.
- **Outer Opus review, mechanics: ONE looped Opus-5 cross-surface review.** For a
  review-worthy change, closeout spawns the `cross-surface-reviewer` agent
  (`model: opus`) -- passed the bead's exit criteria, the inner loop's
  `## Changed contracts` list, and pointed at the real LOCAL diff
  (`origin/dev...HEAD`, BEFORE the PR opens) -- and loops it (fix -> re-spawn) to
  `NO-GAPS`, no round cap, looping while findings are correct blockers. That single
  `NO-GAPS` is the **adversarial clear**: it closes the bead and feeds the merge
  decision (auto-merge a routine low-risk PR, else ping). **Why Opus-5:** it is the
  most capable reviewer routinely available, and cross-surface tracing is the one
  job the cheaper tiers demonstrably cannot do (the bo4m regression cleared two
  Sonnet rounds). The gate does **NOT** rest on out-ranking the author -- when the
  author ran on Opus the reviewer is the SAME tier. It rests on **independence**: a
  fresh subagent with no shared context, prompted adversarially, reading the real
  diff. **Why not just trust the pre-PR fresh-eyes `NO-GAPS`:**
  that pass ran on the SAME diff with the author's framing fresh in context, and its
  job was the local diff, not the blast radius; the
  outer review exists precisely to add that independent, differently-scoped look. The
  outer-review subagent is read directly (its `NO-GAPS` / `GAPS-FOUND` STATUS
  line), NOT watched by `pr_review_watcher.py` -- that watcher was the GitHub-bot
  (Codex) path, now retired.
- **Spawn-failure fallback: the effort-400 (2026-07-27).** Subagents inherit the
  SESSION's reasoning-effort setting, and the orchestrator cannot read that setting.
  When the session is Fable at `xhigh`, an Agent-tool spawn of a non-Fable model dies
  with `400 output_config.effort 'xhigh' is not supported when thinking is disabled
  on this model. Use effort 'high' or below, or enable thinking.` **That 400 is a
  transport failure, not a review failure or a `BLOCKED` verdict** -- it does not
  escalate, and it does NOT justify downgrading the reviewer to a cheaper model.
  Retry the same single spawn wrapped in a **one-agent Workflow** whose `agent()`
  call passes `effort: 'high'` explicitly; the Workflow tool exposes an `effort`
  option the Agent tool lacks (verified by controlled A/B 2026-07-27: `{model:
  'opus', effort: 'high'}` succeeded while an identical spawn inheriting `xhigh`
  took the 400). **This covers EVERY subagent spawn in the flow, at any model and any
  step** -- the inner fresh-eyes rounds routed to haiku/sonnet, the Opus outer
  reviewer, and the Haiku `closeout-runner` that drives the mechanical tail --
  since all of them are non-Fable spawns that fail identically. The
  standing permission covers a **single-agent wrapper only** -- genuine multi-agent
  orchestration still needs the maintainer's explicit opt-in. **If the wrapped retry
  also fails, that IS a genuine stop:** surface it, and never open the PR without
  the outer review on a review-worthy change. Retire this fallback when the upstream
  bug is fixed.
- **Review-worthiness gate: a THREE-way fork, so nothing ships unreviewed (bd
  saxh, 2026-08-05).** The orchestrator classifies the diff. **Source** PRs
  (`backend/`, `frontend/src/`, scripts, runtime config) get the Opus cross-surface
  review. **Docs-only** PRs (`docs/`, `*.md`, `.beads/`, journal) get ONE adversarial
  **Haiku** review (`docs-reviewer`) -- a full Opus cross-surface trace is wasted on
  prose that changes no runtime contract, but *zero* adversarial review is the wrong
  answer too: a doc asserting something the code contradicts ships silently and then
  teaches it to every future session that auto-loads it. Only a genuinely **trivial**
  diff (typo, whitespace, a bare beads sync) skips adversarial review. When
  ambiguous between docs and source, run the **Opus** review -- a wasted review is
  cheaper than a shipped bug, and a diff touching even one executable file is a
  source diff no matter how much prose rides along. *History:* before bd saxh this
  was a skip/run binary, and docs PRs got their only adversarial look from the inner
  loop's guaranteed-Opus round; retiring that round (bd ofh6) left them at zero,
  which is the gap this fork closes.
- **Fresh-eyes FIRST, then the outer review -- both pre-PR, serial not
  parallel.** The inner fresh-eyes assess loop runs first and loops to `NO-GAPS`;
  then the ONE outer adversarial pass (Opus cross-surface for source, Haiku prose
  for docs-only) runs on the same local branch and loops to `NO-GAPS`. Only after BOTH clear does the PR open. They catch
  different bug classes **because they are given different jobs** -- fresh-eyes scores
  outcome-fitness against the rubric and asks "what did the author's own priorities
  blind them to" *within the diff*; the outer review is an independent,
  no-shared-context look at what the settled diff breaks *outside* it. **Why serial,
  not parallel:** Assess is a gate -- a diff that still has rubric gaps is not ready
  for the outer review, so the inner loop must finish first; running the outer review
  on a diff the inner loop is about to change wastes it; **and the outer pass depends
  on the inner pass's `## Changed contracts` output as its starting point.**
  Fresh-eyes runs even when the outer review is skipped.
- **Each layer loops independently; fixes within a layer batch together.**
  The inner loop fixes all of a fresh-eyes pass's gaps before re-spawning; the outer
  loop fixes all of an Opus review's findings before re-spawning the next pass.
  One re-review per round, never one per finding.
- **NO draft PRs.** A draft adds a pointless state flip. The "cannot merge itself"
  safety a draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md) -- a PR never merges on its own; it is merged by an explicit
  `gh pr merge` (the orchestrator's, under the auto-merge rule, or the
  maintainer's), draft or not. Always open normal.
- **Loop the outer review until CLEAN -- but only a BEHAVIORAL fix re-opens
  it.** After a **behavioral** fix (committed locally, not pushed -- the PR does not
  exist yet), re-spawn whichever outer reviewer the diff type selected on the
  updated local diff. A
  **non-behavioral** fix -- filing a bead, a comment or docstring edit, `docs/`-only
  prose, a journal entry, a `.beads/` sync -- leaves the clear standing; re-running a
  heavy Opus pass because a journal sentence was written is pure waste, and the fear
  of it is what pushed reviewers to fix nits inline instead of filing them. The
  tie-breaker is "does the program do anything different?", not "did I touch a source
  file". The subagent is read directly -- there is no bot watcher and no re-trigger
  comment.
- **Resolve mechanical merge conflicts inline; escalate only structural ones.**
  When the loop's rebase hits a conflict, the orchestrator decides it -- it is not
  an automatic escalation. **Mechanical / ordering** conflicts (append-only journal
  entries, changelog interleaving, independent additions to the same
  list/table) are resolved inline by **keeping both sides** in a sensible order,
  then re-reading the merged region to confirm both intents survived. **Escalate
  (STOP and ask) only on genuine structural incompatibility** -- the two sides
  change the same logic/contract incompatibly so keeping both is wrong and
  choosing is a design call; ambiguous counts as structural. On escalation, abort
  the rebase first so the branch is left clean. Full procedure + the inline-vs-
  escalate boundary: the closeout skill's "Merge-conflict resolution" subsection
  under Step 5.6 (bd polyglot-pdf-hrn.6).
- **Merge is autonomous for routine low-risk PRs, the maintainer's for
  consequence-bearing ones** (autonomy increase 2026-07-04). Once review is CLEAN
  and checks are green, a PR that is NOT consequence-bearing is merged with
  `gh pr merge`; a consequence-bearing PR (proves the bead direction impossible /
  substantially changes an approved plan / affects operational cost / affects
  user-facing features / risks downstream disruption / needs substantial
  multi-surface rework) is pinged to the maintainer instead. Same line as the
  step-2 escalation triggers; when unsure, ping. Full rule: CLAUDE.md "Auto-merge
  vs. maintainer merge". Force-push / `bd dolt push --force` stay barred.

## Reviewers are read-only on the working tree

All three reviewers produce a REPORT (and may file beads). None of them may
change the repo. They are given `Bash`, so this is a discipline, not a tool
limitation -- and they run inside a worktree whose session usually has
UNCOMMITTED work in it, so any write, revert, stash, or checkout destroys that
work silently.

The rule lives in each agent file as its first section; the short form:

- Read, `git diff`/`log`/`show`/`status`, and RUN TESTS freely -- verification
  is most of a reviewer's value.
- To test a mutation, copy the file OUTSIDE the repo and mutate there, or
  report the mutation and its predicted result as an explicitly unverified
  finding. An honestly-unverified finding beats a verified one that ate the
  author's work.
- Never `git stash`/`checkout`/`restore`/`reset`/`clean`/`add`/`commit`, and
  never write inside the repo (redirects, `sed -i`, `mv`, `rm`).
- ONE exception: **filing a bead**. `bd create`/`bd note`/`bd dolt push`
  write to the tracked `.beads/`, and that is the reviewer's sanctioned
  output channel -- the rule protects the author's IN-FLIGHT WORK, which
  `.beads/` is not. (`bd dolt pull`, which the filing sequence runs first,
  needs no exception -- it writes only to the gitignored `.beads/dolt/` and
  `.beads/embeddeddolt/`, never a tracked path.) Use the `bd` commands,
  never a hand edit of those files.
- If a test run leaves an artifact behind, NAME IT in the report; do not tidy
  it away. Cleanup is indistinguishable from deleting the author's work.

Why this is doctrine and not a nit (bd polyglot-pdf-fytzi, 2026-08-22): a
reviewer stashed an author's uncommitted fix mid-review and later restored
files outright. The same two fixes had to be reconstructed twice, and the
author burned the round chasing "my change vanished" rather than reviewing.
The orchestrator's half of the same lesson: **commit before spawning a
reviewer** -- an uncommitted edit is not safe while another agent holds the
worktree.

## The three reviewers

**Inner -- `.claude/agents/fresh-eyes-reviewer.md`** (spawn by type; Sonnet, or
diff-size-routed Haiku). It MUST read the real `git diff origin/dev...HEAD`, never a
summary -- bugs hide in the detail a summary elides. As the SPEAR
Assessor it is passed the bead's exit criteria and **opens with a rubric
scorecard** (PASS/FAIL per criterion), then returns up to 8 findings with
confidence + how-to-verify, **a `## Changed contracts` block enumerating every
value/format/wire-key/signature/contract the diff changed**, any out-of-scope beads
it filed, and **a STATUS line carrying the gap verdict** (`NO-GAPS` /
`GAPS-FOUND (n)`) that drives the inner loop. It does **not** trace contracts into
consumers -- that is the outer reviewer's job, and duplicating it is the cost this
split removes. Triage: a **rubric-criterion gap is FIXED before the PR opens** (a
criterion failure, never a deferrable nit) -- as is any other correct blocker;
**pre-existing and non-blocking findings are FILED as beads, not chased inline**; a
rejected finding gets its reason recorded. **Doc findings route by TIER** (bd
`polyglot-pdf-9feav`): tier 3 (`docs/journal/`, research notes, `docs/archive/`) is ALWAYS filed,
never a gap; in tier 1/2 -- including `.claude/` agent and skill files, which load
into a session's context -- a WRONG claim about the code is a gap and merely UGLY
wording is filed. The test is mechanical (*which file, and is the claim wrong or
just ugly?*), deliberately not predictive: a "might this change what an agent
does?" test gets resolved conservatively and turns every doc nit into a blocker. The orchestrator runs this loop to
`NO-GAPS` pre-PR (no round cap -- loop while gaps are correct blockers), folds the
adopt/reject/defer breakdown into the journal entry, and carries the final scorecard
into the PR body's `## Exit criteria` section.

**Outer, docs-only -- `.claude/agents/docs-reviewer.md`** (`model: haiku`). For a
diff that changes no runtime contract, the outer slot is filled by an adversarial
**prose** review instead of a trace. It hunts claims that contradict the code they
document (it opens the cited source to check), stale or broken cross-references,
doc-vs-doc conflicts, and a `*Last updated:*` bump with no real prose review. It is
explicitly NOT a contract trace and NOT a rubric re-score, and it does not flag
style (markdown is exempt from the ASCII rule). Same loop, same STATUS-line verdict.

**Outer, source -- `.claude/agents/cross-surface-reviewer.md`** (`model: opus`). It is
handed the inner loop's `## Changed contracts` list and the same real local diff.
Its job is the **blast radius**: follow each contract into its consumers in files
the diff never touched, using `docs/technical_guide.md` and the relevant
`docs/components/*.md` as the map of where this app's surfaces meet. It does **not**
re-hunt local bugs -- finding none is not a failure. It **may not render `NO-GAPS`
until it has traced every entry and named the consumer files it opened.** One
clearing `NO-GAPS` is the gate.
