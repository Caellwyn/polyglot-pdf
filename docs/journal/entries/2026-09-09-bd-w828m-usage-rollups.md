---
date: 2026-09-09
bead: polyglot-pdf-w828m
title: "feat(telemetry): E3.4 session-end Firestore usage rollups per firm and per kit (FieldPath-safe keys)"
sprint: 22
tags: [security, testing, conventions]
---

## Trigger

Epic 3 (telemetry, monitoring, alerts) bead 4, plan section "Session-end
Firestore rollups" in `docs/sprint_22_admin-console_plan.md`. Epic 3's earlier
beads (E3.2 live-voice plumbing, E3.3 text/TTS usage events) landed the raw
per-call usage-event stream; this bead adds the coarser per-firm and per-kit
month rollups the console's usage view and future alert thresholds need
without scanning the fine-grained event log.

## What shipped

New `backend/services/usage_rollups.py`:

- `record_session_end(firm_id, kit_id, employee_id, language, channel, kind,
  completion_status, cost_usd, now=None)` -- called from the SAME teardown
  block in `backend/routes/websocket_routes.py` that already runs
  `log_form_session_end` and `_bank_link_spend`, on every connection
  teardown. Writes ONE BATCHED `db.batch()` set of `firestore.Increment`
  updates to `firms/{firm_id}/usage/{YYYY-MM}` and
  `kits/{kit_id}/usage/{YYYY-MM}` -- `connections_ended`,
  `sessions_completed`, `cost_usd_total`, and the `by_kit`/`by_employee`/
  `by_language` (firm doc) / `by_firm` (kit doc) nested breakdowns -- so a
  mid-write failure cannot leave one side bumped with no matching entry on
  the other.
- `record_link_opened(firm_id)` / `record_link_completed(firm_id)` -- single-
  doc `links_opened`/`links_completed` increments, hooked into
  `backend/services/link_redemptions.py`'s `open_link()` (ONLY the genuine
  first-open branch, never the idempotent re-open of an in-window link) and
  `complete_link()`.

Both entry points are best-effort, matching `alerts.py`'s established
contract in this codebase exactly (including a broken `firebase_admin` app --
`get_db()` RAISING, not just returning `None`) -- nothing here can propagate
into the teardown, the redemption gate, or the paid-session path.

`backend/routes/websocket_routes.py` gains two small shared helpers so the
new call site and the pre-existing `_bank_link_spend` read the connection's
cost identically: `_session_cost_usd(service)` (extracted from
`_bank_link_spend`'s own read) and `_rollup_language_key(service)` (resolves
`FormFillingService.spoken_language()` -- a new public accessor for the
otherwise-private `_spoken_language` -- to its BCP-47 code via
`backend.utils.language_codes.bcp47_codes_for_spoken_language`, falling back
to the raw spoken-language name when the map has no entry, per the
never-pin-a-language doctrine).

### The FieldPath-safety finding

The bead's premise is that a hyphenated map key (`i-90`, `zh-CN`) breaks a
dotted string field path. Verifying this against the vendored SDK before
writing a line of the module surfaced a sharper and more useful fact: the
break has almost nothing to do with hyphens specifically, and the two
Firestore write APIs fail on flat string keys in DIFFERENT ways.

- `update()`'s extractor (`DocumentExtractorForUpdate`) DOES dot-expand a
  flat string key correctly (via `FieldPath.from_string`/`from_api_repr`),
  including one built from `FieldPath(*parts).to_api_repr()` -- the
  backtick-escaped form. But `update()` defaults to an `exists=True`
  precondition and RAISES on a document that does not exist yet, which for a
  brand-new firm/kit-month rollup document is the common case, not an edge
  case.
- `set(merge=True)` -- the write API this module actually needs, because it
  creates the document on first write -- uses a DIFFERENT extractor
  (`DocumentExtractorForMerge`) whose `_get_document_iterator` calls
  `extract_fields(document_data, prefix_path)` with `expand_dots` defaulting
  to `False`. A flat string key, hyphenated or not, hand-joined or a
  properly-escaped `FieldPath.to_api_repr()` string, is therefore stored as
  ONE LITERAL TOP-LEVEL FIELD named e.g. `by_kit.i-90.sessions`, never the
  intended nested path `by_kit -> i-90 -> sessions`. This has nothing to do
  with hyphens: it silently mis-nests EVERY map key the moment a flat string
  is handed to `set(merge=True)`.

