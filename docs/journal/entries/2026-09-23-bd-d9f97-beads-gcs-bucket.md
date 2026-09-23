---
date: 2026-09-23
bead: polyglot-pdf-d9f97
title: "infra(beads): provision the beads GCS bucket via an idempotent setup script"
tags: [harness, performance]
---

## Trigger

First child of epic polyglot-pdf-mlcgn: move the live beads (Dolt) remote off
`git+https://github.com/...` to a Google Cloud Storage bucket. The epic exists
because the git-backed remote is the source of the console-window cascade --
Dolt reads a git remote one `git cat-file` process per chunk, and every one of
those is a window on Windows. Measured on 2026-09-18/22 with a fixed script
(three concurrent bead-write cycles): the git remote peaked at up to 214
concurrent `git.exe`; a `gs://` remote, on a copy of the live store, peaked at
4 -- and those 4 were other sessions' github.com traffic. Every keep-it-in-git
alternative (dolt upgrade, bd upgrade to 1.3.0, clearing the git-remote-cache,
credential-helper changes) was measured and failed first; the maintainer chose
GCS knowing it moves bead data out of the git repo.

This bead only provisions storage. It does not point the store at the bucket.

## What shipped

`scripts/setup-beads-remote.sh <PROJECT_ID>` -- operator-run, same pattern as
`setup-telemetry.sh`. Creates `gs://<project>-beads` in us-central1 (matching
the form-kits buckets) only if absent, then ALWAYS converges four settings:
public access prevention enforced (the store holds every bead body), uniform
bucket-level access (IAM only), object versioning (Dolt rewrites a manifest
object per push; versioning makes a bad push recoverable), and a lifecycle
rule deleting NONCURRENT versions 30 days after they stop being current. It
refuses the retired project and fails loudly if an existing bucket is in the
wrong location (location is immutable, so "converging" could not fix it).

Run against polyglot-demo-aa709: the bucket exists and all four settings read
back as configured. A second run exited 0, took the "exists; converging
settings only" path, and left every setting identical. The bucket's
metageneration counter does increment on re-apply -- a metadata bookkeeping
write, not a settings change.

`tests/test_setup_beads_remote_script.py` (12 tests) pins the script text.

## Lessons

**Scope the evidence to the claim, again.** Every setting appears three times
in the script: header comment, `create`, and `update`. Only `update` runs on
every invocation, so only `update` enforces a setting on an existing bucket.
A whole-file search would have stayed green with a setting deleted from
`update` -- the exact regression that matters. The tests parse the `update`
command block and look only there; mutation-verified by deleting each flag
from `update` alone while it still appeared elsewhere in the file (for the two
access-control flags, once more in `create`) -- each turned its own case red.

**Parse, don't grep, anything that can destroy data.** The lifecycle rule is
checked by parsing the heredoc JSON: `isLive: false` versus `true` is the
difference between pruning old versions and deleting the live store, and a
substring match cannot tell those apart reliably. Mutation flipping it to
`true` turns the test red.

**A mutation that does not apply proves nothing.** The first mutation pass was
written in a Bash heredoc, which halves backslashes on this machine; four of
six mutations silently failed to apply and would have "passed." Rewritten with
the Write tool and `chr(92)`; all six then applied and all six went red.

## Doc freshness

No tier-1/2 doc describes this script yet -- `docs/beads-setup.md` is updated
in the cutover bead (polyglot-pdf-h06sv), which is where a new machine's setup
first changes. No stale doc tracks the two new files.

## Files touched

- `scripts/setup-beads-remote.sh` -- NEW. Idempotent bucket provisioning.
- `tests/test_setup_beads_remote_script.py` -- NEW. Script-text pins, scoped to
  the `update` block, lifecycle parsed as JSON.
