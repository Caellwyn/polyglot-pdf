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

## The extraction was not quite behavior-preserving

I described the extraction as behavior-preserving. The pre-PR review found it was
not: the function wrote plain `[WARN]`/`[ERROR]` to **stderr**, while the inline
code it replaced used `log_warn`/`log_error`, which `echo -e` to **stdout with
ANSI colour**. So deploy-all.sh's diagnostics silently changed stream and lost
their colour -- and a wrapper capturing only stdout would have lost them
entirely. Nothing in the repo does that today, but the claim was still false.

The motivation was real (`deploy-new.sh` defines no `log_*` helpers), but it was
applied to BOTH copies when only one needed it. The function now delegates:

    _gate_error() { if declare -f log_error >/dev/null 2>&1; then log_error "$1"
                    else echo "[ERROR] $1" >&2; fi; }

`deploy-all.sh` keeps its original coloured stdout exactly; `deploy-new.sh` falls
back to stderr. Both paths are pinned by tests and mutation-verified.

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

## The outer review: presence is not enough, the CALL SHAPE matters

The Opus cross-surface pass showed the gate could be silently neutered while all
38 tests stayed green: appending `| cat` to the call puts the function in a
SUBSHELL, so its `exit 1` kills only that subshell and the script proceeds to
"Deployment Complete!" and exits 0. `|| true`, `if ...`, and `$(...)` do the same.

Deleting the call was already caught; *keeping it and defanging it* was not.
Pinned now by test_gate_is_called_as_a_bare_command, parametrized over both
scripts, and mutation-verified with the reviewer's own `| cat` plus `|| true`.

That is the third variation of one lesson in this bead: a guard is only as good
as the narrowest thing it actually asserts. Presence, shape, and behavior are
three different claims.

## The guard I wrote to prevent scar #8, committing scar #8

Round two found the call-shape guard **did not see `deploy-all.sh` at all**. Its
call is already a line continuation:

```
    verify_service_publicly_reachable         "$BACKEND_SERVICE_NAME" "$REGION" "$POLYGLOT_PROJECT_NAME"
```

A line-oriented collector only ever inspected `verify_service_publicly_reachable
\` -- the ARGUMENTS line, exactly where a neutering `| cat` goes, was invisible.
So the guard protected `deploy-new.sh` and left unguarded the script already
written in the vulnerable shape. The reviewer proved it by appending `| cat`
there: 15 tests green, deploy reporting success over an unreachable service.

Fixed by joining continuations before splitting. The irony is the point: this was
a guard written specifically to stop "fixed one member, believed the set was
done", and it committed that error in its own implementation one round later.

The same round found the **ordering** half of the finding still unpinned --
moving the gate below the success banner also stayed green, though
`deploy-new.sh`'s own comment calls that ordering load-bearing. Now pinned by
`test_gate_runs_before_the_success_banner`.

## A comment that stated a false cause

I had matched the error banner to the box-drawing glyph the rest of
`deploy-all.sh` uses; it broke four tests with `UnicodeDecodeError`, so I
reverted to ASCII and wrote a comment blaming Windows' cp1252 handling of shell
output -- citing scar #6.

The reviewer showed that reason was wrong. The constraint was **my test's**:
`subprocess.run(..., text=True)` with no `encoding=`, so the child's output was
decoded with the locale codec. Adding `encoding="utf-8"` makes the glyph
round-trip cleanly -- verified by experiment. The comment also claimed "this file
uses box-drawing elsewhere", which is false for `backend/deploy-new.sh` (no
box-drawing at all), and the two copies are byte-identical, so it was wrong in
one of the two files it appeared in.

Fixed the real defect (explicit UTF-8 at all three capture sites) and rewrote the
comment to say ASCII is a free choice rather than a constraint. A comment
recording a phantom rule is worse than no comment: the next author avoids
something harmless for a reason that does not exist.

## Round three: the ordering guard had both defects it was written to prevent

The guard added in round two to pin ordering turned out to carry, simultaneously,
the two failure shapes this bead had already been burned by:

**Vacuous pass.** It matched a banner with two loose conditions
(`log_success "` plus "deployed successfully") and took the FIRST hit. But
`deploy-all.sh` has THREE such banners -- backend, form-kits, frontend. Rewording
the backend one silently fell through to the form-kits banner 117 lines later,
and the ordering assertion then held for almost any gate placement. The
`banner_idx is not None` check, whose entire job was to make a rewording fail
LOUDLY, was itself satisfied by the wrong banner. Fixed by matching one exact,
distinctive substring per script and asserting it matches EXACTLY ONE line.

**A no-op join.** Its continuation join was written `body.replace("\n", " ")` --
the literal two characters backslash-n, not a backslash followed by a newline. It
matched nothing (766 lines before, 766 after; the correct form gives 738). That is
the identical defect the sibling guard had been fixed for one round earlier, in
the very commit that fixed it.

Both found by the outer review, both mutation-verified after fixing.

## Exit criteria

1. **Met.** `deploy-new.sh` verifies the binding and exits non-zero when it is
   absent, using logic byte-identical to `deploy-all.sh`'s.
2. **Met.** `test_allow_unauthenticated_set_is_complete` walks every `*.sh` in
   the repo and asserts the set of scripts passing `--allow-unauthenticated`
   matches the gated list -- verified by adding a third ungated script and
   watching it redden.

## Testing

Fourteen mutations, each confirmed to apply before trusting the result: remove
`--flatten` (from both copies, so identity could not mask it), `grep -qx` ->
`grep -q`, `exit 1` -> `return 0`, a third ungated script, drift between the two
copies, removing `deploy-new.sh`'s call, re-merging stderr, and reverting
the log-helper delegation. All caught by the intended test except the stderr
one, which is analysed above.

Full suite: 4392 passed, 126 skipped, exit 0.
