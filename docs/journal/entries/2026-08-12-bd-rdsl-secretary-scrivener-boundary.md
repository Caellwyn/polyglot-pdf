---
date: 2026-08-12
bead: polyglot-pdf-rdsl
title: "ask_secretary quotes official text and declines advice"
tags: [security, conventions, testing]
---

## Trigger

The one remaining place where product BEHAVIOR contradicted the stated legal
position. The disclaimer says the AI cannot give legal advice; our position is
that we are not the preparer. The `ask_secretary` tool declaration nonetheless
scoped use (3) as looking up official guidance "when the current field's
reference text does not clearly answer a REQUIREMENTS QUESTION", with the
literal example *"what documents does exception 3 require?"* -- an eligibility
question, answered generatively, to an immigration applicant. Where the two
conflict, a regulator reads the behavior.

## What shipped

The secretary stays -- it is genuinely useful and it really does hold the whole
official instructions booklet verbatim (`secretary_context` renders
`metadata.booklet_text` into the cacheable prefix), so quoting is feasible.
What changed is WHAT IT MAY RETURN, in three places. All three are needed;
each alone is defeatable.

1. **The secretary's own rubric** (`SECRETARY_SI`,
   `backend/adapters/text_ai_gemini.py`) -- where the answer is actually
   generated, and the real hole. It defined exactly TWO question kinds (value
   recall, field identification) while the tool advertised a THIRD, so the
   model was asked for something its instructions never scoped: the least
   constrained state available. It now defines kind (C) OFFICIAL-TEXT LOOKUP
   as quote-or-point ("do not rewrite it"), names the SCRIVENER/ADVISOR line
   as a legal boundary rather than a style preference, enumerates what it must
   not do (apply instructions to this applicant's facts; say which
   option/exception applies; say whether they qualify; state a requirement not
   written in the text it holds), and says to DECLINE the applicant-framed
   shapes ("what should I put", "do I qualify", "applies to me") while quoting
   whatever official text bears on the topic and redirecting to the reviewing
   human. Two subtler bars: declining stands even when the answer looks obvious
   ("an obvious-looking eligibility call is still a legal judgment about a real
   person, and being confident is not the same as being permitted"), and with
   NO official text held it must say so rather than reason from training data
   ("your own knowledge of immigration law is not a source here").
2. **The tool declaration** (`backend/config.py`) -- use (3) is now "get the
   OFFICIAL INSTRUCTION TEXT quoted back", example reframed to "what do the
   instructions say about exception 3?", with the caller told the secretary
   declines advice-shaped asks so a refusal reads as expected behavior rather
   than a tool malfunction. The `query` param description carried only two uses
   and has drifted from the description before, so it was updated in the same
   pass.
3. **The live model's SI** (`backend/config.py`) -- closes the bypass that
   would defeat the other two: a well-behaved secretary declines, and a helpful
   voice model then answers from its own knowledge. The SI now says to relay a
   refusal ("quote whatever it quoted and say the choice is theirs to make with
   the person reviewing their form. Do not answer it yourself instead").

ENUMERATED THE SET first (scar tissue #7): grepped for every site describing
the secretary's purpose. `ai_context.py:373` is about value recall only and
correctly needed no change; nothing else describes the guidance use. The
pre-existing SI rule "INFORMATION, NEVER ADVICE" was already correct and is now
pinned so an SI diet cannot drop it silently.

**Tests** (`backend/tests/unit/test_secretary_scrivener_boundary.py`, 14 cases)
are ALLOWLIST-style per the bead and the repo memory
(pin-message-tests-with-allowlists): they assert the sanctioned behavior is
STATED -- quote, decline, redirect -- rather than banning words. A banned-word
test is one synonym from defeat and would also fail on prose that names the
prohibition in order to forbid it. The one negative assertion is narrow and
justified in-file: the specific advice-shaped example that shipped.

Each of the three layers is mutation-verified SEPARATELY (reverting the rubric
reddens 6, the declaration 1, the SI relay sentence 1 -- no mutation touches
another layer's cases). Full both-roots suite green at 3074 passed.

## Lessons

- **Mutation-testing the test found a real weakness, not just a checkbox.** The
  first negative assertion matched a raw substring of the declaration. The
  declaration is built from CONCATENATED string literals, so the sanctioned
  phrase straddles a line break -- and restoring HALF the old advice example
  left the assertion green, because the surviving half still matched. Fixed by
  normalizing whitespace and asserting the SUBSTANCE (any framing that asks
  what the form REQUIRES) rather than one phrasing. Generalizes: when asserting
  against text assembled from adjacent literals, normalize before matching, or
  the line break is an invisible hole.
- **A mutation that fails to APPLY produces a false green.** Two attempts here
  silently matched nothing and the suite passed, which reads exactly like "the
  test does not catch this". Assert the file actually changed before trusting
  the result -- the repo rule exists because this is easy to miss twice in one
  sitting.
- **A tool declaration advertising a capability the answering model was never
  scoped for is the dangerous shape.** The fix was not only narrowing what may
  be asked, but DEFINING the third use on the answering side so it is not left
  to inference.

## Doc freshness

No tier-1/2 doc describes ask_secretary's answer scope; the boundary lives in
the rubric, the declaration, and the SI, all in code and now test-pinned.
`docs/standards/validation-delegation.md` is flagged STALE by the freshness
checker because it Tracks: `text_ai_gemini.py`, which this diff edits -- but
that is a timestamp artifact, not drift. Every claim it makes about the
secretary is about the PORT: the `ask(query, context) -> (answer, sources,
resolved)` signature, the `sources` shape, `resolved` as the semantic-pushback
signal, and the fail-open `("", [], True)`. This change altered the prompt's
CONTENT, not the contract, so all of those remain true and the doc was
reviewed-and-left rather than bumped (checked line by line, not assumed).

## Files touched

- backend/adapters/text_ai_gemini.py -- SECRETARY_SI: kind (C) + the scrivener bar
- backend/config.py -- the ask_secretary declaration, its query param, and the SI relay rule
- backend/tests/unit/test_secretary_scrivener_boundary.py (new, 14 cases)
- docs/journal/entries/2026-08-12-bd-rdsl-secretary-scrivener-boundary.md
