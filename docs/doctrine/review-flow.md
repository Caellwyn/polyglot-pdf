# Review-flow doctrine: pre-PR adversarial assess + Codex outer review, looped to clean

*Last updated: 2026-07-05. Three review-hardening safeguards added under bd `polyglot-pdf-dgoa` (after a cross-file interaction regression, bd `polyglot-pdf-bo4m`, passed two Sonnet fresh-eyes rounds and was caught only by the stronger outer review): (1) the fresh-eyes mandate now REQUIRES tracing every changed value/format/contract into its downstream consumers in untouched files; (2) the FINAL confirming pre-PR fresh-eyes round always runs on Opus; (3) when Codex is unavailable, the fallback requires TWO independent clearing reviews, not one. See [the bd bo4m journal entry](../journal/entries/2026-07-05-bd-bo4m-field-fine-print-reaches-voice-ai.md) for the motivating regression. Earlier: see [the hrn.9 journal entry](../journal/entries/) for the Copilot->Codex cutover details, and [`planning.md`](planning.md) for the SPEAR Assess doctrine this layers in (bd `polyglot-pdf-7dkb`). The Opus-4.8 reviewer-of-last-resort + the watcher's acknowledgment phase / `NO-ACK` state were added under bd `polyglot-pdf-n6ks`. The auto-merge-vs-ping rule was added under bd `polyglot-pdf-16pj`.*

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
       spawn fresh-eyes (criteria passed in, ADVERSARIAL; MUST trace changed
         values into untouched-file consumers) -> fix gaps -> re-spawn
       ... until NO-GAPS (loop while gaps are correct blockers; no round cap)
       -> FINAL confirming round on OPUS (the clearing NO-GAPS must come from an
          Opus pass; earlier rounds route cheaply by diff size)
  -> judge review-worthiness              [orchestrator: does this diff warrant Codex?]
  -> open a NORMAL (non-draft) PR         [scorecard in the PR BODY; if review-worthy: `@codex review` line; Codex auto-reviews on open]
  -> OUTER LOOP (post-PR Codex review):    [review-worthy PRs only]
       watch Codex (ack window 2 min) -> fix -> push -> re-comment `@codex review`
       ... until CLEAN (loop while findings are correct blockers; no round cap)
       |
       +-- Codex UNAVAILABLE (ERROR quota / TIMEOUT / NO-ACK)
           -> FALLBACK: TWO independent Opus-4.8 adversarial reviews (both must clear)
              primary: spawn fresh-eyes-reviewer @ model:opus -> fix -> re-spawn
                ... until NO-GAPS (loop while gaps are correct blockers; no round cap)
              second: independent confirming review on the SAME final diff (fresh
                Opus, or Sonnet if a 2nd Opus is unavailable) -> must ALSO be
                NO-GAPS; any fix invalidates both clears and re-runs both
              -> two independent NO-GAPS on the identical diff = same authority as Codex
  -> close bead + [auto-merge if routine/low-risk & clean | else ping the maintainer]
