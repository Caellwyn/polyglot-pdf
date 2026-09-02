---
date: 2026-09-02
bead: polyglot-pdf-6oi9s
title: "fix(deploy): gate deploy-new.sh too -- the set had two members and only one was fixed"
tags: [doctrine, testing]
---

## Trigger

bd `polyglot-pdf-pidtg` closed the "deploy reports success over an unreachable
service" bug in `deploy-all.sh`. Its outer cross-surface review then pointed out
that the set of scripts passing `--allow-unauthenticated` has **two** members,
and only one was fixed:

```
deploy-all.sh          -> gated by pidtg
backend/deploy-new.sh  -> still ungated
```

Textbook scar #8 (ENUMERATE THE SET). Worse, the unfixed one is the more exposed:
`deploy-new.sh`'s documented purpose is bootstrapping a **brand-new** Cloud Run
service, and the refused-binding failure appears *only* on a new service (an
existing one's binding predates the org policy and is not retroactively
stripped). The one script whose entire job is the triggering case was the one
still able to print `✅ Deployment Complete!` over a service that 403s
everything.

## What shipped

The gate became a function, `verify_service_publicly_reachable`, which both
scripts carry a **byte-identical copy** of.

The repo has **no shared shell library** -- the manifest helpers are duplicated
between `deploy-all.sh` and `scripts/deploy-form-kit.sh` with "MUST match" prose
and pinned by `tests/test_deploy_manifest_validation.py`
(`test_helper_copies_are_identical`). Rather than invent a sourcing mechanism for
one function, this follows the established pattern: duplicate, and pin identity
mechanically.

## The real upgrade: the tests now EXECUTE the gate

pidtg could only assert on `deploy-all.sh`'s TEXT, because the gate was inline.
A function can be run, so `tests/test_deploy_reachability_gate.py` extracts it,
stubs `gcloud`, and asserts the actual exit code:

| policy | expected |
|---|---|
| allUsers -> invoker | pass |
| allUsers -> invoker, plus another binding | pass (the false-FAIL case) |
| no bindings at all | abort (the original bug) |
| allUsers -> viewer only | abort (the false-PASS case) |
| allUsers -> `roles/run.invoker.custom` | abort (lookalike) |
| IAM read fails | warn, continue |

**The stub emulates gcloud's PROJECTION rather than returning a canned answer**,
and that detail was earned the hard way. My first stub always returned
pre-flattened output -- so removing `--flatten` from the query was caught only by
the byte-identity test, never behaviorally. A stub that cannot reproduce the
failure cannot test for it. The stub now inspects the flags it was called with
and reproduces the real `;`-joined output when `--flatten` is absent, and the
multi-binding case then fails exactly as production would.

Two other traps hit on the way:

- **A PATH-based `gcloud` stub silently did not shadow anything.** Python's
  `os.pathsep` is `;` on Windows while bash wants `:`, so the stub was never
  found and every case would have run the live CLI. Switched to a shell
  **function** override, which needs no PATH manipulation. (`bash` also had to be
  resolved with `shutil.which` -- a bare `"bash"` finds WSL's, which cannot see
  the Git-Bash filesystem. `test_deploy_manifest_validation.py` already knew
  this.)
- **The refactor broke a neighbouring guard.** `test_deploy_channel_parity.py`
  locates the gcloud invocation by finding the first line containing
  `gcloud run deploy`; my new function's comment used that exact phrase, so the
  parser latched onto a comment and its "guard the guard" assertion fired.
  Reworded the comment rather than loosening their parser -- that guard exists
  because a reviewer once disabled a flag by moving it into a trailing comment.

## An overclaim I made and then disproved

The supersession note first said "nothing was dropped in the move -- only
strengthened." That was not true, and I only found out by testing it: the removed
suite asserted the query carries no `2>&1`, and my behavior tests did not cover
it.

Investigating properly showed the *behavior* is safe for a different reason --
`grep -qx` requires the whole line to be exactly `roles/run.invoker`, and any
real gcloud warning carries surrounding text, so a merged stderr cannot satisfy
the check regardless. So the dropped assertion guarded a code SHAPE whose risk
the exact-match fix had already eliminated.

Kept a test pinning the OUTCOME (stderr noise never yields a false pass), with a
docstring that says plainly what it does and does not prove, including that it
still passes if `2>&1` returns. An honest test that states its limits beats a
confident one that overstates its coverage.

## Exit criteria

1. **Met.** `deploy-new.sh` verifies the binding and exits non-zero when it is
   absent, using logic byte-identical to `deploy-all.sh`'s.
2. **Met.** `test_allow_unauthenticated_set_is_complete` walks every `*.sh` in
   the repo and asserts the set of scripts passing `--allow-unauthenticated`
   matches the gated list -- verified by adding a third ungated script and
   watching it redden.

## Testing

Seven mutations, each confirmed to apply before trusting the result: remove
`--flatten` (from both copies, so identity could not mask it), `grep -qx` ->
`grep -q`, `exit 1` -> `return 0`, a third ungated script, drift between the two
copies, removing `deploy-new.sh`'s call, and re-merging stderr. All caught by the
intended test except the last, which is analysed above.

Full suite: 4386 passed, 126 skipped, exit 0.
