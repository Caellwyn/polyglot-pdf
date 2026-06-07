---
date: 2026-06-07
bead: polyglot-pdf-sun
title: "ASCII-clean SYSTEM_INSTRUCTION + JIT strings in config.py; correct stale status legend"
tags: [conventions, testing]
---

## Trigger

`polyglot-pdf-sun` (filed 2026-06-07 during the `5oq` model-switch work, and the
same non-ASCII I flagged while doing the `h79/efd/t1c` bundle). `Settings.SYSTEM_INSTRUCTION`
and `JIT_SYSTEM_INSTRUCTION` in `backend/config.py` embedded non-ASCII codepoints,
plus em-dashes in nearby comments. Per CLAUDE.md scar #6 this is a real cp1252
crash hazard, not a style nit -- reading the file through the default Windows
console encoding raises `UnicodeDecodeError` (it did, mid-inventory, during this
work). It was kept OUT of the `5oq` PR because the strings are sent to Gemini and
normalizing them could shift behavior, so the bead required a separate,
probe-verified change.

## What shipped

**ASCII normalization (config.py now has 0 non-ASCII bytes).** Six distinct
codepoints replaced by behavior-preserving ASCII:

- U+2022 bullet (`-` bullet) -> `-` (30x, the TOOLS/MATCHING/CONSTRAINTS lists)
- U+2192 arrow -> `->` (5x, WORKFLOW "User answers -> call update_form_fields")
- U+2014 em-dash -> `--` (10x, comments + one inline)
- U+2713 / U+2717 / U+2212 (check / x / minus) -> removed via the legend rewrite below

The diff is exactly 43 lines changed / 43 lines (one per line that carried a
non-ASCII char) -- a pure character swap, no logic touched.

**Corrected a stale, inaccurate legend (not just ASCII).** The JIT instruction's
`get_form_status` description claimed the tool returns
`status: <check>=confirmed, <x>=unconfirmed, <minus>=empty`. That never matched
the real output: `callback_handler` emits the WORDS `confirmed`/`unconfirmed`
(`f"{field_id}:{value}:{status}"`) and simply omits empty fields. The non-JIT
`SYSTEM_INSTRUCTION` already described it correctly. So the glyph legend was both
non-ASCII AND wrong; I replaced it with the accurate wording (`status is
'confirmed' or 'unconfirmed' (empty fields are omitted)`), aligning the JIT prompt
with the real tool output and with the non-JIT instruction.

**Behavior verified live (the acceptance criterion).** Because the strings are
sent to Gemini, ASCII normalization could in principle shift tool-calling
behavior, so the bead required a probe, not an assumption. I ran the `kbf`/`5oq`
`probe_tool_call.py` (which connects with the REAL `SYSTEM_INSTRUCTION` +
`TOOL_DECLARATIONS` from `backend.config` and sends a stand-in user answer)
against the default 2.5 model with this edited config: **3/3 runs EMITTED
`update_form_fields`** with correct args (`field_id=p1_line1_aliennumber`,
`value=A123456789`). The probe is not in this branch's tree (it landed on the
`5oq` branch under `backend/scripts/`); I ran a copy from git history out of a
temp path with `PYTHONPATH` pointed at this worktree, so it loaded THIS edited
config.

Decisions made autonomously (defended in the merge ping): rewriting the legend to
the accurate wording (rather than mechanically transliterating the glyphs to
ASCII art) -- the glyphs were wrong, so a faithful ASCII transliteration would
have preserved an inaccuracy; correcting it is strictly more correct and matches
the sibling non-JIT string. Doing the comment em-dashes in the same PR (in scope:
config.py "0 non-ASCII bytes" is the acceptance criterion, which covers comments).

Nothing deferred; no new beads filed.

## Lessons

Scar #6 (ASCII-only in .py) has a correctness edge beyond style: a non-ASCII char
anywhere in a .py file makes the whole file unreadable on a default cp1252
console, so even comments matter. Already in CLAUDE.md scar #6 and bd memory; this
entry is another confirmed instance, no new doc one-liner needed.

When ASCII-cleaning prompt strings that are sent to a model, treat it as a
behavior change and probe-verify -- don't assume a glyph swap is inert.

## Doc freshness

- **Reviewed and left** every doc the freshness checker flagged
  (`config-deployment.md`, `voice-and-vad.md`, `ai-models.md`, `risk-rating.md`,
  `logging-and-cost.md`, `context-compression.md`, `terminology.md`,
  `confirmation-and-audit.md`, `stateless-architecture.md`, `websocket-routing.md`,
  `schema-forms.md`, `auth.md`, `technical_guide.md`): all flagged only because
  `config.py` got a fresh mtime from this branch's edit. None quote the prompt
  bullets, the arrows, or the `get_form_status` glyph legend (grep-verified), so
  this string-normalization diff invalidates no doc prose. `config-deployment.md`
  mentions `JIT_SYSTEM_INSTRUCTION` only to describe the `USE_JIT_SCHEMA` flag's
  behavior, which is unchanged.

## Beads housekeeping

The housekeeping audit again flagged `polyglot-pdf-hrn` (P1 harness epic) as stale
in_progress (5 days). Unrelated to this bead and owned by another active track;
left as-is (noted, not transitioned), same call as the prior closeout.

## Files touched

- `backend/config.py` -- ASCII-normalize the SYSTEM_INSTRUCTION + JIT strings + comments (bullets/arrows/em-dashes); rewrite the JIT get_form_status legend to the accurate `confirmed`/`unconfirmed` wording. 0 non-ASCII bytes.
