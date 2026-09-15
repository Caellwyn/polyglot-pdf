# Testing

**Tracks:** pytest.ini backend/tests/conftest.py admin_backend/tests/conftest.py tests/conftest.py backend/requirements.txt frontend/package.json frontend/vite.config.ts .github/workflows/ci.yml

*Last updated: 2026-09-15 (bd polyglot-pdf-ikdnd: the pytest pins moved to `backend/requirements-dev.txt` (which pulls in `requirements.txt`); every pytest runner -- `ci.yml`, `cloudbuild.yaml`, the dev scripts -- installs the dev file, and the image installs `requirements.txt` alone. `ci.yml` also gained an INFORMATIONAL `security` job (pip-audit, npm audit x3, detect-secrets on the PR's files, bandit, semgrep), pinned by `tests/test_ci_security_job.py`.)*

*Last updated: 2026-09-15 (bd polyglot-pdf-21m1y: the no-real-Firestore guard, autouse in both `backend/tests/conftest.py` and `admin_backend/tests/conftest.py`). See [the pnoik journal entry](../journal/entries/2026-09-03-bd-pnoik-admin-backend-skeleton.md) for the THIRD collected suite (`admin_backend/tests`)'s closeout details.*

Where tests live, how to run them on this repo's split-venv layout, and what the
suite does and doesn't cover today. Two test stacks: **pytest** for the
Python/FastAPI backend, **vitest** for the React/TS frontend. An **informational
(non-blocking) CI run** and **opt-in coverage tooling** exist on both stacks (see
below); the local suite remains the gate for every PR via
[`/closeout`](../doctrine/review-flow.md).

For the PII/PHI rules the logging tests enforce, see
[hipaa-pii-policy.md](hipaa-pii-policy.md).

## Backend (pytest)

Config is a single **root `pytest.ini`** (no `pyproject.toml` / `setup.cfg` /
`tox.ini`). It lives at the repo root — not under `backend/` — so a bare `pytest`
invoked from the root (or CI) discovers it; a backend-only config was previously
missed on a root invocation, which made pytest scan dev probe scripts and error on
collection:

```ini
[pytest]
pythonpath = .
testpaths =
    backend/tests
    tests
addopts = --import-mode=importlib
norecursedirs = scripts .venv node_modules .git build dist .claude
markers =
    external: marks tests requiring real Gemini access
```

`--cov` is **not** in `addopts` — coverage is opt-in via the flag so a bare
`pytest` (and the closeout gate) stays fast. The coverage **source/omit scoping
lives in a standalone `.coveragerc`** at the repo root, **not** in `pytest.ini`:
coverage.py only auto-discovers `.coveragerc` / `setup.cfg` / `tox.ini` /
`pyproject.toml`, so `[coverage:*]` sections in `pytest.ini` would be silently
ignored. `.coveragerc` sets `source = backend` (so untested modules show at 0%
rather than hiding) with `omit = backend/tests/*` to keep test files out.

`--import-mode=importlib` lets duplicate test basenames coexist without
`__init__.py` packaging. `norecursedirs` plus the scoped `testpaths` keep
**probe scripts** out of collection: a `test_*.py` file outside `backend/tests/`
or `tests/` (e.g. a probe under `scripts/` or `backend/scripts/`) is a
standalone `python <file>` script (`__main__` / required CLI args), **not** a
pytest suite — do not let it get collected, and do not park real pytest files
outside the two `testpaths` roots (they silently never run; bd polyglot-pdf-o0pc
relocated one such orphan).

There are **three collected suites** under `testpaths`:

- `backend/tests` — the product backend suite (below).
- `admin_backend/tests` — the privileged admin service's suite (bd
  `polyglot-pdf-pnoik`). `admin_backend/` is a **sibling top-level package**, so
  it is not reached via `backend/tests` and needs its own root.
- `tests` (repo root) — the **harness-tooling** suite (closeout, `bd_safe`,
  `next_bead`, doc-freshness, `pr_review_watcher`, pricing). It runs from the repo
  root on defaults and is now part of the same `pytest` run.

> **The gates must never re-list these roots by hand.** CI
> (`.github/workflows/ci.yml`) and the pre-PR gate
> (`closeout_prep.check_tests`) both run a **bare** `pytest` and inherit
> `testpaths`, so a new suite is gated the day it is added. Hardcoding suite
> paths there is what let a whole suite ship un-run twice — CI in bd
> `polyglot-pdf-3ave`, and `admin_backend/tests` in bd `polyglot-pdf-pnoik`.
> Pinned as a set by `tests/test_every_suite_root_is_gated.py`.

<!-- suite-path-citation: names the anti-pattern, not a recipe -->
> **Pre-PR, run EVERY root — a bare `pytest`, not `pytest backend/tests`.** A
> scoped run silently skips the other roots, and a **cross-suite leak is invisible
> to every scoped run**. (The closeout recipe used to name `backend/tests` for
> speed; it no longer does — see the gates rule above.) Measured
> (`polyglot-pdf-gnb0`): a new test under `backend/tests/unit/` assigned
> `subprocess.run` directly instead of via `monkeypatch`, and because collection is
> alphabetical that leak reddened **5 tests in two untouched files under `tests/`** —
> green in isolation, green under `backend/tests`, red only on the full run the
> reviewer did. Related rule: patch a module attribute with `monkeypatch.setattr`,
> never a bare assignment. `importlib`-loading a module by path gives you a fresh
> copy of THAT module but the **same stdlib modules it imported**, so
> `mymod.subprocess.run = fake` is a process-wide patch wearing a local disguise.

The backend suite is organized **by directory**, not by marker:

| Dir | What | Notes |
|-----|------|-------|
| `backend/tests/unit/` | Fast, isolated unit tests | The bulk of the suite. |
| `backend/tests/integration/` | Multi-component flows (WS ephemeral session, idle-timeout flow) | |
| `backend/tests/contract/` | Protocol / tool / live-adapter contracts | Holds the one **`external`** test (`test_live_ai_gemini_integration.py`); `test_websocket_protocol.py` pins the ws-protocol.md wire contract via doc-vs-code diffs (bd polyglot-pdf-ceyt) and `test_tool_contracts.py` pins the tool-call sequence — add to these rather than creating a fourth file. |
| `backend/tests/*.py` (root) | Cross-cutting tests | `test_audio_handler.py`, `test_callback_handler.py`, `test_no_pii_logging.py`, `test_request_coordinator.py`. |

- **Async tests** use `pytest-asyncio` with an **explicit** `@pytest.mark.asyncio`
  on each coroutine test (there is no `asyncio_mode = auto`; the marker is
  required). Dep pins: `pytest==7.4.3`, `pytest-asyncio==0.21.1` in
  `backend/requirements-dev.txt` (test tooling only -- never installed into the
  image) and `httpx==0.28.1` in `backend/requirements.txt`.
- **The `external` marker** gates tests that hit the **real Gemini Live API** --
  currently `backend/tests/contract/test_live_ai_gemini_integration.py` and
  `test_tool_contracts.py` (both set a module-level
  `pytestmark = pytest.mark.external`). It needs live credentials and costs
  tokens — deselect it in the default loop with `-m "not external"`.
- **Hermetic logs.** `backend/tests/conftest.py` has an autouse fixture that
  redirects `CONFIRMATION_LOG_DIR` to a per-test `tmp_path`, so confirmation-audit
  tests don't dirty the repo's real `logs/confirmations/` tree. Keep new tests that
  write logs hermetic the same way.
- **K_SERVICE isolation.** `backend/tests/conftest.py` also strips `K_SERVICE`
  from the environment -- both at import time (a module-level `os.environ.pop`,
  so it is gone before any test module is even collected) and per-test (an
  autouse fixture, as defense-in-depth) -- so a bare `Settings()` never
  inherits a deployed-service identity from the ambient shell.
  `backend/config.py`'s VERTEXAI and VFF_DISABLE_AUTH guards both key off this
  var; Cloud Run sets it, a local shell normally does not. The top-level
  `tests/` suite (pytest.ini's other testpath) carries the same import-time
  guard in its own `tests/conftest.py`, since it does not share
  `backend/tests/conftest.py`'s fixtures. Tests that deliberately exercise the
  deployed path still work -- they set `K_SERVICE` themselves via
  `monkeypatch.setenv`, which wins over both guards.
- **No real Firestore.** `backend/tests/conftest.py` and
  `admin_backend/tests/conftest.py` both carry an autouse `_no_real_firestore`
  fixture (bd polyglot-pdf-21m1y) that patches THREE targets to raise a loud
  `RealFirestoreReachedInTest` instead of touching anything real:
  `firebase_admin.initialize_app`, `google.cloud.firestore.Client.__init__`,
  and `firebase_admin.firestore.client` itself. The third target exists
  because the first two are not sufficient on their own: firebase_admin
  caches clients on the App object for the life of the process, so once any
  earlier call (including `backend/services/auth.py`'s own import-time
  `initialize_app()` plus a first real `get_db()` call) has warmed that
  cache, every later call to `firebase_admin.firestore.client()` is a cache
  hit that returns the cached real client WITHOUT reconstructing it -- the
  constructor patch alone never fires for it. Patching `client()`, the one
  function every consumer in this repo actually calls, catches a cache hit
  exactly as reliably as a cache miss. This exists because every store under
  `backend/services/` (`alerts.py`, `usage_rollups.py`,
  `link_redemptions.py`, `links_store.py`, `credit_ledger.py`) reaches
  Firestore through one seam -- `backend.services.auth.get_db()` -- which
  lazily initializes `firebase_admin` with ADC and constructs a real client
  the moment an unpatched test exercises it; on a developer machine with
  working gcloud ADC this silently writes real documents into the shared
  project (see `backend/tests/unit/_no_real_firestore.py`'s docstring for
  the 2026-09-15 incident this closed, and the warm-cache gap fix that
  followed). The fix for a test the guard catches is the same fix every
  existing store test already uses: patch `get_db()` (or the module's own
  `_get_db`/`_collection`) with a fake, the way `test_alerts_dedup.py` /
  `test_links_store.py` / `test_usage_rollups.py` / `test_credit_ledger.py`
  do -- never disable the guard. The one sanctioned opt-out is
  `@pytest.mark.external`, the same marker that already gates the two
  real-Gemini tests. Cleanup for documents the incident already wrote:
  `scripts/purge_test_artifacts.py --dry-run` / `--apply` (operator-run;
  data deletion is the maintainer's).

### Running the backend suite (split-venv gotcha)

<!-- suite-path-citation: quotes an older README line, not a recipe -->
Older docs show `python -m pytest backend/tests -v`, which assumes an **activated
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
PYTHONPATH="$PWD" "$PY" -m pytest -q                         # EVERY collected suite
PYTHONPATH="$PWD" "$PY" -m pytest -q -m "not external"       # ditto, skip live-Gemini
PYTHONPATH="$PWD" "$PY" -m pytest backend/tests/unit -q      # narrow: one dir, while iterating
```

> **Watch the COLLECTED count, not just pass/fail.** pytest does fail the run on a
> collection-time import error — but a *misresolved* invocation (wrong CWD →
> `PYTHONPATH` at the wrong tree, or a path typo) can quietly run a **partial or
> empty** suite and still report green. The collected count is how you catch that.

## Frontend (vitest)

`frontend/package.json` script: **`"test": "vitest --environment jsdom"`** (run
`npm run test` from `frontend/`; a `pretest` hook runs `form-kits:prepare` first).
Stack: `vitest ^3.2.6` (on `vite ^6.4.3`), `@testing-library/react`,
`@testing-library/user-event`, `jsdom`. There is **no separate `vitest.config.ts`**;
the test config is a `test` block in **`frontend/vite.config.ts`** that sets
`environment: 'jsdom'`, so a bare `vitest run` (CI, no CLI flag) uses jsdom — tests
touch `sessionStorage`/DOM and fail under vitest's default node environment. The
`--environment jsdom` flag on the npm script is now redundant but harmless.

Test files are colocated next to the code as `*.test.ts(x)` (the `.spec.` suffix is
not used). The suite spans the client-state logic (schema-form utilities,
`fieldManager`, `schemaFormState`), the WS/connection layer (`webFormConnection`,
`connection`, audio gating), UI components (field components, disclaimer modal,
navigation-confirmation), and contexts — run `vitest run` for the current count.

> **No test files are parked.** The former `.NEEDS_CLEANUP` renames (the field
> components `RadioField` / `SelectField` / `TextField`) were revived in
> bd polyglot-pdf-63zi — the parked tests still matched the components' contracts
> and only needed the repo's explicit `afterEach(cleanup)` convention (no
> `test.globals`, so testing-library auto-cleanup never fires) and the removal of
> `toBeInTheDocument()` (`@testing-library/jest-dom` is not installed; use
> `toBeTruthy()`). Follow both conventions in every new component test. Do NOT
> park a test by renaming it off the `*.test.ts(x)` glob — fix it or delete it
> with its coverage mapped.

> **Running a Vite dev server from a git worktree needs `server.fs.allow`.** A
> worktree's `node_modules` is typically a junction into the main checkout, so Vite
> serves realpath-resolved modules (e.g. the pdfjs worker via
> `new URL(..., import.meta.url)`) from a path OUTSIDE the worktree root and refuses
> it with "403 Restricted". Add the realpath-resolved `node_modules` to
> `server.fs.allow` (a no-op in a normal checkout). The schema-editor does this; see
> [../journal/entries/2026-06-19-bd-7a9.17-wire-extractor-into-editor.md](../journal/entries/2026-06-19-bd-7a9.17-wire-extractor-into-editor.md).

## E2E + manual testing

An automated E2E harness covers the voice form-fill loop --
[`tests/e2e/voice-harness/`](../../tests/e2e/voice-harness/) (see the
[`voice-harness`](../../.claude/skills/voice-harness/SKILL.md) skill), shipped as
`polyglot-pdf-g8w`. It drives the real frontend (Chrome) against a local backend
and the real Gemini Live API, injecting committed 16 kHz PCM16 WAV fixtures
through a dev-gated in-app hook (`window.__VFF_TEST_INJECT`) and asserting on
concrete outcomes -- field value, confirmed flag, advance -- for the cycle
"Gemini asks a field -> audio answer -> field fills -> audio confirm -> Gemini
advances." It is agent-driven (the agent is the runner, via the `preview_*`
Chrome tools), not a `pytest`/CI-collected suite.

It does not yet cover a full I-90 completion across all 6 field types,
idle-timeout/reconnect, and PDF generation in one pass -- that broader sweep is
tracked by open bead `polyglot-pdf-277` (*full I-90 form completion across all
field types*, verified end-to-end at least twice, failures triaged into new
beads). The native-vs-manual-VAD smoke test shipped as `polyglot-pdf-333`
(closed).

Manual debug runbooks exist for the PDF-fill path — `DEBUG_PDF_FILLING.md` /
`test-pdf-filling.md` at the repo root (wrapped-value symptoms, `field_count=0`,
`filled=0`, a curl recipe against `/api/fill-pdf`); see also
[pdf-filling.md](../components/pdf-filling.md#debugging).

## Live-endpoint probes and spikes: deploy fidelity is mandatory

**Before planning any probe/spike run, see the
[`experimentation`](../../.claude/skills/experimentation/SKILL.md) skill** --
it gates all measurement work on a prior-work audit (don't re-run research
that already exists) and a pre-spend cost estimate (don't surprise-bill the
project). This section covers deploy-fidelity specifically; the skill covers
the full run lifecycle.

**A probe must represent what deploy will actually send** (maintainer directive,
2026-06-12): the production tool declarations, the real system-instruction path
(`build_form_context_message` with a real schema — not a one-line stand-in), and
realistic user-answer content. A "minimal" probe config is a different system with
different behavior, and its verdicts do not transfer. This rule exists because a
minimal probe (`tool_declarations=None`) crashed `gemini-2.5` Live sessions with
1011s for a week across multiple sessions, producing false "2.5 is unstable /
transient server-side" verdicts — while the deploy-shaped config was stable the
whole time, and even evicted under compression (bd `h04c`; bd memory
`gemini-2p5-1011-needs-tool-declarations`). Deviate from deploy config only as a
deliberate, labeled experimental arm (e.g. an isolation control), never as the
probe's default. Cost/behavior measurements (token curves, latency, tool-call
compliance) additionally need realistic CONTENT — production-length system
instructions and plausible answers — because the unevictable base (SI + tools)
sets the floor the numbers sit on.

**A stray CONTROL CHARACTER in a source file silently defeats code review.**
A literal NUL (`0x00`) landed inside a template literal in
`frontend/src/shared/introPlayer.ts` (bd `polyglot-pdf-s1iex.5`): it RENDERS
as a space, `tsc` accepts it, and all 16 tests plus a five-mutation pass went
green — because no test inspected the bytes. Its real cost is that **git then
classifies the whole file as binary and `git diff` prints NOTHING for it**,
locally and in the PR view, so every future edit to that file is invisible to
review. Behavioral tests cannot catch this class. When a file is new and
load-bearing, add a control-character scan over its source (see
`introPlayer.test.ts`'s "source hygiene" block), and if `git diff` ever shows
`Bin` for a text file, that is the tell —
`node -e "console.log(require('fs').readFileSync(F).indexOf(0))"` locates it.

**A test that READS SOURCE must resolve the path from the test file, not
`process.cwd()`.** Worktree vitest runs are invoked from the MAIN checkout
here (the `node_modules` junction workaround), so a cwd-relative
`readFileSync` audits **main's** copy: a set-pin for bd
`polyglot-pdf-s1iex.4` counted 3 sites while the branch under review had 4,
and would have passed against an unfixed branch. Use
`expect.getState().testPath` (`import.meta.url` is a non-file URL under vite).

**Suspect a NEW harness before you suspect the code — and never let a harness
depend on tab focus.** A browser check for bd `polyglot-pdf-s1iex.4` reported
`FAIL` (peak audio energy 0.00) against a correct implementation: it sampled
inside `requestAnimationFrame`, which Chrome throttles to **zero in a
background tab**. Re-measured on `setInterval`: 26.64. Same rule as the
backend probe guidance below — check the measuring instrument first (see the
[s1iex.4 journal entry](../journal/entries/2026-08-14-bd-s1iex.4-sol-animates-during-clips.md)).

**A frozen fake clock can WEDGE vitest instead of failing it.** Any
production loop that waits for a *sustained* condition (`spellbackPlayer`'s
pre-clip drain-wait: quiet for N ms, measured with an injected `now()`) spins
forever when a test pins `now: () => 0` — the worker never exits, nothing
prints, and it mimics an environment/junction failure. Advance injected
clocks. To bisect: run one pure-function `describe` alone (a clean exit
isolates the culprit) and re-run an EXISTING neighbouring test as the control
that proves the environment is fine.

**A generative endpoint's output varies run to run — never accept a
single-draw measurement at a decision boundary.** Chirp3-HD TTS re-generates
prosody per request: identical ~80s text measured 81.6/81.6/88.6s (~9% swing),
so one draw landing 0.1s inside a duration window proved nothing. Repeat the
measurement and center with margin for the spread (see the
[2026-08-13 s1iex.1 journal entry](../journal/entries/2026-08-13-bd-s1iex.1-intro-copy-master-and-translations.md)).

## Coverage & CI

**Coverage tooling is wired on all four stacks but opt-in (a secondary signal,
not enforced).** Run it explicitly:

- **Backend:** `pytest -m "not external" --cov --cov-report=term-missing`
  (`pytest-cov`; source/omit scoping in the root `.coveragerc`).
- **Frontend:** `npm run test:coverage` from `frontend/` (`@vitest/coverage-v8`).
- **Schema-editor:** `npm run test:coverage` from `schema-editor/`.
- **Admin-console:** `npm run test:coverage` from `admin-console/` (bd
  polyglot-pdf-b6943; same `@vitest/coverage-v8` wiring as the other two
  Vite apps -- no baseline recorded yet for this newest stack).

Baseline statement coverage (recorded 2026-06-09, backend/frontend/schema-editor
only): **backend 54%** (source-scoped via `.coveragerc`, so untested modules
count), **frontend 12%**, **schema-editor 33%**. These are instruments, not
gates — no threshold is enforced and a low number is not a closeout blocker.
Coverage artifacts (`.coverage`, `coverage/`) are gitignored.

**CI is informational and non-blocking.** `.github/workflows/ci.yml` runs the
backend pytest suite (`-m "not external"`) plus all three vitest suites --
`frontend`, `schema-editor`, and `admin-console` (bd polyglot-pdf-b6943) -- each
preceded by its own `tsc --noEmit` typecheck step, on every PR. A fifth job,
`security` (bd polyglot-pdf-ikdnd), runs pip-audit on the runtime pins, `npm
audit --omit=dev` for the three apps, detect-secrets on the PR's changed files
against `.secrets.baseline`, bandit, and semgrep (Python + TypeScript
rulesets); every one of its scanner steps is `continue-on-error`, so it
reports and never gates either.
It is **not** a required status check: the merge gate is the closeout merge
decision (auto-merge a routine low-risk PR that reviewed CLEAN, else a maintainer
merge -- see [review-flow.md](../doctrine/review-flow.md) and CLAUDE.md "Auto-merge
vs. maintainer merge"), and deploys stay manual
([config-deployment.md](../components/config-deployment.md)). The **local**
suite, enforced per-PR by [`/closeout`](../doctrine/review-flow.md) (which runs
the backend suite before opening the PR), remains the real gate.

**xfail counts as pass everywhere.** A spec-test that documents a known defect is
marked `@pytest.mark.xfail` (pytest) or `test.fails` (vitest); neither runner
sets a non-zero exit for an expected failure, so CI stays green and the closeout
gate (which keys off the pytest exit code) treats it as a pass. This is what lets
the spec-driven-test epic land intentionally-red specs without breaking every
closeout. An *unexpected* failure (a real regression, or an `xpass` under
`strict`) still exits non-zero and shows red.

## TDD cadence

Match the surrounding pattern when adding code: a bug fix lands **with a regression
test that pins the contract** (e.g. the VAD-config 1007 fix extracted a pure helper
specifically so it could be unit-tested — `polyglot-pdf-p1t`). New pure logic gets a
unit test; new multi-component flows get an integration test. The suite must be
**green before a PR opens** — `/closeout` will not open a PR on a red suite.

<a name="test-the-tests"></a>
**TEST THE TESTS — a new test is not done until you have watched it FAIL.** Green
is not evidence; green *after you broke the thing it pins* is. This is the
**author's** job, not the reviewer's: a reviewer finding a vacuous test is a review
round you paid for avoidably, and that has happened repeatedly here — PR #540's
reviewer reverted an entire route and **6 of 7 tests still passed**, then defeated
the remaining guard with a one-token mutation. Standard practice, every time:

1. **Break the REAL path, not a convenient neighbour.** Revert the production
   behavior the test claims to pin — the `if a or b` -> `if a` the regression would
   actually look like, not a cosmetic edit elsewhere.
2. **Confirm the mutation APPLIED before trusting the result.** A find-and-replace
   that silently matched nothing (line wrapping, a reflowed string) "passes" while
   testing nothing. Assert the file changed.
3. **Mutate per PARAMETRIZATION, not once per file.** A mutation that reddens some
   cases says nothing about the rest; parametrize over the whole dimension.
4. **Restore and re-verify.** A mutation-restore can revert a real edit — re-read
   the diff after restoring, and write commit messages from the staged diff rather
   than memory.

The trap this most often prevents is the **self-fulfilling mock** (below): a test
that constructs the expected payload, feeds it to a mock, and asserts the mock got
it -- deleting the production code leaves it green.

**Mutate the EXACT line that prompted the guard -- a near-miss variant is not the
test.** When a reviewer finding is what made you write a pin, the first mutation
must be that finding's own text, verbatim, not a tidier version of it. bd
`polyglot-pdf-pnoik`'s round-2 pin against scoped `pytest` recipes was
mutation-verified on a tidied-up form of the recipe and went red, which looked
like proof:
<!-- suite-path-citation: quotes the mutation pair under discussion -->
tried `pytest backend/tests/ -q`, but the blocker read `pytest "$WT/backend/tests/"`.
Against THAT the brand-new guard passed -- the `$WT/` prefix defeated a
`(?<![\w/-])` lookbehind. A guard that is green on the one line it was written for is worse
than no guard, because it also retires the reviewer's finding. Copy the offending
string out of the report and mutate with that.

**A CONCURRENCY test must reproduce production's concurrency, or it is vacuous.**
Check what the harness actually does before believing a passing race test. FastAPI's
`TestClient` runs **each request on its own fresh event loop**, so any per-loop
primitive (the `weakref`-keyed `asyncio.Lock` maps in `editor_kit_routes.py`) hands
two concurrent requests two *different* locks and they can never contend -- a
lost-update test written on `TestClient` passed with the lock **removed**
(`polyglot-pdf-gnb0`). Production is the opposite shape: uvicorn serves the whole
process on ONE loop. Drive both requests as concurrent tasks on a single loop
(`httpx.ASGITransport` + `asyncio.gather`) so the contention is real. Two related
rules: hold the first request open with a latch keyed on its **own data** (which
record it touches), never on arrival order -- a first-caller-wins flag is itself
racy and makes the test nondeterministic; and mutation-verify by **removing the
guard**, which is the only proof the race is what the test is measuring.

**A green vitest run does not prove a canvas/PDF UI works.** jsdom has no canvas
backend, so `getContext` returns null and the real `pdfjs-dist` render path — and
the bugs that live in it (render races under StrictMode, ref-vs-rerender gaps,
worker teardown) — never executes under vitest. For such surfaces the suite pins
the logic, but a **real-browser visual check** (the preview tools) is the
load-bearing verification: `polyglot-pdf-7a9.6` shipped a green 113/113 suite while
three runtime bugs blocked the actual PDF render, all invisible to jsdom.

**A green vitest run does not prove type-correctness either.** vitest transpiles
(esbuild) without full type-checking, so type errors -- including ones that mask
real bugs, like a duplicate local type that let `field.required`/`field.options`
resolve wrong -- pass the suite. The standalone `npm run typecheck`
(`tsc --noEmit`) gate in CI's frontend, schema-editor, and admin-console jobs is
the thing that catches this class; keep all three green
(`polyglot-pdf-uov.17`, `polyglot-pdf-1rgr`).

**Beware the self-fulfilling mock test.** A test that constructs the expected
payload, calls a mock with it, and then asserts the mock was called with it
verifies nothing -- deleting the production code under test leaves it green. The
discriminating question when auditing a "green" test: *does any production symbol
appear on the path between the arrange and the assert?* If the only thing exercised
is the mock the test set up, it is fake coverage. The fix is to import and run the
real unit and let IT drive the mock; a cheap guard against writing the fake version
is to mutate one production assertion (e.g. flip a close code) and confirm the test
goes red. (`polyglot-pdf-uov.9` found this in `test_idle_timeout.py`; the honest
idle-watchdog spec drives the real `_handle_fill_session` watchdog.)

<a name="change-the-mechanism"></a>
**When the same defect class survives your fix TWICE, change the MECHANISM, not
the instance.** A third occurrence is not bad luck -- it is evidence the approach
is wrong. `polyglot-pdf-saxh` burned six review rounds on one PR because rounds 4,
5 and 6 each defeated a test written in the round before, and each of my fixes
patched the case in hand: the pin's verb list was too narrow (added verbs), then
its noun pattern allowed only one literal infix (widened the infix), then it
required the denial *before* the noun **and** its allowlist matched by substring
so a sentence could quote an allowed fragment verbatim while asserting the
opposite. All three escapes shared one root -- the test was **matching** prose
instead of **enumerating** it. Replacing the mechanism (enumerate every candidate
sentence with no denial test at all, then require exact whole-sentence equality
against an allowlist) held against every earlier escape at once.

<a name="assert-the-mechanism"></a>
**Assert the MECHANISM you claim to pin, not a symptom it happens to produce.**
The commonest way a test lies is passing for a reason unrelated to its name.
`polyglot-pdf-6dz0` burned six review rounds on this one class, and every
instance was the same shape -- an assertion satisfied by something OTHER than
the behaviour under test:

- **A render branch standing in for a handler.** A test named "refuses a status
  change" only asserted which element rendered; deleting the guard it named left
  all 56 tests green. The guard was unreachable from the UI by construction, so
  no UI test could pin it -- the fix was to move the lock into the write
  primitive, where it protects every caller AND is directly callable.
- **One value standing in for a dimension.** A property test asserting "every
  write route refuses a locked kit" hardcoded `status="complete"`, so when a
  second locked status arrived, five of six gates could be reverted with the
  full 1779-test suite green. Parametrize over the whole dimension; a property
  test that fixes one value of it is pinning a sample.
- **A status code standing in for the work.** "Republish goes through the
  publish gate" asserted `200` plus a metadata flip -- both satisfied by a bare
  write. A mutation skipping every gate left 245 tests green. Assert the gate's
  observable consequence (a bad kit is REFUSED), not the success shape.
- **An unrelated candidate satisfying an ambiguity check.** A retrieval test
  expected "ambiguous", but the live schema supplied a second candidate on its
  own, so the assertion held whether or not the code found what it was supposed
  to (`polyglot-pdf-w3zw`). Isolate the thing under test, and assert the COUNT
  or the identity, not merely that the branch fired.

The cheap audit, before trusting any new test: **name the one line of production
code this test exists to protect, delete it, and confirm the test fails.** If it
stays green the test is decorative -- and per the rule above, if this keeps
happening the mechanism (where the code lives, how the assertion is framed) is
what needs changing, not the assertion.

**Prefer a NATURAL scope over a tuned constant.** The same pin was then defeated
twice more on *scope* rather than vocabulary: matching one sentence at a time lost
to an `e.g.` mid-sentence split, and widening to a two-sentence sliding window lost
to a three-sentence phrasing. Each fix was a bigger N, and each invited the next
phrasing just outside it. What held was dropping N entirely and scoping to the
**paragraph** -- the unit the prose itself uses for one claim. When you find
yourself tuning a window, span, or threshold, ask what natural boundary the
artifact already has.

**Then STOP, and name what you are not covering.** A natural scope is better than
a tuned one, not perfect: the very next round split a claim across a paragraph
break and escaped that too. Every scope has an adjacent-scope escape, so a prose
heuristic cannot be made evasion-proof and iterating toward one is the trap in a
new costume. The discriminating question is **what failure are you actually
defending against?** Here it is DRIFT -- a maintainer updating one statement of a
rule and missing another -- and all three real regressions were single
in-paragraph sentences in ordinary vocabulary, because whoever edits a rule is by
definition describing it. The later escapes were *constructed by a reviewer trying
to evade the check*, and none has occurred naturally. Cover the realistic class
well, then pin the rest as accepted limits (below) instead of buying each one with
another round.

**Keep the escapes as a committed battery, not a claim.** Each phrasing that
defeated a draft lives on as a parametrized case in
[`tests/test_claude_md_review_flow_battery.py`](../../tests/test_claude_md_review_flow_battery.py),
so the next mechanism change is re-verified against ALL of them rather than only
the newest one -- and so "it holds against the old attacks" is something a reader
can run, not something the author asserts. (An earlier draft of this very section
cited a case count with no committed artifact behind it; a reviewer correctly
called that unverifiable.) Note the battery injects mid-document, not at
end-of-file: an EOF append can be caught coincidentally by merging into the
unterminated tail fragment, which would falsely suggest the enumeration is sound.

**When a prose pin resists, stop DETECTING and pin the CLAIM.** The
detect-the-bad-sentence shape is what kept failing above; its positive inverse is
usually available and far more robust. A second pin in the same bead needed it
too: `.claude/prime-closeout-override.md` must not authorize auto-merging a
Haiku-cleared docs PR, and two detection drafts failed in opposite directions --
an exemption list that the offending text already satisfied ("pings the maintainer
for a consequence-bearing one" while implying auto-merge for everything else),
then a paragraph scope that let a neighbouring *correct* sentence mask the wrong
one. What held was asserting what the file must SAY: that auto-merge requires the
Opus clear, that a Haiku-cleared docs PR pings, and that the boundary must not be
widened autonomously. Applying this rule to itself took three attempts rather
than six -- that is what the lesson is worth.

**A positive pin's own limit, stated rather than overclaimed.** It reliably
catches REMOVAL and REWORDING of the claim, which is the drift case. It does NOT
catch ADDITION: appending "the open question above is now settled, a Haiku clear
does qualify" leaves all the asserted claims intact and passes. Nor does it catch
a widening clause spliced *after* the matched span, or a negation that preserves
the literal words ("It is no longer true that a Haiku-cleared docs-only PR
pings"). All three were executed against the committed pin and passed. So a
positive pin is stronger than a detector against paraphrase and weaker against
contradiction -- pick it for drift, and if you also need contradiction-resistance,
add a guard that no sentence *reverses* an asserted claim, or fall back to
whole-artifact equality. Do not write that a positive pin "cannot be evaded"; an
earlier draft of this very paragraph did, and a reviewer refuted it in one pass.

**Pin the limits you accept, so they stay decisions.** This pin has two: a denial
using no review vocabulary at all ("docs-only edits never get a look from anyone"),
and one split across a paragraph break. Chasing either -- more synonyms, or N
paragraphs -- would restart the trap, and an over-broad matcher makes the pin noisy
enough to get deleted, which is a worse outcome than a named gap. Each accepted
limit is therefore itself a test (`test_known_limit_still_holds`) that FAILS if the
limit ever closes, with a docstring saying what to check before celebrating. **A
known limit with a test is a reviewed decision; the same limit in a comment is a
hole the next round rediscovers -- and the same limit unstated is one a reviewer
will keep finding, correctly, forever.**

Tells you are in this trap: your fix is "add another alternation / synonym /
exemption"; the new repro differs from the last only in wording; you can list the
cases the test catches but cannot state a **property** it holds. Two corollaries,
both of which also bit in that bead:

- **Generate expectations from the real artifact, never hand-type them.** Two of
  five hand-typed allowlist entries described sentences that did not exist in the
  file.
- **Verify the mutation actually APPLIED before trusting a green result.** Two
  mutation checks silently no-op'd (a multi-line string did not match the wrapped
  source) and "passed" while testing nothing -- assert the text changed first. A
  mutation you did not confirm landed is worth less than no mutation at all,
  because it manufactures false confidence in the pin.

Related: **regexes do not parse English.** A prose pin that must judge meaning
will be wrong in one direction or the other -- a false negative is silent, a false
positive gets the test deleted. Prefer enumerate-and-allowlist, and accept that it
fails loudly whenever the prose changes; that IS the design, and the failure
message should say so.
