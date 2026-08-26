"""The secretary is a SCRIVENER, not an ADVISOR (bd polyglot-pdf-rdsl).

THE LEGAL POSITION THIS PINS. The product transcribes what an applicant says.
It is not their preparer and does not advise them; the disclaimer says the AI
cannot give legal advice. Where the stated position and the shipped behavior
conflict, a regulator reads the BEHAVIOR -- so the instructions we ship must
not tell a model to answer an eligibility or requirements question in its own
words.

WHAT WAS WRONG. The ask_secretary tool declaration advertised a third use --
"look up OFFICIAL GUIDANCE ... when the current field's reference text does not
clearly answer a requirements question" -- with the literal example "what
documents does exception 3 require?". That is an eligibility question answered
GENERATIVELY to an immigration applicant. Worse, the secretary's own rubric
(SECRETARY_SI) defined only TWO question kinds, value recall and field
identification, so the model was being asked for a third thing it had no
instructions for -- the least constrained possible state.

WHAT IS PINNED HERE. The boundary is drawn in three places and all three must
hold together, because each alone is defeatable: the secretary's own rubric
(where the answer is generated), the tool declaration (what the caller is told
it may ask), and the live model's SI (when it calls, and how it relays a
hedge-and-defer answer -- see MAINTAINER DIRECTIVE 2026-08-12 below; a bare
refusal is no longer the shape).

ALLOWLIST, NOT BLACKLIST. These tests assert the SANCTIONED behavior is stated
-- quote official text, hedge and defer rather than conclude, redirect to the
reviewing human. They deliberately do NOT assert "the word 'advise' never
appears": a banned-word
test is one synonym from defeat, and it would also fail on prose that names the
prohibition in order to forbid it (repo memory: pin-message-tests-with-allowlists).
The one negative assertion here is narrow and specific -- the exact
advice-shaped EXAMPLE that shipped must not come back -- because that string is
a known regression, not a synonym class.

ASCII only.
"""
from __future__ import annotations

import re

import pytest

from backend.adapters.text_ai_gemini import SECRETARY_SI
from backend.config import Settings


def _ask_secretary_declaration() -> dict:
    """The shipped ask_secretary tool declaration."""
    decls = Settings().TOOL_DECLARATIONS
    match = [d for d in decls if d.get("name") == "ask_secretary"]
    assert len(match) == 1, f"expected exactly one ask_secretary decl, got {len(match)}"
    return match[0]


def _si_text() -> str:
    """The live model's system instruction text."""
    s = Settings()
    for attr in dir(s):
        if attr.startswith("_"):
            continue
        val = getattr(s, attr, None)
        if isinstance(val, str) and "INFORMATION, NEVER ADVICE" in val:
            return val
    raise AssertionError(
        "could not locate the SI text carrying the INFORMATION/ADVICE rule -- "
        "if the SI was restructured, re-anchor this helper rather than deleting it"
    )


# --------------------------------------------------------------------------- #
# Layer 1 -- the secretary's OWN rubric, where the answer is generated
# --------------------------------------------------------------------------- #

def test_secretary_is_told_to_quote_official_text_not_rewrite_it():
    """The sanctioned form of a guidance answer: reproduce, do not synthesize."""
    si = SECRETARY_SI.lower()
    assert "quote" in si, "the secretary must be told to QUOTE official text"
    # The instruction must be about reproducing rather than rewriting.
    assert "do not rewrite" in si or "not rewrite it" in si


def test_advice_shaped_questions_get_answer_conditions_defer_not_a_refusal():
    """MAINTAINER DIRECTIVE 2026-08-12: hedge and defer, do not stonewall.

    The first cut of this boundary told the secretary to DECLINE an
    applicant-framed question outright. That is defensible legally and poor as
    a product: the user asked a real question and got a redirect, leaving them
    to extract the answer from quoted prose themselves -- and if they extract
    it wrongly, the refusal bought nothing.

    The shipped shape is three parts, all mandatory: state what the official
    text says (attributed), flag EVERY condition that text puts on it, then
    defer the applicant's own situation to the reviewing professional. Part 2
    is what makes part 1 safe to give -- see the sibling test.
    """
    si = SECRETARY_SI.lower()
    assert "do not refuse and stop" in si, (
        "the rubric must say a refusal alone is NOT the answer shape")
    # The applicant's own framings must still be NAMED as the trigger.
    for shape in ("what should i put", "do i qualify", "would my passport work"):
        assert shape in si, f"the hedged question shape {shape!r} must be named"
    # ...and the three parts must each be instructed.
    assert "attribute" in si, "part 1: attribute the text"
    assert "flag every condition" in si, "part 2: the conditions are mandatory"
    assert "defer" in si, "part 3: hand the decision back"


