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

Each of the three layers is mutation-verified SEPARATELY: reverting the rubric
reddens 6 cases, the full declaration (description + query param together) 4,
the SI relay sentence 1 -- no mutation touches another layer's cases. The
declaration figure is the fresh-eyes reviewer's measurement; my own note had
said 1, which was the count for the single half-line mutation I ran rather
than for reverting the layer, and the reviewer reproduced the real number
twice. Full both-roots suite green at 3074 passed.

Opus cross-surface round 1 found the one place the fix only half-reached its
own goal, and it was fixed inline rather than deferred. Kind (C) said "you
hold the form's official instructions verbatim -- QUOTE" without saying WHICH
part of the catalog is official. Measured against the SHIPPED kits that
premise is false on two of three: the i-90 has 0 chars of booklet_text and
0/132 help.details -- the only text the secretary holds is 132 authored
`help.instructions` PARAPHRASES -- and the f1040 has no text at all; only the
W-7 (81,200 chars) satisfies it. So the secretary would have quoted OUR
wording with government framing to an immigration applicant: the exact
misattribution this bead exists to prevent, reintroduced by its own fix. The
catalog renderer already distinguishes the two (verbatim text renders under
"OFFICIAL FORM INSTRUCTIONS (verbatim reference)" or a field's `details:`
block; a paraphrase renders under a bare `help:`), so kind (C) now keys on
those markings, says the help line is NOT official and may only be spoken in
the secretary's own voice, and says to state the official instructions are
unavailable rather than dress a paraphrase as one. Three tests pin it,
including one that DERIVES the marker from the renderer so the rubric and the
catalog cannot drift apart, and one asserting the i-90 really is the
no-official-text case. The reviewer filed it as bd polyglot-pdf-5nhxl
(provenance labelling in the catalog itself, a surface this diff does not
touch); that bead stays open for the broader labelling work.

Opus round 2 then caught that the provenance fix ITSELF enumerated the wrong
set: it named two official markers, but `_render_form_reference` emits THREE
labelled blocks, and the omitted one (`=== FORM-LEVEL GUIDANCE ===`, from
`form_metadata.details`) is 9,487 chars of VERBATIM IRS prose on the W-7 --
the Supporting Documentation / When To Apply / Who Can Sign sections, i.e. the
deepest questions users actually ask. A closed two-item allowlist told the
secretary that real IRS text in its own context was not the government's
wording, and its fallback would then have claimed the instructions were
unavailable. Only 3 of 12 of those paragraphs appear byte-identically in
booklet_text, so it is not recoverable from the marked block either.

The mechanism mattered more than the instance, and it is scar #7 again: my
derived-marker test rendered a BOOKLET-ONLY schema, so the form-level branch
never executed and its heading was never compared -- the guard was shaped so a
third block could not fail it. Deriving one member of a set is not deriving
the set. The test now renders with EVERY official-text key populated, regexes
out every `=== HEADING ===` the renderer returns, and requires the rubric to
classify each one, so a FOURTH block fails here instead of landing silently
outside the allowlist. Mutation-verified: removing any single marker from the
rubric reddens it.

The same review confirmed the escalated `resolved` question is a NON-issue,
and worth recording so it is not re-litigated: a kind-(C) decline correctly
returns `resolved: true`. The user path voices the decline prose (which the
new SI relay rule is built to consume), and the internal navigation path
hard-codes a kind-(B) query so a (C) decline cannot reach it. Setting
`resolved: false` would be the bug -- it routes into the pushback branch that
appends "ask the user to describe the field more specifically", nonsense for
an eligibility refusal.

## DIRECTION CHANGE mid-PR: hedge-and-defer, not decline (maintainer 2026-08-12)

After the reviews cleared, the maintainer walked a real W-7 exchange -- "what
documents do I need?" then "would a copy of my Italian passport work?" -- and
rejected the DECLINE shape this bead originally shipped. It is defensible
legally and poor as a product: the user asked a real question and got a
redirect, leaving them to extract the answer from quoted prose. If they
extract it wrongly the refusal bought nothing.

The directive: ALWAYS hedge and defer, but ANSWER. The shape is the
maintainer's own example -- "According to the IRS documentation for this form,
a passport can work for both identity and connection to the foreign country.
It also says it must be original or a certified copy. However, please consult
with your legal professional regarding your specific situation."