```

The final gate is the **merge decision** (autonomy increase 2026-07-04, bd
`polyglot-pdf-16pj`): once review is CLEAN and checks are green, a PR that is NOT
consequence-bearing is **merged autonomously** (`gh pr merge`); a
consequence-bearing PR (affects operational cost / user-facing features /
downstream disruption / an approved plan / needs substantial multi-surface rework)
is **pinged to the maintainer**. Same line as the step-2 escalation triggers; when
unsure, ping. A **review-skipped** PR (docs/beads/journal-only) runs the inner
fresh-eyes assess loop only and has no Codex loop -- it had no adversarial *review*,
so it is not auto-merge-eligible and pings; the last fresh-eyes `NO-GAPS` verdict is
its review record. Force-push and `bd dolt push --force` stay barred throughout.

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
- **The reviewer of last resort: TWO independent Opus-4.8 adversarial reviews when
  Codex is unavailable (bd dgoa).** Codex can be down three ways -- it posts a quota
  notice (`ERROR`), it produces no verdict in the window (`TIMEOUT`), or it never
  reacts to the trigger comment within the 2-minute acknowledgment window
  (`NO-ACK`). In ALL three the PR must NOT stall, so closeout routes to the Opus
  fallback (the same `fresh-eyes-reviewer` agent, spawned with `model: opus`). But
  because the fallback is then the ONLY adversarial gate, ONE pass is not enough:
  **two independent reviews must BOTH return `NO-GAPS` on the identical final diff**
  (the primary looped Opus review + a second independent confirming review -- a
  fresh Opus, or a fresh Sonnet only if a second Opus is unavailable). A fix found
  by either invalidates both clears and re-runs both. Two agreeing `NO-GAPS`
  carries the **same authority as a clean Codex review** -- it closes the bead and
  feeds the same merge decision as a Codex CLEAN (auto-merge a routine low-risk PR,
  else ping the maintainer), and the ping records that two reviews cleared it +
  names the second reviewer's model. See the "fallback reviewer" subsection below.
  A review-skipped PR (docs/beads/journal-only) still has no outer loop at all --
  there the last fresh-eyes `NO-GAPS` (from the Opus final round) is the record.

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
- **When Codex is unavailable, the fallback requires TWO independent clearing
  reviews, not one (bd dgoa).** Codex-down (ERROR/TIMEOUT/NO-ACK) makes the Opus
  fallback the ONLY adversarial gate, so a single pass is a single point of
  failure -- the exact path PR #312 relied on. The gate is met only when two
  independent reviews (the primary looped Opus review + a second independent
  confirming review -- a fresh Opus, or a fresh Sonnet if a second Opus is
  unavailable) BOTH return `NO-GAPS` on the identical final diff. A fix found by
  either invalidates both clears and re-runs both. The merge ping records that two
  reviews cleared it and names the second reviewer's model. (The operational
  mechanics -- primary loop then second confirming review, and the read-directly
  vs. watcher distinction -- are in the "Reviewer of last resort, mechanics" bullet
  below.) (When Codex IS
  available, its review + the pre-PR Opus final round already provide two
  independent looks, so this two-reviewer requirement is specific to the
  Codex-down fallback.)
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
  trigger COMMENT -- distinct from the 👍 CLEAN verdict.** The watcher's
  acknowledgment phase (armed by `--ack-timeout-min 2` on round 2+) waits up to
  2 minutes for the eyeballs reaction on the `@codex review` issue comment; if it
  never appears, the watch exits `NO-ACK` (exit 4) and routes straight to the
  fallback. **Round 1 does NOT use the ack phase** -- its trigger is the PR body,
  not an issue comment, so the eyeballs reaction is unobservable; round 1 goes
  straight to the verdict wait. A Codex that acks on round 2+ gets the full 20-min
  verdict window.
- **Reviewer of last resort, mechanics: TWO independent looped Opus-4.8 reviews
  when Codex is unavailable (bd dgoa).** On `ERROR` (quota), `TIMEOUT` (no
  verdict), or `NO-ACK` (never started), closeout spawns the
  `fresh-eyes-reviewer` agent with `model: opus` -- passed the bead's exit criteria
  and pointed at the real post-PR diff -- and loops it (fix gaps -> re-spawn) to
  `NO-GAPS` -- no round cap, looping while gaps are correct blockers, same
  outcome-based stop as the Codex loop. Then a SECOND independent confirming review
  (a fresh Opus spawn, or a fresh Sonnet only if a second Opus is unavailable) must
  ALSO return `NO-GAPS` on the identical final diff; a fix found by either
  invalidates both clears and re-runs both (the two-review gate above -- Codex-down
  makes the fallback the only adversarial gate, so one pass is a single point of
  failure). Two agreeing `NO-GAPS` carry the **same authority as a clean Codex
  review**: they close the bead and feed the same merge decision (auto-merge a
  routine low-risk PR, else ping -- and whichever happens, the note to the
  maintainer records the fallback path, which trigger fired, and that two reviews
  cleared it + the second reviewer's model). **Why Opus-4.8:** it is the most
  capable affordable reviewer once Codex credits are spent -- same model family as
  the Sonnet fresh-eyes that ALREADY cleared the rubric pre-PR and as the author,
  but a stronger tier, so this is a genuine fresh adversarial look rather than
  re-running an already-clean process. A different vendor would cost more for no
  clear gain. **Why not just trust the pre-PR fresh-eyes `NO-GAPS`** (the old
  behavior while credits were exhausted)**:** that pass and the author share a
  model family and ran on the SAME diff with the author's framing fresh in context;
  the outer review exists precisely to add an independent look, and the Opus
  fallback preserves that independence (stronger tier, post-PR, adversarial) when
  Codex can't provide it. The fallback subagents are read directly (their `NO-GAPS`
  / `GAPS-FOUND` STATUS lines), NOT watched by `pr_review_watcher.py` -- that
  watcher is the GitHub-bot (Codex) path only, same as the Step 5.5 fresh-eyes
  loop.
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
- **NO draft PRs.** A draft adds a pointless state flip. The "cannot merge itself"
  safety a draft provides is already guaranteed by allow_auto_merge=false (see
  promotion-tiers.md) -- a PR never merges on its own; it is merged by an explicit
  `gh pr merge` (the orchestrator's, under the auto-merge rule, or the
  maintainer's), draft or not. Always open normal.
- **Loop Codex until CLEAN.** A fix-push does NOT re-trigger Codex -- you MUST post
  a fresh `@codex review` comment (capturing its `created_at` as the next round's
  `--since` floor) to request each re-review. The fresh-eyes inner loop is already
  done (pre-PR); the outer loop is Codex only.
- **Handle all five pr_review_watcher.py states.** CLEAN/COMMENTS (exit 0) proceed
  normally. ERROR (exit 1), TIMEOUT (exit 2), and NO-ACK (exit 4) all route to the
  Opus-4.8 fallback reviewer (Step 7.5) -- NEVER treat them as clean and NEVER
  dead-end at the maintainer. CLOSE-FAILED (exit 3) surfaces to the maintainer (a
  bead-close failure is a genuine stop). An unhandled state must never fall through
  to "done."
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
