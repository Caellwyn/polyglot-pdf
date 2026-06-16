# Review-flow doctrine: pre-PR adversarial assess + Codex outer review, looped to clean

*Last updated: 2026-06-16. See [the hrn.9 journal entry](../journal/entries/) for the Copilot->Codex cutover details, and [`planning.md`](planning.md) for the SPEAR Assess doctrine this layers in (bd `polyglot-pdf-7dkb`). The Opus-4.8 reviewer-of-last-resort + the watcher's acknowledgment phase / `NO-ACK` state were added under bd `polyglot-pdf-n6ks`.*

How every change gets reviewed before merge. This is the procedure the
`/closeout` skill automates; it is the result of several iterations and the
rationale for each choice is preserved below so it is not re-litigated.

Review is **two layers**: an **inner** adversarial fresh-eyes loop that runs
BEFORE the PR opens and scores the diff against the bead's exit-criteria rubric
(the SPEAR Assess gate), and an **outer** Codex review that runs after the PR
opens. Fresh-eyes is the gap-exhaustion assessor; Codex is the local-correctness
backstop.

## The flow

```
clean tree
  -> score the exit-criteria rubric       [orchestrator: PASS/FAIL each criterion + evidence; any FAIL -> fix]
  -> INNER LOOP (pre-PR Assess):           [ALWAYS, review-worthy or not]
       spawn fresh-eyes (criteria passed in, ADVERSARIAL) -> fix gaps -> re-spawn
       ... until NO-GAPS (ceiling MAX_FRESH_EYES_ROUNDS = 3)
  -> judge review-worthiness              [orchestrator: does this diff warrant Codex?]
  -> open a NORMAL (non-draft) PR         [scorecard in the PR BODY; if review-worthy: `@codex review` line; Codex auto-reviews on open]
  -> OUTER LOOP (post-PR Codex review):    [review-worthy PRs only]
       watch Codex (ack window 2 min) -> fix -> push -> re-comment `@codex review`
       ... until Codex reports CLEAN (ceiling MAX_REVIEW_ROUNDS = 2)
       |
       +-- Codex UNAVAILABLE (ERROR quota / TIMEOUT / NO-ACK)
           -> FALLBACK: Opus-4.8 adversarial review (reviewer of last resort)
              spawn fresh-eyes-reviewer @ model:opus -> fix -> re-spawn
              ... until NO-GAPS (ceiling MAX_FALLBACK_ROUNDS = 2); same authority as Codex
  -> close bead + ping the maintainer to merge
```

The maintainer's only gate is the **final manual merge**. Everything up to the
ping is autonomous. A review-skipped PR (docs/beads/journal-only) runs the inner
fresh-eyes assess loop only and has no Codex loop -- the last fresh-eyes `NO-GAPS`
verdict is then the review record.

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
  the gaps, commits, and re-spawns; the loop runs until `NO-GAPS` or the ceiling
  `MAX_FRESH_EYES_ROUNDS = 3` (at which point it escalates, never auto-passes).
  A subagent TIMEOUT/ERROR surfaces to the orchestrator -- silence is never read as
  `NO-GAPS`.
- **Out-of-scope bugs are filed, not escalated.** Fresh-eyes files a genuine bug
  outside the current bead's criteria as a NEW bead itself (it has `Bash`; the bead
  body carries >= 1 exit criterion + `surfaces` metadata) and lists the filed IDs
  in its output. The executor is not interrupted for out-of-scope finds.
- **The reviewer of last resort: an Opus-4.8 adversarial review when Codex is
  unavailable.** Codex can be down three ways -- it posts a quota notice (`ERROR`),
  it produces no verdict in the window (`TIMEOUT`), or it never reacts to the
  trigger comment within the 2-minute acknowledgment window (`NO-ACK`). In ALL
  three the PR must NOT stall, so closeout routes to ONE looped Opus-4.8
  adversarial review (the same `fresh-eyes-reviewer` agent, spawned with
  `model: opus`) with the **same authority as a clean Codex review** -- a
  `NO-GAPS` closes the bead and pings the maintainer to merge. See the "fallback
  reviewer" subsection below. A review-skipped PR (docs/beads/journal-only) still
  has no outer loop at all -- there the last fresh-eyes `NO-GAPS` is the record.

