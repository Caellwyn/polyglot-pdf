# Review-flow doctrine: pre-PR adversarial assess + Opus outer review, looped to clean

*Last updated: 2026-07-27. **External model reviewers are retired.** The maintainer's Codex (OpenAI) subscription has ended, and the repo uses NO external reviewer. Review is now entirely Claude-based: a Sonnet/Haiku fresh-eyes inner loop and an Opus-5 outer loop. Mechanically this was the smallest possible change -- the Opus reviewer that already existed as the fallback for when Codex was unavailable simply became the ALWAYS-ON primary outer review (Codex is now permanently unavailable), keeping its two-independent-clearing-reviews gate. The Codex trigger/watch machinery (`@codex review`, `pr_review_watcher.py`, `requested_reviewers`) is dead path -- never invoked. Earlier context preserved: three review-hardening safeguards were added under bd `polyglot-pdf-dgoa` (after a cross-file interaction regression, bd `polyglot-pdf-bo4m`, passed two Sonnet fresh-eyes rounds and was caught only by the stronger outer review): (1) the fresh-eyes mandate REQUIRES tracing every changed value/format/contract into its downstream consumers in untouched files; (2) the FINAL confirming pre-PR fresh-eyes round always runs on Opus; (3) the Opus outer review requires TWO independent clearing reviews, not one. See [the bd bo4m journal entry](../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md) for the motivating regression, and [`planning.md`](planning.md) for the SPEAR Assess doctrine this layers in (bd `polyglot-pdf-7dkb`). The Opus outer reviewer was introduced under bd `polyglot-pdf-n6ks` (then Opus 4.8; the outer review moved to Opus 5 under bd `polyglot-pdf-wntz`, 2026-07-27, when code production moved to Opus 5); the auto-merge-vs-ping rule under bd `polyglot-pdf-16pj`.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

Review is **two layers, both Claude, and BOTH run BEFORE the PR opens** (flow
change 2026-07-08): an **inner** adversarial fresh-eyes loop that scores the local
diff against the bead's exit-criteria rubric (the SPEAR Assess gate, Sonnet/Haiku
with a guaranteed Opus final round), then an **outer** Opus-5 review (TWO
independent clearing passes) on the same local branch. Fresh-eyes is the
gap-exhaustion assessor; the Opus outer review is the independent adversarial
backstop (a fresh subagent, no shared context, two passes must agree). There is NO external reviewer. The PR opens only AFTER both loops clear --
so opening the PR, closing the bead(s), and the merge decision are the final steps,
not a review surface.

## The flow

```
clean tree
  -> score the exit-criteria rubric       [orchestrator: PASS/FAIL each criterion + evidence; any FAIL -> fix]
  -> INNER LOOP (pre-PR Assess):           [ALWAYS, review-worthy or not]
       spawn fresh-eyes (criteria passed in, ADVERSARIAL; MUST trace changed
         values into untouched-file consumers) -> fix gaps -> re-spawn
       ... until NO-GAPS (loop while gaps are correct blockers; no round cap)
       -> FINAL confirming round on OPUS (the clearing NO-GAPS must come from an
          Opus pass; earlier rounds route cheaply by diff size)
  -> judge review-worthiness              [orchestrator: does this diff warrant an outer review?]
  -> OUTER LOOP (pre-PR Opus-5 review):  [review-worthy changes only -- TWO independent Opus passes, on the LOCAL branch]
       primary: spawn fresh-eyes-reviewer @ model:opus on the local diff (origin/dev...HEAD)
         -> fix -> re-spawn ... until NO-GAPS (loop while gaps are correct blockers; no round cap)
       second: independent confirming review on the SAME final diff (fresh Opus,
         or Sonnet only if a 2nd Opus is unavailable) -> must ALSO be NO-GAPS;
         any fix invalidates both clears and re-runs both
       -> two independent NO-GAPS on the identical diff = the adversarial clear
  -> open a NORMAL (non-draft) PR + close the bead(s)   [one closeout_finish.py run; scorecard in the PR BODY; no external-reviewer trigger]
  -> merge decision: [auto-merge if routine/low-risk & clean | else ping the maintainer]
```

