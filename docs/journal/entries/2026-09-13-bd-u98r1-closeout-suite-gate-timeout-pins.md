---
date: 2026-09-13
bead: polyglot-pdf-u98r1
title: "fix(closeout): check_tests now runs all three suites (~706s) but keeps timeout=600, so the pre-PR gate always PREP-ERRORs"
tags: [testing, harness, review]
---

## Trigger

The bead was filed 2026-09-04 after `closeout_prep.py::check_tests` widened its
pytest invocation from `pytest <WT>/backend/tests` to a bare `pytest` (inheriting
`pytest.ini`'s three testpaths roots) without raising its 600s subprocess ceiling.
Measured at the time: the narrow scope ran 590s, the widened scope 706s. So the
gate died on its own timeout on every run.

The failure mode is what makes this worth a bead rather than a one-line fix.
`subprocess.TimeoutExpired` subclasses `subprocess.SubprocessError`, so the
generic `except (OSError, subprocess.SubprocessError)` arm swallowed the timeout
and returned `STATUS_FAIL "could not run pytest"`, which `render_todo` prints as
`RESULT: PREP-ERROR -- a check could not run (not a closeout verdict)`. An
orchestrator reads past a tooling error. **So the pre-PR suite gate verified
nothing on every closeout while still looking like it had run.**

I hit this personally on the immediately preceding PR (bd polyglot-pdf-96um6):
prep timed out, I hand-drove the remaining checklist, and the gate contributed
nothing. That is what moved this bead to the front of the queue -- it is the
tooling every later closeout's verification rests on.

## What shipped

**Criterion 1 turned out to be already satisfied on `dev`.** The production fix
had landed: `_TESTS_TIMEOUT_S = 1800`, and a dedicated `except
subprocess.TimeoutExpired` arm ordered BEFORE the `SubprocessError` arm, returning
`STATUS_ATTENTION` with a message naming the ceiling. I verified this empirically
rather than by reading, because the bead's criterion is explicitly behavioural:
ran the real gate, which completed the full suite in **597.21s** and returned
`RESULT: ATTENTION` / `tests: test suite FAILED (exit 1)`. A real verdict, not a
PREP-ERROR.

**Criterion 2 was not satisfied, and that is what this PR supplies.** Nothing in
`tests/test_closeout_prep.py` mentioned the timeout at all -- the exact mechanism
that broke had no pin, leaving the fix one edit from silently regressing. Three
tests added (`tests/test_closeout_prep.py:718-781`), each mutation-verified
against the real defect rather than a convenient neighbour:

- deleting the `TimeoutExpired` arm (the actual shipped bug) reddens
  `test_timeout_is_its_own_status_not_a_launch_failure` with `'fail' ==
  'attention'` -- the exact production symptom;
- restoring the 600s ceiling reddens
  `test_ceiling_clears_the_measured_full_suite_runtime`;
- downgrading a genuine launch failure to ATTENTION (the lazy way to "pass" the
  first test) reddens `test_launch_failure_is_still_fail`.

Each mutation reddens only its own test, so the three pin distinct properties.
The negative test exists specifically so the first test cannot be satisfied by
mapping every subprocess error to ATTENTION, which would hide a broken
interpreter.

No production change: `scripts/closeout_prep.py` is byte-identical to `origin/dev`.

**Review.** Fresh-eyes (haiku, routed by diff size at 69 lines): `NO-GAPS` in one
round, both criteria PASS; it re-derived the mutation matrix itself rather than
taking the claim. Opus cross-surface: `NO-GAPS` in one round, with two findings
filed rather than blocked:

- `polyglot-pdf-f3svv` -- the guard's `706s`/`4494-test` baseline is already
  stale. Measured during review: **6017 tests collected today**. See Lessons.
- `polyglot-pdf-i1hej` -- `test_every_suite_root_is_gated.py` already pinned the
  same two invariants on `dev` by reading source TEXT, so the ceiling is now
  pinned twice with mismatched thresholds (1200 vs 1412).

Both reproduce unchanged on `origin/dev`, so both are pre-existing by the
closeout triage rule and are filed, not fixed here.

## Lessons

**A guard that pins one constant against another constant cannot observe the
thing it exists to prevent.** My headroom test asserts `_TESTS_TIMEOUT_S >= 2 *
706`, where 706 is a measured runtime hardcoded from the bead. The Opus reviewer
pointed out that neither side of that comparison observes real runtime, so the
suite can grow until the gate times out again while the guard stays green. The
measurement makes it concrete: the comment's baseline was 4494 tests, and the
suite collects 6017 today -- 1.34x growth in nine days.

The 2x multiple is therefore decorative, not load-bearing. It was the best shape
available for criterion 2 as written (the bead asks for "a stated margin"), and
the reviewer correctly ruled it pre-existing rather than blocking, but it is worth
recording honestly: **I wrote a guard aimed at a number rather than at the
invariant**, in the same session I was congratulating myself on mutation-verifying
it. Mutation testing proves a test CAN fail; it says nothing about whether the
property pinned is the property that matters. That distinction has its own repo
memory (`mutation-verified-does-not-mean-correct`) and I still walked into it.

The durable fix, deferred to `f3svv`: observe the actual elapsed time. The gate
already knows how long the run took, so a guard can compare the ceiling against a
freshly measured runtime instead of against a literal that rots the moment anyone
adds a test.

**Verifying a behavioural criterion means running the thing.** Criterion 1 says
the gate must "report an actual suite verdict". The cheap reading is to diff the
source, see the 1800s ceiling, and call it PASS. Running it instead cost twelve
minutes and produced two things reading could not: proof the gate now returns a
verdict, and -- because it ran -- a genuinely red suite (the stale-kit artifact of
`polyglot-pdf-079xg`), which is the gate doing exactly its job on its first
working run.

**An operator script exited on a bad flag and I nearly read it as success.** My
first prep invocation passed `--bead`, which `closeout_prep.py` does not accept.
It exited in under a second with an argparse error into a redirect file. The fast
exit looked like a fast success; only reading the file caught it. Same shape as
`run-operator-scripts-as-an-operator` -- check `--help` before assuming a flag,
and read the output rather than the exit timing.

## Doc freshness

`check_doc_freshness.py` flagged several tier-2 docs as STALE
(`docs/standards/voice-and-vad.md`, `docs/standards/ws-protocol.md`,
`docs/technical_guide.md`, and others). **All track files this branch did not
touch** -- they were flagged against yesterday's frontend/backend merges, not
against this diff, which changes one test file. Reviewed and left; no stamps
bumped. `docs/technical_guide.md` additionally carries no `*Last updated:*` stamp
by design (bd polyglot-pdf-abn4o) and must not be given one.

## Files touched

- `tests/test_closeout_prep.py` -- +69 lines, three mutation-verified tests
  pinning the suite-gate timeout's distinguishable status and its ceiling
  headroom. No production file changed.
