---
date: 2026-11-18
bead: polyglot-pdf-hfhtp
title: "cost(claude-cli): strip ANTHROPIC_API_KEY from every claude CLI spawn so it stays on the subscription"
tags: [conventions, testing]
---

## Trigger

The maintainer set `ANTHROPIC_API_KEY` machine-wide so the sim-user Haiku
actor (epic `polyglot-pdf-ya4vi`) could use the Claude API. Other projects of
theirs use the same key.

The Opus cross-surface review of PR #917 found a side effect. The repo's
"free" provider paths run the local `claude -p` CLI, which normally signs in
with the maintainer's subscription. When `ANTHROPIC_API_KEY` is in its
environment, though, the CLI uses the key and bills the metered API instead.
Every one of those spawns inherited the full environment.

The maintainer weighed two options: renaming the variable, or stripping it in
the repo. They chose stripping it ("so we don't interrupt the other projects").

## What shipped

- **New helper.** `claude_cli_env()` returns a copy of `os.environ` without
  `ANTHROPIC_API_KEY`. All five spawn sites now pass it as `env=`:
  - `backend/adapters/text_ai_claude_cli.py::_run_cli` (the local schema editor's translation and guidance path);
  - `backend/scripts/probe_secretary_recall.py::_judge_case` (imports the adapter's helper);
  - `scripts/bakeoff/llm_providers.py::ClaudeCliProvider.run` and `::run_json_claude_cli` (the default extractor, also reached from the schema editor via `extract_form.py`);
  - `scripts/bakeoff/order_probe.py::ask_order`.
- **Where the helper lives.** It is defined in three modules. This mirrors the
  repo's existing per-module `windowless_creationflags()` pattern, because the
  bakeoff scripts run standalone and do not import `backend`.
- **The guard test.** `backend/tests/unit/test_claude_cli_subscription_env.py`
  pins the SET (scar #8):
  - An AST scan over git-tracked `backend/` and `scripts/` finds every
    function that both resolves `shutil.which("claude")` and spawns a
    subprocess.
  - The discovered set must equal the five expected sites, and each spawn must
    pass `env=claude_cli_env()`.
  - Each helper is checked behaviorally.
  - Two real entry points are driven with `subprocess.run` captured.
- **Mutation verification** (scar #9). I removed the `env=` from each of the
  five sites in turn, and also turned the helper's `pop` into a no-op. All six
  mutations went red.
- **Reviews:**
  - Haiku fresh-eyes self-escalated (a shared helper is used across modules).
  - Sonnet fresh-eyes: NO-GAPS. Its independent repo-wide re-enumeration,
    covering `.ts`, `.sh`, `.ps1`, `os.system` and asyncio spawns, found no
    sixth site.
- **The live check (exit criterion 2) was blocked at first.** The `claude` CLI's
  own OAuth login on this machine had expired ("OAuth session expired and could
  not be refreshed"). So since the key was set, these paths could only have run
  by billing the API key. With the key stripped they fail until the maintainer
  runs `claude` -> `/login` again.

## Lessons

- A machine-wide credential changes the behavior of every program that reads
  it, including ones nobody connected to it. Before suggesting a machine- or
  user-scope env var, ask which other tools read that exact name.
- A "free" path can stop being free without any code change. The CLI picks its
  auth from the environment, so the spawn site, not the CLI, is where the
  billing route has to be pinned.

## Doc freshness

None of the touched files is tracked by a component or standards doc. The
docs prep flagged as stale were already stale on `origin/dev` and track other
files. No doc describes the CLI's environment handling.

## Files touched

- `backend/adapters/text_ai_claude_cli.py` (helper + `_run_cli` env)
- `backend/scripts/probe_secretary_recall.py` (import + `_judge_case` env)
- `scripts/bakeoff/llm_providers.py` (helper + two spawn envs)
- `scripts/bakeoff/order_probe.py` (helper + `ask_order` env)
- `backend/tests/unit/test_claude_cli_subscription_env.py` (new)