The final gate is the **merge decision** (autonomy increase 2026-07-04, bd
`polyglot-pdf-16pj`): once review is CLEAN (both pre-PR loops cleared) and checks are
green, a PR that is NOT consequence-bearing is **merged autonomously**
(`gh pr merge`); a consequence-bearing PR (affects operational cost / user-facing
features / downstream disruption / an approved plan / needs substantial
multi-surface rework) is **pinged to the maintainer**. Same line as the step-2
escalation triggers; when unsure, ping. A **review-skipped** change
(docs/beads/journal-only) runs the inner fresh-eyes assess loop only and has no
outer Opus loop -- it had no independent adversarial *review*, so its PR is not
auto-merge-eligible and pings; the last fresh-eyes `NO-GAPS` verdict is its review
record. Force-push and `bd dolt push --force` stay barred throughout.

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
  `NO-GAPS` (terminal) or `GAPS-FOUND (n)`. On `GAPS-FOUND`, the orchestrator fixes
  the gaps, commits, and re-spawns; the loop runs -- with **no round cap** -- until
  every remaining gap is incorrect (refuted) or a true nit (filed as a bead), which
  is `NO-GAPS`. Any correct blocker means fix-and-re-spawn, however many rounds it
  takes (maintainer directive 2026-07-04, bd `polyglot-pdf-16pj`); a gap that can be
  neither fixed nor honestly refuted/deferred escalates, never a round count.
  A subagent TIMEOUT/ERROR surfaces to the orchestrator -- silence is never read as
  `NO-GAPS`.
- **Out-of-scope bugs are filed, not escalated.** Fresh-eyes files a genuine bug
  outside the current bead's criteria as a NEW bead itself (it has `Bash`; the bead
  body carries >= 1 exit criterion + `surfaces` metadata) and lists the filed IDs
  in its output. The executor is not interrupted for out-of-scope finds.
- **The outer review: TWO independent Opus-5 adversarial reviews (bd dgoa).**
  For a review-worthy change, closeout spawns the Opus outer review -- the same
  `fresh-eyes-reviewer` agent, spawned with `model: opus`, on the LOCAL diff
  (`origin/dev...HEAD`), BEFORE the PR opens.
  Because it is the ONLY independent adversarial gate, ONE pass is not enough:
  **two independent reviews must BOTH return `NO-GAPS` on the identical final diff**
  (the primary looped Opus review + a second independent confirming review -- a
  fresh Opus, or a fresh Sonnet only if a second Opus is unavailable). A fix found
  by either invalidates both clears and re-runs both. Two agreeing `NO-GAPS` is the
  **adversarial clear** -- it closes the bead and feeds the merge decision
  (auto-merge a routine low-risk PR, else ping the maintainer), and the ping records
  that two reviews cleared it + names the second reviewer's model. See the "outer
  Opus review" subsection below. (This is the former "reviewer of last resort":
  when the repo used Codex, this two-Opus review was the fallback for when Codex was
  unavailable; now that external reviewers are retired it is simply the primary
  outer review.) A review-skipped PR (docs/beads/journal-only) has no outer loop at
  all -- there the last fresh-eyes `NO-GAPS` (from the Opus final round) is the
  record.

## Why each choice

- **Fresh-eyes MUST trace changed values into their consumers in untouched files
  (bd dgoa).** The costliest miss is an *interaction* the diff can't show: the
  changed code is correct in isolation but breaks a downstream reader in a file
  the diff never touched. bd `polyglot-pdf-bo4m` appended text after a
  `(field_id: ...)` marker in a voice hint; an untouched backend stripper was
  end-anchored on that marker being LAST, so it silently stopped stripping and the
  raw field_id was spoken aloud again -- a clean `NO-GAPS` from two Sonnet rounds
  that read only the diff. So the reviewer mandate now requires, for every changed
  string/format/wire-shape/signature/contract, grepping for its consumers (which
  are NOT in the diff), opening them, and confirming each still works against the
  new shape -- BEFORE rendering `NO-GAPS`. See `.claude/agents/fresh-eyes-reviewer.md`
  "What to look for."
