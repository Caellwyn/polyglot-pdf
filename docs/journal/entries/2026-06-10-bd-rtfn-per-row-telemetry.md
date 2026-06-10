---
id: 2026-06-10-bd-rtfn-per-row-telemetry
beads: [polyglot-pdf-rtfn]
tags: [harness, telemetry, merge-conflict, scripts]
pr: 142
date: 2026-06-10
---

# Per-row telemetry files: eliminate GitHub PR merge conflicts (bd polyglot-pdf-rtfn)

## Problem

`docs/journal/harness_ledger.jsonl` was a single append-only file shared by
every closeout session. Two PRs open at the same time both append a row; GitHub's
server-side merge cannot resolve that -- it reports an unresolvable conflict.

The existing `.gitattributes` `union` merge driver only applies to local `git
merge`, not to GitHub's server-side PR merge. It was silently ineffective for the
actual workflow.

## Solution

Each closeout now writes one JSON file:

```
docs/journal/telemetry/<recorded_at_hyphens>-<session_id_prefix8>.json
```

e.g. `docs/journal/telemetry/2026-06-10T12-34-56Z-ab12cd34.json`

Parallel PRs never touch the same path, so GitHub merges them trivially with no
configuration needed.

## Changes

- `scripts/harness_ledger.py` -- new `append_row()` writes one file per row to
  `TELEMETRY_DIR`; new `_iter_all_rows()` scans both new dir and legacy JSONL;
  `main()` prints `TELEMETRY_FILE: <repo-relative-path>` on stdout
- `scripts/closeout_finish.py` -- captures the `TELEMETRY_FILE:` stdout line,
  commits only that exact file; returns early if None (GAP or --dry-run)
- `tests/test_harness_ledger.py` + `tests/test_closeout_finish.py` -- rewritten
  for per-file protocol (60 tests; 256 total passing)
- `docs/journal/telemetry/` -- 71 migrated rows + `.gitkeep`
- `.gitattributes` -- union rule annotated as inert/legacy with explanation
- `.gitignore` -- comment updated to reference new path
- `.claude/skills/closeout/SKILL.md` -- step 8.5 updated

## Backward compatibility

`_iter_all_rows()` scans both the new per-file directory and the old
`harness_ledger.jsonl`, so all 71 pre-migration rows still count toward
experiment state. The legacy JSONL is no longer written but remains readable.

## Stale docs (pre-existing, not caused by this PR)

`closeout_prep` flagged several docs as stale:

- `docs/components/config-deployment.md`
- `docs/components/context-compression.md`
- `docs/components/websocket-routing.md`
- `docs/standards/ai-models.md`
- `docs/standards/confirmation-and-audit.md`
- `docs/standards/hipaa-pii-policy.md`
- `docs/standards/logging-and-cost.md`
- `docs/standards/risk-rating.md`
- `docs/standards/stateless-architecture.md`
- `docs/standards/voice-and-vad.md`
- `docs/technical_guide.md`

All track `backend/config.py`, `live_ai_gemini.py`, `webFormConnection.ts`, or
`callback_handler.py` -- none of which this PR touches. The staleness comes from
other open work (bpm7, pen, wpw bundles merged 2026-06-10). These docs are tracked
by their respective beads.