Confirmed against `backend/.venv/Lib/site-packages/google/cloud/firestore_v1/
_helpers.py` interactively (`DocumentExtractorForMerge._get_document_iterator`
vs. `...ForUpdate`'s, the latter passing `expand_dots=True`) before choosing
an implementation, not after a test failure. The fix: `_nest_increment()`
builds every nested increment as a REAL nested Python dict, walking a
`FieldPath(*parts).parts` tuple (the raw, unescaped segment strings -- never
serialized through a dotted string at any point), so a hyphen, a literal dot,
or a backtick in a segment is equally safe because there is no path syntax
for any of them to be mis-parsed by.

`firestore.rules` gains client deny blocks for both new nested `usage`
subcollections (`firms/{firmId}/usage/{monthId}`,
`kits/{kitId}/usage/{monthId}`), folded into the existing set-derived rules
test (`test_firestore_rules_text.py`) rather than hand-added assertions.

### Fresh-eyes round -- adopt/reject/defer

The Opus cross-surface fresh-eyes pass on this bead's diff returned
`GAPS-FOUND (2)`, both fixed inline (no rubric-fail; the rubric's three
exit criteria were already PASS, independently re-verified by the reviewer
including a from-scratch mutation of `_nest_increment`):

- **ADOPTED -- finding 1 (ASCII):** `usage_rollups.py`'s module docstring
  had a literal Unicode ellipsis (`U+2026`) in one sentence -- a correctness
  issue per CLAUDE.md scar #6 (a cp1252 Windows console `print()`/stdout
  path would `UnicodeEncodeError` on it), not just style, since this file
  is wholly new in this diff. Replaced with `...`. Re-scanned every changed
  source file in the diff (`rg -P '[^\x00-\x7F]'`) per scar #8
  (enumerate-the-set) to confirm no sibling instance existed elsewhere in
  the same PR.