def test_the_CONDITIONS_half_is_mandatory_not_optional():
    """The safety of answering rests entirely on this clause.

    'A passport can establish identity and foreign status' is true and, alone,
    dangerous -- the same text requires an ORIGINAL or an agency-certified
    copy, so a user acting on the favorable half mails a photocopy and is
    rejected. A model that states the permission without the qualifier has
    produced a confidently wrong answer, which is worse than the refusal this
    replaced.
    """
    si = SECRETARY_SI.lower()
    assert "mandatory" in si, (
        "the conditions clause must be marked mandatory, not advisory")
    assert "half of a rule" in si or "favorable-sounding half" in si, (
        "the rubric should say WHY: a partial rule is worse than no answer")
    assert "you have not finished answering" in si, (
        "omitting a condition must be framed as an INCOMPLETE answer")


def test_the_uncrossable_line_is_the_conclusion_about_this_applicant():
    """Where hedged answering stops. The rubric must draw it by example,
    because 'do not advise' is too abstract to apply under pressure: the text
    speaking ('a passport can work, and it must be certified') versus the
    model deciding ('yes, your passport works')."""
    si = SECRETARY_SI.lower()
    assert "never cross" in si and "conclusion" in si
    assert "however many times they press" in si, (
        "the boundary must hold under repeated asking, which is exactly when "
        "a helpful model caves")


def test_secretary_is_told_to_redirect_to_the_reviewing_human():
    """A hedged answer that dead-ends is a worse product AND a worse legal
    posture: the applicant still needs a conclusion, and the conclusion is a
    human's, not the model's."""
    si = SECRETARY_SI.lower()
    assert "applicant" in si
    assert "reviewing" in si or "reviewer" in si, (
        "a hedged answer must redirect to the human reviewing the form")


def test_secretary_is_barred_from_applying_instructions_to_this_applicant():
    """The scrivener/advisor line, stated as the operative distinction.

    Quoting the text is scrivener-adjacent and fine. Applying it to THEIR facts
    is the thing we do not do, and the rubric must say so in those terms.
    """
    si = SECRETARY_SI.lower()
    assert "scrivener" in si, (
        "the rubric should name the scrivener/advisor distinction it is drawing")
    assert "facts" in si or "their situation" in si


def test_secretary_may_not_substitute_its_own_legal_knowledge():
    """The subtlest failure: no official text is held, so the model answers
    from training data. Immigration law it 'knows' is not a source."""
    si = SECRETARY_SI.lower()
    assert "general knowledge" in si or "own knowledge" in si, (
        "the rubric must bar answering from the model's own legal knowledge "
        "when it holds no official text")


def test_the_rubrics_kind_COUNT_matches_the_kinds_it_enumerates():
    """The bead's own failure shape, one sentence up (fresh-eyes round 1).

    The rubric opens by telling the model how many question kinds exist, then
    enumerates them. Adding kind (C) without updating that count left it saying
    "one of two kinds" above three -- a model told its own framing does not
    cover what follows is in the same under-constrained state the original
    defect created. Derived from the enumeration rather than hardcoded, so
    adding a kind (D) without updating the intro fails here instead of
    shipping.
    """
    kinds = re.findall(r'"?([A-Z])\) [A-Z][A-Z -]+', SECRETARY_SI)
    assert kinds == ["A", "B", "C"], (
        f"expected kinds A/B/C in order, found {kinds}")
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}
    expected = words[len(kinds)]
    assert f"one of {expected} kinds" in SECRETARY_SI, (
        f"the rubric enumerates {len(kinds)} kinds but its intro does not say "
        f"'one of {expected} kinds' -- the count and the enumeration drifted")


