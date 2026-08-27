---
date: 2026-08-27
bead: polyglot-pdf-b5nmq
title: "fix(scripts): actually scope the local backend reload watch -- uvicorn drops a --reload-dir under the cwd"
tags: [hotfix, harness, schema-editor, verification]
---

## Trigger

The maintainer reported the SAME symptom the previous day's fix
(bd polyglot-pdf-nukx2, PR #650) was supposed to have removed: the local
schema-editor backend still reloading on other worktrees' edits --

```
WARNING:  WatchFiles detected changes in '.claude\worktrees\ik7e-cost-ceiling\backend\routes\websocket_routes.py'. Reloading...
```

-- mid-request, this time killing a translation-status call on `i-90_v2`.
The running backend was confirmed to be launched with the #650 fix in
place (absolute `--reload-dir C:/Users/caell/.../backend`), so the fix was
present and not working.

## Root cause

`uvicorn.supervisors.watchfilesreload.WatchFilesReload.__init__` filters
the configured reload dirs:

```python
for directory in config.reload_dirs:
    if Path.cwd() not in directory.parents:
        self.reload_dirs.append(directory)
if Path.cwd() not in self.reload_dirs:
    self.reload_dirs.append(Path.cwd())
```

Any reload dir that is a **child of the process cwd** is dropped, and the
cwd is appended in its place. Both launchers ran uvicorn from the repo
root with a reload dir of `backend/` underneath it, so the effective watch
set was the whole repo root -- `.claude/worktrees/` and its ~130 sibling
checkouts included. This is true for the relative form and the absolute
form alike; #650's move from relative to absolute changed nothing, because
the discriminator is the parent relationship, not the path's spelling.

Reproduced against the installed uvicorn (0.24.0) by replaying that dir
resolution:

| cwd | `--reload-dir` | effective watch |
|---|---|---|
| repo root | `backend` | repo root |
| repo root | `<abs>/backend` | repo root |
| `<repo>/backend` | `<abs>/backend` | `<repo>/backend` |

## Why #650 looked verified

uvicorn's startup banner --
`INFO: Will watch for changes in these directories: [...\backend]` --
prints `config.reload_dirs`, the **configured** set, before the supervisor
filters it. The log says the fix worked while the watcher watches
something else entirely. Nothing downstream ever contradicts it, so the
only way to catch this is to observe an actual reload (or replay the
supervisor's own filter), never to read the banner.

## Fix

Launch uvicorn with `backend/` as its **working directory**, in both
`scripts/run-schema-editor.sh` and `scripts/dev-local.ps1`. With
`cwd == the reload dir` the supervisor's filter keeps exactly that dir.
The absolute `--reload-dir` is retained: it is what newer uvicorns honor
directly, and it is inert under the 0.24 filter now that the cwd matches.

`PYTHONPATH` already pins imports to the repo root, so `backend.main`
still resolves to this checkout. But the cwd move is NOT free for file
paths, and the first version of this fix got that wrong -- see below.

`--reload-exclude` remains the wrong tool here, for a second reason beyond
the one #650 recorded (its resolver takes relative patterns only and
raises `NotImplementedError` on an absolute one): a relative exclude dir
would never match the absolute changed paths the watcher reports.

## The second half: cwd-relative paths, and repeating scar #8

The first version of this fix shipped a comment asserting that "backend
runtime paths anchor on `__file__`, not the cwd." I had grepped, seen
`backend/config.py`'s `__file__`-anchored `FORM_KITS` root, and
generalized. The pre-PR fresh-eyes review caught that the claim was false:
my grep pattern missed default ARGUMENTS (`log_dir: str = "backend/logs"`),
so `DevFileLogger` and the three `live_ai_gemini` debug dumps would all
have started writing to `backend/backend/logs/...`.

That is scar #8 exactly -- I fixed the instance the maintainer reported
and asserted the set was clean instead of mechanically enumerating it.
Re-enumerating with an AST scan rather than a regex then found a THIRD
site my corrected grep still missed: the `.env.DEV` marker probe in
`_is_development_mode()`, whose cwd-relative candidates decide whether
local PHI logging turns on at all.

Fixed sites, all now `__file__`-anchored:

| Site | Was |
|---|---|
| `dev_file_logger.DevFileLogger.log_dir` | `Path("backend/logs")` |
| `dev_file_logger._is_development_mode()` | 2 cwd-relative `.env.DEV` candidates |
| `live_ai_gemini` audio-out + SI dumps (x3) | `Path("backend/logs/...")` |

`token_file_logger` already resolved against a `__file__`-derived root and
needed no change -- it is pinned rather than edited.

The pin is on the SET, not the sites: `test_runtime_paths_are_cwd_independent.py`
AST-scans runtime code for a `Path()`/`open()` built from a `"backend/..."`
literal, so the next such path fails CI. That test is what found the third
site, which is the argument for pinning the set over the instances.

## Verification

Started a backend the new way on a spare port and watched the log:

- touching `.claude/worktrees/ik7e-cost-ceiling/backend/routes/websocket_routes.py`
  (the exact file from the maintainer's report) produced **zero**
  `WatchFiles detected` events;
- touching this worktree's own `backend/main.py` reloaded immediately.

Plus the 5-mutation check on the new pin: each mutation reverted one real
behavior (the `_LOG_ROOT` anchor, its use at a call site, the two logger
defaults, the marker probe) and turned the corresponding assertion red;
restore green.

## Lessons

**A log line that reports configuration is not evidence about behavior.**
#650 was verified by reading uvicorn's own claim about what it would
watch, rather than by causing the event the fix was supposed to suppress.
Where a fix suppresses an event, the verification is to fire the event.
Stored as `bd remember verify-suppression-by-firing-the-event`.

**A grep that comes back clean has not enumerated the set.** Both halves
of this bead are the same error at different scales: #650 fixed the
reported instance and generalized from a plausible-looking check, and then
my own first commit did it again one layer down. The AST scan found what
two rounds of grep did not -- when the claim is "there are no others,"
the enumeration has to be structural, not textual.
