---
date: 2026-06-04
bead: polyglot-pdf-j47
title: "Remote bootstrap: reliable proxy sync + fail-loud freshness gate (no more silent stale store)"
tags: [postmortem, harness]
---

## Trigger

`bd polyglot-pdf-j47`. A fresh remote session (branch `claude/beautiful-faraday`,
based on dev AFTER the `0q8` reconcile fix merged) filed a detailed error report:
it was served a **stale 30-issue snapshot** while the SessionStart bootstrap
printed `hydrated (30 issues). Done.` -- a SILENT failure. `bd dolt pull` failed
(`Error 1105: no remote`) or hung ~180s, so the live ref (124 issues) was never
loaded; `bd ready` listed already-done beads (`daa`, the `gfb` epic, `j2l`) as
open.

## Why `0q8` was necessary but not sufficient

The `0q8` reconcile rebases the working branch onto `origin/main` -- but only if
`origin/main` was actually fetched. In that container bd's **dolt-native** sync
never populated it, so reconcile found no ref and silently no-op'd. The deeper
root cause (which the report nailed): bd's dolt sync targets the **unreachable
public `sync.remote` github URL** (and/or a snapshot-baked dolt remote on a dead
rotated port), while the data is reachable over the **authenticated proxy** as the
git ref `refs/dolt/data`. Confirmed on a healthy container: `git ls-remote origin
refs/dolt/data` and `git fetch origin refs/dolt/data` both work over the proxy;
bd's `git+http` dolt pull is the flaky part.

## What shipped

`scripts/beads_remote_bootstrap.py`:

1. **Reliable proxy sync.** Before reconciling (on BOTH the fresh and the
   already-hydrated paths) the script re-points the dolt `origin` at this
   session's live proxy (`repoint_dolt_remote_to_proxy`), lands `refs/dolt/data`
   with **plain `git fetch`** (`_git_fetch_dolt_ref` -- reliable even when
   dolt-native sync stalls), then runs a **bounded** `bd dolt pull`
   (`bd_dolt_pull`, default 90s) so it can never silently hang the 180s the report
   saw.
2. **Fail-loud freshness gate.** The anchor is `git ls-remote origin
   refs/dolt/data` (reachable when dolt sync is not). If the live ref exists but bd
   did NOT load it (`origin/main` absent ⇒ serving the committed JSONL), the script
   prints `ERROR: STALE STORE ... DO NOT trust 'bd ready'` and **exits non-zero**,
   refusing to mark hydrated. No more false `Done.` over stale data.
3. **Freshness is stamped, not inferred.** `mark_hydrated` records the verified
   `refs/dolt/data` commit in `.beads/.cache/.hydrated`, so a later session/tool
   can check freshness against a real commit instead of an issue count.
4. **Resume path is honest.** When the already-hydrated refresh can't reach the
   remote, it now WARNs that `bd ready` may be stale instead of a bland "refresh
   skipped".
5. **Noise cleanup** (`quiet_beads_hygiene`): `chmod 700 .beads` and set
   `beads.role=contributor` so every `bd` invocation stops printing two warnings.

`scripts/next_bead.py` + `.claude/skills/next-bead/SKILL.md` (the report's
collateral): a failed `bd dolt pull` now **taints the output** with a
`stale_warning` (in JSON + on stderr) instead of aborting the whole engine, so
`/next-bead` is usable on remote; and the skill's Python resolution falls back to
`python3` when there is no `backend/.venv` (remote containers have none).

### What was deliberately NOT changed

- **`.beads/issues.jsonl` stays git-tracked.** The report floated gitignoring it,
  but it is the intentional off-machine backup snapshot. The fail-loud gate makes
  its staleness harmless (it can no longer masquerade as the live store), which is
  the right fix rather than deleting the backup.
- **The deepest "why does bd's dolt-native `git+http` pull hang in some
  containers" is not root-caused** -- it could not be reproduced on this (healthy)
  container. The mitigation is to bypass it (plain git fetch) and to FAIL LOUD when
  the store is stale, so a future occurrence is visible and safe rather than
  silent. Left as a watch item.

## Validation

Done against the live store on this container (the previous fix's lesson: do not
ship unverifiable remote-infra guesses):

- **Fail-loud gate, both ways:** healthy store -> `origin_main_count` 124 (gate
  passes, marks); stale store (a copy with `origin/main` removed) -> `None` (gate
  fires the `STALE STORE` error, returns non-zero, no marker).
- **Freshness anchor:** `_live_ref_commit()` returns the live `6d9585...` over the
  proxy via plain git.
- **Full fresh-container mock:** dropped the marker, ran the bootstrap end to end
  -> `hydrated (124 issues). Done.`, marker stamped `(refs/dolt/data 6d9585...)`,
  `bd dolt pull` -> "Pull complete.", working branch **identical** to ground truth
  (124 issues, all statuses).
- **next_bead:** a forced pull failure yields exit 0 with a `stale_warning` (not an
  abort); `--no-pull` still produces candidates.

## Doc freshness

`docs/components/beads-remote-bootstrap.md` updated: new steps 5 (proxy sync) and
6 (fail-loud freshness gate), and step 7 (mark) now records the stamped ref.

## Files touched

- `scripts/beads_remote_bootstrap.py` -- proxy re-point, plain-git ref fetch,
  bounded pull, fail-loud freshness gate, ref-stamped marker, hygiene, honest
  resume warning.
- `scripts/next_bead.py` -- failed pull taints output instead of aborting.
- `.claude/skills/next-bead/SKILL.md` -- `python3` fallback when no venv.
- `docs/components/beads-remote-bootstrap.md` -- current-state doc bump.

## Lessons

- **A bootstrap must never report success it did not verify.** "Issue count > 0"
  is satisfied by a stale snapshot; freshness has to be anchored to something
  external and reachable (here, `refs/dolt/data` via plain git) and the success
  path must be GATED on it.
- **When a vendored sync path is flaky over the proxy, drop to plain git.**
  `git ls-remote`/`git fetch` of `refs/dolt/data` work where bd's `git+http`
  dolt-native pull does not.
- **An unreproducible remote failure is still actionable:** make it loud and safe
  even if you cannot make it stop.