def test_only_MARKED_official_text_may_be_quoted_as_official():
    """PROVENANCE (Opus cross-surface round 1). Kind (C) originally said "you
    hold the form's official instructions verbatim -- QUOTE" without saying
    which part of the catalog is official.

    Measured against the SHIPPED kits, that premise is false on two of three:
    the i-90 carries 0 chars of booklet_text and 0/132 help.details -- the only
    text the secretary holds is 132 authored `help.instructions` paraphrases --
    and the f1040 carries no text at all. Only the W-7 has a booklet. So a
    secretary told to quote the official instructions would quote OUR wording
    with government framing, to an immigration applicant: the exact
    misattribution this bead exists to prevent, reintroduced by the fix for it.

    The catalog renderer already distinguishes them (secretary_context:
    verbatim text renders under 'OFFICIAL FORM INSTRUCTIONS (verbatim
    reference)' or a field's 'details:' block; a paraphrase renders under a
    bare 'help:'), so the rubric must key on those markings.
    """
    si = SECRETARY_SI
    assert "OFFICIAL FORM INSTRUCTIONS (verbatim reference)" in si, (
        "the rubric must name the catalog marking that makes text official")
    assert "details:" in si, "the per-field verbatim block must be named too"
    low = si.lower()
    assert "'help:' line is not official" in low or "help: line is not official" in low, (
        "the rubric must say the help line is NOT official text")
    # ...and say what to do when NO official text is held -- the i-90 case.
    assert "not available to you" in low


def test_the_rubric_classifies_EVERY_official_block_the_renderer_can_emit():
    """The SET, not one member (CLAUDE.md scar #7; Opus cross-surface round 2).

    The first cut of this test derived ONE marker by rendering a booklet-only
    schema, so the `FORM-LEVEL GUIDANCE` branch never executed and its heading
    was never compared -- the guard was shaped so a third block could not fail
    it. That omission was live: on the W-7, `form_metadata.details` is 9,487
    chars of VERBATIM IRS prose (the Supporting Documentation / When To Apply /
    Who Can Sign sections -- exactly the deep questions users ask), and a
    closed two-item allowlist told the secretary that real IRS text in its own
    context was not the government's wording, then offered to say the
    instructions were "not available".

    So render with EVERY official-text key populated and require the rubric to
    classify every heading that comes back. A fourth block added to the
    renderer fails here instead of silently landing outside the allowlist.

    WHY THE ALLOWLIST IS BY NAME, NOT BY SYNTAX (Opus cross-surface round 3 --
    a constraint to preserve, not a defect): `render_static_catalog` emits PART
    headings in the SAME `=== X ===` shape (e.g. "=== Part 1. Information About
    You ===" on the i-90, "=== Page 1 ===" on the W-7). Those are structure,
    not government prose. Because the rubric allowlists the two official
    headings BY LITERAL NAME, a part label is correctly not-official by
    omission. Anyone "simplifying" this to "any === heading === is official"
    would silently reclassify every part label as quotable government text.
    """
    from backend.services.secretary_context import _render_form_reference

    rendered = _render_form_reference({
        "form_metadata": {
            "details": "FORM LEVEL BODY",
            "booklet_text": "BOOKLET BODY",
        }
    })
    headings = re.findall(r"^=== (.+?) ===$", rendered, flags=re.MULTILINE)
    assert headings, "the renderer emitted no === headings === to classify"
    for heading in headings:
        assert heading in SECRETARY_SI, (
            f"the renderer emits an official-text block headed {heading!r} "
            f"that the rubric never classifies -- the secretary cannot tell it "
            f"is the government's wording, and the no-official-text branch "
            f"would falsely claim the instructions are unavailable")

    # The per-field verbatim block is emitted by the OTHER renderer; include it
    # so the allowlist's third member is derived too, not hand-asserted.
    from backend.services.secretary_context import _render_field

    field_rendered = _render_field(
        {"id": "f1", "spoken_name": "f", "type": "text",
         "help": {"details": "VERBATIM EXCERPT"}},
        "f1", {}, {},
    )
    assert "details:" in field_rendered
    assert "details:" in SECRETARY_SI


