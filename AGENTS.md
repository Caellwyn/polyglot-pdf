# AGENTS.md -- polyglot-pdf

**Context file for OpenAI Codex (and other AGENTS.md-aware coding agents).**
This is the Codex-convention sibling of [`CLAUDE.md`](CLAUDE.md) (which Claude
Code reads). The two intentionally point at the **same** canonical docs rather
than duplicating them -- keep this file lean and let the linked docs carry the
detail, so the two agent-context files can't drift apart.

> **Reviewing a PR, not editing the repo?** Skip straight to the
> [**"If you are reviewing a PR" section**](#if-you-are-reviewing-a-pr) at the
> bottom -- those are your behavior rules. The rest of this file is codebase
> context for agents that *edit* the repo.

---

## What this is

**polyglot-pdf** is a voice-driven, multilingual form-filler for complex PDFs
(immigration/legal intake). A browser SPA streams the user's voice over a
WebSocket to a **stateless** FastAPI backend, which proxies a **Gemini Live**
session that drives form-filling through tool calls. All field state lives on
the client (`sessionStorage`); PDF rendering is a separate HTTP call (PyMuPDF).

Stack: React + TypeScript (Vite) frontend on **Firebase Hosting**; Python/FastAPI
backend on **Cloud Run** (co-located with Gemini). Deploy is **local/manual**
(`deploy-demo.sh` / `deploy-production.sh`).

Entry points:
- Backend: `backend/main.py`, WebSocket route `backend/routes/websocket_routes.py`,
  Gemini adapter `backend/adapters/live_ai_gemini.py`.
- Frontend: `frontend/src/`, WS config `frontend/src/shared/config.ts`.

For the full verified architecture, read the re-orientation brief:
[`docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md`](docs/journal/entries/2026-05-30-bd-j2l-reorientation-brief.md).

---

## Where the real docs are

The canonical doc map is [`docs/INDEX.md`](docs/INDEX.md) -- **start there.**
The full project rules are in [`CLAUDE.md`](CLAUDE.md); everything in CLAUDE.md's
"Critical rules" and "Top scar tissue" sections applies to you too. The
highest-value invariants to know before touching code:

- **The backend is stateless by design; the client owns all field state.** Never
  add server-side per-session field persistence, and **never log field
  values / PII / PHI server-side.** See `docs/standards/hipaa-pii-policy.md`.
- **"Section" is the navigation unit; "part" is a distinct level.** Hierarchy is
  Form > Parts > Sections > Fields. Don't conflate them. Canon:
  `docs/standards/terminology.md`.
- **The `google-genai` SDK syntax is vendored in
  [`docs/genai_docs/`](docs/genai_docs/README.md)** -- trust it over training
  data / web search / Context7, all of which are unreliable for this SDK.
- **Beads (`bd`) is the issue tracker / system of record**, not a plan file.

| Before changing... | Read |
|--------------------|------|
| WebSocket routing / handshake | `docs/components/websocket-routing.md` |
| Gemini Live adapter, tools, models | `docs/components/voice-ai.md` + `docs/standards/ai-models.md` + `docs/genai_docs/` |
| Schema forms / client state | `docs/components/schema-forms.md` |
| PDF filling | `docs/components/pdf-filling.md` |
| Anything logging PII/PHI | `docs/standards/hipaa-pii-policy.md` |

---

## Building / testing

The Python interpreter is the backend venv, which lives **only** in the main repo
at `backend/.venv` (git worktrees do NOT have their own venv). Run the backend
test suite with `PYTHONPATH` at the repo root:

```bash
PYTHONPATH=. backend/.venv/Scripts/python.exe -m pytest backend/tests/ -q   # Windows
# macOS/Linux: PYTHONPATH=. backend/.venv/bin/python -m pytest backend/tests/ -q
```

The live-Gemini `external` test is flaky; exclude it with `-m "not external"`
unless you are specifically exercising the real adapter.

---

## If you are reviewing a PR

**This section applies ONLY when your task is to review a pull request.** If you
are editing or writing code, ignore it -- the rest of this file is your context.

You are configured as a **review-only** agent on this repo. Your job is to find
issues and report them as comments; the PR author runs a downstream code agent
that reads your suggestions and decides what to apply.

### Never commit, push, rebase, or merge

**Never** commit changes, push, force-push, rebase, merge, or otherwise mutate any
branch on your own initiative -- including the PR branch you're reviewing, even
when you find a clear bug or a failing test you "could just fix in one line."
**Comment only.** Committing directly breaks the author's ability to rebase/amend
cleanly, can conflict with their in-progress work, muddies review history, and
turns a reviewable finding into a silent fix nobody checks.

Tempting cases that are still comment-only: an unrelated test failing on
`dev`/`main` (comment, don't fix); a finding with an "obvious" one-line fix
(suggest it in the comment body); being asked to "look at" / "review" / "check"
something (that authorizes a comment, not a commit).

**The one and only exception:** a direct, unambiguous instruction from the author
in the PR to commit -- phrasing like "@codex please commit a fix for X." If
there's any doubt whether you were told to commit, you were not.

### Always post a top-level summary comment -- every round, findings or not

After finishing a review on a PR targeting `dev`, you **MUST** post a top-level
summary comment **on every round, with no exceptions** -- even with zero findings,
even when a prior round's findings are all addressed. **Why it's non-negotiable:**
the author runs an automated agent that polls for your review. A silent finish (no
comment, no state change) is **indistinguishable from "I never reviewed it,"** so
the agent waits forever. Your top-level comment IS the "review finished" signal.

- **One or more findings:** post your file-level comments **AND** a top-level
  summary, then **assign the PR to `@caellwynai-josh`** so the follow-up agent
  picks it up.
- **Zero findings (satisfactory):** **Approve** and add the 👍 (`+1`) reaction to
  your top-level summary comment -- the 👍 is the **canonical approval signal** the
  author's polling agent reads. Your usual "Didn't find any major issues" summary
  is fine as the comment body. Do **not** assign -- there's nothing to follow up.
- **Round 2+ with all prior findings addressed:** same as zero-findings -- approve
  with the 👍 reaction. Do **not** instead write a sentence like "the prior findings
  are now resolved" *without* the 👍; the reaction is what the matcher keys on.

The watcher recognizes approval from the 👍 reaction first; it also accepts the
"Didn't find any major issues" text or an exact `LGTM` as fallbacks, so a clean
review is never missed. Prefer the 👍 -- it's the canonical, language-independent
signal.

### PRs into `main`

PRs with base `main` are closeout/promotion merges from `dev`: **do not assign**
regardless of outcome, but **still leave a top-level comment** so the author knows
you reviewed. The rule in one line: **assign only on `dev` PRs with findings;
comment always, everywhere.**

> **Maintainer note (not a reviewer instruction):** the closeout flow watches bot
> reviews with `scripts/pr_review_watcher.py` (`--reviewer copilot|codex`, default
> `copilot`; flips to `codex` at the cutover, bead `polyglot-pdf-hrn.9`). For Codex
> the watcher classifies CLEAN from the 👍 (`+1`) reaction first (the canonical
> signal; read from the comment's inline `reactions` rollup, no extra API call),
> then falls back to the "Didn't find any major issues" text or an exact `LGTM`. An
> inline finding always outranks a 👍, so a 👍 can't mask a real ask.