- **The final pre-PR fresh-eyes round always runs on Opus (bd dgoa).** The
  diff-size router (`pick_review_model.py`) still routes EARLIER rounds cheaply
  (haiku/sonnet) to save tokens, but a `NO-GAPS` is only terminal when the round
  that produced it ran on Opus -- the strongest reviewer always gets the last look
  before the PR opens. The cheaper tiers miss cross-file interaction bugs (the bo4m
  regression cleared two Sonnet rounds; the stronger tier's trace caught it). This
  is one guaranteed Opus pass at the end, not a change to the merge decision or the
  A/B cost accounting for earlier rounds. (If the diff already routed to Opus, or
  `CLAUDE_CODE_SUBAGENT_MODEL` forces it, no extra pass is needed.)
- **The outer Opus review requires TWO independent clearing reviews, not one
  (bd dgoa).** The Opus outer review is the ONLY independent adversarial gate, so a
  single pass is a single point of failure -- the exact path PR #312 relied on. The
  gate is met only when two independent reviews (the primary looped Opus review + a
  second independent confirming review -- a fresh Opus, or a fresh Sonnet if a
  second Opus is unavailable) BOTH return `NO-GAPS` on the identical final diff. A
  fix found by either invalidates both clears and re-runs both. The merge ping
  records that two reviews cleared it and names the second reviewer's model. (The
  operational mechanics -- primary loop then second confirming review -- are in the
  "Outer Opus review, mechanics" bullet below.)
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
- **Outer Opus review, mechanics: TWO independent looped Opus-5 reviews (bd dgoa,
  now always-on).** For a review-worthy change, closeout spawns the
  `fresh-eyes-reviewer` agent with `model: opus` -- passed the bead's exit criteria
  and pointed at the real LOCAL diff (`origin/dev...HEAD`, BEFORE the PR opens) --
  and loops it (fix gaps -> re-spawn) to
  `NO-GAPS` -- no round cap, looping while gaps are correct blockers. Then a SECOND
  independent confirming review (a fresh Opus spawn, or a fresh Sonnet only if a
  second Opus is unavailable) must ALSO return `NO-GAPS` on the identical final diff;
  a fix found by either invalidates both clears and re-runs both (the two-review
  gate above -- the outer review is the only adversarial gate, so one pass is a
  single point of failure). Two agreeing `NO-GAPS` are the **adversarial clear**:
  they close the bead and feed the merge decision (auto-merge a routine low-risk PR,
  else ping -- and whichever happens, the note to the maintainer records that two
  reviews cleared it + the second reviewer's model). **Why Opus-5:** it is the most
  capable reviewer routinely available. The gate does **NOT** rest on out-ranking
  either the author or the fresh-eyes pass -- the final fresh-eyes clearing round is
  itself Opus (bd dgoa, above), and when the author ran on Opus the outer reviewer is
  the SAME tier as both. It rests on **independence**: a fresh
  subagent with no shared context, prompted adversarially, reading the real diff --
  and on **two independent passes** having to agree, so a single reviewer's blind
  spot is not the whole gate. **Why not just trust the pre-PR fresh-eyes `NO-GAPS`:**
  that pass ran on the SAME diff with the author's framing fresh in context; the
  outer review exists precisely to add that independent look. The
  outer-review subagents are read directly (their `NO-GAPS` / `GAPS-FOUND` STATUS
  lines), NOT watched by `pr_review_watcher.py` -- that watcher was the GitHub-bot
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
  took the 400). **This covers EVERY subagent spawn in the flow, at any model** --
  the inner fresh-eyes rounds routed to haiku/sonnet as well as the Opus outer
  reviewer -- since all of them are non-Fable spawns that fail identically. The
  standing permission covers a **single-agent wrapper only** -- genuine multi-agent
  orchestration still needs the maintainer's explicit opt-in. **If the wrapped retry
  also fails, that IS a genuine stop:** surface it, and never open the PR without
  the outer review on a review-worthy change. Retire this fallback when the upstream
  bug is fixed.
