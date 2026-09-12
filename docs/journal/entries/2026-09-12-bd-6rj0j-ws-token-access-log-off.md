---
date: 2026-09-12
bead: polyglot-pdf-6rj0j
title: "fix(logging): B0 stop the WS-token bleed -- --no-access-log on the CMD, uvicorn.access off, exclusion + invalidation asks (sprint 23)"
sprint: 23
tags: [security, testing, doctrine]
---

## Trigger

Sprint 23 is the security + data-leak audit
(`docs/sprint_23_security-audit_plan.md`, epic `polyglot-pdf-uijam`, approved
2026-09-09 in plan mode after three read-only exploration passes and one
maintainer review round). Its one P0 pre-finding, PF-1: `/ws/fill` takes its
Firebase ID token or client magic-link token as the `?token=` query
parameter, and `backend/utils/logging.py` deliberately kept uvicorn's access
logger at INFO "for visibility" while the `Dockerfile` CMD passed no
`--no-access-log`. uvicorn's access line is the full request target, so every
voice connection wrote a live, replayable credential into the container's
stdout and Cloud Logging. None of the PII guards saw it: `test_no_pii_logging.py`
scans app `_log.*` calls and `print()`, and this is a server logger.

The maintainer's review of the plan moved this fix into its own wave-0 bead
(B0) so it would not sit behind the rest of the epic. This PR also carries the
plan doc itself and the INDEX row, since the epic and its 15 children were
filed the same day.

## What shipped

**Two independent guards, each pinned by a test proven red first.**
`Dockerfile`'s CMD passes `--no-access-log` (uvicorn 0.24 supports it; no
upgrade), pinned by `tests/test_dockerfile_app_module.py::test_the_cmd_disables_uvicorns_access_log`.
`configure_logging()` lists `uvicorn.access` among the WARNING-capped library
loggers and the explicit `setLevel(INFO)` line is gone, pinned by
`tests/test_logging_access_log.py` (which snapshots and restores the logger so
it leaves no process-wide state behind). The second guard matters because the
local launchers start uvicorn without the flag. Round-1 fresh-eyes verified
the mechanism against uvicorn 0.24.0's own source: uvicorn configures its
`uvicorn.access` logger in `Config.__init__`, BEFORE `config.load()` imports
the app, so the app's later WARNING cap is the final state, in `--reload`
mode too.

**Local verification (criterion 2).** Backend started via
`scripts/dev-local.sh backend` (no flag on that launcher, so the level cap
alone was under test): `/health` 200, a websockets client connected to
`/ws/fill?token=...` and received the handled `invalid_schema` close, and the
backend's stdout contained zero access-log lines.

**What this does NOT fix.** Cloud Run's own request log
(`run.googleapis.com/requests`) records `httpRequest.requestUrl` independently
of uvicorn, so the credential is still written there until sprint 23 bead C2
moves it into the first WS frame. Two live-change asks ride the merge ping
(criterion 3): a narrow Cloud Logging exclusion on that request log, and the
rotate-`LINK_TOKEN_SECRET`-vs-delete-the-log choice for the link tokens
already sitting in the retention window. The maintainer's answer and the fix
timestamp are recorded on the bead when they arrive; criterion 2 of the epic's
rubric measures "zero hits" from that timestamp.

**Docs.** `config-deployment.md` (CMD quote, a paragraph on the guard and its
diagnostic cost, stamp), `hipaa-pii-policy.md` (a "uvicorn access log" row in
the per-surface table), `logging-and-cost.md` (a subsection), and -- found by
fresh-eyes round 2 -- the other two verbatim CMD quotes in
`technical_guide.md` and `admin-service.md`. The set of non-journal CMD
quotes is three and all now match the file. Re-stamping replaced each doc's
stacked `*Last updated:*` paragraphs with one current stamp (admin-service.md
had three stamps stacked, 191 lines); every removed bead pointer has its own
journal entry, verified by round 3.

**Fresh-eyes (sonnet, routed by diff size): three rounds.**
- Round 1: GAPS-FOUND (1) + 1 nit, both adopted -- the new config-deployment
  paragraph read as if the exclusion filter were already applied (reworded:
  it is an unapplied ask on the bead); the new test left `uvicorn.access` at
  WARNING process-wide (restore fixture added).
