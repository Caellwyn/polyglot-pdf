---
date: 2026-06-01
bead: polyglot-pdf-p1t
title: "Live API 1007: VAD config sends disabled:true AND sensitivity fields together (rejected) — on dev AND main"
tags: [hotfix, refactor, testing]
---

## Trigger

`bd polyglot-pdf-p1t` (P2 bug). Discovered 2026-05-31 while running the tak
token-cost spike against the real Live API: the adapter's VAD-config builder set
`automatic_activity_detection.disabled=True` (when `DISABLE_GEMINI_VAD=True`, the
default) and then *unconditionally* also appended `start_of_speech_sensitivity`,
`end_of_speech_sensitivity`, `prefix_padding_ms`, and `silence_duration_ms` from
the `VAD_*` settings. The Live API now rejects that combination on connect with
close code 1007 ("disabled is true, but the following fields were also set:
..."), so a default-config session fails to connect → no turns. The block exists
on `origin/main` too, so this is not new work — the API tightened enforcement (or
the deployed demo image predates the `VAD_*` fields). Maintainer confirmed prod is
not currently affected (the live demo has not been redeployed since these
changes), so this was scoped as a standalone fix to land before the next deploy.

## What shipped

- **Fix + extraction** in `backend/adapters/live_ai_gemini.py`: pulled the VAD
  assembly (previously inline, buried mid-way through the long async
  `_run_session_loop`) into a pure `@staticmethod _build_vad_settings(settings)`.
  The fix is an either/or gate: when `DISABLE_GEMINI_VAD` is true, return **only**
  `{disabled: True}`; the sensitivity/padding knobs are emitted **only** when
  Gemini auto-VAD is enabled. Behavior otherwise preserved (enabled-with-no-knobs
  still yields `{}` so Gemini uses its own defaults).
- **Scope decision** (maintainer-steered): focused VAD-helper extraction only, not
  a broader `_run_session_loop` refactor. The rest of that method is genuine async
  session-lifecycle code (sender/receiver tasks, reconnect, token accounting) that
  is not cleanly extractable the way the pure config block was. No follow-up bead
  filed — the remaining length is acceptable and not blocking.
- **Doc fix** in `docs/standards/voice-and-vad.md`: the standards doc documented
  the now-fixed "knobs are wired in but inert" behavior, which was the bug. Updated
  the code snippet and the callout to state the 1007 either/or constraint.
- **3 regression tests** in `backend/tests/unit/test_live_ai_gemini.py` pinning the
  contract: disabled⇒`{disabled:True}` only; enabled⇒sensitivity fields with no
  `disabled`; enabled-with-UNSPECIFIED/None⇒`{}`.

## Lessons

The Live API's `automatic_activity_detection` is a hard either/or: `disabled=True`
is mutually exclusive with the sensitivity/padding fields, enforced at connect with
close 1007. Already captured in the updated `docs/standards/voice-and-vad.md`
callout, so no separate standards one-liner needed. Secondary lesson: a pure-dict
config builder entangled inside a long-lived async loop is untestable until
extracted to a static helper — the extraction is what makes the regression test
trivial (no client, no async, no instance).

## Doc freshness

- `docs/standards/voice-and-vad.md` — bumped (the inert-knobs note was the
  now-fixed behavior); already stamped `2026-05-31`.
- `check_doc_freshness.py` reports `docs/components/` + `docs/standards/` empty in
  the main checkout (the docs-reorg epic is populating them on other branches), so
  no other doc was flagged.
- Four pre-existing stale `in_progress` beads (`gfb.2`, `m3f`, `pki`, `hjo`) were
  surfaced by closeout housekeeping; all belong to other in-flight work, none are
  orphans, left untouched.

## Files touched

- `backend/adapters/live_ai_gemini.py` — extracted `_build_vad_settings`; gated knobs behind `not DISABLE_GEMINI_VAD`.
- `backend/tests/unit/test_live_ai_gemini.py` — added 3 regression tests + `_vad_settings` stub helper.
- `docs/standards/voice-and-vad.md` — corrected the VAD config snippet + 1007 callout.
- `docs/journal/entries/2026-06-01-bd-p1t-live-api-1007-vad-config-sends-disabled-true-and.md` — this entry.
