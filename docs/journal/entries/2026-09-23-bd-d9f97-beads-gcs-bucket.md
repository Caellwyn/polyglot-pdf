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

`tests/test_setup_beads_remote_script.py` pins the script text (12 tests at
this stage; 32 after the guard below).

**Review outcome.** Fresh-eyes: `NO-GAPS`, round 1, including a read-only
check of the live bucket. The Opus cross-surface review found what neither the
author nor fresh-eyes had: **a bucket inherits every project-level storage
role, and public access prevention does not stop them.** On polyglot-demo-aa709
the public backend's service account (`polyglot-backend-sa`, used by both the
demo and staging backends) holds `roles/storage.objectViewer` project-wide, so
it can read this bucket; the default compute account (`roles/editor`) and the
legacy Cloud Build account (`cloudbuild.builds.builder`) can write and delete
in it. Verified live. The bucket is EMPTY, so nothing is exposed today -- but
cutting over as planned would make every bead body readable by the running
app, including staging's unverified code.

Triage: the project-wide grant pre-exists on dev (granted by
`scripts/setup-gcp-project.sh`), so it is filed rather than fixed here --
polyglot-pdf-fuao2 (P1), now wired to BLOCK the cutover bead h06sv. Fixing it
means changing a deployed identity's permissions (CLAUDE.md scar #7) or
homing the bucket in a separate project; that is a maintainer decision. The
script's own header had claimed operator-only access -- false -- and now states
the inherited-access posture and points at fuao2. Also filed:
polyglot-pdf-95pln (P2) -- `scripts/audit/infra_posture.sh` never re-checks the
new bucket, so its settings are verified once and never again.

**Maintainer decision: a dedicated project (option A).** Rather than narrow the
live app's permissions (option B: changing a deployed identity's IAM, scar #7,
and staging-verified before it is safe), the store moves to its own project,
`polyglot-beads`, where no service account holds any role -- nothing
inherits. The empty bucket in polyglot-demo-aa709 was deleted (confirmed empty,
all versions, first). Option B stays worth doing on its own merits -- the app
can read unrelated buckets today -- and is tracked separately.

**The rule is enforced, not just documented -- on the second try.** The first
guard was a BLOCKLIST of risky roles (owner, editor, storage.*,
cloudbuild.builds.builder) held by service accounts, read from the project
policy only. It worked live against polyglot-demo-aa709 (refused, named the
three accounts). The round-2 Opus review then showed it was the wrong shape:
49 non-Google predefined roles grant `storage.objects.get` and matched none of
it (firebase.*, run.builder, dataflow.worker, the new admin/reader/writer...);
`roles/viewer` reaches objects through every UBLA bucket's default
projectViewer -> legacyObjectReader binding; custom roles never match a
`^roles/` anchor; `group:` and workload-identity principals skipped the
`serviceAccount:` check entirely; and a bucket inherits ORG- and FOLDER-level
grants the project policy does not show.

The guard is now an ALLOWLIST of who may hold roles anywhere up the
hierarchy: human users, Workspace domains (humans only), and Google-managed
service agents. Any other principal holding ANY role refuses, and it reads
`get-ancestors-iam-policy`, so org and folder grants count. That read needs
org-level IAM access; without it the script stops before touching anything
(verified live as caellwyn@gmail.com: exit 1, no bucket). Tests extract the
SHIPPED `case` patterns and check real member strings both ways, including
the three accounts found on the app project and look-alikes of the allowed
agents. Five mutations -- allow groups, broaden the agent pattern, read the
project policy only, drop the exit, move the guard after create -- each
applied and each went red. 32 tests.

## Lessons

**Scope the evidence to the claim, again.** Every setting appears three times
in the script: header comment, `create`, and `update`. Only `update` runs on
every invocation, so only `update` enforces a setting on an existing bucket.
A whole-file search would have stayed green with a setting deleted from
`update` -- the exact regression that matters. The tests parse the `update`
command block and look only there; mutation-verified by deleting each flag
from `update` alone while it still appeared elsewhere in the file (for the two
access-control flags, once more in `create`) -- each turned its own case red.

**"Nobody was granted access" is not "nobody has access."** The script's
settings were all correct and all verified, and the bucket was still readable
by the public app -- through a project-wide role granted long ago for a
different bucket. Provisioning a sensitive store in a shared project has to
ask who inherits access, not only what the new resource grants. It took the
reviewer whose mandate is to follow things OUT of the diff to see it; the
in-diff review, correctly, found nothing wrong with the script.

**I wrote a blocklist while this repo's memory says "allowlist."** The lesson
was already recorded (pin message text with an allowlist; guard the property,
not the code shape) and I still reached for a list of bad roles first,
because it was concrete and it passed a live test. A live test against the
ONE project I had in hand proved the list caught that project's three
accounts -- not that the list was complete. When the property is "nobody but
X", encode "nobody but X".

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