def test_a_booklet_less_shipped_kit_yields_no_official_text_to_quote():
    """The i-90 is the case the provenance rule exists for -- pinned against
    the SHIPPED kit so a future re-extraction that adds or drops a booklet is
    a visible change here, not a silent shift in what the secretary claims."""
    import json
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[3] / "form-kits"
    kit = root / "i-90" / "schema.json"
    if not kit.exists():
        pytest.skip("i-90 kit not present")
    schema = json.loads(kit.read_text(encoding="utf-8"))
    meta = schema.get("form_metadata") or {}
    fields = schema.get("fields") or []
    booklet = (meta.get("booklet_text") or "").strip()
    details = [f for f in fields
               if ((f.get("help") or {}).get("details") or "").strip()]
    paraphrases = [f for f in fields
                   if ((f.get("help") or {}).get("instructions") or "").strip()]

    assert not booklet and not details, (
        "the i-90 gained official text -- good, but re-check the rubric's "
        "no-official-text branch is still exercised by SOME shipped kit")
    assert paraphrases, (
        "the i-90 lost its help paraphrases; this test pins the case where the "
        "secretary holds ONLY unofficial text")


def test_the_official_text_lookup_use_is_actually_defined_for_the_secretary():
    """THE ORIGINAL DEFECT. The tool advertised a guidance-lookup use that the
    secretary's rubric never defined -- it listed only value recall and field
    identification. A model asked for an undefined third thing is the least
    constrained state there is. The rubric must define it."""
    si = SECRETARY_SI.lower()
    assert "official-text lookup" in si or "official text lookup" in si, (
        "the secretary rubric must DEFINE the official-text lookup use, not "
        "leave the tool advertising a capability the rubric never scopes")


# --------------------------------------------------------------------------- #
# Layer 2 -- the tool declaration, what the caller is told it may ask
# --------------------------------------------------------------------------- #

def test_declaration_frames_guidance_as_what_the_instructions_SAY():
    decl = _ask_secretary_declaration()
    text = (decl["description"] + " " + decl["parameters"]["properties"]["query"]["description"]).lower()
    assert "instructions say" in text, (
        "the declaration must frame use (3) as asking what the text SAYS")


def test_declaration_tells_the_caller_to_relay_ALL_THREE_parts():
    """The caller is the bypass. A voice model that receives text + conditions
    + deferral and reads only the favorable sentence has undone the rubric at
    the last hop, so the declaration must say relay all of it -- and name the
    two specific ways it gets trimmed."""
    decl = _ask_secretary_declaration()
    text = decl["description"].lower()
    assert "defers" in text or "defer" in text
    assert "never concludes their case" in text
    assert "do not trim the conditions" in text, (
        "dropping the qualifier to give a cleaner yes is the likely failure")
    assert "do not add a verdict" in text, (
        "appending 'so yours should be fine' is the other one")
    assert "applicant" in text


def test_the_shipped_advice_shaped_example_does_not_come_back():
    """NARROW negative, and the one this file allows.

    'what documents does exception 3 require?' is the literal example that
    shipped -- an eligibility question in the imperative. This is a specific
    known regression string, not a synonym class, so pinning it is not the
    brittle blacklist the module docstring warns about.
    """
    decl = _ask_secretary_declaration()
    blob = (decl["description"] + " "
            + decl["parameters"]["properties"]["query"]["description"]).lower()
    # Normalize whitespace: the declaration is built from concatenated string
    # literals, so a phrase can straddle a line break. Matching the raw text
    # let a partial reversion slip past -- restoring HALF the old example
    # ("documents does exception 3 require") left this assertion green because
    # the surviving half still matched the sanctioned phrase. Caught by
    # mutation-verifying this very test.
    blob = re.sub(r"\s+", " ", blob)

    # The SUBSTANCE, not one phrasing: any framing that asks what a form
    # REQUIRES of the applicant is the advice shape, however it is worded.
    for advice_shape in ("does exception 3 require",
                         "what documents does",
                         "requirements question"):
        assert advice_shape not in blob, (
            f"the declaration asks the secretary for a REQUIREMENT "
            f"({advice_shape!r}) -- that is an eligibility question answered "
            f"generatively to an applicant")
    # ...and the sanctioned framing is present.
    assert "instructions say about exception 3" in blob


