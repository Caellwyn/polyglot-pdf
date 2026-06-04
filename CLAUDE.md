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
separate commit. The tier-2 docs below are being populated under the docs-reorg
epic (`polyglot-pdf-gfb`); until each lands, fall back to the cited code path.

| Before changing... | Read |
|--------------------|------|
| WebSocket session routing / handshake (`backend/routes/websocket_routes.py`) | `docs/components/websocket-routing.md` |
| Gemini Live adapter, tools, models (`backend/adapters/live_ai_gemini.py`, `backend/config.py`) | `docs/components/voice-ai.md` + `docs/standards/ai-models.md` + [`docs/genai_docs/`](docs/genai_docs/README.md) (authoritative SDK syntax) |
| Context-window compression / session cost+duration bounding (`ContextWindowCompressionConfig`) | `docs/components/context-compression.md` |
| Anything calling the `google-genai` SDK (`from google import genai`) | [`docs/genai_docs/`](docs/genai_docs/README.md) -- vendored SDK reference; web search + Context7 are unreliable for this SDK |
| Schema forms / client state (`frontend/src/schema-forms/`, `frontend/src/shared/`) | `docs/components/schema-forms.md` |
| PDF filling (`backend/routes/pdf_fill_routes.py`, `backend/services/form_kits.py`) | `docs/components/pdf-filling.md` |
| Anything logging PII/PHI or audit trails | `docs/standards/hipaa-pii-policy.md` + `docs/standards/confirmation-and-audit.md` |
| VAD / activity signals (`DISABLE_GEMINI_VAD`, `activity_start/end`) | `docs/standards/voice-and-vad.md` |

---

## Top scar tissue (always-relevant lessons)

1. **Beads is the system of record for "what to do next."** Resume work via
   `bd ready` / `bd show <id>`, not by reading a plan file. Pull before reads,
   push after every write. See [`docs/doctrine/workflow.md`](docs/doctrine/workflow.md).
2. **Every PR ships through `/closeout`:** commit, then closeout opens a normal
   PR and runs fresh-eyes, **requesting Copilot in parallel only when the PR is
   review-worthy.** Copilot review is OPT-IN since 2026-06-01 (metered per-token,
   finite monthly credits) -- auto-review is OFF, so a review fires only when a PR
   COMMENT contains `@copilot please review` (the trigger is chained into the
   create call -- one Bash turn, not a body line); docs/beads/journal-only PRs skip it.
   Then closeout loops Copilot to clean and the maintainer merges. No draft PRs;
   never hand-poll Copilot. See the "Closeout" section below and
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
   `current_part_id` / `part_id`. The internal holdouts have been renamed
   (`polyglot-pdf-gfb.4`); the only remaining `part` drift is on the **wire format**
   (the token-log payload key + the WS-handshake manifest keys), sequenced against
   consumers under `polyglot-pdf-zun`. Full canon (incl. field-id brackets,
   form-session vs session) in
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
   to do it yourself. You never `git push --force`, never deploy to any
   environment, and never run `gh pr merge`. The maintainer gates all deployment
   and clicks every merge; dev merges go through PR + review. (Deliberately
   conservative while autonomy ramps up.) **Pinging the maintainer that a PR is
   ready for them to merge is NOT "asking to merge"** -- it's the handoff that ends
   closeout, and it stays required (see "Closeout" below).
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

## Closeout -- mandatory, once per PR

**Every PR ships through the `/closeout` skill. No PR is "done" until closeout has
run on it to clean.** Run `/closeout` **once per PR**, not once per bead.

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
  parallel-review setup and tempts hand-polling).
- **Copilot review is OPT-IN -- request it only for review-worthy PRs.** Auto-review
  on open is OFF (metered credits). The orchestrator judges per-PR whether the diff
  can regress runtime behavior; if so, it puts `@copilot please review` in the PR
  BODY (not a comment -- that wastes a turn). Docs-only / `.beads`-only /
  journal-only / trivial PRs get NO trigger and skip the watch loop. With auto-review
  off, each re-review must also be explicitly requested via `@copilot please review`.
- **Copilot is watched by a script, never by hand.** For a review-worthy PR,
  `/closeout` launches `scripts/pr_review_watcher.py <pr#>` via `run_in_background`; the
  harness wakes you once with the classified verdict -- one of `CLEAN`/`COMMENTS`
  (both exit 0), `ERROR` (exit 1), or `TIMEOUT` (exit 2). Never treat
  `ERROR`/`TIMEOUT` as clean. **Never poll `gh api .../comments` yourself** -- that's
  the expensive manual loop the watcher exists to replace, and hand-polling silently
  misses feedback.
- **Fresh-eyes runs in parallel** with Copilot round 1 (and runs even when Copilot is
  skipped); you fix the COMBINED findings, push once, and **loop Copilot until it
  reports `CLEAN`.**
- Closeout then **closes the bead(s)** the PR resolves and **pings the maintainer
  to merge** -- it never merges (that's the maintainer's).

The full checklist (beads housekeeping, doc-freshness, journal entry, tests, the
PR + dual review loop) lives in
[`.claude/skills/closeout/SKILL.md`](.claude/skills/closeout/SKILL.md) -- that
skill is the source of truth; this section just makes running it **non-optional,
once per PR.**
