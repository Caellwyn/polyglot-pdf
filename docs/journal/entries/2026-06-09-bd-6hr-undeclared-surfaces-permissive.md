---
date: 2026-06-09
bead: polyglot-pdf-6hr
title: "Undeclared surfaces no longer collide with everything (permissive guard)"
tags: [harness, beads, workflow, collision-guard]
---

## Trigger

While picking up uov Phase 1 (uov.4, a frontend-only test bead), `/next-bead`
and `bd_safe.py claim` BLOCKED it -- and every other ready bead -- against
`polyglot-pdf-akn`, an active P1 backend-only bug (open PR #128, touches only
`backend/services/form_filling_service.py`) that had declared NO surfaces. The
write-overlap guard treated akn's empty surface set as "collides with
everything," freezing the whole board behind one undeclared in-progress bead,
despite uov.4 (frontend) and akn (backend) having provably disjoint footprints.
Attempting to declare akn's surfaces to unblock was (correctly) denied -- it is
another session's bead.

## Maintainer decision

The guard should only block on POSITIVELY-STATED, actually-overlapping surfaces.
An empty surface set on EITHER side -- whether the bead was simply never
annotated (the common case) or a tooling failure left it UNKNOWN -- means "no
stated surface to collide on" and must NOT block. It should be the RARE bead that
legitimately blocks everything; the default is permissive, not fail-closed. This
reverses the conservative half of bd polyglot-pdf-8y7.

## What shipped

- `bd_safe.py _surfaces_overlap`: returns `False` (was `True`) when either side
  is empty. Now only two concretely-declared, overlapping surfaces block.
- `_surface_collision`: dropped the now-unreachable "UNKNOWN surfaces" detail
  branch -- post-fix, reaching the collision body implies both sides are
  non-empty with a nameable overlapping pair.
- The PR-derivation path (bd 8y7) stays: it still derives an under-declared
  active claim's real footprint from its open PR, so a genuine overlap is matched
  on real files. It is just no longer load-bearing for the empty case.
- Tests: `test_surfaces_overlap_empty_policy` (renamed, flipped expectations);
  `test_undeclared_surfaces_candidate_not_blocked` + a new
  `test_undeclared_active_claim_does_not_block_others` (the akn case) in
  test_next_bead.py; comments on the UNKNOWN/derivation tests updated to note the
  permissive downstream policy.
- Doctrine: `docs/doctrine/workflow.md` surface-declaration bullet rewritten.

## Decisions (defended)

- **Empty = no block on BOTH the unannotated AND the tooling-failure path**
  (maintainer's explicit call when asked: "everything empty = no block," the
  literal positively-stated-only semantics). Trade-off noted in the docstring: a
  transient gh/bd failure that empties one side could let a real overlap through;
  surfaces are advisory scheduling hints and the same-bead PR/branch guards remain
  the hard backstop against two workers on one bead.
- **Filed 6hr WITH declared surfaces** (the four files above) -- a surface-less
  bug bead would itself have been the next board-freezer under the old policy.

## Verification

- Live: with the fixed code, `_surface_collision('polyglot-pdf-uov.4')` and
  `'uov.5'` both return `None` against the real bead state (akn still undeclared)
  -- the board is unfrozen.
- Harness suite: 397 passed (incl. the rewritten bd_safe + next_bead cases).
- All edited source files ASCII-clean.
- Note: the fix only protects OTHER sessions once merged to dev -- until then the
  unpatched `bd_safe.py` on dev still blocks on akn. Inherent to fixing the tool
  with the tool.
