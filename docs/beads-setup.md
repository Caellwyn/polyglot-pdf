# Beads setup (prerequisite for the swarm tooling)

*Last updated: 2026-09-16. See [docs/journal/entries/2026-09-16-bd-prskq-windows-bd-path-setup.md](journal/entries/2026-09-16-bd-prskq-windows-bd-path-setup.md) for closeout details.*

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

There is also an npm wrapper (`@beads/bd`) that carries the same binary; it is
a fine way to install, and it is what this machine uses. **On Windows an npm
install needs step 2 as well** -- npm puts a shell script on PATH ahead of the
real executable, which makes every `bd` call open a console window. A release
binary installed directly does not need it.

### 2. Windows: put the native `bd.exe` ahead of npm's shim (skip on macOS/Linux)

**Skip this if `bd` came from the beads releases** -- a directly-installed
binary has no shim. This is only for an npm install (`@beads/bd`).

npm's Windows install puts three launchers in `%APPDATA%\npm\`: `bd` (a
`#!/bin/sh` script), `bd.cmd`, and `bd.ps1`. That directory goes on PATH; the
package's own `bin\` -- which holds the real `bd.exe` -- does not. So a bare
`bd` from Git Bash finds the **shell script**, and Windows runs it by launching
`sh.exe`, which opens a console window. One window per `bd` call is unpleasant;
across several concurrent agent sessions each doing pull-before-read and
push-after-write it becomes a cascade of windows that steal keyboard focus
while you type (bd polyglot-pdf-rdftu; measured peak 261 concurrent `git.exe`
and 74 `sh.exe`).

Fix it by putting the package's `bin\` directory FIRST in your **user** PATH:

```powershell
# Normal (non-elevated) PowerShell. Back up first -- this rewrites user PATH.
$bd = Join-Path $env:APPDATA 'npm\node_modules\@beads\bd\bin'
if (-not (Test-Path (Join-Path $bd 'bd.exe'))) { throw "no bd.exe at $bd" }
$u = [Environment]::GetEnvironmentVariable('PATH','User')
# Timestamped so re-running cannot overwrite an earlier backup.
$u | Set-Content "$env:USERPROFILE\Desktop\userpath-backup-$(Get-Date -f yyyyMMdd-HHmmss).txt"
if ($u -notlike "*$bd*") {
  [Environment]::SetEnvironmentVariable('PATH', "$bd;$u", 'User')
}
```

Open a NEW terminal, then verify `bd.exe` -- not the extensionless shim --
comes first:

```
where bd
```

The first line must end in `\@beads\bd\bin\bd.exe`. If it names
`%APPDATA%\npm\bd` instead, the entry did not land or the terminal is stale.

**Why this lives in your user PATH and not in the repo.** A tracked config
cannot express it: the PATH separator is `;` on Windows and `:` on POSIX, and
no single literal is correct on both -- `;` silently drops the first real entry
on macOS/Linux, `:` splits the `C:` drive letter on Windows, and the Git-Bash
form (`/c/Users/...`) resolves in bash but not for a Windows-native process.
Machine-specific paths therefore stay on the machine; a test
(`tests/test_claude_settings_env.py`) keeps them out of the shared
`.claude/settings*.json` (bd polyglot-pdf-6peeg).

Python callers are already covered and need no setup -- `scripts/swarm_config.py`
prepends the same directory to `os.environ["PATH"]` at import time, derived
from the home directory and guarded on the file existing, so it is a no-op off
Windows. This step covers the *shell* callers (the skills and hooks that run
bare `bd`).

### 3. Windows long-path prerequisites (skip on macOS/Linux)

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

### 4. Set the maintainer role BEFORE the first bd command

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
