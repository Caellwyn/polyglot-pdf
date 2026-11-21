---
date: 2026-11-21
bead: polyglot-pdf-k914j
title: "Sim-harness and closeout-script follow-ups from the 3.8 benchmark (qgw48, my0xl, ya4vi.4, k914j)"
tags: [harness, testing, doctrine]
---

## Trigger

Follow-up beads filed during the 3.8 sim-user benchmark (bd `15j9v`) and its
two PRs (#938, #939). The maintainer asked for the follow-ups to be worked.
This PR carries the four that touch only measurement tooling and the closeout
script:
- `qgw48`: gTTS retry sleeps could freeze a live session's event loop;
- `my0xl`: the sim-user turn record lost the actor's own verdict on a referee
  override, and meta.json had no referee count;
- `ya4vi.4`: the referee could confirm a read-back that contained the true
  value but stored a wrong one;
- `k914j`: closeout_finish rebased a pushed, merge-updated branch (push
  rejected), and accepted `--bead a,b` as one id.

## What changed

- **gTTS off the event loop.** Async callers in
  `measure_form_session_costs.py` now await `synth_off_loop`
  (`asyncio.to_thread(synth_cached, ...)`). An AST test pins that no
  `async def` calls `synth_cached` / `_gtts_mp3` directly.
- **Actor verdict recorded.** Every `user_turns` entry carries `actor_move`
  and `actor_field_key` (pre-referee) and `referee_veto`. meta.json's
  `sim_user` projection is now `project_sim_meta` over `META_SIM_USER_KEYS`,
  which includes `referee_overrides`.
- **Stored-value gate on the referee.** `reject_to_confirm` stands only when
  the field's stored client value is right by the run's strict key
  (`SimDriver._stored_is_true`, using the scorer's own comparison, now
  factored out as `value_matches_expected`, so an any-of rendering such as
  "USA" counts). Otherwise the actor's reject stands and the
  turn is marked `referee_veto: stored_value_wrong`. Tests cover the
  extra-token case ("Ana Zebulon") and the cross-field summary case.
- **Push-safe pre-push sync.** `closeout_finish.rebase()`:
  - skips the sync when `origin/<base>` is already in HEAD;
  - merges the base into a branch that already exists on origin;
  - rebases only a never-pushed branch;
  - fails closed when `ls-remote` cannot tell.

  `--bead a,b` is split before any side effect. The conflict-resolution prose
  in SKILL.md, `docs/doctrine/review-flow.md` and `closeout-runner.md` now
  finishes or aborts the sync the way the script ran it (merge or rebase).

## Lessons

- **A fake that cannot hear a correction looks like a hung test.** The first
  stored-value-gate test looped to the 500-turn cap: the gate correctly kept
  rejecting, but the fake model only understood an answer said in full, not a
  spelled correction ("A - N - A"). A capped `max_user_turns` trace found it
  in one run. When a new sim-driver test hangs, trace 15 turns before
  suspecting the production change.
- **Bash heredocs halve backslashes (again).** A `\n` inside a Python patch
  written through a heredoc became a real newline in three string literals.
  `ast.parse` after every scripted edit caught it before any test ran.

- **Gate a judge with the scorer's own comparison.** The first stored-value
  gate compared against the persona's single true value. Fresh-eyes flagged
  that 10 fields have any-of keys, so a correct "USA" would have been vetoed
  and the reject loop the referee exists to break could return. When one
  judge vetoes another, reuse the final scorer's predicate, not a simpler
  copy.
- **Changing a script's behavior changes every procedure that describes
  it.** The Opus pass found three docs still saying `git rebase --continue`
  / `--abort` for what is now sometimes a merge. Grep the prose for the old
  verb, not just the code for the old call.
- **Out of scope, filed:** `polyglot-pdf-cpjm5` (rescore_fill_accuracy.py
  re-implements the scorer without the checkbox rule, pre-existing). Not
  changed: `.claude/settings.json` has no allow entry for `git merge
  --abort` (permission settings are the maintainer's).

## Doc freshness

- `.claude/skills/closeout/SKILL.md`, `docs/doctrine/review-flow.md`,
  `.claude/agents/closeout-runner.md`: sync and conflict-resolution prose.
- No tier-2 doc tracks the spikes harness or `closeout_finish.py`.

## Files touched

- `scripts/spikes/measure_form_session_costs.py`
- `backend/tests/unit/test_sim_user_harness.py`
- `scripts/closeout_finish.py`, `tests/test_closeout_finish.py`
- `.claude/skills/closeout/SKILL.md`, `.claude/agents/closeout-runner.md`,
  `docs/doctrine/review-flow.md`
