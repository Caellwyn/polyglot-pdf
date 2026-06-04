---
date: 2026-06-04
bead: polyglot-pdf-jpe
title: "Stale config refs (VFF_DEV_LOGGING comment + retired Gemini alias) + ASCII-only code rule"
tags: [conventions, harness]
---

## Trigger

Bundle of three small stale-reference / config-drift beads, picked as a
low-risk "knock out some beads" batch:

- **polyglot-pdf-jpe** -- `callback_handler.py:194` comment named the dead
  `VFF_DEV_LOGGING` env var as the `_dev_log` gate.
- **polyglot-pdf-0kv** -- `scripts/test_gemini_connection.py` hardcoded a
  retired native-audio model alias that 1008s on connect.
- **polyglot-pdf-bnt** -- the closeout test gate should exclude the flaky
  `external` live-Gemini test.

A fourth item emerged mid-work: while editing the `.py` files I introduced a
Unicode em-dash into a comment, which the maintainer flagged. That became a new
scar-tissue rule (below).

## What shipped

- **jpe (fixed):** `backend/services/callback_handler.py` -- the `_dev_log`
  comment now names the real gate (the `backend/.env.DEV` marker, via
  `dev_file_logger.DEV_LOGGING_ENABLED`) instead of the dead `VFF_DEV_LOGGING`
  env var. Comment-only change; verified `_dev_log` is gated by `.env.DEV`
  (the fixed comment at `callback_handler.py:194-195`, confirmed at
  `callback_handler.py:205` and `dev_file_logger.py:55`).
- **0kv (fixed):** `scripts/test_gemini_connection.py` -- replaced the
  hardcoded retired alias `gemini-live-2.5-flash-preview-native-audio-09-2025`
  with `os.getenv("GEMINI_LIVE_MODEL", "gemini-2.5-flash-native-audio-preview-12-2025")`,
  matching the contract test's env-read pattern. (Pre-existing: the script's
  `response_modalities: ["TEXT"]` against a native-audio model will still 1007;
  that is beyond 0kv's scope -- 0kv was strictly the retired alias.)
- **bnt (already resolved -- closing as done):** the closeout test gate already
  excludes the flaky `external` test. `scripts/closeout_prep.py:283` and the
  SKILL Step-4 re-run command both pass `-m "not external"` (committed in
  d6260ed / earlier hrn work). The bead's requested change is already live, so
  it is closed as already-done. (A cosmetic consistency touch to an
  illustrative SKILL example line was attempted but blocked by the auto-mode
  self-modification guard and dropped -- not needed, the real gate is correct.)
- **New scar-tissue rule (CLAUDE.md #6): ASCII only in code files.** No
  em-dashes / smart quotes / emoji in `.py`/`.ts`/`.tsx`/`.js` (comments +
  strings); markdown exempt. Rationale: Windows cp1252 console crashes on
  non-ASCII reaching `print()`/stdout or `open()` without an explicit encoding
  -- a class of bug the repo has burned multiple beads on (39a, 6xp, 4ln,
  hrn.14/16). The em-dash I introduced in `test_gemini_connection.py` was
  converted back to `--`; my `callback_handler.py` edit was already ASCII.

Review-worthiness: this is a comment + diagnostic-script + tier-1-doc-text PR
with zero runtime-behavior change, so Copilot review is skipped per the Step-6
gate; fresh-eyes still runs.

**Fresh-eyes triage (sonnet, arm B):** 4 findings, all addressed.
- #1 (high) -- `test_gemini_connection.py` still 1007s on the `TEXT` modality
  against the native-audio default. **Deferred** -- out of scope for 0kv (which
  was strictly the retired alias); filed as **bd polyglot-pdf-0y2** (the
  standalone-diagnostic analogue of a7k). Added an in-script NOTE pointing there.
- #2 (med) -- journal cited `callback_handler.py:204` for the gate; the +1-line
  edit shifted it. **Adopted** -- corrected to lines 194-195 / 205.
- #3 (med) -- script comment was incomplete about the post-fix 1007. **Adopted**
  -- added the NOTE comment (same fix as the #1 pointer).
- #4 (med) -- CLAUDE.md rule #6 over-claimed the cp1252 rationale for TS/JS.
  **Adopted** -- split the rule: correctness rule for Python (cp1252),
  consistency rule for the UTF-8 TS/JS frontend.

## Lessons

- **ASCII-only in code files** is now codified (CLAUDE.md scar #6 + auto-memory).
  It existed only in the journal (the cp1252 beads) but never as a stated rule;
  the maintainer asked for it explicit after the em-dash slip.
- A bead can be "already done" by work landed under a different bead/PR. The
  honest close is as already-resolved with a pointer to where it actually
  shipped, not a fresh no-op edit.

## Doc freshness

Prep flagged four docs STALE because they track `callback_handler.py` (touched
2026-06-03): `docs/components/config-deployment.md`, `docs/components/voice-ai.md`,
`docs/standards/confirmation-and-audit.md`, `docs/standards/hipaa-pii-policy.md`.
**Reviewed, left as-is:** the change was a comment-only fix that brings the code
into line with what these docs *already* say -- config-deployment.md already
documents `.env.DEV`/`DEV_LOGGING_ENABLED` as the real gate and explicitly calls
`VFF_DEV_LOGGING` "dead config ... tracked for [removal]" (lines 64-84), and
hipaa-pii-policy.md already describes the `.env.DEV`-gated `_dev_log` (lines
33-34). No CURRENT-STATE prose changed, so no doc bump is warranted. CLAUDE.md
gained scar rule #6 (noted here per the doc-maintenance convention).

Pre-existing slip (NOT triaged into this PR): `polyglot-pdf-hrn` (harness-tuning
epic) is IN_PROGRESS > 1d -- a separate owner's epic, not an orphan, out of
scope for this batch.

## Files touched

- `backend/services/callback_handler.py` -- fixed stale `_dev_log` gate comment (jpe).
- `scripts/test_gemini_connection.py` -- env-read model + ASCII em-dash fix (0kv).
- `CLAUDE.md` -- new scar-tissue rule #6 (ASCII-only in code files).
- `docs/journal/entries/2026-06-04-bd-jpe-0kv-bnt-stale-config-refs-and-ascii-rule.md` -- this entry.
