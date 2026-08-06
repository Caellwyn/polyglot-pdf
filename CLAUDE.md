# CLAUDE.md -- polyglot-pdf

**Project-specific instructions for AI assistants. Read this before making any changes.**

> This file is the tier-1, always-loaded doc. Keep it lean: it should point at
> the on-demand docs (tier 2 + 3), not duplicate them. See
> [`docs/INDEX.md`](docs/INDEX.md) for the canonical doc map and
> [`docs/doc-architecture.md`](docs/doc-architecture.md) for the progressive-
> discovery system this file sits at the top of.

---

## What this is

**polyglot-pdf** is a voice-driven, multilingual form-filler for complex PDFs
(immigration/legal intake). A browser SPA streams the user's voice over a
WebSocket to a stateless FastAPI backend, which proxies a **Gemini Live** session
that drives form-filling through tool calls; all field state lives on the client
(`sessionStorage`), and PDF rendering is a separate HTTP call (PyMuPDF). Stack:
React + TypeScript (Vite) frontend on **Firebase Hosting**; Python/FastAPI backend
on **Cloud Run** (co-located with Gemini). Entry points: backend `backend/main.py`
(WebSocket route `backend/routes/websocket_routes.py`, Gemini adapter
`backend/adapters/live_ai_gemini.py`); frontend `frontend/src/` (WS config
`frontend/src/shared/config.ts`). Deploy is **local/manual**
(`deploy-demo.sh` / `deploy-production.sh`). For the full verified architecture,
read the re-orientation brief
([`docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md`](docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md)).

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
separate commit. The full tier-2 set exists (docs-reorg epic `polyglot-pdf-gfb`,
closed); the cited code path is the ground truth when a doc and the code disagree.

| Before changing... | Read |
|--------------------|------|
| WebSocket session routing / handshake (`backend/routes/websocket_routes.py`) | `docs/components/websocket-routing.md` |
| Gemini Live adapter, tools, models (`backend/adapters/live_ai_gemini.py`, `backend/config.py`) | `docs/components/voice-ai.md` + `docs/standards/ai-models.md` + [`docs/genai_docs/`](docs/genai_docs/README.md) (authoritative SDK syntax) |
| Context-window compression / session cost+duration bounding (`ContextWindowCompressionConfig`) | `docs/components/context-compression.md` |
| Token/cost work, or any change to SI size / session cost (esp. SI-reduction epic `polyglot-pdf-jnjj`) | `docs/standards/logging-and-cost.md` -- holds the MEASURED cost invariant (on 2.5, text-in = per-turn SI = 95-98% of cost; audio is negligible) |
| Anything calling the `google-genai` SDK (`from google import genai`) | [`docs/genai_docs/`](docs/genai_docs/README.md) -- vendored SDK reference; web search + Context7 are unreliable for this SDK |
| Schema forms / client state (`frontend/src/schema-forms/`, `frontend/src/shared/`) | `docs/components/schema-forms.md` |
| PDF filling (`backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py`) | `docs/components/pdf-filling.md` |
| Anything logging PII/PHI or audit trails | `docs/standards/hipaa-pii-policy.md` + `docs/standards/confirmation-and-audit.md` |
| VAD / activity signals (`DISABLE_GEMINI_VAD`, `activity_start/end`) | `docs/standards/voice-and-vad.md` |
| Running a measurement/probe experiment against the live app (new `scripts/spikes/*` or `backend/scripts/probe_*.py` work, cost/accuracy/latency sweeps) | [`.claude/skills/experimentation/SKILL.md`](.claude/skills/experimentation/SKILL.md) -- mandatory prior-work audit + pre-spend cost estimate gates before any API call |
| Planning a feature/epic, filing a bead, or model-tiering a task (`/plan-epic`, exit criteria, SPEAR) | [`docs/doctrine/planning.md`](docs/doctrine/planning.md) |
| Session drain/handover hooks (`scripts/drain_flag.py`, PreCompact/SessionStart wiring) | [`docs/doctrine/drain-handover.md`](docs/doctrine/drain-handover.md) |

---