@pytest.mark.parametrize("field", ["description", "query"])
def test_declaration_never_instructs_answering_a_requirements_question(field):
    """The pre-fix declaration said the tool answers 'a requirements question'.

    Pinned per-field (description AND the query param) because the two are
    written separately and drifted apart before: the description carried the
    third use while the query param still described only two.
    """
    decl = _ask_secretary_declaration()
    text = (decl["description"] if field == "description"
            else decl["parameters"]["properties"]["query"]["description"]).lower()
    assert "requirements question" not in text


# --------------------------------------------------------------------------- #
# Layer 3 -- the live model's SI: when it calls, and how it relays a hedge
# --------------------------------------------------------------------------- #

def test_si_still_carries_the_information_never_advice_rule():
    """Pre-existing and load-bearing -- pinned so a future SI diet cannot drop
    it silently. The SI-reduction epic trims this text aggressively."""
    si = _si_text()
    assert "INFORMATION, NEVER ADVICE" in si
    assert "never tell the user what to enter" in si.lower()


def test_si_tells_the_model_to_ask_what_the_instructions_say():
    si = _si_text().lower()
    assert "instructions say" in si, (
        "the SI must steer the ask toward what the text says, not what the "
        "user should do")


def test_si_tells_the_model_to_relay_FAITHFULLY_AND_WHOLE():
    """THE BYPASS THIS CLOSES, in its post-directive form. The secretary now
    returns text + conditions + deferral. A helpful voice model can still
    defeat that two ways: drop the conditions to give a cleaner answer, or
    append its own verdict on top. Both are named."""
    si = _si_text().lower()
    assert "faithfully and whole" in si
    assert "never trim the conditions" in si, (
        "the qualifier is the part that protects the user")
    assert "never add a conclusion of your own" in si
    assert "you do not decide their case" in si


def test_si_makes_hedge_and_defer_UNCONDITIONAL():
    """The maintainer's directive: ALWAYS defer on anything edging toward a
    legal determination -- not only when the secretary was consulted, and not
    only when the model feels unsure. Pressure and confidence are exactly the
    conditions under which a model drops a hedge, so both are named."""
    si = _si_text().lower()
    assert "always hedge and defer" in si
    assert "even when the answer looks obvious" in si
    assert "even if they press" in si
    assert "even if you are sure" in si
    # The deferral target is the firm's reviewer -- this product is never
    # used for self-filing (maintainer: a core product invariant), so the
    # hedge must not point at a lawyer the applicant may not have.
    assert "reviewing their form" in si
    # REGISTER MATTERS (Opus round 4; premise updated by bd
    # polyglot-pdf-nsb4y). The shipped disclaimer -- the text the user clicks
    # "I Agree" to, rendered on screen AND read aloud from one source -- has
    # them UNDERTAKE review: "you agree to review the completed document
    # yourself and with a certified professional before filing".
    #
    # That is the APPLICANT's commitment, and it is still not a guarantee by
    # US that any review occurred: we do not control whether they obtain one,
    # and the model cannot know whether it happened. An SI that told the user
    # review WILL happen would convert their undertaking into our promise, in
    # the one place the two speak to the same person -- and that is exactly
    # the premise an applicant would lean on when accepting a hedged answer
    # about their own eligibility. Pin the conditional register.
    #
    # (This comment previously reasoned from "the disclaimer only ADVISES
    # review", which nsb4y made false. The ASSERTIONS below were correct
    # either way -- what changed is why.)
    assert "expected to review this form" in si
    assert "do not promise the user that a review will happen" in si
    assert "reviewed by a qualified human before filing" not in si, (
        "that phrasing asserts review as certain; the applicant UNDERTAKES "
        "review but we never guarantee it happened -- keep the SI conditional")


