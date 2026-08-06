# Testing

**Tracks:** pytest.ini backend/tests/conftest.py backend/requirements.txt frontend/package.json frontend/vite.config.ts .github/workflows/ci.yml

*Last updated: 2026-08-05 (bd polyglot-pdf-saxh: new TDD-cadence rule -- when the same defect class survives your fix TWICE, change the MECHANISM not the instance; plus generate expectations from the real artifact, and verify a mutation actually applied. See [journal/entries/2026-08-05-bd-1bsx-bead-tier-routing.md](../journal/entries/2026-08-05-bd-1bsx-bead-tier-routing.md)). Prior: 2026-07-17 (bd polyglot-pdf-1rgr: schema-editor CI job now runs a `tsc --noEmit` typecheck step, mirroring frontend's).*

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

There are **two collected suites** under `testpaths`:

- `backend/tests` — the product backend suite (below).
- `tests` (repo root) — the **harness-tooling** suite (closeout, `bd_safe`,
  `next_bead`, doc-freshness, `pr_review_watcher`, pricing). It runs from the repo
  root on defaults and is now part of the same `pytest` run.

The backend suite is organized **by directory**, not by marker:

| Dir | What | Notes |
|-----|------|-------|
| `backend/tests/unit/` | Fast, isolated unit tests | The bulk of the suite. |
| `backend/tests/integration/` | Multi-component flows (WS ephemeral session, idle-timeout flow) | |
| `backend/tests/contract/` | Protocol / tool / live-adapter contracts | Holds the one **`external`** test (`test_live_ai_gemini_integration.py`); `test_websocket_protocol.py` pins the ws-protocol.md wire contract via doc-vs-code diffs (bd polyglot-pdf-ceyt) and `test_tool_contracts.py` pins the tool-call sequence — add to these rather than creating a fourth file. |
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

There is **no automated E2E suite yet.** Writing a repeatable one is tracked by
`polyglot-pdf-277` (*full I-90 form completion across all field types* — all 6 field
types, the confirmation workflow, idle-timeout/reconnect, and PDF
generation/download, verified end-to-end at least twice, failures triaged into new
beads). The native-vs-manual-VAD smoke test is `polyglot-pdf-333`.

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

## Coverage & CI

**Coverage tooling is wired on all three stacks but opt-in (a secondary signal,
not enforced).** Run it explicitly:

- **Backend:** `pytest backend/tests -m "not external" --cov --cov-report=term-missing`
  (`pytest-cov`; source/omit scoping in the root `.coveragerc`).
- **Frontend:** `npm run test:coverage` from `frontend/` (`@vitest/coverage-v8`).
- **Schema-editor:** `npm run test:coverage` from `schema-editor/`.

Baseline statement coverage (recorded 2026-06-09): **backend 54%** (source-scoped
via `.coveragerc`, so untested modules count), **frontend 12%**, **schema-editor
33%**. These are instruments, not gates — no threshold is enforced and a low
number is not a closeout blocker. Coverage artifacts (`.coverage`, `coverage/`)
are gitignored.

**CI is informational and non-blocking.** `.github/workflows/ci.yml` runs the
backend pytest suite (`-m "not external"`) plus both vitest suites (each preceded
by its own `tsc --noEmit` typecheck step) on every PR.
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
(`tsc --noEmit`) gate in CI's frontend and schema-editor jobs is the thing that
catches this class; keep both green (`polyglot-pdf-uov.17`, `polyglot-pdf-1rgr`).

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
