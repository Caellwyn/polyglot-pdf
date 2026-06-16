---
date: 2026-06-16
beads: [polyglot-pdf-ignt]
pr: TBD
tags: [deployment]
---

# ignt: set the Cloud Run service account during the deploy, not after it

## Why

Codex review of PR #220 (the demo Vertex switch, bd a079) flagged a deploy-ordering
robustness gap. `deploy-all.sh` ran `gcloud run deploy`, which creates AND routes a
new revision under the service's CURRENT/default identity; `deploy-demo.sh` then ran
a SEPARATE `gcloud run services update --service-account=$SA_EMAIL` to swap the
runtime identity to the custom SA (`polyglot-backend-sa`, which holds
`roles/aiplatform.user` for the Vertex path).

For a fresh demo service -- or one whose identity had drifted -- that ordering means
traffic briefly shifts to a Vertex revision under the wrong/default identity, and if
the follow-up `services update` fails, the demo is left serving a revision that
cannot call Vertex. Pre-existing; the happy path works (PR #220 was verified live),
so this is hardening, not a live bug.

## What changed

- `deploy-all.sh`: a new optional `BACKEND_SERVICE_ACCOUNT` env. When non-empty, the
  `gcloud run deploy` carries `--service-account "$BACKEND_SERVICE_ACCOUNT"` (built
  as an array flag, matching the existing optional-flag pattern in the file). Empty
  default -> no flag -> behavior unchanged for a bare `deploy-all.sh` run or
  `deploy-production.sh` (neither sets it). So the new revision is created+routed
  under the correct identity from the start.
- `deploy-demo.sh`: exports `BACKEND_SERVICE_ACCOUNT="$SA_EMAIL"` on the
  `deploy-all.sh` invocation and DROPS the now-redundant post-deploy
  `gcloud run services update --service-account` block.

`deploy-all.sh` is shared, so the env is the seam: only `deploy-demo.sh` sets it,
only `deploy-all.sh` consumes it; every other caller is untouched.

## Verification

- `bash -n` on both scripts: clean.
- SA-flag logic: empty -> no `--service-account`; set -> `--service-account <sa>`.
- `BACKEND_SERVICE_ACCOUNT` referenced only by deploy-all.sh (consumer) and
  deploy-demo.sh (producer) -- `deploy-production.sh` does not set it.
- `deploy-all.sh` kit-gate harness (`tests/test_deploy_all_kit_gates.sh`): 10/10
  passed -- the change is in the deploy-flow body, which only runs on direct
  execution, so the sourced `kit_is_complete`/`kit_schema_file` functions are
  untouched. (The pytest wrapper skips under the WSL bash shim; ran the `.sh`
  directly.)

A live redeploy is not part of this bead -- the running demo already serves the
correct SA (set by the old post-deploy update on the last deploy). This change
takes effect on the next `deploy-demo.sh` run, which will set the SA in-deploy.
