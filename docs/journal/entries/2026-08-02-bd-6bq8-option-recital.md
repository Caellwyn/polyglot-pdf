---
date: 2026-08-02
bead: polyglot-pdf-6bq8
title: "fix(voice): model must recite ALL options of a multiple-choice field aloud (W-7 reason, I-90 P2SA)"
tags: [conventions, harness, testing]
---

## Trigger

Maintainer report (2026-08-02): the voice model does not faithfully recite the
options of multiple-choice fields. On W-7 question 2 (the 8-option "Reason you
are submitting Form W-7" group) it under-describes the choices; on I-90 Part 2
Section A (a 12-option radio) it skipped the options entirely and said "you can
pick one of the options shown". The product premise is that users may not be
able to read the form -- the voice model is their ONLY access to the options, so
summarizing or skipping them is a correctness failure, and it bodes ill for
every long-option field as more forms are authored.

## What shipped

Four coordinated prompt-surface changes (no wire-format or state change):

- **DTI SI (`backend/config.py`): a new `PRESENTING OPTIONS` block.** The user
  cannot see the form; when the current field has options the model must read
  EVERY option aloud, in the given order, without summarizing, skipping,
  merging, stopping partway, or referring to "the options shown". It explicitly
  bans the one-at-a-time yes/no walk ("Is it X?" per turn) observed live, and
  licenses the length ("reading a long list takes a while -- that is expected
  and correct") because a brevity-biased audio model shortens what feels too
  long. One carve-out: a list the guidance marks as a *long standard list*
  (e.g. the 50-state selects) is asked directly with an offer to read the full
  list, read in full the moment the user asks or seems unsure.
- **WORKFLOW step 1** wires the recital into the ask step itself, so the
  numbered workflow agrees with the options block.
- **Per-field guidance render (`backend/services/ai_context.py`):** the
  `Options:` segment now carries the option COUNT plus a per-turn imperative --
  `Options (8 -- read ALL 8 aloud when asking; the user cannot see them): [...]`
  -- switching above `LONG_OPTION_LIST_THRESHOLD` (20; W-7 reason is 8, I-90
  P2SA is 12, the state selects are 50) to the long-standard-list marker the SI
  carve-out keys on. The directive rides the LATEST injected guidance block on
  exactly the turns that have options.
- **Both initiating templates** now direct "read EVERY option aloud". The
  RESUME template's unqualified "ask in one short sentence" was observed live
  overriding the SI recital (a resume onto the 8-option reason field compressed
  it to a yes/no about option (a)); brevity is now scoped to option-less
  fields.

**Live verification (local voice harness, Vertex 2.5 native-audio):** W-7
question 2 now recites all 8 reasons (a-h) in one ask via the confirm-path
injection; I-90 Part 2 Section A recites all 12 options verbatim, in order, on
the resume-initiating path (the exact scenario the maintainer reported).

**Review outcome:** recorded in the merge ping; fresh-eyes + Opus outer review
ran pre-PR per the standard flow.

**Cost impact (measured):** the DTI SI grows 14,086 -> 15,221 chars (~8%), and
each option-bearing field's injected guidance grows by ~62 chars. Because the
per-turn SI is the 2.5 cost lever (text-in is 95-98% of session cost,
docs/standards/logging-and-cost.md), this is a recurring per-turn increase of
up to roughly the same ~8% on text-in. Accepted deliberately: the recital is a
maintainer-requested correctness requirement (non-readers have no other access
to the options), and the growth is prose the SI-reduction epic can later
compress like any other block. Flagged for the maintainer in the merge report.

Deliberately NOT changed: the legacy `SYSTEM_INSTRUCTION` full-dump path still
truncates >5-option lists to 3 (`build_form_context`) -- it belongs to the
deprecated section-reset fallback with a deletion inventory, and expanding its
per-section dump would balloon the per-turn SI cost of a dead-end mode.

## Lessons

- **The debugging detour that mattered: `frontend/public/form-kits` was a stale
  COPY, not a junction.** A previous session (2026-07-30) had copied an
  outdated W-7 kit (59 fields, per-checkbox `reason_a..h`, no `reason` group)
  into the vite-served path. The path is gitignored, so `git status` was clean
  while every live test silently exercised the WRONG schema -- the model's
  "failure to recite options" was initially it correctly answering yes/no
  checkbox fields one at a time. Before any schema-dependent local voice test,
  verify the served kit matches the branch (junction it to the worktree's own
  `form-kits`). Saved to local memory; the fix for the trap is one
  `fsutil reparsepoint query` check.
- **An unqualified brevity instruction beats a distant behavioral rule.** The
  RESUME template's "in one short sentence" sat closer to the model's ask than
  the SI's recital rule and won every time. When adding a behavioral rule,
  sweep the injection/initiating templates for standing directives that
  contradict it in the specific path under test.
- **Live-verify prompt changes per PATH, not per feature.** The recital has
  three delivery paths (fresh initiating, resume initiating, confirm-response
  injection) and each needed its own check; the first two runs only ever tested
  one path.

## Doc freshness

- `docs/standards/si-reduction.md` -- bumped: records the new `Options (N ...)`
  render shape, `LONG_OPTION_LIST_THRESHOLD`, the `PRESENTING OPTIONS` SI
  block, and the initiating-template recital directives. SI remains fully
  static.
- `docs/components/voice-ai.md` -- reviewed, left as-is: it tracks the adapter
  and callback handler, neither of which changed.
- The freshness checker flags a pre-existing stale set (ai-models,
  logging-and-cost, risk-rating, section-reset-deprecation,
  validation-delegation, voice-and-vad, technical_guide track `config.py`;
  plus six others that track files this branch did not touch). All were stale
  BEFORE this branch; this branch's `config.py` diff is SI/template prose
  only, which none of them document (the SI shape is owned by si-reduction.md,
  bumped above). Reviewed against THIS diff and left as-is per the
  already-stale-before-you rule; their older drift is not verified here.

## Files touched

- `backend/config.py` -- DTI SI `PRESENTING OPTIONS` block + WORKFLOW step 1;
  `INITIATING_MESSAGE` + `RESUME_INITIATING_MESSAGE` recital directives.
- `backend/services/ai_context.py` -- `LONG_OPTION_LIST_THRESHOLD`; the
  Options segment's count + per-turn imperative / long-list marker.
- `backend/tests/unit/test_dti_si_voice_rules.py` -- pins for the new SI
  prose, the anti-yes/no-walk rule, the template directives, and the guidance
  render (count imperative, long-list marker, threshold bounds, no-options
  render unchanged).
- `docs/standards/si-reduction.md` -- freshness bump (above).
- `docs/journal/entries/2026-08-02-bd-6bq8-option-recital.md` -- this entry.
