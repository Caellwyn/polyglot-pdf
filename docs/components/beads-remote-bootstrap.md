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
whenever a remote container hasn't hydrated the live store — empty, un-openable,
**or showing a stale committed snapshot** — so a session never has to rediscover
this.

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

### The stale-snapshot trap (why a hydration marker, not an issue count)

There is a fourth, subtler failure that an issue count alone cannot catch. The
repo also ships a committed `.beads/issues.jsonl` **backup snapshot**, and bd is
configured (via `issue-prefix` in `config.yaml`) to rebuild a local DB from it on
a fresh clone. In a remote container that snapshot can be **days stale** (it is
only refreshed when someone commits it), yet it makes `bd` report a *populated*
store — so "`total_issues > 0`" looks hydrated while the session is actually
staring at an old, partial tracker (e.g. 30 issues instead of 117). That is worse
than failing loudly.

So in a **remote container** (detected by the `local_proxy` git origin) the
committed JSONL is **never** treated as authoritative. The bootstrap writes a
per-container marker — **`.beads/.cache/.hydrated`** — *only* after a successful
hydrate from `refs/dolt/data`, and that marker (not an issue count) is the
authoritative "this container holds the live store" signal for both the script's
idempotency check and the `bd_prime` banner. Fresh container ⇒ no marker ⇒
re-hydrate, no matter what the JSONL snapshot says.

## What the script does

Idempotent; safe to run anytime. It NEVER pushes. On a **non-remote** checkout it
refuses the destructive wipe-and-clone and leaves a populated local store
untouched (this self-heal is for disposable remote/web containers only).

1. **Already hydrated this container?** (`.beads/.cache/.hydrated` marker exists
   **and** `bd stats --json` → `summary.total_issues > 0`) → exit. Both halves
   matter: `bd prime` auto-creates an *empty but openable* DB, and a stale JSONL
   snapshot creates a *populated but outdated* one — the marker is what
   distinguishes either from the real live store. The script wipes any such
   empty / partial / stale DB before cloning.
2. **Hydrate** over the authenticated proxy origin (`sync.remote` neutralised, then
   restored). This already advances the clone through migrations 41→46.
3. **Repair wisps** (only if bd still can't open): recreate the `wisps` / `wisp_*`
   tables with the **exact schema of the installed bd version** — sourced from a
   throwaway `bd init` in a tempdir, so there is no hand-written DDL to rot — then bd
   runs its final migration (0047) and opens. Needs a `dolt` CLI: PATH → cached
   download → latest release download → `go install`, in that order, cached under
   the gitignored `.beads/.cache/`.
4. **Mark hydrated** — write `.beads/.cache/.hydrated` so subsequent `bd prime`
   runs in this container stay quiet and re-runs no-op.

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
  bootstrap banner when a remote container's store is un-hydrated, empty, or stale.
- `.beads/config.yaml` — `sync.remote` (the github URL the script temporarily steers
  around) and the dolt data-dir.
- Closeout / beads workflow: [`../doctrine/workflow.md`](../doctrine/workflow.md).
