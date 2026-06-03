# Beads remote bootstrap

**Tracks:** scripts/beads_remote_bootstrap.py scripts/bd_prime.py

*Last updated: 2026-06-03*

How a fresh **remote / web / ephemeral** Claude Code session gets a working beads
(`bd`) database. Local long-lived checkouts never need this — they already hold a
hydrated store. This subsystem exists entirely for containers that are cloned
fresh on every session.

## TL;DR

A new remote container has the **code** but not the **beads database**. Run once:

```
python scripts/beads_remote_bootstrap.py
```

Then `bd ready` / `bd show` / `bd create` work normally. The SessionStart hook
([`scripts/bd_prime.py`](../../scripts/bd_prime.py)) prints a banner pointing here
whenever it detects an un-hydrated or empty store, so a session never has to
rediscover this.

## Why it's needed (three independent blockers)

The beads store does **not** live in the git working tree. It lives in the Dolt
ref **`refs/dolt/data`** (a repo-level ref, synced over the same git origin as the
code). A plain container clone does not materialise it, and three things then
block a naive `bd bootstrap`:

1. **The prime hook lies.** Generic `bd prime` prints *"No git remote configured —
   issues are saved locally only."* That is false here: beads **does** sync, through
   `refs/dolt/data`. `bd_prime.py` now suppresses that confusion and prints an
   accurate, actionable banner instead.
2. **Credentials.** `sync.remote` in `.beads/config.yaml` is the public
   `github.com` URL, so `bd bootstrap` attempts a *Dolt-native* clone of github.com —
   which has no credentials in the sandbox and fails. Git in a remote container only
   works through the session's **authenticated local proxy origin**
   (`git+http://local_proxy@127.0.0.1:<port>/…`). The script neutralises
   `sync.remote` for the duration of the clone so `bd bootstrap` falls back to
   cloning over that git origin, then restores `config.yaml` exactly.
3. **The dolt-ignored `wisps` tables.** `wisps` / `wisp_*` are in `dolt_ignore`
   (so per-clone wisp state can't cause merge conflicts), which also means they are
   **absent from `refs/dolt/data`**. On a fresh clone bd migrates the schema forward,
   but migration `0047_recompute_mixed_is_blocked` references `wisps` — which does not
   exist — so bd aborts with `table not found: wisps` and **cannot open the database
   at all**. (A long-lived local checkout dodges this: it only ever *pulls* into a DB
   that already has the local wisp tables. Only a fresh clone trips it. This is an
   upstream beads fresh-clone bug.)

## What the script does

Idempotent; safe to run anytime. It NEVER pushes.

1. **Already hydrated?** (`bd stats --json` → `summary.total_issues > 0`) → exit.
   The `> 0` check is load-bearing: `bd prime` auto-creates an *empty but openable*
   DB, so "does bd open?" alone is a false positive that would strand the session on
   an empty tracker. The script wipes any such empty/partial DB before cloning.
2. **Hydrate** over the authenticated proxy origin (`sync.remote` neutralised, then
   restored). This already advances the clone through migrations 41→46.
3. **Repair wisps** (only if bd still can't open): recreate the `wisps` / `wisp_*`
   tables with the **exact schema of the installed bd version** — sourced from a
   throwaway `bd init` in a tempdir, so there is no hand-written DDL to rot — then bd
   runs its final migration (0047) and opens. Needs a `dolt` CLI: PATH → cached
   download → latest release download → `go install`, in that order, cached under
   the gitignored `.beads/.cache/`.

## The one caveat: schema version on push

A remote session runs bd **`@latest`** (newer schema than the maintainer's
level-40 canonical store). Reading and local writes are fine. But the **first
`bd dolt push` from a remote session** (e.g. via `/closeout`) bumps the canonical
schema and carries the recreated wisp tables into `refs/dolt/data`. After that the
maintainer's local `bd` must be **`@latest`** too, or it can't read the upgraded
store:

```
go install github.com/steveyegge/beads/cmd/bd@latest
```

The local DB migrates 40→47 cleanly because `wisps` already exists locally (unlike
a fresh clone). Do this before — or right after — the first remote-session push.

## Related

- [`scripts/bd_prime.py`](../../scripts/bd_prime.py) — SessionStart hook; prints the
  bootstrap banner when the store is un-hydrated/empty.
- `.beads/config.yaml` — `sync.remote` (the github URL the script temporarily steers
  around) and the dolt data-dir.
- Closeout / beads workflow: [`../doctrine/workflow.md`](../doctrine/workflow.md).
