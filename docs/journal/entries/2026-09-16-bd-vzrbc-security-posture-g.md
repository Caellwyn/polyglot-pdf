---
date: 2026-09-16
bead: polyglot-pdf-vzrbc
tags: [security-audit, docs, findings, sprint-23]
surfaces: [docs/standards/security-posture.md, docs/INDEX.md, docs/standards/hipaa-pii-policy.md, tests/test_security_posture_doc.py]
---

# G: the sprint-23 findings register, the processor table, and `security-posture.md`

Sprint 23 (the security + data-leak audit, epic `polyglot-pdf-uijam`, plan
`docs/sprint_23_security-audit_plan.md`), workstream G: the closing bead.
Every finding the sprint started with (PF-1..16) and every finding its
fourteen other beads and their reviews produced gets a severity and a
disposition here; the third-party processor table (T4) and the
current-state posture doc are written; the doc's store table is diffed
against the inventory script by a test.

Severity is by HARM (the plan's scale): **P0** a live credential or client
PII exposed, or unauthenticated access to client data; **P1** client data
or staff identity exposed to a wrong-tier user, an insider with ordinary
log/console access, or the next user of a shared device; **P2** defence in
depth; **P3** hygiene.

## What shipped here

- `docs/standards/security-posture.md` (tier 2, current state only, with a
  Tracks line): the threat model (T1-T6 and the control that answers each),
  the data inventory (26 rows: every store the inventory script iterates,
  named in backticks, plus the five it cannot read, each pointing at the
  check that covers it), the route/gate matrix for both services, the
  credential systems, the third-party processor table, the three live
  checks with their last clean run, the accepted-risk list, and the
  decisions handed to the maintainer.
- `tests/test_security_posture_doc.py`: the doc's STORE cells (first
  backticked identifier only, never the prose columns -- the `abn4o`
  lesson) must equal the set derived from the script's SOURCE
  (`PINNED_ALLOWLISTS` keys minus the four subcollection allowlist keys,
  plus the four subcollection report names, the bucket, and every default
  BigQuery view); every key in a store's pinned allowlist must appear in
  that row's Key-set cell (an `as \`other\`` cell resolves to the other row);
  every unscripted row must name a covering check; every row carries six
  non-empty cells. Mutations, each red: the `alerts` row deleted; a
  `bigquery:made_up` row added; the Firebase Auth row's `infra_posture.sh`
  pointer dropped; `actor_email` dropped from the ledger row.
