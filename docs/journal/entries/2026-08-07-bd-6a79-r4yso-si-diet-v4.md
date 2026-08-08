---
date: 2026-08-07
beads: [polyglot-pdf-6a79, polyglot-pdf-r4yso]
tags: [voice, si, cost, testing, prompt-engineering, validation]
surfaces:
  - backend/config.py
  - backend/tests/unit/test_dti_si_voice_rules.py
  - backend/tests/unit/test_spoken_name_delivery.py
  - backend/tests/unit/test_tool_contract_static.py
  - docs/standards/si-reduction.md
  - tests/e2e/voice-harness/
---

# The SI diet that kept shrinking, then grew back, then shrank properly

`DTI_SYSTEM_INSTRUCTION` is now 11,865 chars (~2,966 tok), down from 17,555
(~4,388) -- **32.4%**, ~1,422 tokens off EVERY turn on the dominant cost line.

The handoff draft claimed 46.6%. It got there by deleting rules that turned out
to be load-bearing, and the gap between those two numbers is the whole story.

## What the draft had deleted

Each of these was found by an adversarial review or a live run, not by reading:

- **`UNMISTAKABLY`** -- vendor-documented phrasing (`docs/genai_docs/live-api-best-practices.md`),
  endpoint-verified in this repo. The other three channels (both initiating
  templates, every per-field injection) repeat it per turn; the draft made the
  SI the only one that dropped it.
- **The bd-87a9 mid-session language switch**, reintroduced verbatim -- a licence
  to honour a switch the app cannot service.
- **ADDRESS CONSISTENCY**, deleted on a supersession claim that
  `validator_service.py`'s own docstring contradicts ("the in-SI prose STAYS as
  the primary check").

## The defect that nearly shipped

The W-7 `reason` option (a) carries "(you must also check and complete box h)" --
a binding obligation. The candidate DROPPED it in a live Russian session. The
shipped SI spoke it 2/2.

It was not a missing rule. Both SIs carry both relevant rules. They *collide*:

- "Read each option VERBATIM AND IN ITS ENTIRETY ... every qualifier,
  parenthetical, and condition"
- "never read a label's printed-form NAVIGATION aloud -- item/line/**box numbers**"

The dropped clause is a **parenthetical naming a box** that is also an
obligation. The model resolved the ambiguity differently on different runs. The
shipped SI carries the same two rules but spends more words holding them apart,
and the compression had cut exactly that connective tissue.

Adding "read VERBATIM AND IN ITS ENTIRETY" made it *worse* (1/2) by sharpening
the collision. What fixed it (3/3) was making the test FUNCTIONAL: ask what a
clause DOES -- obligation/condition -> speak; pointer with no obligation -> omit;
cannot tell -> speak.

**A substring harness cannot see this.** Every rule was present and all 163
assertions passed while the behaviour was broken.

## Then the fixes themselves became the problem

Six rounds of patching -- add a rule, leave the superseded text -- pushed the cut
from 32% down to **19.3%**. The options block ended up saying "do not shorten"
in four phrasings; the names block warned against guessing a spelling three
times. That is precisely how the original SI reached 4,388 tokens.

The maintainer called it: *"the fixes have added redundancy, which was exactly
how the previous SI grew so large... targeted changes with blinders on, rather
than looking at the SI holistically."*

Rewriting the whole document from scratch -- same rules, no leftovers -- went
19.3% -> **32.4%**. Recorded as scar tissue in
[`docs/standards/si-reduction.md`](../../standards/si-reduction.md).

One deduplication was deliberately REVERSED: WORKFLOW step 1 restates the option
carve-outs, and `test_dti_si_forbids_one_by_one_yes_no_option_walk` exists
because an unqualified step-1 imperative contradicted the two-option rule on
every confirm-path turn. That repetition IS a fix.

## Validation

Pre-registered plan, decision rule fixed before any data (si-slim-handoff/):

- **8 runs x 15 steps, interleaved.** Candidate 60/60 fill+confirm, **0
  misfills**; shipped SI 60/60 with **4** (`JOSIE`, `JOSE` twice for a
  `J-O-S-E` fixture, `123 MAIN ST`). The driver called all 8 PASS -- it checks
  filled+confirmed, never whether the value is RIGHT.
- **Russian session** (`ru-RU`, so Cyrillic reaches the model): no language
  slippage, plain model-authored Russian, and the candidate asks for the
  latinized *document* spelling where the shipped SI asks a bare "how do you
  spell it?".
- **Seven instrument defects** were caught and fixed before they produced
  findings -- a phantom transcript hook, a case-mismatch, a mis-scoped session
  lookup, a probe that aborted before firing and reported the PASS condition. A
  measured "candidate language-lock regression" reproduced identically on the
  shipped SI and was the probe's own broken VAD framing.

## Also

- **Spell-back removed** (maintainer directive): spelling aloud desyncs the
  native-audio model's audio/text layers; a TTS tool will own it and merge its
  instructions back. Accepted window with no letter read-back -- not in
  production use.
- **~35 test assertions re-pointed**, each triaged first (rule survives in new
  words / deliberately removed / both-SI assertion where only the DTI half
  changed). None weakened to silence a failure.
- **bd polyglot-pdf-r4yso**: the suite now pins RULES, not wording or block
  layout, with a docstring stating it cannot detect contradictions.
  Mutation-verified on two differently-shaped assertions.

## Doc freshness

`check_doc_freshness.py` reports several tier-2 docs stale against
`backend/config.py`. Reviewed: all are stale because config.py's TIMESTAMP moved
(this change + PR #556 earlier today), not because their content is wrong.
`si-reduction.md` is the one doc this change actually alters, and it is updated
and bumped. No other doc's claims changed.

## Filed, not fixed

- **polyglot-pdf-020a4** (P1): `/ws/fill` builds three Vertex clients
  synchronously per connection -- ~9s of blocked event loop off-GCP, invisible on
  Cloud Run. Blocked local voice work across three sessions and was twice
  misdiagnosed as a websockets-vs-wsproto transport bug.
- **polyglot-pdf-0m7df** (P3): the model asks for the latin spelling and then
  answers its own question in the same turn. Mitigated by spell-back
  confirmation + human review of a draft.