- **Review-worthiness gate.** The orchestrator decides per-PR whether the diff can
  contain a runtime/logic regression. Docs-only / `.beads`-only / journal-only /
  trivial PRs skip the outer Opus review entirely -- reviewing them spends review
  effort on content that can't regress. Source PRs (`backend/`, `frontend/src/`,
  scripts, runtime config) get the outer review. When genuinely ambiguous, run the
  review -- a wasted review is cheaper than a shipped bug, but the gate is not an
  excuse to dodge review of real code.
- **Fresh-eyes FIRST, then the Opus outer review -- both pre-PR, serial not
  parallel.** The inner fresh-eyes assess loop runs first and loops to `NO-GAPS`;
  then the Opus outer review runs on the same local branch and loops to
  two-independent-`NO-GAPS`. Only after BOTH clear does the PR open. They catch
  different bug classes -- the outer review is an independent, no-shared-context look at
  the settled diff, fresh-eyes at "what did the author's own priorities blind them
  to" and at scoring outcome-fitness against the rubric. **Why serial, not
  parallel:** Assess is a gate -- a diff that still has rubric gaps is not ready for
  the outer review, so the inner loop must finish first; and running the outer review
  on a diff the inner loop is about to change wastes it. Fresh-eyes runs even when
  the outer review is skipped.
- **Each layer loops independently; fixes within a layer batch together.**
  The inner loop fixes all of a fresh-eyes pass's gaps before re-spawning; the outer
  loop fixes all of an Opus review's findings before re-spawning the next pass.
  One re-review per round, never one per finding.
- **NO draft PRs.** A draft adds a pointless state flip. The "cannot merge itself"
  safety a draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md) -- a PR never merges on its own; it is merged by an explicit
  `gh pr merge` (the orchestrator's, under the auto-merge rule, or the
  maintainer's), draft or not. Always open normal.
- **Loop the Opus outer review until CLEAN.** After a fix (committed locally, not
  pushed -- the PR does not exist yet), re-spawn the Opus reviewer on the updated
  local diff. The fresh-eyes inner loop is already done first; the outer loop is the
  two-independent-Opus-review gate. The subagents are read directly -- there is no
  bot watcher and no re-trigger comment.
- **Resolve mechanical merge conflicts inline; escalate only structural ones.**
  When the loop's rebase hits a conflict, the orchestrator decides it -- it is not
  an automatic escalation. **Mechanical / ordering** conflicts (append-only journal
  or ledger rows, changelog interleaving, independent additions to the same
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

## Fresh-eyes specifics

The fresh-eyes reviewer is `.claude/agents/fresh-eyes-reviewer.md` (spawn by
type) or its prompt run as a one-off Sonnet (or diff-size-routed Haiku) subagent.
It MUST read the real `git diff origin/dev...HEAD`, never a summary -- bugs hide
in the detail a summary elides -- and it MUST **trace every changed
value/format/contract into its consumers in untouched files** before clearing
(bd dgoa; the cross-file interaction class the diff cannot show). As the SPEAR
Assessor it is passed the bead's exit criteria and **opens with a rubric
scorecard** (PASS/FAIL per criterion), then returns up to 8 findings with
confidence + how-to-verify, lists any out-of-scope beads it filed, and **ends with
a STATUS line carrying the gap verdict** (`NO-GAPS` / `GAPS-FOUND (n)`) that drives
the inner loop. Triage: a **rubric-criterion gap is FIXED before the PR opens** (it
is a criterion failure, never a deferrable nit) -- as is any other high-confidence
finding; a genuinely out-of-scope bug is filed as a separate bead (fresh-eyes
files its own); a rejected finding gets its reason recorded. The orchestrator runs
this loop to `NO-GAPS` pre-PR (no round cap -- loop while gaps are correct
blockers), with the **FINAL clearing round always on Opus** (bd dgoa; earlier
rounds route cheaply by diff size), folds the adopt/reject/defer breakdown into the
journal entry, and carries the final scorecard into the PR body's `## Exit
criteria` section.