- `docs/INDEX.md`: the standards row. `docs/standards/hipaa-pii-policy.md`:
  the two per-surface rows the plan reserved for G (the ledger `reason`,
  the audit log's `before`/`after`) and the Enforcement section's pointer
  at the live sweep.

## The processor table (T4, PF-16)

In the posture doc. The one cell no script could fill: the Vertex AI
abuse-monitoring opt-out is a console-only toggle (D's runbook reports it
N/A; the Organization Policy proxy is disabled on the project), so the
maintainer reads it in the console and the answer goes on this entry. Cloud
TTS has no per-project data-use setting at all; Firebase Auth's settings
were unreadable because the operator identity lacks Identity Toolkit read.

## Findings register

Every pre-finding, then every finding a bead or its reviews produced.
"Fixed" means merged to `dev` unless the row says otherwise. One PR is
open for the maintainer's merge at the time of writing: C2 (#834); its
rows say "in PR". C3 (#833) and F2 (#835) merged on 2026-09-17 UTC.

### The plan's pre-findings

| PF | Sev | Finding | Disposition |
|----|-----|---------|-------------|
| PF-1 | **P0** | The WS credential rode `?token=` on `/ws/fill` into uvicorn's access log and Cloud Run's request log | FIXED in two steps: B0 (`6rj0j`, #786) took the access line off and the maintainer applied the `ws-token-in-url` exclusion on the request log (2026-09-14T19:28Z); C2 (`bwevj`, #834, in PR) moves the credential into the first frame with `?token=` honoured one more deploy. The 88-89 pre-fix request-log rows are ACCEPTED residue (maintainer, 2026-09-14, option C), aging out by 2026-10-14. Removal of the deprecated form: `0j8e5`. |
| PF-2 | P1 | Exception messages (which can embed a field value) reached Cloud Logging through ungated `.exception()` sites and 199 `error=str(exc)` kwargs | FIXED: `e4dt8` (the type-and-frames processor) + B1b (`2kbo0`, #831: 193 sites rewritten, the guard widened to both services and every call spelling). Residual class members filed: `6inaj` (P2, the `reason=` family incl. operator and model-supplied text), `x7685`, `h5529`, `lvwvy`, `l9zsf`, `o2uyn` (P3). |
| PF-3 | P1 | A 422 echoed the request body's values back to the caller; `debug` unpinned | FIXED: B1a (`wfgjz`, #825) -- value-free 422 on both apps incl. the custom-validator `msg` channel; `debug` pinned False. Sibling sink filed: `giebe` (P2, the editor's own schema-validation 422); `jbb44` (P3). |
| PF-4 | P1 | No response headers on any of the five Hosting sites | FIXED: E2 (`j29z1`, #828) -- HSTS, nosniff, Referrer-Policy, Permissions-Policy, `frame-ancestors`, CSP in REPORT-ONLY mode; needs the next Hosting deploy to be live (D's runbook reports FAIL until then). Enforcement gated on `18o7c` (self-host the VAD/ONNX assets, P2) and the staging soak; `p3o51` (P2), `b45a4` (P3). |
| PF-5 | P1 | No rate limiting on the unauthenticated doors | NOT FIXED -- a cost decision. The options memo is on `6088m`; the new `POST /api/signup/check` door (C3) joined its scope. **Needs the maintainer's choice or a written acceptance** (a P1 with neither is the one open item on epic criterion 5). |
| PF-6 | P1 | `authorized_emails` publicly listable (staff-email enumeration) | FIXED: C3 (`vcjgs`, #833, merged) -- full client deny; server-side `POST /api/signup/check` behind the uniform 404; needs the rules deploy (backend first). Emulator-backed rules tests: `34y4y` (P2, Java in CI). |
| PF-7 | P2 | No dependency/secret/SAST scanning; test tooling in the image; stale pins | FIXED: F1 (`ikdnd`, #812) -- the informational CI job, Dependabot, the requirements split, digest-pinned non-root image, `python-multipart` and two others bumped; F2 (`cwiip`, #835, merged) -- uvicorn 0.53 + websockets 16.1.1, harness-gated. Remaining: `5r456` (P2, the starlette 2026 advisories; fastapi moves with it, same harness gate), `gdqmr` (P3), `kq042` (P3). |
| PF-8 | P2 | `confirmation_events` safe only by the implicit deny; no retention decision | FIXED (rules half): C3 -- explicit deny + `ADMIN_SDK_ONLY_COLLECTIONS`. FILED (retention): `t5v83` (P2, maintainer-owned, with `pol2`'s legal input). |
| PF-9 | P1 | Operator free text (`reason`) unbounded, stored in three places and logged | FIXED for the credit path: A (`uaxt5`, #802) -- 500-char bound at both doors, ids-only log line, the audit-log `before`/`after` shapes pinned per route. One sibling site remains: `e8wzz` (`set_firm_kind` logs its free-text reason) -- **a P1-class residual that needs a fix or written acceptance**; `uanl9` (P2, the console's opaque 422), `q2cu7`, `g2wib`. |
| PF-10 | P2 | Dev routes gated on a marker file; `MAX_UPLOAD_MB` unenforced; resume-form decoded before its size check with no parse timeout; `/health` disclosed config; no WS frame cap or Origin check | FIXED: C4 (`6088m`, #803: `K_SERVICE` fail-closed + the dockerignore pin, byte-accurate caps, parse timeout, bounded disclaimer timestamp), B1b (`/health` trimmed), C2 (the two WS dev sockets fail closed on `K_SERVICE`, text-frame cap, Origin allowlist). Filed: `07vpc` (P2, four editor routes with unbounded bodies), `ij9ue` (P2), `lhrln` (P2), `nb9tx` (P3, binary frames uncapped). |
| PF-11 | P3 | The token dashboard file written on the production container; a bare usage `print()` | FIXED: B1a -- no-op with `K_SERVICE`, gated on the dev marker, the banner is one structured event. |
| PF-12 | P3 | No key-file gitignore; project-wide bucket viewer role; public-access prevention unverified | gitignore FIXED (F1). Bucket public-access prevention is `inherited`, not `enforced`: a live-change ASK on `m1dlv`. The project-wide `storage.objectViewer` is an ACCEPTED RISK for now (no other bucket on the project; tightening is a scar-7 ritual). |
| PF-13 | P2 | Field values `console.log`ged in the production bundle | FIXED: E1 (`8v8i7`, #796) -- the sites deleted, `pure` strip in all three production builds, a source guard and per-app bundle guards. |
| PF-14 | P1 | Nothing cleared a client's answers or link credential on a shared device; no logout control | FIXED: E1 -- automatic wipe on completion (after the download/print), after a 10-minute idle grace, and on logout, every wipe site reloading (set-pinned); `ylokf`, `ugn55`, `xv4eb` closed. Filed: `vzvkk` (P2, three non-PII sessionStorage keys survive). The voice app's persistence mode is a maintainer decision (`8v8i7` notes). |
| PF-15 | P3 | Google Fonts egress from the voice app | FIXED: E2 -- 45 self-hosted subsets. |
| PF-16 | P2 | No record of what each third-party processor receives | FIXED: this bead (the processor table), with the Vertex opt-out state as the one cell the maintainer fills. |

### Findings the beads and their reviews produced

| Found by | Sev | Finding | Disposition |
|----------|-----|---------|-------------|
| C1 (`fr20a`) | P1 | A STAFF token's handshake `kit_id` was never scoped to the caller's firm on `/ws/fill` (a firm-A manager could open a session naming a firm-B private kit; no kit bytes served, but record and telemetry integrity) | FIXED in C2 (#834, in PR): publish + visibility gates on the socket, the C1 tripwire inverted. |
| C1 | P2 | `LINK_TOKEN_SECRET` has no rotation runbook and no key-version claim (rotation is an all-at-once cutover) | FILED `jx5u9`. |
| C1 | P3 | `open_link` reopen check is not transactional; a reopen racing completion can admit one extra paid session | FILED `mzhrp`. |
| A (`uaxt5`) reviews | P2 | The CLI's ledger door was unbounded; three usage subcollections missing from the inventory; the admin console's opaque 422 on a long reason; two resolver blind spots; a stale route row | `bnkuv`, `wg9yz` FIXED in A; `uanl9`, `q2cu7`, `g2wib` FILED. |
| A reviews | P2 | `set_firm_kind` logs the operator's free-text reason (the PF-9 class, second site) | FILED `e8wzz` -- see PF-9's note. |
| A | P2 | No retention decision for any store | FILED `t5v83`. |
| B1a (`wfgjz`) reviews | P2/P3 | The editor's schema-validation 422 is a separate sink; the pydantic error-type catalogue unpinned; the adapter's remaining `print()` blocks | `giebe` (P2), `jbb44` (P3), `l9zsf` (P3; its headline `str(exc)` print was fixed by B1b) FILED. |
| B1b (`2kbo0`) reviews | P2/P3 | The `reason=` kwarg family (12 non-literal sites); five WS error envelopes send `str(e)` to the client; a Firestore message logged as `unverifiable=`; `mark_failed` stores the raw message; three precision gaps in the guard; a stale rationale sentence | `6inaj` (P2), `x7685`, `h5529`, `lvwvy`, `o2uyn`, `68shs` (P3) FILED. |
| B2 (`v8l6m`) | P0 (pre-fix) | 93 raw `?token=` hits in the request logs (79 demo, 14 staging; 73 + 13 of them Firebase ID tokens): 4 post-fix hits were the orchestrator's own bogus-token probes (1 staging, 3 demo), leaving 89 real pre-fix rows by that itemisation (76 demo, 13 staging) -- the B2 entry's own summary says 75 demo / 88; the one-row disagreement does not change the disposition | ACCEPTED residue (maintainer, 2026-09-14); zero real post-fix hits; zero app-stream or BigQuery hits. `k7h3l` (P3, RECORD/REPEATED columns unswept) FILED. |
| C2 (`bwevj`) reviews | P2/P3 | The deprecated `?token=` removal set (~54 test sites + the B0 filter); binary frames uncapped; a policy refusal had no on-screen message and the translated-schema size will one day cross the frame cap; the 1013 metric now also counts kit-store failures; a status-classifier test pins neither terminal status | `0j8e5` (P2), `4uub0` (P2), `nb9tx`, `5bbj1`, `6jezt` (P3) FILED. Fixed in C2 itself before the PR: a transient store error refused as a permanent denial; policy refusals retried five times and skipped the client save prompt (a dedicated terminal status now). |
| C3 (`vcjgs`) | P2/P3 | Emulator-backed rules tests need Java (none locally or in CI); `users/{uid}` write has no shape validation (rules auditor score 4, minor); one admin sign-in log line carried the email | `34y4y` (P2), `wnkky` (P3) FILED; the log line FIXED in C3. |
| C4 (`6088m`) reviews | P2 | Four editor schema-body routes accept unbounded JSON; the 5 MB fill-pdf cap is ~2x a large translated schema; wrong client messages for 413/408 | `07vpc`, `ij9ue`, `lhrln` FILED. |
| D (`m1dlv`) | P2 | Two human project Owners; `polyglot-cloudbuild-sa` never provisioned; bucket public-access prevention `inherited`; Hosting headers absent (E2); container scanning off; Firebase Auth settings and the Vertex opt-out unreadable | Hosting FIXED by E2 (live after deploy). The rest are maintainer decisions/asks listed in the posture doc. The runbook's own four defects (`dk5ok`, `zsr2h`, `hm0cw`, `ugbda`) FIXED in D. |
| E1 (`8v8i7`) reviews | P2 | The idle wipe fired 5 s after a status that only means "no socket traffic"; the bundle test built apps whose deps CI never installs; three sessionStorage keys survive the wipe; a pre-existing overlay test flake | The first two FIXED in E1; `vzvkk`, `y6b48` FILED. |
| E2 (`j29z1`) reviews | P1 (avoided) / P2 | `X-Frame-Options: DENY` would have broken Google sign-in (the app site serves Firebase Auth's iframe); the voice overlay loads executable code from jsdelivr; the ONNX glue needs `'unsafe-eval'`; the env-derived pin's wss demand | XFO dropped for `frame-ancestors` before the PR; `18o7c` (P2), `p3o51` (P2), `b45a4` (P3) FILED. |
| F1 (`ikdnd`) | P2/P3 | starlette 0.48's 2026 advisories; React Router 6 advisories; editor/admin deploy scripts build stale packages; Dependabot PRs close no bead; venv-path mismatch; the grouped Dependabot merge broke `dev` (#830 reverted it) | `5r456` (P2), `o9b51` (P2), `gdqmr`, `g4p1j`, `datcz` (P3) FILED. |
| F2 (`cwiip`) review | P2 (pre-existing) | uvicorn's "WebSocket accepted" line logs the request target incl. `?token=` at INFO on `uvicorn.error`, which `--no-access-log` does not cover; only an unpinned logger entry suppressed it | FIXED in F2 (#835, merged): pinned by `test_logging_access_log.py`. `kq042` (P3) FILED. |
| B0 (`6rj0j`) review | P3 | Stacked doc stamps | `q7oml` FILED (`dfxet` tracks the pattern). |

Every P2/P3 above has a bead (all children of `polyglot-pdf-uijam`, or
linked from the finding bead). Two P1-class items are NOT fixed and carry
no written acceptance yet: **PF-5 rate limiting** and **`e8wzz`** (the
second free-text `reason` site). Both are in the posture doc's decision
table; epic criterion 5 closes when the maintainer records a choice on
each.

## Epic criteria, as of this entry

| # | Criterion | State |
|---|-----------|-------|
| 1 | Inventory complete + live-verified | MET: the doc's store set equals the script's (tested); every row carries key set, PII class, retention, readers and guard; the 2026-09-15 live run reported zero keys outside any allowlist. |
| 2 | No credential or field value in Cloud Logging or BigQuery after the fix | MET for the fix timestamps B0 set (zero real post-fix hits; the residue accepted); each sink shape has its red-then-green sentinel. C2's deploy retires the last URL-borne form; a re-sweep after that deploy is the closing check. |
| 3 | Every route classified and cross-tenant-tested | MET (C1's matrices; C2 closes the one WS gap in PR). |
| 4 | Live posture equals the repo | PENDING the deploys: E2's headers and C3's rules are merged or in PR but not live; the bucket, container-scanning, Cloud Build SA and Owner items are the maintainer's asks; the Vertex opt-out is a console read. The runbook itself is complete. |
| 5 | Every finding dispositioned, scanning recurs | MET except the two P1 acceptances above; the CI security job runs on every PR since #812. |

## Review record

Fresh-eyes (Sonnet, read-only): round 1 found three inventory rows omitting
a staff-email key the script pins (`actor_email`, `employee_email`), C2's
socket changes stated as present fact while #834 is unmerged, the B2
count misquoted, the four undeployed BigQuery views presented as live, and
that the test pinned store names only -- all fixed (every scripted row now
carries the script's keys verbatim and the test pins them; C2 is hedged
everywhere; the views say so). Round 2: no gaps; it found the B2 entry's
own summary (75 demo) disagreeing with its itemised post-fix list (76) by
one -- pre-existing, now stated as 88-89 here rather than resolved from
prose. Docs-reviewer (Haiku, adversarial): NO-GAPS; its one borderline
note (the INDEX stamp) taken. No process other than git was started by
any reviewer.

## Lessons

- **The register is the deliverable, not the doc.** Writing the posture
  doc took an hour; establishing that every one of ~60 findings had a
  bead, a fix or an acceptance took longer and found the two P1 items with
  neither.
- **Derive the doc-vs-script set from the script's source, and only from
  the store cell.** The first draft of the test read the script's report
  keys by importing it (which pulls the Firebase Admin SDK) and matched
  store names anywhere in a row; both would have passed on prose.

## Files

`docs/standards/security-posture.md` (new), `tests/test_security_posture_doc.py`
(new), `docs/INDEX.md`, `docs/standards/hipaa-pii-policy.md`.