So kind (C) now answers in THREE mandatory parts: (1) attribute and state what
the official text says, (2) FLAG EVERY CONDITION that text puts on it, (3)
defer the applicant's own situation to the reviewing professional. Part 2 is
what makes part 1 safe to give, and the rubric says so: a favorable-sounding
half of a rule is worse than no answer, because the applicant acts on it. The
worked case is exactly why -- "a passport establishes identity and foreign
status" is true and, alone, dangerous: the same text requires an ORIGINAL or
an agency-certified copy, so a user acting on the favorable half mails a
photocopy and is rejected. The uncrossable line is now drawn by example
rather than abstraction: "a passport can work, and it must be certified" is
the text speaking; "yes, your passport works" is the model deciding their
case.

The live SI gained an UNCONDITIONAL hedge rule (always defer on anything
touching eligibility, requirements, or what a rule means for THIS user --
"even when the answer looks obvious, even if they press, even if you are
sure") plus a faithful-relay rule naming the two ways a helpful voice model
would otherwise leak: trimming the conditions for a cleaner yes, or appending
its own verdict ("so yours should be fine").

WHO the hedge defers to changed too, and it is a product invariant worth
recording: NOT "your legal professional" but the firm or professional
REVIEWING THE FORM. The maintainer states this app is never used for
self-filing -- it is used by a legal entity to pre-prepare first drafts, and
customer contracts require staff review before filing. Deferring to a lawyer
the applicant may not have would misdescribe the product; the shipped
DisclaimerModal already says "have a qualified professional check your final
form".

REGISTER CORRECTION (Opus round 4, and the one thing in this bead I got wrong
on my own initiative): my first wording had the SI assert "Every form drafted
here IS reviewed by a qualified human before filing" -- a categorical
guarantee. The disclaimer the user actually clicks "I Agree" to, and which is
read aloud verbatim, says "We strongly ADVISE you to have a qualified
professional check your final form." That is a RECOMMENDATION, and its whole
force is that review might not happen. My journal even claimed the SI
"matches language the user has already agreed to" -- it did not; it upgraded
an advisory into a promise, in the one place the two speak to the same person,
and it is exactly the premise an applicant would lean on when accepting a
hedged answer about their own eligibility. The mandatory-review arrangement is
real, but it is a CONTRACT WITH THE FIRM, not a fact the applicant was told.
Corrected to "A qualified human is expected to review this form before it is
filed", plus an explicit "do not promise the user that a review WILL happen",
and pinned (including a negative assertion on the guarantee phrasing).

Both new clauses are mutation-verified: weakening "FLAG EVERY CONDITION", or
making the always-hedge rule conditional ("hedge when unsure"), each reddens
its own test.

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
- **The same defect can hide one sentence above the fix.** Fresh-eyes found
  that adding kind (C) left the rubric's own intro saying "one of two kinds"
  above three -- a model told its framing does not cover what follows, which
  is the identical under-constrained state this bead exists to remove, just
  relocated. The pin derives the expected count FROM the enumeration, so
  adding a kind (D) without updating the intro fails instead of shipping;
  mutation-verified in both directions: reverting the count alone reddens
  exactly that one test, and dropping kind (C)'s header while leaving the
  count at "three" reddens 2 (the count pin plus the official-text-lookup
  content test). Both figures are the reviewer's independent re-measurement --
  I had said 3 for the second, which was wrong.
- **Check that an instruction's PREMISE holds on the real data.** Kind (C)
  told the model it holds official text; on two of three shipped kits it does
  not, and the catalog gave it no way to tell ours from the government's. An
  instruction can be perfectly worded and still false in production. Measure
  the premise against shipped content, not against the one kit you had in
  mind (the W-7).
- **A legally-safe answer and a useful answer are not opposites.** The first
  cut treated refusal as the safe default; the maintainer's shape is safer AND
  more useful, because the CONDITIONS reach the user instead of depending on
  them parsing quoted prose. When a boundary makes the product worse, check
  whether the boundary is drawn in the wrong place before accepting the cost.
- **Deriving ONE member of a set is not deriving the set.** The derived-marker
  test looked rigorous -- it called the real renderer instead of restating a
  string -- but it fed that renderer a single-key fixture, so only one branch
  ran. A guard that derives from production code can still be shaped so the
  regression it exists for cannot reach it. Populate every input that makes
  the producer emit a distinct case, then assert over what comes back.
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
