---
date: 2026-09-14
bead: polyglot-pdf-o4f7c
title: "fix(deploy): verify_service_reachable.py crashes with WinError 2 (gcloud not found by subprocess) instead of warning"
tags: [hotfix, harness, testing]
---

## Trigger

Found while running sprint 23's post-merge deploys (bd `polyglot-pdf-6rj0j`
follow-through, maintainer go-ahead 2026-09-14). The admin service's first
deploy and then `deploy-staging.sh --frontend` both did their real work and
then aborted at the post-deploy reachability gate with a Python traceback:
`scripts/verify_service_reachable.py` spawned a bare `gcloud` via
`subprocess.run`, and on Windows `CreateProcess` resolves a bare name only to
`.exe` -- the Cloud SDK ships `gcloud.cmd` -- so the spawn raised
`FileNotFoundError: [WinError 2]`. Under the wrappers' `set -e` that exited 1
AFTER a successful deploy, so every deploy-all.sh stage on this machine
looked failed while the service was up.

Why it had never bitten before: the gate became a Python module (bd `ywxoh`,
PR #783) after the last staging backend deploy on 2026-09-13, which still ran
the old bash-function copy. The module's own docstring says an IAM read that
cannot run is INCONCLUSIVE and must warn-and-continue; a spawn that cannot
start is exactly that case.

## What shipped

Two independent properties in `_default_gcloud_runner`, each pinned by a
test proven red first:

- `argv[0]` is resolved through `shutil.which` (PATHEXT-aware on Windows, so
  it finds `gcloud.cmd`; a no-op on POSIX; an unresolvable name passes
  through unchanged so the pre-fix behaviour is preserved where it worked).
- An `OSError` from the spawn returns as `(127, "", "<ExcType>: <msg>")`, so
  `_query_invoker_roles` reports the read as failed and the caller takes its
  documented warn path at both severities -- never a traceback.

Tests live in `tests/test_verify_service_reachable.py` beside the module's
other unit tests (not in the wrapper-focused
`test_deploy_reachability_gate.py` the bead named -- a placement call).
Mutations: the bare `argv[0]` and an `except` that no longer catches
`OSError` each turn exactly one test red. Live check (exit criterion 2): the
CLI now completes against `polyglot-admin` from Git Bash with exit 0.
Fresh-eyes additionally confirmed on this machine that `subprocess.run` on
the resolved `.cmd` path works without `shell=True` and that the module's
real argv (`--flatten=bindings[].members`, `--filter=...`,
`--format=value(bindings.role)`) survives cmd.exe unmangled.

Doc: `docs/components/config-deployment.md` gains a paragraph under "The
reachability gate is ONE module" and its stamp paragraph was replaced by one
current stamp (bd `dfxet` is the doctrine bead for that stacking problem).

**Fresh-eyes (sonnet): one round, NO-GAPS.** No findings adopted or filed.

**Opus cross-surface review: two rounds.** Round 1 GAPS-FOUND (2), both
adopted: the collapsed stamp conflicted with dev's same-day `p4ale` stamp
(#784) -- resolved by merging dev and keeping ONE stamp line carrying both
clauses, a deliberate deviation from bd `dfxet`'s take-dev's-paragraph rule
since that rule would have restored the 15-bead chain the collapse removed;
and the new paragraph pointed at prose the doc did not contain -- made
self-contained. The first attempt at that merge committed conflict markers
(a `;`-chained resolver ran `git add` past a failed assertion) and was
corrected in the next commit; lesson recorded. Round 2 NO-GAPS. Filed by
the reviewers: `polyglot-pdf-mrrtg` (a stale `URL_BAKING_SEVERITY`
citation, pre-existing), `polyglot-pdf-g44so` (pin the set of bare-name
external-tool spawns), `polyglot-pdf-fgzue` (its premise -- the local gate
always inconclusive for the operator -- did not reproduce against the real
project; narrowed to surfacing gcloud's stderr in the inconclusive warning).

**Housekeeping reviewed and left:** other sessions' in-progress beads and the
stale docs the checker lists for files this branch did not touch
(`technical_guide.md` mentions the module but its claims are still correct).

## Lessons

- **A gate that crashes is worse than a gate that warns.** Every fallible
  step in a guard needs an explicit "could not check" outcome; an unhandled
  exception turns a diagnostic into a false deploy failure -- and on this
  machine it did so on the very first run of a freshly-ported module.
- **Python subprocess does not apply PATHEXT.** A bare command name that
  works in Git Bash can still be unspawnable from Python on Windows; resolve
  with `shutil.which` (the same trap as the npm `bd` shim two days earlier).
- **A port changes the runtime, not just the language.** The bash copy ran
  `gcloud` through the shell; the Python port dropped that implicitly. When
  porting a shell-out, name the resolution the shell used to do for free.

## Doc freshness

Bumped: `docs/components/config-deployment.md` (paragraph + single stamp).
Reviewed and left: `docs/technical_guide.md` (its description of the module
is still accurate; it tracks files other branches changed and was already
stale before this branch).

## Files touched

- scripts/verify_service_reachable.py -- which-resolution + OSError -> inconclusive
- tests/test_verify_service_reachable.py -- two pin tests
- docs/components/config-deployment.md -- paragraph + stamp
- docs/journal/entries/2026-09-14-bd-o4f7c-reachability-gate-gcloud-spawn.md -- this entry