# --------------------------------------------------------------------------- #
# Layer 4 -- the PLAIN MEANING carve-out (bd polyglot-pdf-gs5f0)
#
# The maintainer hit this live: asked what "ITIN" stands for on the W-7, the
# model refused and read from the instructions instead. The expansion is in the
# form's own title. Expanding an acronym is not a legal determination -- one
# correct answer, no dependence on the user's situation, no consequence -- but
# the SI had no carve-out for it, so it fell into the hedge path by default.
#
# THE RISK THIS PAIR GUARDS. A carve-out written loosely is a licence to
# interpret rules for the user, which would defeat the whole hedge policy and
# the deployment invariant it rests on (docs/standards/confirmation-and-audit.md).
# So BOTH halves are pinned: the permission must exist, AND the applicative
# boundary must still hold. A future SI diet that drops either one fails here.
# Testing only the permission would let the boundary rot silently -- that is the
# redundant-guard trap (repo memory: redundant-guards-need-per-layer-tests).
# --------------------------------------------------------------------------- #

def test_si_allows_answering_a_plain_meaning_question_directly():
    """The permission half. Without this the model hedges on 'what does ITIN
    stand for', which is useless on the easy questions and erodes trust for the
    hard ones where the hedge actually matters."""
    si = _si_text()
    assert "PLAIN MEANING" in si, (
        "the SI must carve out definitional questions; without it every "
        "'what does X mean' falls into the hedge path")
    lowered = si.lower()
    assert "what does itin stand for" in lowered, (
        "the carve-out should name the maintainer's own reported example so a "
        "future edit cannot narrow it past the case that motivated it")
    # The sanctioned behavior, stated positively (allowlist, per this module's
    # header): answer it, and skip the hedge machinery for THIS class only.
    assert "do not hedge" in lowered
    assert "do not call the secretary first" in lowered


def test_si_keeps_the_applicative_boundary_inside_the_carve_out():
    """The boundary half -- the load-bearing one.

    The carve-out is only safe while it stays scoped to word meaning. This
    pins that the SI names the distinction explicitly AND names applicative
    questions as still-hedged, so 'plain meaning' cannot be read as 'you may
    now explain rules'.
    """
    lowered = _si_text().lower()
    assert "what an ordinary word means versus what a rule says" in lowered, (
        "the carve-out must state its own boundary, not just its permission")
    # THE LEAK THIS CLOSES (fresh-eyes round 1). A question about a NAMED RULE
    # is rule-interpretation wearing definitional clothing: on the W-7,
    # "exception 3" is not a word, it is an eligibility condition, so "what
    # does exception 3 mean" IS the hedged question even though it is phrased
    # as a definition. An earlier draft used "what does exemption mean" as a
    # SANCTIONED example, which pointed the carve-out straight at that leak.
    assert "a named rule on the form is never plain meaning" in lowered, (
        "without this, a rule label read as a 'word' escapes the hedge path")
    assert "what does exception 3 mean" in lowered, (
        "name the hard case explicitly -- it is the one a model gets wrong")
    assert "what a rule requires" in lowered
    # Eligibility phrased as a question is the exact thing that must NOT be
    # swept in by the carve-out.
    assert "are you eligible for an itin" in lowered
    assert "should you check box a" in lowered
    # And the tie-break must fall on the SAFE side.
    assert "treat it as a rule question and hedge" in lowered, (
        "an ambiguous question must default to hedging, never to answering")

    # STRUCTURAL, not just presence (fresh-eyes round 1): every boundary clause
    # must live INSIDE the carve-out sentence it scopes. Asserting mere presence
    # would survive a mutation that relocates the tie-break elsewhere in the SI,
    # where it no longer says WHICH class of question it disambiguates.
    carve_start = _si_text().index("PLAIN MEANING")
    carve_end = _si_text().index("ALWAYS HEDGE AND DEFER")
    carve_out = _si_text()[carve_start:carve_end].lower()
    for clause in (
        "a named rule on the form is never plain meaning",
        "treat it as a rule question and hedge",
        "what an ordinary word means versus what a rule says",
    ):
        assert clause in carve_out, (
            f"boundary clause {clause!r} must sit INSIDE the carve-out that it "
            "scopes, not merely somewhere in the SI")