## Why each choice

- **The reviewer is OpenAI Codex; it AUTO-REVIEWS on PR open (bd hrn.8/hrn.9).**
  The prepaid GitHub Copilot credits were exhausted, so the repo cut over to
  OpenAI Codex (`chatgpt-codex-connector[bot]`). Codex reviews a PR automatically
  when it opens, so ROUND 1 needs no explicit trigger -- we just put an `@codex
  review` line in the PR BODY as a belt-and-suspenders nudge. ROUND 2+ re-reviews
  (after a fix-push) DO need an explicit `@codex review` issue comment, posted as
  the gh-authenticated user. Never use the GitHub reviewer API
  (`requested_reviewers`) -- that fires Copilot, which is retired here. The
  round-1 watch floor is the PR-open time (the auto-review lands after it); each
  re-review's floor is its trigger comment's `created_at`.
- **The trigger string is EXACTLY `@codex review`.** A different phrasing such as
  `@codex please commit ...` would invoke Codex's commit path (it can push to the
  PR), not a review -- see the "If you are reviewing a PR" section of `AGENTS.md`,
  which is the file Codex actually reads for its review etiquette (approve via a
  👍 reaction; always post a summary comment).
- **Codex's CLEAN signal is a 👍 (`+1`) reaction** on its summary comment (the
  canonical, language-independent approval), with "Didn't find any major issues"
  text or an exact `LGTM` as fallbacks. The watcher
  (`scripts/pr_review_watcher.py --reviewer codex`, now the default) classifies
  all three; an inline finding always outranks a 👍, so a thumbs-up can't mask a
  real ask.
- **Codex's "begun work" signal is an eyeballs (👀 / `eyes`) reaction on the
  trigger comment -- distinct from the 👍 CLEAN verdict.** The watcher's
  acknowledgment phase (armed by `--ack-timeout-min 2`, which closeout passes)
  waits up to 2 minutes for proof Codex has started -- that eyeballs reaction OR
  any in-window review/comment it posts (round 1's trigger is the PR body, which
  has no issue-comment eyeballs to read, so round 1 leans on the activity signal).
  If neither appears, the watch exits `NO-ACK` (exit 4) instead of blocking on the
  full 20-minute verdict timeout -- a fast, specific "Codex is asleep" signal that
  routes straight to the fallback. A Codex that is genuinely working is never
  falsely `NO-ACK`'d.
- **Reviewer of last resort: a looped Opus-4.8 adversarial review when Codex is
  unavailable.** On `ERROR` (quota), `TIMEOUT` (no verdict), or `NO-ACK` (never
  started), closeout spawns the `fresh-eyes-reviewer` agent with `model: opus` --
  passed the bead's exit criteria and pointed at the real post-PR diff -- and loops
  it (fix gaps -> re-spawn) to `NO-GAPS`, ceiling `MAX_FALLBACK_ROUNDS = 2`. A
  clean fallback has the **same authority as a clean Codex review**: it closes the
  bead and pings the maintainer to merge (the merge ping notes the fallback path
  and which trigger fired). **Why Opus-4.8:** it is the most capable affordable
  reviewer once Codex credits are spent -- same model family as the Sonnet
  fresh-eyes that ALREADY cleared the rubric pre-PR and as the author, but a
  stronger tier, so this is a genuine fresh adversarial look rather than re-running
  an already-clean process. A different vendor would cost more for no clear gain.
  **Why not just trust the pre-PR fresh-eyes `NO-GAPS`** (the old behavior while
  credits were exhausted)**:** that pass and the author share a model family and
  ran on the SAME diff with the author's framing fresh in context; the outer review
  exists precisely to add an independent look, and the Opus fallback preserves that
  independence (stronger tier, post-PR, adversarial) when Codex can't provide it.
  The fallback subagent is read directly (its `NO-GAPS` / `GAPS-FOUND` STATUS
  line), NOT watched by `pr_review_watcher.py` -- that watcher is the GitHub-bot
  (Codex) path only, same as the Step 5.5 fresh-eyes loop.
