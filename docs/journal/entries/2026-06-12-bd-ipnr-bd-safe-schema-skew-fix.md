---
date: 2026-06-12
bead: polyglot-pdf-ipnr
title: "BUG: bd_safe.py close/claim blocker-check fails -- 'column depends_on_id could not be found'"
tags: [tooling, beads, windows]
---

## Trigger

After upgrading `bd` from 1.0.4 to 1.0.5 via npm, every `bd_safe.py close` and
`bd_safe.py claim` call started failing with:

    Error checking blockers for <id>: check blockers: Error 1105: column
    "depends_on_id" could not be found in any table in scope

Worked around per session by calling `bd close` directly. Filed as bd
polyglot-pdf-ipnr.

## What shipped

Two-part fix:

1. **Root cause: two `bd` binaries, wrong one wins in subprocess.** Windows had
   both an npm-installed `bd` 1.0.5 and a standalone installer `bd` 1.0.4 at
   `AppData/Local/Programs/bd/bd.exe`. Python `subprocess.run(["bd", ...])` cannot
   execute `.CMD` shims (they need the Windows shell), so it fell through to
   `bd.exe` in the Programs directory -- the older 1.0.4 build that has a
   schema query referencing `depends_on_id`, a column that no longer exists in
   the dolt DB. The npm package ships its own `bd.exe` under
   `node_modules/@beads/bd/bin/`; prepending that directory to `PATH` at import
   time gives subprocess a directly-executable 1.0.5 binary.

2. **Fix lives in `swarm_config.py`, covers all swarm scripts.** The PATH fix
   was initially added to `bd_safe.py` but `closeout_housekeeping.py` (which also
   calls `bd` directly) does not import `swarm_config`, so closeout prep still
   failed. Moved the fix to `swarm_config.py` (runs at import time) and added
   `import swarm_config` to `closeout_housekeeping.py` and `bd_prime.py`.
   `next_bead.py` picks it up transitively via `bd_safe`.

3. **Removed the 1.0.4 standalone installer.** Deleted
   `AppData/Local/Programs/bd/{bd,bd.exe}` and the now-empty directory. The PATH
   fix in `swarm_config.py` remains as a defence-in-depth guard against any future
   dual-install scenario (no-op when the npm package dir doesn't exist).

Remote sessions are unaffected: they install `bd` via `go install` to a single
binary at `$(go env GOPATH)/bin/bd`, no `.CMD` shim, no dual-install possible.

## Lessons

**On Windows, `subprocess.run(["cmd_name", ...])` cannot execute `.CMD` shims.**
npm packages install a `.CMD` shim in `Roaming/npm/` which the Windows shell
resolves but Python subprocess does not; it falls through to the next `.exe` in
PATH. Fix: prepend the npm package's own `bin/` directory (which ships a real
`.exe`) to `os.environ["PATH"]` at import time. See `scripts/swarm_config.py`.

**One PATH fix in a shared config module beats per-script fixes.** Any script
that imports `swarm_config` gets it automatically at import time.

## Doc freshness

All stale docs flagged by closeout_prep (docs/components/auth.md,
schema-forms.md, tool-call-flow.md, ai-models.md, confirmation-and-audit.md,
hipaa-pii-policy.md, logging-and-cost.md, risk-rating.md,
stateless-architecture.md, terminology.md) are pre-existing staleness from
unrelated June 11 changes -- none track any file touched by this PR. Reviewed
and left as-is; their update is out of scope for this bug fix.

`docs/components/beads-remote-bootstrap.md` was flagged because `bd_prime.py`
was modified. Change was an internal `import swarm_config` for side-effect only;
no behavioral change to the bootstrap or prime flow. Doc content is current;
left as-is.

## Files touched

- `scripts/swarm_config.py` -- added npm bd PATH fix at module level
- `scripts/bd_safe.py` -- removed per-script copy of the fix (now in swarm_config)
- `scripts/closeout_housekeeping.py` -- added `import swarm_config`
- `scripts/bd_prime.py` -- added `import swarm_config`
