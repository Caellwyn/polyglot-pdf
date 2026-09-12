# `deploy/channels/` -- per-channel Cloud Run configuration

Plain `KEY=value` data, read by BOTH `deploy-all.sh` (bash) and
`cloudbuild.yaml` (Cloud Build). One source, two consumers -- which is the
whole point: before this directory existed, the channel env lived only inside
`deploy-staging.sh` / `deploy-demo.sh` as an inline `BACKEND_EXTRA_ENV` string,
so a Cloud Build target could not read it without restating it.

## File format

Three section headers, each introduced by a line of the form `[SECTION]`:

    [SET_ENV_VARS]      -> gcloud run deploy --set-env-vars
    [SET_SECRETS]       -> gcloud run deploy --set-secrets
    [SERVICE_ACCOUNT]   -> gcloud run deploy --service-account

Inside a section, one `KEY=value` per line. `#` starts a comment (only at the
start of a line, so a `#` inside a value is safe). Blank lines are ignored.
`[SERVICE_ACCOUNT]` carries the single key `SERVICE_ACCOUNT`.

Values are literal: no shell expansion, no `$VAR`. A value that must be
computed at deploy time (`GIT_SHA`, the resolved backend URL) is supplied by
the caller, NOT written here -- see `deploy-all.sh`'s `BACKEND_ENV`
assembly, which layers the channel file under the computed keys.

Semicolons separate the sub-values of `CORS_EXTRA_ORIGINS` (matching
`parse_extra_origins`), because a comma is the separator `--set-env-vars`
itself uses.

## Parity

`staging.env` and `demo.env` must agree LINE FOR LINE except for the keys in
`tests/test_deploy_channel_parity.py`'s `CHANNEL_SPECIFIC` allowlist. That is
the staging channel's entire premise: a config difference means staging stops
predicting demo behaviour, and the deploy-only bugs the tier exists to catch
are precisely the config-shaped ones. Change staging FIRST, verify, then
promote to demo.

`admin.env` is deliberately NOT in the parity pair. The admin service has no
channel -- there is ONE admin service backing both channels' data -- so it
has a different runtime identity (`admin-backend-sa`) and a different ASGI
entrypoint (`APP_MODULE=admin_backend.main:app`).