## Top scar tissue (always-relevant lessons)

1. **Beads is the system of record for "what to do next."** Resume work via
   `bd ready` / `bd show <id>`, not by reading a plan file. Pull before reads,
   push after every write. See [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).
2. **Every PR ships through `/closeout`, and BOTH review layers run PRE-PR -- with
   DIFFERENT jobs:** commit, then closeout runs the **fresh-eyes assess loop**
   (Sonnet/Haiku: score the bead's exit criteria, get the LOCAL DIFF right, and
   **enumerate** every changed contract; looped to no-gap at the routed model --
   there is no Opus round here), **then** ONE looped **Opus-5 outer cross-surface
   review** (review-worthy changes only: take that enumeration and follow each
   contract OUT into consumers in untouched files) -- both on the
   LOCAL branch, serial not parallel. Only AFTER both loops clear does closeout open a
   normal PR, close the bead(s), and make the merge decision. **Review is entirely
   Claude-based; there is NO external reviewer** (the maintainer's OpenAI Codex
   subscription ended 2026-07-08). The outer review spawns the
   `cross-surface-reviewer` agent (`model: opus`) on the
   local diff (`origin/dev...HEAD`) and loops to `NO-GAPS` -- **a single clearing
   pass is the gate** (the duplicate confirming pass was retired 2026-08-05: it
   doubled the most expensive step for a marginal catch rate). **Only a BEHAVIORAL
   fix voids a clear** -- filing a bead, a comment/docstring edit, docs prose, or a
   journal entry does not re-run the review. The subagents' STATUS lines are read
   directly -- there is **no bot watcher and no `@codex review` /
   `pr_review_watcher.py` / `requested_reviewers` trigger** (all dead path).
   **Docs-only changes get ONE adversarial HAIKU review** instead (the
   `docs-reviewer` agent -- prose review, not a contract trace); only a genuinely
   TRIVIAL diff skips adversarial review entirely (fresh-eyes `NO-GAPS` is its
   record). Once both clear,
   **one `closeout_finish.py` run opens the PR AND closes the bead(s)** (no two-call
   watcher pattern), then closeout auto-merges a routine low-risk PR or pings the
   maintainer for a consequence-bearing one (see "Auto-merge vs. maintainer merge").
   No draft PRs. See the "Closeout" section below and
   [`docs/doctrine/review-flow.md`](docs/doctrine/review-flow.md).
3. **In a worktree, run every git command via `git -C <worktree-path>`** --
   the shell cwd resets between tool calls; a chained `cd <main-repo> && git ...`
   silently operates on the main checkout. The same trap hits file writes: an
   absolute path into the main repo writes there, not the worktree.
4. **The backend is stateless by design; the client owns all field state.**
   Field values, confirmations, and section state live in the browser's
   `sessionStorage` -- the backend rebuilds context from the WS handshake on
   every (re)connect. Never add server-side per-session field persistence, and
   never log field values/PII/PHI server-side. See the re-orientation brief.
5. **"Section" is the navigation unit; "part" is a real but distinct level.**
   The hierarchy is Form > Parts > Sections > Fields -- *part* is an optional
   grouping of sections, **not** a synonym for section. Don't name section-state
   `current_part_id` / `part_id`. The internal holdouts and the wire-format keys
   are now section-canonical (`polyglot-pdf-gfb.4` + `polyglot-pdf-zun`: token-log
   `section_id`; frontend handshake-manifest keys). The one remaining `part`-named
   holdout is the backend-internal `manifest_service.py` / `ai_context.py`
   SI-text path -- deliberately deferred (renaming changes the Gemini prompt
   wording); the `manifest.parts` navigation key keeps its name because that IS
   the backend wire contract. Full canon (incl. field-id brackets, form-session
   vs session) in
   [`docs/standards/terminology.md`](docs/standards/terminology.md) (`polyglot-pdf-m3f`).
