---
date: 2026-07-05
bead: polyglot-pdf-bo4m
title: "Field fine-print (help.instructions) now rides the next-field hint + an SI directive to convey it"
tags: [hotfix, testing]
---

## Trigger

On the deployed demo (I-90, English), the voice AI asked the Part 1 name-change
question ("Has your name changed?") WITHOUT the qualifying context -- the form's
fine print says the question means "changed since your Permanent Resident Card
was issued". The maintainer's goal: make field `help.instructions` reliably
reach the voice AI in general, not patch one field.

## Root cause (exit criterion 1: wire-strip vs. salience)

**NOT a wire-strip.** Traced empirically end to end:

- The legacy handshake sends whole field objects
  (`SchemaFormStateManager.extractSectionFields` filters `schema.fields` without
  reshaping), so `field.help` survives the wire -- pinned by a new
  `schemaFormState.test.ts` case asserting the payload carries the help block
  intact.
- `websocket_routes.py` passes the handshake `schema` dict through untouched,
  and `ai_context.build_form_context` renders `help.instructions` as a
  `Note:` segment (the bd jnjj.23 fix) -- already pinned by
  `test_real_i90_section_si_carries_help_instructions` against the REAL
  form-kits/i-90/schema.json.

So the text WAS in the SI. The real gaps were **salience + no directive**
(hypotheses 2 and 3 in the bead):

1. The per-turn steering channel -- `formatNextFieldHint` (frontend
   `navigation.ts`), which builds the initiating message's
   `{next_field_hint}`, the `confirm_field` response hint, and the
   manual-update hint -- carried name/type/options but NOT
   `help.instructions`. The model acts on the hint; the `Note:` line sat
   buried in a ~10-field pipe-delimited SI dump.
2. Neither the legacy nor the JIT SI ever TOLD the model to convey a field's
   note while asking (the DTI SI already does via its guidance blocks).

## What shipped

- **`frontend/src/navigation.ts`**: `formatNextFieldHint` appends
  `. Context to briefly convey when asking: <help.instructions>` when present.
  One choke point serves every hint consumer (initiating message, confirm
  advance, manual-update, recovery, section switch), for any form/field --
  nothing I-90-specific.
- **`backend/config.py`**: both `SYSTEM_INSTRUCTION` (legacy -- the deployed
  path) and `JIT_SYSTEM_INSTRUCTION` gain a CONSTRAINTS directive: when a
  field carries a Note / context-to-convey, briefly convey it in your own
  words WHILE asking (one short sentence, not a lecture); never ask a
  qualified question as if it were unqualified.
- **Tests**: `navigation-hint.test.ts` (hint carries instructions; no suffix
  when absent; options/required unaffected), a handshake help-preservation
  case in `schemaFormState.test.ts`, and two `test_ai_context.py` cases. The
  backend cases claim exactly what they prove (fresh-eyes round-1 fix): the
  legacy one asserts WIRING (help.instructions -> Note:) plus the template
  directive; the JIT one pins the template constant ONLY -- JIT's fine-print
  wiring is the frontend hint (navigation-hint.test.ts), and rendering help
  inside {next_field_schema} stays bd jnjj.31's scope.

Fresh-eyes assess: round 1 GAPS-FOUND(2) -- both adopted (weak/vacuous
directive-test framing -> docstrings/names now state the wiring-vs-template
split; confounded live run -> unconfounded control run added, journal
reframed to foreground the unit-test mechanism proof). Also adopted its
low-confidence JSDoc-drift note on formatNextFieldHint. Round 2: NO-GAPS
expected gate before PR (recorded in the PR body scorecard).

## Live verification (exit criterion 2)

The MECHANISM proof is the unit tests (handshake preserves `help`; the SI
renders the Note; the hint carries the instructions; the templates carry the
convey directive) -- the live runs corroborate that the model actually acts
on it. Voice-harness setup (Chrome MCP + local backend on Vertex + vite 5174,
per `tests/e2e/voice-harness/RUNBOOK.md`), capturing the `transcript` WS
messages. Two runs on the deployed (legacy, non-DTI) path:

**Run 1 -- the reported regression case** (pre-filled the 5 fields before
`p1_checkbox4` via the real manual-edit UI path, clicked I Agree):

> "Hello! Welcome to Section 1 Part 1.1 of the Form I-90. Could you please
> tell me if your name has legally changed **since your Permanent Resident
> Card was issued**? You can respond with 'Yes,' 'No,' or 'Not Applicable.'"

The green-card qualifier and the fine print's option guidance (incl. the N/A
meaning) are conveyed while asking. Attribution caveat: this field's
`spoken_name` also carries the qualifier, so run 1 alone cannot isolate the
fix from the spoken_name.

**Run 2 -- UNCONFOUNDED control** (fresh state; the AI asked for
`p1_line1_aliennumber`, whose `spoken_name` is just "alien registration
number 1" -- none of the fine print is in its name):

> "Welcome! We're starting on Section 1: Part 1.1 - Information About You:
> Numbers and Names. **Your Alien Registration Number (A-Number) is a 7 to
> 9-digit number found on your green card or other immigration documents and
> begins with an 'A'.** What is your A-Number?"

The bolded explanation is a near-verbatim rendition of that field's
`help.instructions` ("...is a 7-9 digit number found on your green card or
other immigration documents. It begins with an 'A'.") -- content that exists
ONLY in the fine print. The model conveyed it unprompted while asking, which
is precisely the behavior the bead reported missing.

## Gotchas hit (harness/session mechanics, not the fix)

- AI Studio (`VERTEXAI=false`) prepayment credits are DEPLETED -- harness
  backend must run `VERTEXAI=true GOOGLE_CLOUD_PROJECT=polyglot-demo-aa709`
  (gcloud ADC works locally).
- Local vite does not serve `/form-kits/*`; the SPA's schema fetch 404s into
  the index.html ("Unexpected token '<'"). Fix: junction
  `frontend/public/form-kits -> <worktree>/form-kits` (gitignored; main's
  checkout already has one).
- The PreToolUse hook path is cwd-relative; a Bash call ending inside
  `frontend/` bricked all subsequent Bash calls. Filed as its own bead
  (P2). Recovery via a temporary shim; the `rm -rf frontend/scripts` cleanup
  deleted tracked files (restored with `git checkout`) -- check directory
  contents before recursive deletes.

## Doc freshness

- **Bumped:** `docs/standards/si-reduction.md` (the SI-shape contract; both
  templates gained the convey-the-note CONSTRAINTS line, and the
  `{next_field_hint}` content now carries `help.instructions`).
- **Reviewed and left:** the other freshness-flagged docs tracking
  `backend/config.py` (config-deployment, context-compression, tool-call-flow,
  logging-and-cost, risk-rating, validation-delegation, voice-and-vad) -- this
  branch's config.py change is two SI CONSTRAINTS lines; none of those docs'
  subject matter (env vars, compression, tool sequence, cost invariant, VAD)
  is affected. Their staleness predates this branch (other tracked files).

## Related open work

- bd `polyglot-pdf-jnjj.31` (P3): the JIT `next_field_schema` block still
  drops help.instructions -- partially mitigated now that the JIT hint
  carries it; the schema-block render remains that bead's scope.
