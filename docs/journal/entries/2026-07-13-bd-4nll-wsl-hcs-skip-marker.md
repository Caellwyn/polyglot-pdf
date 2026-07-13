---
date: 2026-07-13
bead: polyglot-pdf-4nll
title: "deploy-gate wrapper: skip on the WSL VM-boot (HCS/CreateVm) failure too, not just exec failure -- and check stdout"
tags: [testing]
---

## Trigger

`tests/test_deploy_all_kit_gates_wrapper.py` runs the deploy-gate bash harness and
skips (rather than fails) when Windows' System32 WSL `bash` shim can't run it --
but its skip detection only matched `execvpe`/`CreateProcessCommon`/`WSL (` on
`result.stderr`. On a box where the WSL VM itself cannot BOOT, the shim prints a
different error -- "A device which does not exist was specified. Error code:
...CreateVm/ConfigureGpu/HCS/0x800701b1" -- to STDOUT, matching no marker, so the
test FAILED instead of skipping: a false local red on every full-suite run
(observed while reviewing unrelated PRs this session; CI on ubuntu is unaffected).

## Fix

Extended `_WSL_SHIM_MARKERS` with the VM-boot shape (`CreateVm`, `ConfigureGpu`,
`HCS`, `0x800701b1`) and matched against BOTH streams (`stdout` + `stderr`
combined) -- the exec failure lands on stderr, the VM-boot failure on stdout. The
skip reason now reports both streams.

The guard still fires ONLY when `returncode != 0` AND a WSL-shim marker is
present, so a genuine harness regression (a real FAIL / an early abort with no WSL
marker) still fails -- preserving the CI coverage this wrapper exists to add. On
Linux CI bash execs natively, so no shape ever matches there.

## Verification

- On this box (WSL shim broken): the test now SKIPS with a recognizable reason
  (previously FAILED). Both shapes occur here across runs -- an `execvpe` exec
  failure and the `CreateVm/HCS` boot failure -- and the fix covers both.
- Decision-logic check across four cases: (A) HCS-on-stdout -> skip; (B)
  execvpe-on-stderr -> skip; (C) genuine regression (real FAIL, no WSL marker) ->
  does NOT skip (fails, as CI must); (D) success -> does NOT skip.
- `py_compile` clean; ASCII-only.

## Files touched

- `tests/test_deploy_all_kit_gates_wrapper.py`
