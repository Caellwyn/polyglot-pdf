---
date: 2026-07-10
bead: polyglot-pdf-4w0l
title: "deploy scripts: json.tool validation failure falls back to shipping the RAW (possibly invalid) index.json"
tags: [hotfix, testing]
---

## Trigger

Found during the bd 15ic Opus review: deploy-all.sh and
scripts/deploy-form-kit.sh build the voice-app manifest (index.json) by bash
string concatenation and validated it with
`python3 -m json.tool || echo $raw` -- so when validation FAILED, the fallback
shipped the raw invalid JSON to GCS and the deploy reported success. The voice
app then cannot parse the manifest (no forms load) with zero deploy-time
signal. 15ic closed the reachable-from-the-UI trigger (bad labels are now 422
at the route); this is the defense-in-depth fix.

## What shipped

- Both scripts now route the manifest through an identical
  `write_validated_manifest()` helper: invalid JSON aborts the deploy
  (nonzero exit, clear [ERROR] lines, nothing uploaded).
- The old fallback existed to tolerate a missing python3.
  `find_manifest_python()` keeps that tolerance without the swallow: it
  resolves python3 -> python -> py, probing each candidate with `-c pass`
  rather than `command -v` -- the Windows Store ships a python3
  App-Execution-Alias stub that `command -v` finds but that cannot run, which
  would have misreported every manifest as invalid on a stock Windows box
  (hit live on the dev machine during this work). No working interpreter at
  all is fatal: unvalidatable is not shippable, and gcloud itself requires
  Python so a working deploy machine always has one. This narrows criterion
  2's "missing python3 still works" to "a runnable fallback interpreter
  exists" -- a deliberate call, noted in the PR.
- tests/test_deploy_manifest_validation.py extracts the bash helpers from the
  REAL script text and runs them under bash: invalid aborts, valid
  pretty-prints, candidate fallback skips a missing python3, no-interpreter
  aborts, and the two scripts' helper copies are asserted byte-identical (no
  shared lib -- the scripts already duplicate the whole manifest block, so the
  identity test is the drift guard).
- Fresh-eyes triage: round 1 (sonnet) NO-GAPS (two low-confidence latent
  notes -- raw-manifest echo on the abort path, spaces-in-override-path word
  splitting -- both judged non-blocking by the reviewer and by me, no beads
  filed); required Opus final round NO-GAPS. Outer review (Step 5.6):
  primary Opus NO-GAPS + second independent Opus NO-GAPS on the identical
  final diff, one round each.

## Lessons

- `command -v python3` is not "python3 works" on Windows: the Store stub
  passes the existence check and fails execution. Probe with `-c pass`.
- MSYS path conversion at the native-python -> Git-Bash boundary mangles argv
  elements containing colons (any JSON `"key":value`), so a test harness must
  feed JSON to bash via a file, never argv.

## Doc freshness

- No component/standards doc tracks the deploy scripts' manifest validation
  behavior; nothing to bump. Pre-existing stale standards docs (tracking
  files this branch did not touch) reviewed and left per the "already stale
  before you" rule.

## Files touched

- deploy-all.sh
- scripts/deploy-form-kit.sh
- tests/test_deploy_manifest_validation.py (new)
- docs/journal/entries/2026-07-10-bd-4w0l-manifest-validation.md
