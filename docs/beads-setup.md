# Beads setup (prerequisite for the swarm tooling)

*Last updated: 2026-08-05 (docs audit bd polyglot-pdf-2zk3: removed swarm_init.py references; updated beads URLs; fixed config.yaml guidance to sync.remote).*

The swarm scripts (`bd_safe.py`, `closeout_housekeeping.py`, etc.) and the
`/closeout` skill all assume [beads](https://github.com/gastownhall/beads)
(`bd`) is installed and wired to this repo's remote. This doc is the one-time
per-machine + per-clone setup.

> Generalized from a working project's setup notes. The traps below were all
> hit for real -- they are not hypothetical.

## Per-machine (once per computer)

### 1. Install the `bd` binary

Beads is a single Go binary, not a Python/npm package -- the kit can't vendor
it. Install from the beads releases (https://github.com/gastownhall/beads) and
confirm it's on PATH:

```
bd version
```

### 2. Windows long-path prerequisites (skip on macOS/Linux)

Dolt's git-remote-cache builds very deep paths (well over 260 chars even from a
short root), so enable long paths:

```powershell
# Elevated PowerShell -- registry:
Set-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name LongPathsEnabled -Value 1
```
```
git config --global core.longpaths true   # verify: returns "true"
```

Also clone under a SHORT root (`C:\code\`, `C:\Users\<you>\code_projects\`) --
a deep worktree path can still trigger `$GIT_DIR too big` on push.

### 3. Set the maintainer role BEFORE the first bd command

If you OWN this repo, you are a maintainer, not a contributor:

```
git config beads.role maintainer
```

**Trap:** `bd init --contributor` creates a parallel store at
`~/.beads-planning/` and an `additional:` entry in `.beads/config.yaml`.
Symptom: `bd dep add` fails with "issue not found" / "must resolve to the same
store." Keep `.beads/config.yaml` with only `sync.remote:` pointing to your
GitHub repository (do not add multi-repo `repos.primary` configuration).

## Per-clone (once per checkout of this repo)

### 1. Bootstrap the store (NOT `bd init`)

From the **main repo dir** (never a worktree):

```
bd bootstrap --yes
```

This pulls the canonical issue set from the remote. **Use `bd bootstrap`, not
`bd init`** -- `bd init` creates a fresh history with no common ancestor, which
makes `bd dolt push` fail later with "no common ancestor."

### 2. Wire beads to the GitHub remote

Beads keeps its OWN Dolt remote config, separate from `git remote -v`. Seeing
`origin` in `git remote -v` is NOT enough -- configure it once:

```
bd dolt remote add origin https://github.com/OWNER/REPO.git
bd dolt remote list    # should show: origin git+https://github.com/OWNER/REPO.git
```

**Use the SAME protocol your git credential helper authenticates.** If your
system `origin` is SSH (`git@github.com:...`) but beads' remote is HTTPS, you
can have a working `git push` AND a failing `bd dolt pull` (different credential
paths). Smoke-test with the protocol beads uses:

```
git ls-remote https://github.com/OWNER/REPO.git HEAD
```

### 3. Confirm the bd-prime hooks are installed

The kit includes `.claude/settings.json` pre-configured with `SessionStart` +
`PreCompact` hooks (via `beads_remote_bootstrap.py` and `bd_prime.py`) that
inject the beads workflow context every session. If you merged the kit into an
existing `.claude/settings.json`, confirm both hooks are present.

## Sync architecture (how it works)

- The local Dolt DB lives at `<main-repo>/.beads/embeddeddolt/` and is
  **gitignored** (binary, machine-specific -- never commit it).
- The canonical store is the remote at `refs/dolt/data` on `origin` -- invisible
  in GitHub's web UI, accessed via `bd dolt pull` / `bd dolt push` and visible
  via `git ls-remote origin "refs/dolt/*"`.
- **Worktrees inherit the main repo's store** via git common-dir discovery. Use
  `bd worktree create <name>` (it wraps `git worktree add`, auto-gitignores the
  path, verifies inheritance). With plain `git worktree add`, delete any
  `.beads/embeddeddolt/` that gets auto-created in the worktree -- a stray one
  breaks inheritance. Verify: `ls .beads/` in a worktree should NOT show
  `embeddeddolt/`.

## The cadence (why pull-before / push-after)

The local DB is a cache; the remote is truth. Every bd write is bracketed:
`bd dolt pull && bd <write> && bd dolt push`. Skipping the pull is the
parallel-claim bug class (two workers claim the same bead). `scripts/bd_safe.py`
does the bracketing for you. Pull at session start before any read, too.

## Gotchas

- **`bd dolt push` prints "Push complete" even when it no-ops** (no remote
  configured). Verify the remote SHA actually advanced:
  `git ls-remote origin "refs/dolt/*"` before/after.
- **No common ancestor on push** -> two independently-init'd DBs. Recovery:
  `bd dolt push --force` (overwrites remote -- only when one side has all the
  work) or `bd bootstrap` (discards local, re-clones).
- **Don't `bd bootstrap` from inside a worktree** -- it creates a per-worktree
  store that breaks inheritance. Bootstrap from the main repo dir only.

See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for the
beads-side details.