- Round 2: GAPS-FOUND (2) + 1 nit, all adopted -- the two remaining verbatim
  CMD quotes (technical_guide.md, admin-service.md) were stale; the hipaa row
  used `Off` instead of the table's `Safe` vocabulary.
- Round 3: no in-diff gap. It flagged that criterion 3's asks were not yet
  in the bead trail (correct: they are sent in the merge ping, by design) and
  noted the stamp-chain pruning for visibility (verified no prose lost).
- Filed: `polyglot-pdf-q7oml` (docs-nit, pre-existing: technical_guide.md's
  stamp is a running changelog again despite bd abn4o, and admin-service.md
  carried three stamps).

**Housekeeping reviewed and left.** Four `in_progress` beads older than a day
(`0dsv4`, `ih428`, `96um6`, `mpebj`) belong to concurrent sessions and were
not transitioned. B0's declared `surfaces` were narrowed to drop
`docs/components/config-deployment.md` because in-flight bead `1s3ko` (E4.1
Cloud Build) declares that doc; the doc is still bumped here, and any
stamp-line conflict at rebase is mechanical.

## Lessons

- **A server's own logger is a PII sink the app-level guard cannot see.**
  Three months of `test_no_pii_logging.py` never touched uvicorn's access
  line because it is not a `_log.*` call. Whatever the next static guard
  covers, list the sinks the process emits that the app did not write.
- **Stopping the write is not the fix when the log already holds live
  credentials.** Link tokens have a 48-hour open window (up to 14 days) plus
  a completion window; every one minted inside the retention window is in
  the request log now. Invalidation or deletion is a separate decision, and
  the rubric measures from the timestamp of that decision, not from the
  merge.
- **Enumerate the quote set before fixing the first quote (scar #8, again).**
  Fresh-eyes found the CMD quotes one per round until the set was grepped:
  three tier-2 docs quote the CMD verbatim. The grep is one line; the extra
  review round was not.
- **The freshness checker compares the stamp date to the commit's UTC date.**
  A stamp of 2026-09-11 on a doc committed at 18:20 local (01:20 UTC next
  day) reads as stale. Stamp with `date -u +%F`, as the closeout skill says.
- **Windows: a Python `subprocess` cannot run the npm `bd` shim.** The shim
  is a POSIX shell script and `shutil.which` resolves to `bd.CMD`; going
  through `bash` mangled a title containing ` -- `. Calling node on
  `node_modules/@beads/bd/bin/bd.js` directly works. The bead-filing script
  for this sprint did that.

## Doc freshness

Bumped with substance: `docs/components/config-deployment.md`,
`docs/standards/hipaa-pii-policy.md`, `docs/standards/logging-and-cost.md`,
`docs/components/admin-service.md` (CMD quote + stamp), `docs/INDEX.md`
(sprint-23 row + stamp). `docs/technical_guide.md`: CMD quote fixed, no stamp
touched -- it still reports stale against files other branches changed on
2026-09-09 (`backend/main.py`, `websocket_routes.py`, `live_ai_gemini.py`),
which this branch did not touch. The other stale docs the checker lists
(`auth.md`, `voice-ai.md`, `websocket-routing.md`, `ws-protocol.md`, and the
older standards) track files this branch did not change and were left.

## Files touched

- Dockerfile -- `--no-access-log` on the CMD, with the reason above it
- backend/utils/logging.py -- `uvicorn.access` joins the WARNING-capped list; the INFO override removed
- tests/test_dockerfile_app_module.py -- new pin test for the flag
- tests/test_logging_access_log.py -- new; pins the level cap, restores logger state
- docs/components/config-deployment.md -- CMD quote, guard paragraph, stamp
- docs/standards/hipaa-pii-policy.md -- per-surface row, stamp
- docs/standards/logging-and-cost.md -- subsection, stamp
- docs/technical_guide.md -- CMD quote
- docs/components/admin-service.md -- CMD quote, stamp
- docs/sprint_23_security-audit_plan.md -- new; the sprint-23 plan of record
- docs/INDEX.md -- sprint-23 row, stamp
- docs/journal/entries/2026-09-12-bd-6rj0j-ws-token-access-log-off.md -- this entry
