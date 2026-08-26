---
date: 2026-08-25
bead: polyglot-pdf-apkdl
title: "feat(voice): the spell-back tool worked on the demo and not locally, because the cutover never happened"
tags: [voice-ai, config, spellback]
---

## Trigger

The maintainer's first report of the day: on the W-7, the model did not spell
their first name back with the `name_spellback` tool -- it just said *"You said
'John', is that right?"*

Later the same day they added the detail that turned the whole diagnosis around:
**the DEPLOYED demo uses the tool correctly; only local does not.** They asked
me to find the regression.

## There was no regression

`SPELLBACK_TOOL_ENABLED` defaults to `false`. `deploy-demo.sh` sets it to `true`
(maintainer go-ahead 2026-08-10). Nothing local sets it -- not
`scripts/dev-local.ps1`, not the `run-local` skill, not the `voice-harness`
skill, not `backend/.env.DEV`. Verified by enumerating every reference to the
flag in the repo.

With the flag off, two things are missing at once:

- `_build_tool_declarations` never appends `SPELLBACK_TOOL_DECLARATION`, so the
  tool is not in the declared set;
- `ai_context` never appends `DTI_SPELLBACK_SI_ADDENDUM`, so nothing tells the
  model to prefer it.

The model cannot call a tool it was never given, so it falls back to speaking
the spelling itself -- which is precisely the bd `polyglot-pdf-0rpu`
sticky-first-spelling defect the tool exists to remove.

The tool "landed dark" deliberately (bd `polyglot-pdf-22h1f`), and the config
comment said a cutover PR would move it into the main declarations list. **That
cutover never happened.** Local has been in the pre-cutover state ever since,
while the demo ran ahead of it from 2026-08-10.

## What shipped

The default flips to ON. Roughly two weeks of demo traffic is the bake the dark
launch was for.

Two decisions that go against the original plan, both deliberate:

**The env var is kept, not removed.** It is now the rollback.

**`SPELLBACK_TOOL_DECLARATION` stays OUT of `TOOL_DECLARATIONS`,** contrary to
the old comment's stated plan. Appending it under the flag is *what makes the
flag work*: a constant merged into `TOOL_DECLARATIONS` could not be removed by
setting the env var false, so merging it would have silently converted a
rollback switch into a no-op. `TOOL_DECLARATIONS` remains the unconditional
contract the static tests pin; this is its one conditional member.

One flag still drives all four gates -- the declaration, the SI addendum, the
dispatch guard, and the `/api/tts/spellback` 503 -- so flipping it moves them
together.

`deploy-demo.sh` keeps `SPELLBACK_TOOL_ENABLED=true` even though it is now
redundant. A deploy script should state the configuration it deploys rather than
inherit it, so a later default change cannot alter the demo without touching
that file.

## The tests were the actual hole

**Nothing pinned the default.** Every existing spell-back test assigns
`settings.SPELLBACK_TOOL_ENABLED` before asserting, so all 45 of them passed
*identically* with the default off and the default on. The full suite was green
the entire time local was broken.

That is how a feature can be live on the demo and dark locally for two weeks
without a single failing test. The flag-on and flag-off behaviors were both
well covered; the *shipped default* was covered by nothing.

Four new tests pin it: the flag value, the tool actually reaching the declared
set through the real builder, the SI addendum riding the same default, and the
env var still disabling it. Mutation-verified -- flipping the default back
reddens three of the four independently.

One of them was initially written against a function name I guessed at
(`build_system_instruction_for_form`), which does not exist; it *skipped* rather
than failed, and the file reported "44 passed, 1 skipped". A skipped test looks
close enough to a passing one to miss. The real entry point is
`build_form_context`, which reads settings via `get_settings()` rather than an
argument.

## Where this leaves the original bead

`polyglot-pdf-apkdl` was filed this morning as a model-COMPLIANCE problem, with
exit criteria demanding a measured rate over 20+ trials ("18/20 times the model
invoked spellback..."). **That premise was wrong.** There was nothing to
measure: the tool was absent from the build under test. The bead's criteria are
replaced by this cutover.

The general lesson is worth more than the fix: before measuring whether a model
COMPLIES with something, verify the something is actually present in the build
you are measuring. A compliance rate against a feature that was never declared
would have read as damning evidence about the model.

## Verification

- Full backend suite: 2594 passed, 2 skipped.
- Verified end to end that a plain local session -- no env vars at all --
  declares `name_spellback` AND carries the spell-back addendum.
- Docs corrected in five places that said "default off"
  (`config-deployment.md`, `tool-call-flow.md`, `voice-ai.md`,
  `technical_guide.md` x2).
