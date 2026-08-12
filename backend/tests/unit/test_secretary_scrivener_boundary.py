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
it may ask), and the live model's SI (when it calls, and what it does with a
refusal).

ALLOWLIST, NOT BLACKLIST. These tests assert the SANCTIONED behavior is stated
-- quote official text, decline advice, redirect to the reviewing human. They
deliberately do NOT assert "the word 'advise' never appears": a banned-word
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


def test_secretary_is_told_to_decline_advice_shaped_questions():
    """Declining is a POSITIVE instruction, not an absence of permission.

    A rubric that merely omits 'you may advise' leaves the model to infer the
    boundary. The refusal has to be stated.
    """
    si = SECRETARY_SI.lower()
    assert "decline" in si, "the secretary must be told to DECLINE, explicitly"
    # ...and told WHAT to decline, in the applicant's own framing.
    for shape in ("what should i put", "do i qualify", "applies to me"):
        assert shape in si, f"the declined question shape {shape!r} must be named"


def test_secretary_is_told_to_redirect_to_the_reviewing_human():
    """A refusal that dead-ends is a worse product AND a worse legal posture:
    the applicant still needs an answer, and the answer is a human's."""
    si = SECRETARY_SI.lower()
    assert "applicant" in si
    assert "reviewing" in si or "reviewer" in si, (
        "a declined question must redirect to the human reviewing the form")


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


def test_declaration_disclaims_applicability_and_advice():
    decl = _ask_secretary_declaration()
    text = decl["description"].lower()
    assert "declines" in text or "decline" in text, (
        "the caller must be told the secretary declines advice-shaped asks, so "
        "a refusal is expected behavior rather than a tool malfunction")
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
# Layer 3 -- the live model's SI: when it calls, and what it does with a refusal
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


def test_si_tells_the_model_to_RELAY_a_refusal_rather_than_answer_itself():
    """THE BYPASS THIS CLOSES. A well-behaved secretary declines; a helpful
    voice model then answers the question itself from its own knowledge, and
    the refusal has bought nothing. The SI must say: relay, do not substitute."""
    si = _si_text().lower()
    assert "do not answer it yourself" in si, (
        "the SI must forbid the model answering an advice question the "
        "secretary declined")
    assert "choice is theirs" in si or "theirs to make" in si