def test_plain_meaning_carve_out_does_not_displace_the_hedge_rule():
    """Ordering/coexistence: the carve-out is an EXCEPTION, so the general rule
    must still be present and unweakened after it."""
    si = _si_text()
    assert "ALWAYS HEDGE AND DEFER" in si
    assert "INFORMATION, NEVER ADVICE" in si
    # The carve-out must come BEFORE the hedge rule so the hedge reads as the
    # default and the carve-out as the narrow exception -- not the reverse.
    assert si.index("PLAIN MEANING") < si.index("ALWAYS HEDGE AND DEFER"), (
        "the carve-out must be scoped by the hedge rule that follows it, not "
        "appear as a later override of it")


def test_plain_meaning_examples_are_not_terms_the_shipped_KITS_use():
    """Every SANCTIONED example must be a word no shipped form uses as a
    category or rule label -- checked against the KITS, not by judgment.

    THIS CAUGHT THE SAME MISTAKE TWICE (bd polyglot-pdf-gs5f0). The carve-out's
    examples teach the boundary more concretely than its rule text does, so a
    badly-chosen example silently widens it in exactly the direction a reader
    will follow. Draft 1 offered "what does exemption mean"; draft 2 replaced it
    with "what does spouse mean". BOTH are eligibility labels -- "spouse" occurs
    69 times in the W-7 and 66 in the f1040, naming reason-for-applying and
    filing-status categories. Asking what one MEANS on those fields is asking
    which category applies to you: the hedged question, dressed as a definition.

    Two reviewers each caught one instance by reading. This asserts the PROPERTY
    instead, so instance three fails CI (repo memory:
    guard-the-property-not-the-code-shape).
    """
    import json
    import re
    from pathlib import Path

    si = _si_text()
    carve_out = si[si.index("PLAIN MEANING"):si.index("ALWAYS HEDGE AND DEFER")]

    # The sanctioned examples are ONLY the quoted phrases in the opening
    # permission sentence -- the ones offered as "ask me this and I answer".
    # Everything after "The line is" is boundary prose: counter-examples that
    # MUST use rule vocabulary, plus the ITIN expansion itself, which is
    # legitimately full of form terms.
    permission_region = carve_out.split("The line is")[0]
    quoted = re.findall(r"'([^']+)'", permission_region)
    assert quoted, "the carve-out must carry at least one sanctioned example"

    # Content words from each example, minus the interrogative scaffolding that
    # carries no domain meaning.
    ACRONYM_EXEMPT = {"itin"}
    STOPWORDS = {
        "what", "does", "do", "is", "a", "an", "the", "mean", "means",
        "stand", "for", "of", "on", "this", "form", "it",
    }

    kit_root = Path(__file__).resolve().parents[3] / "form-kits"
    kit_texts = {
        p.parent.name: p.read_text(encoding="utf-8").lower()
        for p in kit_root.glob("*/schema.json")
    }
    assert kit_texts, f"no shipped kits found under {kit_root}"

    offenders = []
    for example in quoted:
        for word in re.findall(r"[a-z]+", example.lower()):
            if word in STOPWORDS or len(word) < 4:
                continue
            # An ACRONYM the form itself expands in its own title is the
            # paradigm safe case, not a collision -- that is why "what does
            # ITIN stand for" is the motivating example for this whole bead.
            if word in ACRONYM_EXEMPT:
                continue
            for kit, text in kit_texts.items():
                # Word-boundary match: a term the kit actually uses as its own
                # vocabulary, not an incidental substring.
                hits = len(re.findall(rf"\b{re.escape(word)}\b", text))
                if hits:
                    offenders.append((example, word, kit, hits))

    assert not offenders, (
        "a sanctioned plain-meaning example uses a term the shipped kits use as "
        "their own vocabulary, so asking what it MEANS is plausibly asking which "
        "category applies -- the hedged question wearing definitional clothing:\n"
        + "\n".join(
            f"  example {e!r}: '{w}' appears {n}x in {k}" for e, w, k, n in offenders
        )
        + "\nPick a term absent from every kit (e.g. 'surname', 'abbreviation')."
    )