6. **ASCII ONLY in code files.** In `.py` / `.ts` / `.tsx` / `.js` and any other
   source file -- including comments and string literals -- use plain ASCII: `--`
   not an em-dash, `"`/`'` not smart quotes, no emoji. **For Python this is a
   correctness rule:** Windows' default console is cp1252, and non-ASCII glyphs
   in code that reaches `print()`/stdout (or a file opened without an explicit
   encoding) crash with `UnicodeDecodeError` / `UnicodeEncodeError` -- this repo
   has burned multiple beads on exactly that (39a, 6xp, 4ln, hrn.14/16). **For
   the TS/JS frontend** (read as UTF-8 by Vite/Node, so no cp1252 crash) it is a
   consistency rule: one ASCII style across all source. **Markdown/docs are
   exempt** -- Unicode is fine there. Match the surrounding code's existing ASCII
   style.

---

## Critical rules

The rules that override default behavior. Product-specific invariants live in
"Top scar tissue" above; the cross-cutting workflow rules follow.

### Escalation vs. autonomy

**Default to DECIDING. Make the call, then state what you chose and why in one
line.** Asking the maintainer is the rare exception, not the safe fallback.
Escalation runs one level at a time: a subagent escalates to you (the
orchestrator); you escalate to the maintainer -- each only when the level below
genuinely cannot resolve it. **This is an incremental step, not the final word:**
the current goal is narrow -- stop burning tokens and maintainer attention on
trivial, no-consequence asks -- without letting work creep beyond what a bead
authorizes. **The bead is the unit of authorization.** (We will loosen this later
if it over-escalates.)