- **Review-worthiness gate.** The orchestrator decides per-PR whether the diff can
  contain a runtime/logic regression. Docs-only / `.beads`-only / journal-only /
  trivial PRs get NO trigger and skip the watch loop entirely -- reviewing them
  spends review effort on content that can't regress. Source PRs (`backend/`,
  `frontend/src/`, scripts, runtime config) get the trigger. When genuinely
  ambiguous, trigger the review -- a wasted review is cheaper than a shipped bug,
  but the gate is not an excuse to dodge review of real code.
- **Fresh-eyes BEFORE the PR, Codex AFTER (they do not run in parallel).** The
  inner fresh-eyes assess loop runs pre-PR and loops to `NO-GAPS`, so by the time
  the PR opens the rubric is met and the fixes are committed; Codex (the outer
  review) then auto-reviews the opened PR. They catch different bug classes -- Codex
  is good at local correctness, fresh-eyes at "what did the author's own priorities
  blind them to" and at scoring outcome-fitness against the rubric. **Why serial,
  not parallel:** Assess is a gate -- a diff that still has rubric gaps is not ready
  for the outer review, and opening the PR mid-gap would spend Codex on a diff
  fresh-eyes is about to change. (The earlier flow ran both in parallel post-PR for
  `max(codex, fresh-eyes)` wall-clock; the SPEAR Assess gate trades that for a clean
  "ready before it opens" contract.) Fresh-eyes runs even when Codex is skipped.
- **Each layer loops independently; fixes within a layer batch into one push.**
  The inner loop fixes all of a fresh-eyes pass's gaps before re-spawning; the outer
  loop fixes all of a Codex round's findings before re-commenting `@codex review`.
  One re-trigger per round, never one per finding.
- **NO draft PRs.** A draft adds a pointless state flip. The "cannot merge" safety
  a draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md), which makes the manual merge the only gate regardless of
  draft state. Always open normal.
- **Loop Codex until CLEAN.** A fix-push does NOT re-trigger Codex -- you MUST post
  a fresh `@codex review` comment (capturing its `created_at` as the next round's
  `--since` floor) to request each re-review. The fresh-eyes inner loop is already
  done (pre-PR); the outer loop is Codex only.
- **Handle all four pr_review_watcher.py states.** CLEAN/COMMENTS (exit 0), ERROR
  (exit 1, surface to maintainer, no auto-retry -- a quota error will not clear
  for hours), TIMEOUT (exit 2, treat like ERROR -- NEVER interpret silence as
  CLEAN). An unhandled state must never fall through to "done."
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
  escalate boundary: the closeout skill's Step-7 "Merge-conflict resolution in the
  loop" (bd polyglot-pdf-hrn.6).
- **Never run `gh pr merge`.** The merge is the maintainer's alone.

## Fresh-eyes specifics

The fresh-eyes reviewer is `.claude/agents/fresh-eyes-reviewer.md` (spawn by
type) or its prompt run as a one-off Sonnet (or diff-size-routed Haiku) subagent.
It MUST read the real `git diff origin/dev...HEAD`, never a summary -- bugs hide
in the detail a summary elides. As the SPEAR Assessor it is passed the bead's
exit criteria and **opens with a rubric scorecard** (PASS/FAIL per criterion),
then returns up to 8 findings with confidence + how-to-verify, lists any
out-of-scope beads it filed, and **ends with a STATUS line carrying the gap
verdict** (`NO-GAPS` / `GAPS-FOUND (n)`) that drives the inner loop. Triage: a
**rubric-criterion gap is FIXED before the PR opens** (it is a criterion failure,
never a deferrable nit) -- as is any other high-confidence finding; a genuinely
out-of-scope bug is filed as a separate bead (fresh-eyes files its own); a
rejected finding gets its reason recorded. The orchestrator runs this loop to
`NO-GAPS` pre-PR (ceiling 3 rounds),
folds the adopt/reject/defer breakdown into the journal entry, and carries the
final scorecard into the PR body's `## Exit criteria` section.