- **ADOPTED -- finding 2 (swallowed log line):** extracting the cost read
  into the new shared `_session_cost_usd` helper (so the usage-rollup call
  site and `_bank_link_spend` read the connection's cost identically)
  accidentally moved a `try/except` boundary: a read failure that used to
  propagate up into `_bank_link_spend`'s own `except Exception as e:
  log.error("link_spend_record_failed", ...)` started getting swallowed
  silently inside the new helper instead, on a path that feeds paid-session
  cost banking. Fixed by giving `_session_cost_usd` optional `log`/`jti`
  kwargs: `_bank_link_spend` passes its own logger through and gets the
  exact pre-existing log line back, while the usage-rollup call site (which
  already logs its own `usage_rollup_telemetry_failed` around the whole
  `record_session_end()` call) omits them and stays silent, avoiding a
  double-report of the same failure. Added
  `test_a_broken_adapter_STILL_LOGS_link_spend_record_failed` in
  `test_websocket_ephemeral.py`, mutation-verified red (reverting the
  `log=log, jti=link_jti` kwargs on the call site reproduces exactly the
  silent-drop the finding described) before restoring the fix.
- **DEFERRED -- findings 3, 4, 5:** filed as one bead,
  `polyglot-pdf-lp8fw` ("chore(nits): deferred review nits from
  polyglot-pdf-w828m") per CLAUDE.md scar #8 -- none is a rubric-fail or a
  bug in the current diff. Finding 3: `link_redemptions.open_link()`'s
  `record_link_opened` call has no local `try/except`, relying entirely on
  `usage_rollups._increment_firm_counter`'s blanket catch (verified this
  holds today; brittle only against a hypothetical future narrowing of that
  catch). Finding 4: `_rollup_language_key`'s `hasattr` guard has no test
  exercising a service object that actually lacks the method (currently
  inert -- `FormFillingService` always has it). Finding 5: a redundant
  (non-buggy) double-guard between `firm_kind(firm_id) if firm_id else
  "live"` at the call site and `record_session_end`'s own `if not firm_id`
  check.

### Second fresh-eyes round -- adopt/reject/defer

A second Opus cross-surface pass (after the round above landed) re-verified
all three exit criteria PASS (independently re-ran the hyphenated-key/
FieldPath test and the rules deny-block test) and returned `GAPS-FOUND (1)`:

- **ADOPTED -- finding 1 (untested teardown wiring, blocker):** every
  existing test for `record_session_end`/`_rollup_language_key`/
  `_session_cost_usd` drove them as isolated pure functions with
  hand-supplied arguments; none drove the REAL `_handle_fill_session`
  teardown and asserted the actual keyword arguments passed to
  `record_session_end` at the call site. The reviewer mutation-verified
  this live: swapping `employee_id=usage_employee_id` for
  `employee_id=link_employee_id` at the real call site (the exact
  confusion the module's own comment warns against by name) left
  `test_usage_rollups.py` + `test_websocket_ephemeral.py` fully green.
  Fixed by adding
  `test_TEARDOWN_passes_usage_employee_id_not_link_employee_id_to_rollup`
  to `backend/tests/integration/test_websocket_ephemeral.py`: drives the
  real `_handle_fill_session` end-to-end (immediate-disconnect socket
  double, `firm_id=None` to keep `firm_kind()`'s Firestore read off the
  path), monkeypatches `usage_rollups.record_session_end` to capture its
  kwargs, and asserts `employee_id` resolves to `usage_employee_id`'s
  value specifically -- passing `link_employee_id` and `usage_employee_id`
  as two DIFFERENT sentinel strings so the assertion cannot pass by
  accident. Mutation-verified red against the exact swap the reviewer
  demonstrated, then restored.
- **Findings 2-5 (nits/pre-existing, no action):** finding 2 (the
  `record_link_opened` local-guard brittleness) was already filed and
  correctly scoped in `polyglot-pdf-lp8fw` from the first round -- verified
  it exists and is accurate, not re-filed. Findings 3 and 4 (the redundant
  `firm_kind` ternary; the untested `hasattr` guard branch) are the SAME
  two nits already in `polyglot-pdf-lp8fw` from the first round -- not
  re-filed. Finding 5 (an added `doc_ref.get()` read in `complete_link` on
  every completion) is a real, deliberate behavior change but not a
  correctness gap and the reviewer explicitly did not ask for a fix or a
  new bead; no action taken.

### Outer Opus cross-surface review -- adopt/reject/defer

The full outer cross-surface pass (contract trace out into every consumer
of `usage_rollups`' entry points and Firestore doc shapes) returned
`GAPS-FOUND (2)`, both ADOPTED:

- **ADOPTED -- finding 1 (untested event-loop blocking, blocker):**
  `firm_kind(firm_id)` (an uncached sync Admin-SDK `.get()`) and
  `record_session_end(...)` (its own db lookup plus a `batch.commit()`)
  were called DIRECTLY in the teardown `finally` block, on the shared
  Cloud Run event loop -- while every sibling Firestore call in the SAME
  block (`complete_link`, `_bank_link_spend`'s `record_spend`,
  `enforce_link_redemption`, `_mirror_budget_exhausted`) was already
  `asyncio.to_thread`-dispatched, and `_mirror_budget_exhausted`'s own
  docstring states the rule by name. Every existing usage-rollup test
  stubbed `record_session_end` to return instantly, so the missing wrapper
  was invisible to the suite -- the same shape `test_link_routes.py`'s
  `test_the_minting_flag_check_runs_OFF_the_event_loop` already exists to
  catch on a sibling route. Fixed by wrapping both calls in ONE
  `asyncio.to_thread(_resolve_kind_and_record_rollup)` dispatch (mirrors
  the existing `_resolve_ceiling_and_check_budget` pattern in this same
  file, since `firm_kind`'s result feeds `record_session_end`'s `kind`
  argument). Pinned by
  `test_TEARDOWN_dispatches_the_usage_rollup_OFF_the_event_loop` in
  `backend/tests/integration/test_websocket_ephemeral.py`, which spies on
  `asyncio.to_thread` itself (the same technique
  `test_link_routes.py`'s sibling test uses) rather than trusting a fake
  Firestore's instant return. Mutation-verified red against a direct call
  (dropping the `to_thread` wrapper), then restored.
- **ADOPTED -- finding 2 (channel partitioning, medium-high confidence):**
  the rollup documents (`firms/{firm_id}/usage/{YYYY-MM}`,
  `kits/{kit_id}/usage/{YYYY-MM}`) used a bare month id with `channel` as a
  last-writer-wins SCALAR FIELD each write overwrites -- not a partition
  key. Because staging and demo share one Firestore project, a staging
  test-drive would increment the SAME document the demo's billing view
  (bd `polyglot-pdf-mpebj`) reads. This repo's established remedy is the
  channel-suffix convention from bd `polyglot-pdf-3q9qn`
  (`link_redemptions._collection_name` / `links_store._collection_name`:
  the demo keeps the bare name, every other channel gets its own
  suffixed one). That convention suffixes a COLLECTION name; these
  rollup docs live at a fixed collection path keyed by firm_id/kit_id, so
  the fix suffixes the MONTH DOCUMENT ID instead: `_month_key` now takes
  an optional `channel` and returns `YYYY-MM` for the demo channel (its
  pre-existing default, so nothing already written is orphaned) or
  `YYYY-MM_{channel}` for every other channel, resolving to this
  process's own `link_channel()` when no channel is given explicitly
  (matching `link_redemptions._collection()`'s own default-resolution
  pattern) -- covers `record_session_end` (channel is an explicit,
  required parameter there) and `_increment_firm_counter` (backing
  `record_link_opened`/`record_link_completed`, which have no channel
  parameter of their own since both callers run only on the public
  backend). Deliberately did NOT change `credit_ledger.py`'s reasoning
  (channel stays a plain field there) -- that module's entries are
  append-only rows where channel is a record of WHERE a debit happened,
  not a partition key; that reasoning does not transfer to a shared
  aggregate counter document that overwrites in place. Pinned by four new
  tests in `backend/tests/unit/test_usage_rollups.py`: a staging session
  does not touch the demo firm doc's totals, same for the kit doc, the
  demo channel keeps its bare month id, and `record_link_opened`/
  `record_link_completed` are also channel-partitioned. Mutation-verified
  red against dropping the channel suffix in `_month_key` (3 of 4 new
  tests went red; the fourth pins the unchanged demo-default behavior and
  correctly stayed green), then restored.

Whether the maintainer wants staging traffic PARTITIONED (this fix) vs.
EXCLUDED from the rollups entirely was flagged by the reviewer as a
product call with no obvious default; partitioning was chosen because it
is the repo's own established convention for exactly this shared-project
hazard, it is reversible (a later exclude-staging change is a filter on
top of this, not a rework), and leaving it unpartitioned is an active
correctness bug (demo billing figures inflated by staging test-drives) --
not a case where "no fix" was a safe default to leave in place pending an
answer.

### Third fresh-eyes round -- adopt/reject/defer

A further Opus cross-surface pass returned `GAPS-FOUND (2)`:

- **ADOPTED -- finding 1 (unvalidated handshake kit_id as a Firestore path
  segment, blocker):** on a STAFF session (not a client link), the
  handshake's `kit_id` (`websocket_routes.py`'s `kit_id =
  handshake.get("kit_id")`) is raw, unvalidated client input -- the
  client-link branch overrides it with the signed token's `link_kit_id`,
  but that override does not run for staff, and that value flowed straight
  into `record_session_end(kit_id=kit_id)` -> `.document(kit_id)`. The
  reviewer verified against the vendored SDK that Firestore's `.document()`
  does not reject embedded slashes: an id like `"a/b/c"` commits
  successfully to `kits/a/b/c/usage/...`, a path this module never intended
  to touch, and a non-string kit_id (dict/list) raised `TypeError`,
  silently dropping the whole rollup write (including the firm-side half)
  under the module's broad `except`. Fixed by adding `_safe_kit_id()` to
  `usage_rollups.py` -- the SAME charset as `form_kit_routes.py`'s
  `_KIT_ID_RE`/`_safe_kit_id` (bd `polyglot-pdf-sbfk`/`0dsv4`), duplicated
  rather than imported (a route module importing FastAPI/Depends has no
  business being a dependency of a service module) -- called once at the
  top of `record_session_end` so every downstream use (the `.document()`
  call AND the `by_kit` map key) sees only a validated id; an invalid one
  degrades to kit-less (same as a genuinely absent one) rather than failing
  the whole write. Four new tests in `test_usage_rollups.py`
  (`test_a_SLASHED_kit_id_is_DROPPED...`, `..._PATH_TRAVERSAL_kit_id...`,
  `..._VALID_kit_id_still_writes...`, `..._NON_STRING_kit_id...`),
  mutation-verified red against removing the `_safe_kit_id` call (3 of 4
  went red; the "still writes a valid id" sanity test correctly stayed
  green since it does not depend on the guard).
- **ADOPTED -- finding 2 (stale cost-sizing doc, gap):**
  `docs/components/config-deployment.md`'s "size from all four" Firestore-
  write sizing note (redemption reads + writes on the paid path) predates
  this bead's writes and now undercounts: first-open is TWO writes (not
  one -- `open_link`'s record plus the rollup's `links_opened`), completion
  is one read plus TWO writes (not one -- `complete_link`'s update, its own
  read-back for the rollup's firm_id, plus `links_completed`), and every
  connection teardown now separately adds one read (`firm_kind()`) plus
  one-or-two writes (`record_session_end`'s batched commit). Corrected the
  note in place with the exact counts and bumped the doc's own "Last
  updated" stamp; did not touch `kit_gates.py`'s sibling cost-note comment
  or `docs/components/auth.md`'s doc-id stamp -- both already filed as
  separate beads (`polyglot-pdf-ahsn3`, `polyglot-pdf-qrieq`) by this same
  review round, verified to exist before leaving them unfixed here.
- **Finding 3 (the `record_link_opened` import-inside-try coupling): NOT
  filed, per the reviewer's own note** -- traced as unreachable today
  (`record_link_opened` itself cannot raise; only a hypothetical future
  `ImportError` on the lazy import could reach `open_link`'s
  `except Exception`), and the reviewer explicitly folded it into finding
  1's fix rather than asking for a separate bead.

## Lessons

The generalizable lesson: **when a bead's own description names a specific
failure mode ("X breaks because of hyphens"), verify the ACTUAL mechanism
against the real library before implementing the described fix** -- the
described symptom (hyphens) and the real cause (an extractor that does not
dot-expand strings at all, for either reason) were different enough that a
fix aimed only at "escape the hyphens" (e.g. `FieldPath(...).to_api_repr()`
as an update() dict key) would have shipped a real bug for `set(merge=True)`
specifically, discoverable only by testing against a Firestore-faithful fake
rather than one that just echoes back whatever dict it's handed. This
generalizes to any repo using the `google-genai`/`google-cloud-firestore`
SDKs: the vendored source under `.venv/` is more authoritative than the
bead's own prose description of a bug, exactly the way
`docs/genai_docs/README.md` already is for the Gemini SDK.

Also: the test fake for a Firestore `merge=True` write needs to actually
IMPLEMENT the merge (nested-dict recursion + `Increment` resolution against
the prior value), not just record the raw payload passed to `set()` --
otherwise a test asserting on the intended final document shape can pass even
when the production code hands the fake a flat, wrongly-shaped key, because
the fake never exercises the real SDK's (non-)expansion behavior. This mirrors
`test_alerts_dedup.py`'s existing "fake, not mock" precedent one level
further, into actually simulating one specific SDK code path's semantics.

## Doc freshness

- `docs/components/auth.md` (tracks `link_redemptions.py`, `link_spend.py`,
  `websocket_routes.py`, `firestore.rules`): bumped, new paragraph.
- `docs/technical_guide.md`: new Surface contract 26 (session-end usage
  rollups; renumbered from 25 during the rebase onto origin/dev, which had
  merged bd polyglot-pdf-rd3s8's own new Surface contract 25 in the
  meantime), stamp line updated to match the established per-bead chain
  convention in that file.
- `backend/tests/unit/test_firestore_rules_text.py`: extended
  `ADMIN_SDK_ONLY_COLLECTIONS` with the two new nested subcollections.
- Reviewed and left AS-IS: `docs/components/websocket-routing.md` (tracks
  `websocket_routes.py`, but its scope is the WS protocol/message-type
  surface, not teardown telemetry internals -- adding a redundant paragraph
  there would drift against the Surface-contracts map, which is already the
  canonical detail); `docs/components/context-compression.md` (tracks
  `backend/services/form_filling_service.py`, but the one change there -- a
  public `spoken_language()` read accessor -- makes no claim in that doc
  stale; it is unrelated to context-window compression).

## Files touched

- `backend/services/usage_rollups.py` (new)
- `backend/routes/websocket_routes.py` (teardown call site,
  `_session_cost_usd`, `_rollup_language_key`, import)
- `backend/services/link_redemptions.py` (`open_link`/`complete_link` hooks)
- `backend/services/form_filling_service.py` (new `spoken_language()`
  accessor)
- `backend/tests/unit/test_usage_rollups.py` (new)
- `backend/tests/integration/test_websocket_ephemeral.py` (added the
  teardown-wiring test, second fresh-eyes round)
- `backend/tests/unit/test_firestore_rules_text.py` (extended set)
- `firestore.rules` (two new deny blocks)
- `docs/components/auth.md`, `docs/technical_guide.md`
- `docs/components/config-deployment.md` (third fresh-eyes round: corrected
  Firestore write-sizing counts, stamp bumped)
