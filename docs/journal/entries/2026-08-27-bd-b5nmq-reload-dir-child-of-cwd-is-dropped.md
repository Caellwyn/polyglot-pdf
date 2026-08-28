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
AST-scans runtime code for a path built from a leading `"backend"` literal,
so the next such path fails CI. That test is what found the third site,
which is the argument for pinning the set over the instances.

The first version of that test scanned only for `Path("backend/...")` --
and a second review round caught that its docstring claimed to "pin the
set" while `os.path.join("backend", ...)`, `Path(f"backend/{x}")` and
`Path("backend" + x)` all sailed through. Same overclaim, third time, now
one layer further out: the guard against the unenumerated set was itself
unenumerated. It now covers those shapes, and
`test_detector_catches_each_path_building_shape` pins WHICH shapes it can
see -- 8 that must flag, 6 that must not -- so the detector cannot quietly
narrow again. Its docstring also now states the real limit: a path
assembled entirely at runtime is still invisible to a static scan.

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

Full backend suite green at each stage; 2783 passed at the end.

## The third half: the audit trail, and the guard failing its own test

The Opus cross-surface review then found a consumer the cwd move had
broken: `confirmation_logger.py` defaulted to a bare `"logs/confirmations"`,
so the local backend wrote the confirmation audit trail to
`backend/logs/confirmations` while `scripts/read_confirmations.py` -- run
"from the repo root" per its own docs -- read `logs/confirmations`.
Confirmed by resolving both from each cwd: they agree on `origin/dev` and
diverge on this branch. The failure is silent and badly shaped for this
particular file: the reader reports "no events" for a session it cannot
see, indistinguishable from a real gap in a trail whose purpose is
liability protection. Deployed is unaffected (Firestore mirror), which is
also the only reason this stayed local.

The reviewer called it out of scope and filed it. It was fixed here
instead: this change caused it, and shipping the cause while deferring the
fix on an audit path is not a trade worth making.

**Then the interesting part.** Reverting that fix left the new guard
GREEN -- the guard written two rounds earlier to prevent exactly this. Two
reasons, both the same mistake: it only matched `"backend/"`-prefixed
literals (the invariant is "no cwd-relative paths", not "no backend/
literals"), and it only inspected literals sitting inside a call, while the
real one lived in a module CONSTANT and reached `os.getenv` as a variable.
The indirection that hid the bug from a grep hid it from the AST scan too.

Widened to match any cwd-relative literal, to read `os.getenv(KEY, default)`
second arguments, and to scan path-shaped constants. A later re-review found
that scan still blind to ANNOTATED assignments -- and every `config.py`
`Settings` field is annotated, i.e. the likeliest home for the next one --
so that was closed too. Writing the negative case for it then exposed a
false positive the re-review had judged unreachable: a bare `LOG` in the
name pattern matched `LOG_LEVEL`, whose value `"info/debug"` is path-shaped
enough to pass the value check. `LOG` is gone; the trailing noun
(DIR/PATH/ROOT/FILE/FOLDER) is what identifies a path constant.

Both mutations now fail naming the exact file and line -- the real
`confirmation_logger` revert, and the re-review's own annotated repro in
`config.py`. Both were green before.

## Lessons

**A log line that reports configuration is not evidence about behavior.**
#650 was verified by reading uvicorn's own claim about what it would
watch, rather than by causing the event the fix was supposed to suppress.
Where a fix suppresses an event, the verification is to fire the event.
Stored as `bd remember verify-suppression-by-firing-the-event`.

**A check that comes back clean has not enumerated the set.** This bead
is the same error at three scales: #650 fixed the reported instance and
generalized from a plausible-looking check; my first commit did it again
one layer down with a grep; and my first version of the GUARD did it a
third time, catching one path-building shape while claiming to cover them
all. Each time the artifact was correct about what it checked and wrong
about what it implied.

The pattern worth extracting: an incomplete check is more dangerous than
no check, because it converts "unverified" into "verified" in the reader's
head. So the question to ask of any completeness claim is not "did it
pass?" but **"what exactly can this see, and what would slip past it?"** --
and then to pin that answer, as `test_detector_catches_each_path_building_shape`
now does.

**And run the mutation that matters against the guard itself.** The guard
here went green while the bug it existed to catch was live in the tree; it
was only caught by reverting the real fix and watching what the guard did.
Five earlier mutations had all passed -- they tested the sites the guard
already knew about, which is the comfortable mutation, not the informative
one. The informative mutation is the one that reintroduces the *actual
defect a reviewer just found*. Of the five rounds in this bead, four were
found by a reviewer and one by a test case written to contradict a
reviewer's judgment. None were found by the checks passing.
