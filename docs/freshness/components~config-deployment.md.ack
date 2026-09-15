doc: docs/components/config-deployment.md
verified: cloudbuild.yaml, deploy/channels, scripts/deploy_preflight.sh, scripts/setup-cloud-build.sh, scripts/record_build_check.py, deploy-all.sh, deploy-demo.sh, deploy-staging.sh
because: Updated in this same bead (polyglot-pdf-1s3ko): the Backend section was rewritten around the two-layer env assembly (deploy-all.sh's computed keys, then deploy/channels/<channel>.env, then BACKEND_EXTRA_ENV for deploy-time-only values), the channel-file format and parity rule, the empty-section refusal and the new deploy preflight; the Tracks line gained every file listed above; and three now-wrong references (BACKEND_SECRETS_COMMON plus two BACKEND_EXTRA_ENV mentions) were corrected to point at the channel files, since the constants they named no longer exist. The stale flag is a same-day ordering artifact -- the doc is stamped 2026-09-11 and the tracked files were committed later that same day.
sha: 8c9289b7a

---
doc: docs/components/config-deployment.md
verified: scripts/bootstrap_admin_user.py, scripts/verify_service_reachable.py
because: bd polyglot-pdf-rdftu touched these ONLY to add creationflags=windowless_creationflags() to their existing subprocess spawns -- Windows console-window suppression (CREATE_NO_WINDOW), a no-op off Windows. No behavior, CLI surface, env var, IAM grant or deploy step changed, so nothing this doc asserts about them is affected -- including "The reachability gate is ONE module" and the bootstrap_admin_user CLI examples, both re-read and still accurate.
sha: f2d77ce19
