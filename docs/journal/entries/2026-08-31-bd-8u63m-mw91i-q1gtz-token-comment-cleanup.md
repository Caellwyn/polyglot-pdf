---
date: 2026-08-31
bead: polyglot-pdf-8u63m, polyglot-pdf-mw91i, polyglot-pdf-q1gtz, polyglot-pdf-ve94p, polyglot-pdf-3nib0
title: "docs+test: clean up the last comments/fixtures describing the retired editor shared-token gate"
tags: [docs, testing, editor-auth]
---

## Trigger

`bd polyglot-pdf-hn0jq` replaced the editor's shared-secret gate
(`SCHEMA_EDITOR_TOKEN`/`SCHEMA_AUTHOR_TOKEN`) with per-person Firebase
identity; `bd polyglot-pdf-rhc2v` then deleted the settings and the
`X-Editor-Token` path outright (merged as PR #687, closing the
`ijntk` epic). Several comments/docstrings across the backend, tests, and
frontend still described the retired mechanism as live or partially live,
found during earlier reviews (`bd a372q`/`digef`) but deliberately left out
of those beads' narrower scope.

## Enumerated set (CLAUDE.md scar tissue #7)

`bd 8u63m` had already grepped for `token-gated`/`X-Editor-Token`/`503`
across `backend/` and `tests/` and enumerated the full set (2 WRONG
rationale comments, 2 wrong docstrings, 8 merely-stale-wording sites). Fixed
the entire enumerated set in one pass:

- `tests/test_local_editor_credential_chain.py` -- both comments asserting
  "the server still accepts that header until bd rhc2v" corrected (rhc2v
  has landed; the server no longer reads the header at all).
- `backend/tests/unit/test_editor_kit_routes.py` -- module docstring, one
  function docstring, and the `client` fixture docstring, all corrected.
- `backend/tests/unit/test_editor_readiness_routes.py` -- module docstring
  corrected.
- 8 "merely stale wording" sites (`backend/main.py`, `editor_kit_routes.py`,
  `form_kit_routes.py` x2, `form_kits.py`, `App.tsx` x2,
  `RemoteCatalogue.tsx`, `remoteKitStore.ts`, `docs/components/auth.md`,
  `docs/components/pdf-filling.md`) -- "token-gated" -> "editor/author-gated"
  or dropped where redundant.

`docs/components/auth.md`'s fix also closes `bd ve94p` (filed separately for
the same sentence, at a line number that had since drifted from 304 to 314).

## The real bug underneath (bd q1gtz)

While fixing `test_editor_kit_routes.py`'s `client` fixture docstring
(`8u63m`'s item 4), found the deeper issue `bd q1gtz` had already flagged:
the docstring claimed "Auth runs through the real dependency wiring (no
override)", but the very next line calls `_install_actor_auth(app)`, which
does `app.dependency_overrides[require_editor_actor] = _fake_editor` --
literally an override. Corrected the docstring to say so plainly, and
noted that a regression in the REAL `editor_auth.py` Bearer-parsing path
would not be caught by this fixture family (that's what
`test_editor_identity.py` is for).

`q1gtz`'s second half: the `_settings()` helpers in both
`test_editor_kit_routes.py` and `test_editor_readiness_routes.py` still
took `editor=`/`author=` kwargs feeding `SCHEMA_EDITOR_TOKEN=`/
`SCHEMA_AUTHOR_TOKEN=` into a `SimpleNamespace` -- dead cargo since
`hn0jq`, confirmed dead by checking every call site (all pass the same
literal `"edit-tok"`/`"auth-tok"`, never varied). Removed the kwargs and
updated every call site (7 in `test_editor_kit_routes.py`, 1 in
`test_editor_readiness_routes.py`).

## One more found by adversarial review (bd 3nib0)

The Opus/fresh-eyes review of this diff found one more site the enumerated
grep missed: `schema-editor/.env.hosted` -- a dotfile, outside the grep's
`backend/` + `tests/` + `docs/components/` + `.tsx`/`.ts` scope. Fixed in
the same pass rather than filed separately, since it's the identical
one-line class of drift and trivially small. Also fixed a second stale
"access-code entry" phrase a few lines below it in the same file (same
retired-mechanism class, found while already there).

## Verification

Comment/docstring/dead-kwarg removal only -- no assertion changed. Ran
both edited test files (190 passed), the credential-chain test (4 passed),
a broader sweep (`-k "editor_kit or editor_readiness or editor_identity or
lifecycle"`, 340 passed), the full `RemoteCatalogue.test.tsx` suite (99
passed), `tsc --noEmit` (clean), and `scripts/check_doc_freshness.py`
(citations clean). Final grep across every surface `8u63m`/`mw91i` named
confirms zero remaining "token-gated"/"Token-gated" hits.

## Files touched

- `tests/test_local_editor_credential_chain.py`
- `backend/tests/unit/test_editor_kit_routes.py`
- `backend/tests/unit/test_editor_readiness_routes.py`
- `backend/main.py`, `backend/routes/editor_kit_routes.py`,
  `backend/routes/form_kit_routes.py`, `backend/services/form_kits.py`
- `schema-editor/src/App.tsx`, `schema-editor/src/components/RemoteCatalogue.tsx`,
  `schema-editor/src/utils/remoteKitStore.ts`
- `docs/components/auth.md`, `docs/components/pdf-filling.md`
- `schema-editor/.env.hosted`
