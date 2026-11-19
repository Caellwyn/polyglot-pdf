---
date: 2026-11-19
bead: polyglot-pdf-mm3e0
title: "fix(deploy): cloud-sdk:slim no longer has python3 -- backend reachability gate exits 127 after the revision is live, skipping the frontend"
tags: [hotfix, testing]
---

## Trigger

The 2026-11-19 staging deploy of commit ccb73a25c (the gemini-3.8-live
transcript fix, epic r3ham) failed at `backend-reachability-gate`:
`python3: command not found`, exit 127. The new backend revision was already
live and serving, so the failure did not take staging down. It did stop the
deploy wrapper before the frontend target, and the frontend had to be deployed
separately. `cloudbuild.yaml` had not changed since 2026-09-17, and the same
file passed on 2026-10-22, so the unpinned
`gcr.io/google.com/cloudsdktool/cloud-sdk:slim` tag had changed upstream. The
demo backend deploy would hit the same failure.

## What shipped

- **Measured the real image first.** A throwaway Cloud Build (2fc9e5f2,
  deploys nothing) showed:
  - neither `python3` nor `python` is on PATH;
  - `gcloud info --format='value(basic.python_location)'` reports
    `/usr/lib/google-cloud-sdk/platform/bundledpythonunix/bin/python3`
    (Python 3.14.9);
  - running `scripts/verify_service_reachable.py` with that interpreter
    against `polyglot-backend-staging` exits 0.
- **All three steps that ran `python3` now use gcloud's own interpreter:**
  `backend-reachability-gate` (fatal), `editor-reachability-warn` and
  `admin-console-reachability-warn`. Each asks `gcloud info` for its
  interpreter in the same step and runs the module with it.
- **The fatal gate aborts** if no runnable interpreter is reported.
- **The warn steps no longer end in `|| true`.** They print
  `WARN: reachability check did not complete (exit N)` and carry on. Ending in
  `|| true` had hidden this same 127: both warn steps had been silently
  checking nothing.
- **Tests pin the SET over the whole build:**
  - no step off a `python:*` image invokes a bare python;
  - every `.py` script such a step runs goes through an escaped `"$$SDK_PY"`
    resolved in that step;
  - each discovered step is executed against a stubbed `gcloud`, with a
    booby-trapped `python3` first on PATH. Three cases, judged by the step's
    severity: interpreter found, interpreter missing, check failed.
- **Eight mutations each turned the suite red.** One survived the first
  version of the tests: `|| true` appended to the fatal gate. The
  "check failed" case was added to catch it.
- **Bundled bead `polyglot-pdf-pojsz`:** two older comments in
  `cloudbuild.yaml` described a Python in cloud-sdk:slim. The outer reviewer
  found and filed them.
- **Not yet proven:** an actual backend build passing the gate end to end
  needs a deploy, and each deploy needs a per-instance yes from the
  maintainer. The real-image probe above is the evidence before merge.

## Lessons

- **An unpinned base image is an unversioned dependency.** "The image bundles
  X" is a claim about someone else's release. Prefer asking the tool where its
  interpreter is (`gcloud info`) over assuming a PATH entry. That keeps
  working through image changes without pinning a digest that then needs
  bumping.
- **A warn-mode step ending in `|| true` cannot tell "the check warned" from
  "the check never ran".** Print the exit code instead. It costs nothing and
  turns a silent no-op into a visible line in the build log.

## Doc freshness

- `docs/technical_guide.md` 31b "Build callers" / "Pinned by": updated to the
  gcloud-interpreter mechanism. That doc carries no stamp by design.
- `docs/components/config-deployment.md` tracks `cloudbuild.yaml`: added the
  interpreter paragraph to the reachability-gate section and bumped the stamp.
- The other docs that freshness flagged STALE track files this branch did not
  touch; they were stale before it.
- CLAUDE.md is unchanged.

## Files touched

- `cloudbuild.yaml`: the three reachability steps, plus three comments.
- `tests/test_cloudbuild_yaml.py`: the bare-python / gcloud-interpreter set
  tests and the stubbed per-step runs.
- `docs/technical_guide.md`: 31b prose.
- `docs/components/config-deployment.md`: interpreter paragraph and stamp.
