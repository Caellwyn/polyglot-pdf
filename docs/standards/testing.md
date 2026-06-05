# Testing

**Tracks:** backend/pytest.ini backend/tests/conftest.py backend/requirements.txt frontend/package.json

*Last updated: 2026-06-05. See [../journal/entries/2026-06-05-bd-ajx-vite6-vitest3-security-upgrade.md](../journal/entries/2026-06-05-bd-ajx-vite6-vitest3-security-upgrade.md) for closeout details.*

Where tests live, how to run them on this repo's split-venv layout, and what the
suite does and doesn't cover today. Two test stacks: **pytest** for the
Python/FastAPI backend, **vitest** for the React/TS frontend. There is **no CI
test run and no coverage tooling** (both absent by design today — see below); the
suite is run locally and is the gate for every PR via [`/closeout`](../doctrine/review-flow.md).

For the PII/PHI rules the logging tests enforce, see
[hipaa-pii-policy.md](hipaa-pii-policy.md).

## Backend (pytest)

Config is `backend/pytest.ini` (the only pytest config — no `pyproject.toml` /
`setup.cfg` / `tox.ini`):

```ini
[pytest]
pythonpath = .
testpaths = backend/tests
markers = external: marks tests requiring real Gemini access
```

Tests are organized **by directory**, not by marker:

| Dir | What | Notes |
|-----|------|-------|
| `backend/tests/unit/` | Fast, isolated unit tests | The bulk of the suite. |
| `backend/tests/integration/` | Multi-component flows (WS ephemeral session, idle-timeout flow) | |
| `backend/tests/contract/` | Protocol / tool / live-adapter contracts | Holds the one **`external`** test (`test_live_ai_gemini_integration.py`); `test_tool_contracts.py` and `test_websocket_protocol.py` are **empty stubs** (0 collected tests) awaiting fill — populate these rather than adding a fourth file. |
| `backend/tests/*.py` (root) | Cross-cutting tests | `test_audio_handler.py`, `test_callback_handler.py`, `test_no_pii_logging.py`, `test_request_coordinator.py`. |

- **Async tests** use `pytest-asyncio` with an **explicit** `@pytest.mark.asyncio`
  on each coroutine test (there is no `asyncio_mode = auto`; the marker is
  required). Dep pins: `pytest==7.4.3`, `pytest-asyncio==0.21.1`, `httpx==0.28.1`
  (`backend/requirements.txt`).
- **The `external` marker** gates tests that hit the **real Gemini Live API**
  (currently just `backend/tests/contract/test_live_ai_gemini_integration.py`, via a
  module-level `pytestmark = pytest.mark.external`). It needs live credentials and
  costs tokens — deselect it in the default loop with `-m "not external"`.
- **Hermetic logs.** `backend/tests/conftest.py` has one autouse fixture that
  redirects `CONFIRMATION_LOG_DIR` to a per-test `tmp_path`, so confirmation-audit
  tests don't dirty the repo's real `logs/confirmations/` tree. Keep new tests that
  write logs hermetic the same way.

### Running the backend suite (split-venv gotcha)

The README shows `python -m pytest backend/tests -v`, which assumes an **activated
venv**. In practice the dependency venv lives **only in the main repo at
`backend/.venv`** — git **worktrees have no venv of their own**. From a worktree
(or anywhere), resolve the main-repo interpreter and point `PYTHONPATH` at the repo
root you want to test:

**Run from the repo/worktree root** (the recipe uses `$PWD` as the import root, so a
wrong CWD points `PYTHONPATH` at the wrong tree):

```bash
# Windows; on macOS/Linux use backend/.venv/bin/python
REPO="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"
PY="$REPO/backend/.venv/Scripts/python.exe"
PYTHONPATH="$PWD" "$PY" -m pytest backend/tests/ -q          # full suite (this checkout)
PYTHONPATH="$PWD" "$PY" -m pytest backend/tests/unit -q      # unit only
PYTHONPATH="$PWD" "$PY" -m pytest backend/tests/ -m "not external" -q  # skip live-Gemini
```

> **Watch the COLLECTED count, not just pass/fail.** pytest does fail the run on a
> collection-time import error — but a *misresolved* invocation (wrong CWD →
> `PYTHONPATH` at the wrong tree, or a path typo) can quietly run a **partial or
> empty** suite and still report green. The collected count is how you catch that.

## Frontend (vitest)

`frontend/package.json` script: **`"test": "vitest --environment jsdom"`** (run
`npm run test` from `frontend/`; a `pretest` hook runs `form-kits:prepare` first).
Stack: `vitest ^3.2.6` (on `vite ^6.4.3`), `@testing-library/react`,
`@testing-library/user-event`, `jsdom`. There is **no separate `vitest.config.ts`**
and **no `test` block in `vite.config.ts`** — vitest runs on defaults plus the
`--environment jsdom` CLI flag.

Test files are colocated next to the code as `*.test.ts(x)` (the `.spec.` suffix is
not used). **Five are active** and run: schema-form utilities (`fieldValue`,
`conditionalFieldCheck`, `manifestUtils`), the disclaimer modal, and
navigation-confirmation — i.e. the pure client-state logic, not the voice/WS path.

> **Five more are dormant.** Files renamed with a trailing `.NEEDS_CLEANUP` /
> `.NEEDS_SECTION_REFACTOR` suffix (the field components `RadioField` / `SelectField`
> / `TextField`, plus `schemaFormState` and `connection`) no longer match vitest's
> `*.test.ts(x)` glob, so they are **not collected** — parked, not deleted, pending
> the section-refactor cleanup. Don't mistake them for passing coverage; re-enabling
> one means renaming it back and fixing it.

## E2E + manual testing

There is **no automated E2E suite yet.** Writing a repeatable one is tracked by
`polyglot-pdf-277` (*full I-90 form completion across all field types* — all 6 field
types, the confirmation workflow, idle-timeout/reconnect, and PDF
generation/download, verified end-to-end at least twice, failures triaged into new
beads). The native-vs-manual-VAD smoke test is `polyglot-pdf-333`.

Manual debug runbooks exist for the PDF-fill path — `DEBUG_PDF_FILLING.md` /
`test-pdf-filling.md` at the repo root (wrapped-value symptoms, `field_count=0`,
`filled=0`, a curl recipe against `/api/fill-pdf`); see also
[pdf-filling.md](../components/pdf-filling.md#debugging).

## Coverage & CI — intentionally absent today

- **No coverage tooling** on either stack: no `.coveragerc` / `--cov`, no vitest
  coverage config. Coverage is not measured or enforced.
- **No CI test run.** Tests are a **local** gate, enforced per-PR by
  [`/closeout`](../doctrine/review-flow.md) (which runs the full backend suite before
  opening the PR). GitHub can enforce a unit-test status check + Copilot review, but
  that wiring is separate (see the deploy/CI direction notes); deploys stay manual
  ([config-deployment.md](../components/config-deployment.md)).

## TDD cadence

Match the surrounding pattern when adding code: a bug fix lands **with a regression
test that pins the contract** (e.g. the VAD-config 1007 fix extracted a pure helper
specifically so it could be unit-tested — `polyglot-pdf-p1t`). New pure logic gets a
unit test; new multi-component flows get an integration test. The suite must be
**green before a PR opens** — `/closeout` will not open a PR on a red suite.

*Last updated: 2026-06-05. See [../journal/entries/2026-06-05-bd-ajx-vite6-vitest3-security-upgrade.md](../journal/entries/2026-06-05-bd-ajx-vite6-vitest3-security-upgrade.md) for closeout details.*