**`AskUserQuestion` is for decisions you are genuinely BLOCKED on -- never for
confirmation, for sharing a call you've already reached, or for transparency's
sake.** If you find yourself asking to *check* a decision, to *show* your
reasoning, or because a choice feels worth surfacing, that is the over-escalation
anti-pattern: decide it and put it in the merge report's defended-decision list
instead (that list is where you're transparent, at zero blocking cost). The test
is "am I *unable to proceed* without the answer?", not "would the maintainer maybe
want a say?" **One legitimate exception that is NOT over-asking:** when the
maintainer **directly asks you something or tells you to do something** and you are
**genuinely low-confidence about what they meant**, a clarifying question is a fair
*reply* -- clarifying the intent of a direct request is responsiveness, not
escalation. But note the flip side: when the maintainer **delegates a call to you**
("whatever you think", "expand it if it helps", "your call"), **deciding it IS the
response** -- re-asking reads as not listening. Delegated technical calls
(what tags should exist, how to structure a module, which helper to reuse) are
yours the moment they're delegated; do not bounce them back. **Tiebreaker for the
ambiguous middle** ("handle it however makes sense" -- could be a vague direct
request or a delegation): treat it as a **delegation and decide** -- only ask if
you're *also* low-confidence on the underlying intent AND the choice is a step-2
case (a real commitment or product/direction call). Decide-by-default wins the tie.

Run this decision procedure for any choice you face:

1. **Is it on the NEVER list?** -> Don't do it yourself, and don't ask permission
   to do it yourself. You never `git push --force` (the safe `--force-with-lease`
   is likewise reserved for the maintainer). Force-pushing and `bd dolt push
   --force` stay hard-barred regardless of review state.
   - **`gh pr merge` is NO LONGER on the NEVER list** (autonomy increase
     2026-07-04): you MAY merge a PR yourself, but ONLY under the **auto-merge
     rule** below. This is a gated permission, not a blanket one -- merging a PR
     that fails any gate, or a consequence-bearing PR, is the violation. See
     "Auto-merge vs. maintainer merge" immediately below.
   - **Demo deploy is NO LONGER on the NEVER list** (autonomy increase 2026-06-10):
     you MAY run `deploy-demo.sh`, but it is a **per-instance ASK** (step 2 below),
     never standing pre-authorization, and only after the test gates in
     "Deployment / promotion" below. Running it without an explicit per-instance
     yes is the violation.
   - **Syncing the LOCAL ROOT repo to `dev` is autonomous** -- pulling /
     fast-forwarding the main checkout to `origin/dev`, and running the local test
     stack (`scripts/dev-local.ps1` / the `/run-local` skill), need no ask.

**Auto-merge vs. maintainer merge (autonomy increase 2026-07-04).** The maintainer
takes the product-owner seat, not the engineering-lead seat: routine, low-risk PRs
that a **separate model -- including an adversarial one -- has reviewed CLEAN** are
**merged autonomously**, not handed back for a click. You run `gh pr merge` yourself
when **ALL** of these hold:
   - **An adversarial reviewer cleared the diff.** The Opus-5 outer cross-surface
     review returned `NO-GAPS` -- ONE looped clearing pass (see
     [`docs/doctrine/review-flow.md`](docs/doctrine/review-flow.md)). (There is NO
     external reviewer; the maintainer's Codex subscription ended 2026-07-08.) A
     separate, independent model instance, adversarially, found it clean. **This
     condition means the OPUS cross-surface gate specifically** -- a docs-only PR
     cleared by the Haiku `docs-reviewer`, or a trivial PR with no adversarial
     review, does NOT satisfy it and pings (below). (Whether a Haiku-cleared docs
     PR should count is an open question for the maintainer, deliberately left
     undecided by bd polyglot-pdf-saxh; do not widen it autonomously.)
   - **CI / required status checks are green.**
   - **The PR is NOT consequence-bearing** (see the list below).

**Consequence-bearing PRs are STILL the maintainer's merge -- ping, do not merge**
(and usually escalate mid-work per step 2). A PR is consequence-bearing when it:
   - proves the bead's original direction impossible, OR substantially changes a
     maintainer-approved plan;
   - affects **operational costs**;
   - affects **user-facing features**;
   - carries substantial risk of **downstream disruption**;
   - requires **substantial reworking that touches multiple surfaces**.

   This is the SAME line as the step-2 escalation triggers (consequence beyond the
   sprint; product/direction calls) -- the merge boundary and the escalation
   boundary are one line. When a PR is consequence-bearing, pinging the maintainer
   that it is clean and ready for their merge is the handoff that ends closeout (not
   "asking to merge"). When unsure which side of the line a PR is on, treat it as
   consequence-bearing and ping. **Never** merge a PR whose review wasn't CLEAN,
   whose checks are red, or whose adversarial review was not the Opus cross-surface
   gate specifically (a Haiku-cleared docs-only PR, or a trivial PR with no
   adversarial review at all) -- those ping too. (Deliberately conservative while this ramps; it will loosen if it
   over-pings.)
2. **Does it make a longer-term commitment the bead doesn't explicitly call for,
   or is it a product-owner call?** -> Escalate (ask). This is the case you ask:
   - **A longer-term / cross-cutting commitment not explicit in the bead** -- a
     change reaching beyond completing this bead: a new contract other code
     depends on (wire format, API shape, shared schema); a new
     operational/cost/security dependency (a service, datastore, paid API, queue,
     anything needing provisioning or secrets); breaking a documented invariant
     (stateless backend, client-owns-state, PII rules -- see "Top scar tissue");
     or an architectural change **bigger than the small, obvious one clearly in
     service of the bead's instructions**. (That line has a soft edge -- when
     genuinely unsure, escalate; it's deliberately conservative for now and will
     be sharpened once we see which way it errs.)
   - **A product / direction / scope call** -- *what* to build or prioritize, a
     product-or-UX-vs-complexity or cost-vs-quality tradeoff with no obvious
     default. (You are the technical expert; the maintainer is the product owner.)
   - **A bead that is ambiguous, self-contradictory, or proven untenable** -- it
     can't proceed without the owner revising it.

   **Traceability lens (a sharpening of the two triggers above, NOT a new
   trigger).** Every bead traces to a maintainer-approved plan (the epic's `plan:`
   pointer -- see [`docs/doctrine/planning.md`](docs/doctrine/planning.md#plan-traceability)).
   When weighing whether a choice "reaches beyond the bead," a sharper test is:
   **is this derivable from that plan?** A choice that commits to a direction the
   plan *neither states nor implies* is the beyond-bead / product-direction case
   above -- escalate. This lens does **NOT** widen what escalates: implementation,
   internal structure, naming, helper reuse, PR shaping, and process mechanics
   remain **decide-by-default and yours** (step 3 below) even though no plan line
   spells them out. "Not literally in the plan" is not the test -- "commits to a
   *direction* the plan didn't authorize" is. When unsure which, the consequence
   Test in step 3 governs; decide-by-default wins ties.

   **When you DO escalate, isolate the kernel -- never staple a decidable question
   onto a genuine one.** (This is a *how-to-escalate* rule, not a fourth trigger.)
   Ask ONLY the irreducible part. Do not bundle a step-3 decide-it-yourself choice
   into the same ask "while you're here" -- decide that part, and escalate only the
   kernel. (E.g. *"which beads to pick + how to bundle them"* is yours; if the real
   question is whether a marker bead is stale, ask only that.)

   - **Exception -- scope creep: file a bead, don't ask.** If you notice
     worthwhile work *beyond* the bead's scope that **isn't itself a decision the
     maintainer needs to make now** (if it is, escalate it per step 2 instead),
     do NOT ask and do NOT silently expand the bead -- **file a new bead** (via a
     pull/push-bracketed `bd create`; `bd_safe.py` has no `create` subcommand) and
     continue. **For out-of-scope work that is NOT itself a step-2 case, deciding
     *whether* it happens is a decide-or-file call, never an ask** -- the bare
     "should I also do X?" (where X is small/reversible) is the anti-pattern: fold
     it in (if trivially in service of the bead), file a bead, or skip it, and note
     which. This does **not** override the step-2 carve-out above: if X is itself a
     longer-term commitment or a product/direction call, it escalates like any
     other step-2 item -- "it's out of scope" is not a loophole around step 2.
3. **Everything else -> DECIDE it yourself, and note the call.** The common path:
   implementing the bead/plan as written, plus trivia with no consequence beyond
   this sprint. Explicitly includes:
   - **Implementation / internal structure** -- module and function
     decomposition, naming, which existing helper to reuse, where code lives,
     data structures, local refactors, test structure, and small architectural
     changes obviously required to carry out the bead. (Textbook "architecture"
     at this scale is YOURS; only the bigger, beyond-the-bead commitments in
     step 2 escalate.) **This includes the *form* of an artifact when the bead is
     silent on it** -- doc vs. machine-readable config, file layout, which section
     a rule lives in. A bead that says "tag files high/med/low" without naming the
     format leaves the format to YOU; pick the reversible default and note it, do
     not ask.
   - **PR shaping** -- bundle small changes, nits, and few-line fixes into one PR
     to save tokens; split when a bead turns out more complex than expected or
     when bundling would hurt reviewability (split on the fly). Also branch
     basing/stacking and rebase strategy.
   - **Process mechanics** -- plan-first vs. build-directly; which of several
     equally-good ready beads to pick next; nit-vs-blocker triage (per the
     closeout rule); commit granularity; worktree placement; doc/journal/test
     mechanics.
   - **The consequence Test -- apply to EVERY choice before even considering an
     ask** (this is the pre-ask filter; do not skip it). *Does this choice have any
     practical effect beyond completing this bead this sprint?* If no -> decide and
     note it; you are done, do not ask. If unsure, **prefer the reversible option,
     prefer staying within the current bead, decide, and note it** -- a noted
     decision the maintainer can correct later is cheaper than a blocking question.
     A low-consequence choice never clears this Test into an ask, even with no
     single obvious default: "no obvious default" + "no consequence beyond the
     sprint" still means **you pick** (reversible default) and note it.
     **Order of operations:** check step 2 FIRST -- if the choice is a step-2 case
     (a real commitment or a product/direction call), it escalates *regardless* of
     how small its immediate consequence looks; the Test only governs choices that
     are NOT step-2 cases. The "no obvious default" in step 2 (a product tradeoff)
     and the "no obvious default" here (a low-stakes pick) are different animals:
     step 2 escalates, the Test decides. Never use the Test to reclassify a genuine
     product/direction call as "low-consequence" to avoid escalating it.

**Escalating is a hard STOP -- so defer it until nothing further can be done
without the answer.** Asking the maintainer a blocking question ends your turn and
halts the process entirely: you cannot poll for whether they're present, wait an
open-ended amount of time, or keep working "in the background" while a question is
pending (resuming would need a fresh agent the maintainer starts later). Because the
stop is total, **don't escalate the moment a question arises.** When you hit
something that needs the maintainer, keep going on everything that does *not* depend
on the answer: finish the independent work, commit/park it cleanly (never leave it
half-edited), and resolve anything you discover you can actually decide yourself.
The trigger to ask is a **dependency** condition, not a position in the task: you
escalate once you've reached the point where **nothing further can proceed without
the answer** -- which may come early (everything downstream needs the decision) or
late (lots of independent work remained). Often, by working up to that point, the
apparent blocker shrinks or several questions accumulate into one stop instead of
three. Then ask -- with a clear note of exactly what you need decided -- and stop.
The work still stops at the ask; the point is that **as much as possible is already
done** when it does, so the maintainer's one reply unblocks the most. Never
best-guess a product/direction call just to avoid the stop. **A question that
arises before you've started the work is almost never blocking yet** -- resist the
urge to front-load a batch of questions at kickoff; start the independent work
first, and most "questions" dissolve into decisions or answer themselves. (The one
"almost": a step-2 question on which *literally everything* downstream depends --
the bead itself is ambiguous/untenable and no independent work exists to do first.
That is genuinely blocking at kickoff; a low-consequence pick or a question with
*any* independent work ahead of it is not.)

**The PR / merge report is the maintainer's standing checkpoint AND the audit
surface for this rule.** Write it for the product owner, not an engineer: **plain
language, no jargon or acronyms** -- a real overview of what got done and why, and
then **LIST each autonomous decision you made and briefly DEFEND it** (what you
chose, and why it was yours to decide rather than escalate). The maintainer
reviews every merge, so this defended decision list is where they catch anything
**decided that should have been escalated** -- the real risk of widening autonomy.
Make the decisions easy to scan; do not bury them.

### Communication with the maintainer (in-session messages and questions)

This rule covers status updates, questions, and anything you say to the
maintainer during a session. For the PR merge report specifically, see the
guidance at the end of "Escalation vs. autonomy" above.

**Assume the maintainer is juggling other work and hasn't read this session.**
Write every message so it can be understood cold, without scrolling back through
the conversation.

**Three rules:**

1. **Lead with context, not details.** Start with: What is this about? What
   task or bug triggered this? Why does it matter? Then state your question or
   status in one sentence. Details follow after.

2. **Use plain language, and spell out anything the maintainer can't look up.**
   This means two things: (a) never use a bead ID without a plain-English label
   -- not "zun.4" but "task zun.4 (the fix for the WebSocket naming mismatch)";
   (b) never use domain jargon, experiment shorthand, or metric names without
   explaining what they mean in plain terms. If a sentence would confuse someone
   who hasn't been in this session, rewrite it.

   Bad: "The honest geometric-sweep caveat repeatably costs ~1.5 F1 and ~doubles
   spurious fields on (a), but the best (b) relationship-recall runs came from
   it. Which framing should be the default in the trimmed pass?"

   Good: "The form has fields laid out in two columns. The script lists them in
   a rough top-to-bottom sweep, but that sweep jumps between columns in a way
   no human would read. I tested two ways of telling the AI about this: warning
   it that the order is unreliable, vs. just calling it 'reading order' without
   comment. With the honest warning: accuracy at identifying which fields are
   related went up slightly (~2%), but basic extraction got worse -- the AI
   created roughly twice as many duplicate/junk fields. Neither effect is large.
   Which approach should be the default?"

3. **Don't sacrifice clarity for brevity -- but don't pad either.** If context
   and explanation require three paragraphs, write three paragraphs. The goal is
   that the maintainer can understand and respond without a follow-up question.
   A clear three-paragraph message beats a dense one-liner. But if the message
   is clear in two sentences, two sentences is right.

### Task tracking
- Beads (`bd`) is the canonical tracker. Pull-before-read, push-after-write.
  Full cadence: [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).

### Planning + model tiering (SPEAR)
- **Plan features per-epic, not per-bead.** A whole feature is scoped + planned
  up front via `/plan-epic` (orchestrator-owned): probe the Why, challenge the
  How, draft a 2-5 criterion exit rubric, MECE-decompose, gate on maintainer
  approval. **Every code-change bead carries a `## Exit criteria` section in its
  body** (1-3 binary criteria), written at creation time; `/next-bead` retrofits
  any that slipped at claim time. Doctrine: [`docs/doctrine/planning.md`](docs/doctrine/planning.md).
- **Model tiering: expensive models at decision gates ONLY -- never bug-hunting
  or grepping.** Fable/Opus for Plan / escalation / Resolve; Sonnet for execution
  + the fresh-eyes assessor; Haiku/Explore for search + mechanical glue. The
  orchestrator delegates search and keeps the conclusion.

### Deployment / promotion
- **Flow:** worktree -> local test server (`scripts/dev-local.ps1`, via
  `/run-local`) -> `dev` -> demo remote server (`deploy-demo.sh`). **There is NO
  active prod** for this project. Details:
  [`docs/doctrine/promotion-tiers.md`](docs/doctrine/promotion-tiers.md).
- **Demo deploy (`deploy-demo.sh`) is gated by ALL THREE (autonomy increase
  2026-06-10):**
  1. **Local test FIRST.** Start the local stack (`scripts/dev-local.ps1`) and
     actually EXERCISE the specific change working there -- behavioral
     verification, not just "the server boots."
  2. **Explicit per-instance permission.** Ping the maintainer and get a "yes"
     BEFORE each `deploy-demo.sh` run. This is NOT standing pre-authorization --
     every deploy is its own ask, every time. (You may run the deploy; you may
     never run it without that specific yes.)
  3. **Post-deploy test-drive.** After deploying, test-drive the LIVE demo to
     confirm the change actually works there -- the deploy isn't "done" until the
     running demo is verified.
- **Syncing the local root repo to `dev`** (pull / fast-forward the main checkout
  to `origin/dev`) is autonomous -- no ask. Merging a PR INTO `dev` is autonomous
  ONLY under the auto-merge rule (adversarial-review CLEAN + green checks +
  not consequence-bearing -- see "Auto-merge vs. maintainer merge" in Critical
  rules); a consequence-bearing PR is still the maintainer's `gh pr merge`.

### Doc maintenance
- Tier-1 and tier-2 docs are CURRENT STATE ONLY -- no `Previously:` chains, no
  history sections. The journal is the chronological record. Mechanically
  enforced by `scripts/check_doc_freshness.py`. Full rules:
  [`docs/doc-architecture.md`](docs/doc-architecture.md).

---

## Closeout -- mandatory, once per PR

**Every PR ships through the `/closeout` skill. No PR is "done" until closeout has
run on it to clean.** Run `/closeout` **once per PR**, not once per bead.

**Do NOT ask "should I run closeout?" -- just run it.** When the bead is complete
and the pre-PR fresh-eyes assess loop is no-gap, running closeout is the obvious
next step, not a decision the maintainer needs to weigh in on (maintainer directive
2026-07-04: "I don't want to be asked that"). Asking to close out is the
over-escalation anti-pattern -- decide it and proceed. (If something in the work
itself is genuinely blocking -- a step-2 product/direction call -- escalate *that*
specific thing, but that is never phrased as "should I closeout?".)

**Bead/PR contract:** every PR closes **at least one** bead (never zero). A bead
must **not** span multiple PRs -- if a bead would need more than one PR, split it
into multiple beads first. But a PR **may bundle several whole beads** when they're
individually too small to each warrant a full PR cycle (a separate cycle per tiny
bead wastes review resources). So: one bead = exactly one PR; one PR = one or more
whole beads. Closeout closes **all** beads the PR resolves.

Do NOT hand-roll the review cycle. In particular:

- **`/closeout` OWNS PR creation.** Finish the work, commit until the tree is
  clean, *then* invoke `/closeout` -- it opens the **normal** (non-draft) PR
  itself. **Do not `gh pr create` first** (a manually-opened PR breaks the skill's
  review setup and tempts hand-polling).
- **The Opus-5 outer review handles review-worthy changes PRE-PR -- there is NO
  external reviewer.** Review is entirely Claude-based (the maintainer's OpenAI Codex
  subscription ended 2026-07-08; Codex succeeded Copilot at the earlier
  credit-exhaustion cutover, bd hrn.8/hrn.9 -- both retired). The orchestrator
  judges whether the diff can regress runtime behavior; if so, closeout runs
  the outer review ON THE LOCAL BRANCH, before the PR opens: it spawns the
  `cross-surface-reviewer` agent (`model: opus`) on the local diff
  (`origin/dev...HEAD`) and loops it to `NO-GAPS`. **That single clearing pass is
  the gate**, and only a BEHAVIORAL fix voids it.
  There is **no `@codex review` trigger, no `pr_review_watcher.py`, and no
  `requested_reviewers` reviewer API** -- all dead path. Docs-only / `.beads`-only /
  journal-only / trivial changes get NO outer review.
- **The outer review's subagents are read directly, never watched by a script.**
  Closeout reads each Opus reviewer's `NO-GAPS` / `GAPS-FOUND` STATUS line straight
  from the subagent result -- there is no GitHub bot to poll, so the old
  `pr_review_watcher.py` background-watch loop does not run for the outer review.
  Never treat a subagent TIMEOUT/ERROR (no verdict returned) as clean -- surface it.
- **If a subagent spawn dies with the effort-400, fall back to a one-agent Workflow**
  (standing permission, maintainer directive 2026-07-27). Subagents inherit the
  SESSION's effort setting, which you cannot read; from a Fable session at `xhigh`,
  an Agent-tool spawn of a non-Fable model fails with `400 output_config.effort
  'xhigh' is not supported when thinking is disabled on this model.` **That is a
  transport failure, not a review failure** -- it is not a `BLOCKED` verdict, it is
  not the "subagent ERROR" case that escalates, and it does not justify downgrading
  the reviewer to a cheaper model. Retry the SAME single spawn wrapped in a
  one-agent Workflow whose `agent()` passes `effort: 'high'` (the Workflow tool
  exposes an `effort` option the Agent tool lacks). **This standing permission
  covers a single-agent wrapper only** -- real multi-agent orchestration still
  requires an explicit per-instance go-ahead. **Applies to ANY blocked subagent
  spawn at any model and any step** (the closeout fresh-eyes rounds at
  haiku/sonnet, the Opus outer reviewer, and the Haiku `closeout-runner`), not
  just the reviewer. **If the wrapped retry ALSO
  fails, that is a genuine stop** -- surface it. Remove once the upstream bug is
  fixed.
- **BOTH review layers run PRE-PR, serial not parallel** (closeout Steps 5.5 + 5.6):
  the fresh-eyes assess loop first (scored against the bead's exit criteria,
  re-spawned until no gap at the routed haiku/sonnet model), THEN the ONE Opus outer
  cross-surface review (review-worthy changes only, looped until it clears),
  all on the local branch with fixes committed. Only after both clear does the PR
  open.
- Once both reviews are `NO-GAPS`, **one `closeout_finish.py` run opens the PR AND
  closes the bead(s)** the change resolves (no two-call watcher pattern), and closeout
  then **either auto-merges or pings**, per the auto-merge rule (see "Auto-merge vs.
  maintainer merge" in Critical rules): a routine, low-risk PR that the adversarial
  Opus outer review cleared with green checks is **merged autonomously**
  (`gh pr merge`); a **consequence-bearing** PR is instead handed to the maintainer
  with a "clean and ready to merge" ping. Force-pushes and `bd dolt push --force`
  remain barred either way.

The full checklist (beads housekeeping, doc-freshness, journal entry, tests, the
pre-PR fresh-eyes assess loop + the PR + the Opus outer-review loop) lives in
[`.claude/skills/closeout/SKILL.md`](.claude/skills/closeout/SKILL.md) -- that
skill is the source of truth; this section just makes running it **non-optional,
once per PR.**
