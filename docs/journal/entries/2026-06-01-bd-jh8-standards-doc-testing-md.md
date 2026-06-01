---
date: 2026-06-01
bead: polyglot-pdf-jh8
title: "Standards doc: testing.md"
tags: [conventions, testing]
---

## Trigger

`bd polyglot-pdf-jh8`, a child of the docs-reorg epic `polyglot-pdf-gfb`. Write the
tier-2 standards doc for the test surface (pytest backend, vitest frontend, E2E
checklist, coverage/TDD cadence). Dep `cg7` (tier-1 skeleton) already closed →
unblocked.

## What shipped

`docs/standards/testing.md` — INDEX row de-`(planned)`-ed to a live link. Facts
verified against the actual config/source, not assumed:

- **Backend pytest** — `backend/pytest.ini` is the sole config (`pythonpath=.`,
  `testpaths=backend/tests`, one `external` marker). Tests are organized **by
  directory** (`unit/` / `integration/` / `contract/` + a few root files), not by
  marker. Async tests use an **explicit** `@pytest.mark.asyncio` (no
  `asyncio_mode=auto`). The `external` marker gates the one real-Gemini contract
  test (`test_live_ai_gemini_integration.py`, module-level `pytestmark`); deselect
  with `-m "not external"`. `conftest.py` has an autouse fixture redirecting
  `CONFIRMATION_LOG_DIR` to `tmp_path` for hermetic logs.
- **Split-venv gotcha** — the README's `python -m pytest` assumes an activated venv,
  but the venv lives **only in the main repo** (`backend/.venv`); worktrees have
  none. Documented the `git-common-dir`-resolved interpreter + `PYTHONPATH` recipe
  that closeout actually uses, plus the "watch the collected count" warning.
- **Frontend vitest** — `npm run test` → `vitest --environment jsdom`; no separate
  `vitest.config.ts`, no test block in `vite.config.ts`; colocated `*.test.ts(x)`
  (5 files, covering schema-form utils + disclaimer modal + nav-confirmation).
- **E2E / coverage / CI — intentionally absent.** No automated E2E suite (tracked by
  `bd polyglot-pdf-277`; native-vs-manual VAD smoke = `bd polyglot-pdf-333`); manual
  runbooks are `DEBUG_PDF_FILLING.md` / `test-pdf-filling.md`. No coverage tooling on
  either stack; no CI test run — tests are a local gate enforced per-PR by
  `/closeout`. Stated these absences explicitly so the doc is accurate rather than
  aspirational.

Scope boundaries: PII/PHI rules point at `hipaa-pii-policy.md`; the PDF debug
runbook points at `pdf-filling.md`; the CI/deploy story points at
`config-deployment.md` + `review-flow.md`.

### Review triage (PR #39)

The reviewers caught that the first draft presented an **incomplete** picture of the
test tree — all factual gaps, all adopted:

- **Fresh-eyes (8 findings):**
  - F2/F8 (high): **5 dormant frontend test files** with `.NEEDS_CLEANUP` /
    `.NEEDS_SECTION_REFACTOR` suffixes (field components + `schemaFormState` +
    `connection`) exist alongside the 5 active ones and aren't collected by vitest.
    The draft ignored them — added a callout so "5 active" isn't mistaken for total
    coverage.
  - F7 (high): the `contract/` dir has **2 empty stub files** (`test_tool_contracts.py`,
    `test_websocket_protocol.py`, 0 bytes) beside the one external test — documented
    so a contributor populates the stubs instead of adding a fourth file.
  - F6 (high): `pytest.ini` `markers` is a **single line**, not the two-line block I
    quoted — corrected to match the file verbatim.
  - F1 (med): root test dir has **4** files, not the 2 I exampled — listed all four.
  - F4 (high): dropped `frontend/vite.config.ts` from `Tracks:` (it has no test
    config, so tracking it = false-positive staleness; kept the prose reference).
  - F3 (med): added a "run from the repo/worktree root" caveat to the split-venv
    recipe (it uses `$PWD` as the import root).
- **Copilot (1 inline):** my "broken import silently drops a file" warning was wrong
  — pytest fails the run on a collection-time import error. Reworded the COLLECTED-count
  warning to the real failure mode (a misresolved/partial invocation running an
  empty suite and still reporting green).

## Lessons

The README's documented test command (`python -m pytest ...`) is **not runnable
as-written from a worktree** — it silently assumes the main-repo venv on PATH.
Capturing the `git-common-dir` interpreter recipe in testing.md means the next
agent doesn't rediscover the split-venv trap (already in my session memory; now in
a tier-2 doc too). No code lesson — docs-only.

## Doc freshness

- `docs/standards/testing.md` — created, stamped `2026-06-01`, passes the checker
  (run via the worktree's own script copy; the main-repo copy resolves paths against
  its own checkout and can't see a branch's new docs).
- `docs/INDEX.md` — testing row de-`(planned)`-ed.
- Pre-existing STALE, left as-is (track files this branch did NOT touch): the docs
  whose `Tracks:` include `live_ai_gemini.py` (made stale by the merged p1t fix) and
  `technical_guide.md` (owned by in-progress `bd polyglot-pdf-gfb.2`).
- Four pre-existing stale `in_progress` beads (`gfb.2`, `m3f`, `pki`, `hjo`) surfaced
  by housekeeping — all others' in-flight work, none orphaned, untouched.

## Files touched

- `docs/standards/testing.md` — new tier-2 standards doc.
- `docs/INDEX.md` — linked the testing row.
- `docs/journal/entries/2026-06-01-bd-jh8-standards-doc-testing-md.md` — this entry.
