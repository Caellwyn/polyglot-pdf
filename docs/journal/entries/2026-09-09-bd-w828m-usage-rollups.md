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
- `backend/tests/unit/test_firestore_rules_text.py` (extended set)
- `firestore.rules` (two new deny blocks)
- `docs/components/auth.md`, `docs/technical_guide.md`
