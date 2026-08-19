---
date: 2026-08-19
bead: polyglot-pdf-06u5o
title: "fix(deploy): keep _-prefixed kit dirs out of git and the bucket"
tags: [deploy, kits, storage, testing]
---

## Trigger

bd polyglot-pdf-y2l0p added a per-kit keyspace `<kit_id>/_drafts/<n>/` -- up to
10 draft snapshots per kit, written on EVERY editor save. The cross-surface
reviewer on that PR filed this: two untouched surfaces treated the new
directory as ordinary kit content.

1. `.gitignore` had no rule, while the sibling `_archive` keyspace has one at
   line 102. The local store's default root IS the git-tracked `form-kits/`
   tree, so in local mode every editor save wrote snapshots into the working
   copy -- and `scripts/pull-form-kits.sh` rsyncs the bucket back into that
   tree, the exact round trip the `_archive` rule exists to stop.
2. Both deploy scripts ran `gcloud storage cp -r "$kit_dir"/*`. The
   `case "$kit_id" in _*)` guard one line above filters only the TOP-LEVEL kit
   id, not children INSIDE a kit, so the glob swept underscore dirs into the
   bucket on every deploy.

## Two corrections to the bead, both verified rather than assumed

**The suggested `--exclude` flag does not exist.** The bead proposed "an
--exclude on the copy". `gcloud storage cp` has no such flag -- only `rsync`
does, which is why the sole repo precedent (`pull-form-kits.sh:45`) is on
rsync. That spelling would have failed at DEPLOY time, on the maintainer's
machine, mid-deploy. `cp` takes `[SOURCE ...]`, so the fix enumerates
publishable children instead.

**The leak was never `_drafts`-specific.** `_archive` (bd w3zw) rides the same
code path. The exit criteria name only `_drafts`, but fixing only that would
leave a known-live bug in a line already being edited. The filter is the
general underscore rule, and the mutation proving it matters is the narrow one:
scoping the skip to `_drafts)` alone REDDENS the harness.

## The regression that wasn't

Excluding `_archive/` from an upload looked like it might break bd w3zw's
revision archive -- the thing a confirmation record names. The outer review
settled it with the deployment chain rather than reasoning: `deploy-all.sh:286`
sets the deployed backend to `FORM_KITS_MODE=gcs` with the SAME bucket and
prefix the upload loop writes to, so `put_archived_revision` writes `_archive/`
directly into the bucket at publish time. The deploy script only ever
re-uploaded a local copy on top.

For `_drafts` the exclusion is not merely safe but NECESSARY: snapshot ids are
claimed with `if_generation_match=0` (compare-and-swap) against the bucket, so
uploading a local ring over them would corrupt the CAS-claimed ring.

This diff makes the deploy scripts the LAST surface to agree with a rule three
others already enforce independently (`kitCopyFilter.ts` excludes any
underscore basename at every level; both stores' `list_kit_files` ignore
anything deeper than `<kit>/<file>`; `_KIT_ID_RE` cannot match a leading
underscore).

## Four review rounds, all on the TESTS

The shipped fix was correct from round 1. Every subsequent finding was a test
that passed for the wrong reason -- and twice, the fix for the previous one.
Worth recording because the shape repeats.

**Round 1: a second `trap ... EXIT` silently replaced the first.** Bash keeps
ONE EXIT handler per shell; a second does not stack, it overwrites. Mine
orphaned the harness's existing `$TMP` fixture on every run (+1 temp dir per
run; delta 0 on origin/dev). Fixed by nesting under `$TMP`, and pinned with an
assertion that the harness registers exactly one EXIT trap.

**Round 2: a guard that proved the call, not the filter.** `deploy-form-kit.sh`
carries its own copy of the helper (the scripts are independently invocable, so
it cannot source `deploy-all.sh`). Its only coverage was a grep of the CALL
SITE -- deleting that copy's `case _*` arm outright left the harness fully
green. Fixed by extracting and RUNNING that copy.

**Round 3: that fix reintroduced the same defect one layer up.** The harness
sources `deploy-all.sh`, so `collect_publishable_kit_files` already existed in
the subshell -- making `eval "$(sed ...)"` an optional OVERRIDE rather than a
binding. When the sed matched nothing, the test silently exercised the OTHER
file's copy and passed. Demonstrated shipping a real leak: a brace-style
reformat plus a narrowed filter left the harness 26/26 green while `_archive`
rode into the bucket. Three parts were needed, each with its own mutation:
`unset -f` to kill the fallback, an empty-source check that fails LOUDLY, and
`|| exit 1` so a syntax error in the extracted body cannot go green.

**The generalisable lesson:** a guard you reasoned about is not a guard you
tested. The question that catches these is "what would make this pass while the
code is broken?" -- and then actually doing it. Three rounds running, the answer
was something I had not thought to try.

## A near-miss worth recording

Squashing two `wip` commits with `git reset --soft dev` produced a commit that
REVERTED someone else's merged work -- the `kkos` static-bundle changes,
including a journal entry and a 135-line test file. Cause: the worktree was cut
from an older `dev`, so `reset --soft dev` moved the branch pointer forward
while keeping the old tree, turning everything that landed in between into
deletions.

Caught by reading the stat line: **11 files changed, 261 deletions** on a change
that touches 4 files. `git reset --soft <branch>` is only safe when your branch
and that branch share the base you think they do -- and the file count is the
tell. Rebuilt against `origin/dev` and confirmed `kkos` never touched my four
files.

## Folded in rather than deferred

Round 2 filed `polyglot-pdf-j8fe5` (the raw-glob guard regex was pinned to two
incidental spellings and missed `"${kit_dir}"/*` and `cp --recursive`). Fixing
it was three characters in a guard I had just written, protecting the exact bug
I had just fixed, so deferring would have meant shipping a guard I already knew
was evadable. Same for the two round-2 filings (`pvgsr`, `xz3rs`) -- both were
guards that did not guard. Closed all three.

`polyglot-pdf-puxql` stays open and is correctly scoped: `pull-form-kits.sh`
still mirrors pre-existing bucket `_drafts`/`_archive` blobs back down, and
nothing purges what earlier deploys already leaked. The new `.gitignore` rule
stops those being committed, so what remains is local clutter plus stale bucket
objects -- genuinely separate work.
