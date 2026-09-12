"""Guidance content contract + lint rules (bd polyglot-pdf-wsao.3).

Pins: the containment normalization spec (the zero-trust core of the details
channel), the anti-restatement heuristic, and every new schema_lint guidance
rule -- one synthetic violation fixture per rule, plus the exit-criterion
check that the coverage rule fires on the REAL w7 kit (0/59 authored
guidance today).

ASCII only (CLAUDE.md scar #6). Unicode punctuation in fixtures is
chr()-composed.
"""

from __future__ import annotations

import json
from pathlib import Path

from backend.services import guidance_contract as gc
from backend.services.schema_lint import lint_schema

REPO = Path(__file__).resolve().parents[3]

CURLY_APOS = chr(0x2019)
EM_DASH = chr(0x2014)
NBSP = chr(0x00A0)


# --- containment normalization -----------------------------------------------

def test_containment_exact_verbatim_passes():
    src = "If you check this box, you must also check box h."
    res = gc.check_containment("you must also check box h", src)
    assert res.contained and res.matched_at >= 0
    assert "check box h" in res.matched_span


def test_containment_survives_curly_quotes_hyphenation_and_whitespace():
    # The booklet PDF renders curly apostrophes, line-break hyphenation, and
    # hard line wraps; the excerpt is typed clean. Both normalize to the same
    # string -- the PINNED spec.
    src = ("Certain nonresident aliens must get an ITIN to claim tax" + NBSP +
           "treaty benefits even if they don" + CURLY_APOS + "t have to file "
           "a U.S. federal tax return with third-party with-\nholding " +
           EM_DASH + " see Pub. 901.")
    excerpt = ("certain nonresident aliens must get an ITIN to claim tax "
               "treaty benefits even if they don't have to file a U.S. "
               "federal tax return with third-party withholding - see Pub. 901.")
    assert gc.check_containment(excerpt, src).contained


def test_containment_rejects_paraphrase():
    src = "You must attach the documentation required under the exception."
    res = gc.check_containment(
        "Attach whatever documents the exception needs.", src)
    assert not res.contained and res.matched_at == -1


def test_details_paragraphs_excludes_heading_scaffolding():
    details = ("## a. Tax treaty benefit\n"
               "Certain nonresident aliens must get an ITIN.\n\n"
               "Exception 1.\n"
               "This exception may apply for passive income.")
    paras = gc.details_paragraphs(details)
    assert paras == ["Certain nonresident aliens must get an ITIN.",
                     "This exception may apply for passive income."]


def test_label_restatement_detects_filler_and_passes_real_guidance():
    assert gc.is_label_restatement(
        "Select your eye color.", "Eye Color",
        ["Brown", "Blue", "Green"])
    assert not gc.is_label_restatement(
        "This code appears on the front of your Permanent Resident Card.",
        "Class of Admission", [])


# --- lint rules: one synthetic violation per rule ----------------------------

def _schema(fields, booklet=None):
    meta = {"title": "T", "version": "1"}
    if booklet is not None:
        meta["booklet_text"] = booklet
    return {"metadata_unused": {}, "form_metadata": meta, "fields": fields,
            "sections": [], "parts": []}


def _rules(findings):
    return [f.rule for f in findings]


def test_lint_missing_instructions_aggregates_and_respects_exclusions():
    findings = lint_schema(_schema([
        {"id": "a", "name": "A", "type": "text"},
        {"id": "b", "name": "B", "type": "text", "read_only": True},
        {"id": "c", "name": "C", "type": "signature"},
        {"id": "d", "name": "D", "type": "text",
         "help": {"instructions": "Enter the code from your card."}},
    ]))
    hits = [f for f in findings if f.rule == "help-instructions-missing"]
    # ONE aggregated finding (never per-field -- flood guard), counting only
    # the askable/uncovered field 'a' (b read_only + c signature excluded, d
    # covered).
    assert len(hits) == 1
    assert "1 of 2 fields" in hits[0].message and "a" in hits[0].message


def test_lint_too_long_restatement_and_screen_ref():
    findings = lint_schema(_schema([
        {"id": "long", "name": "L", "type": "text",
         "help": {"instructions": "x" * (gc.INSTRUCTIONS_HARD_CHARS + 1)}},
        {"id": "restate", "name": "Eye Color", "type": "select",
         "options": [{"value": "brown", "label": "Brown"}],
         "help": {"instructions": "Select your eye color."}},
        {"id": "deixis", "name": "D", "type": "text",
         "help": {"instructions": "See page 7 of the instructions above."}},
    ]))
    rules = _rules(findings)
    assert "help-instructions-too-long" in rules
    assert "help-instructions-label-restatement" in rules
    assert "help-instructions-screen-ref" in rules


def test_lint_containment_failure_and_floor_missing():
    booklet = "Certain nonresident aliens must get an ITIN to claim benefits."
    # Paragraph NOT in the booklet -> not-contained finding with the paragraph
    # head quoted in the message.
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "This sentence was invented by a model."}},
    ], booklet=booklet))
    hits = [f for f in findings if f.rule == "help-details-not-contained"]
    assert len(hits) == 1
    assert "This sentence was invented" in hits[0].message

    # Same details but NO booklet floor -> the no-reference-floor finding
    # instead (containment cannot run).
    findings2 = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "Anything at all."}},
    ]))
    assert "help-details-no-reference-floor" in _rules(findings2)
    assert "help-details-not-contained" not in _rules(findings2)


def test_lint_containment_checks_form_level_details_too():
    """form_metadata.details is under the SAME zero-trust gate as per-field
    details (wsao.4 outer review: 3 glued paragraphs shipped as 'clean'
    through the form-level blind spot)."""
    booklet = "Purpose of Form. Use Form W-7 to apply for an ITIN."
    schema = _schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage"}},
    ], booklet=booklet)
    schema["form_metadata"]["details"] = "This sentence was invented."
    findings = lint_schema(schema)
    hits = [f for f in findings if f.rule == "help-details-not-contained"]
    assert len(hits) == 1 and hits[0].path == "$.form_metadata.details"
    # verbatim form-level details pass
    schema["form_metadata"]["details"] = \
        "Use Form W-7 to apply for an ITIN."
    assert not [f for f in lint_schema(schema)
                if f.rule == "help-details-not-contained"]
    # form-level details without a floor -> the no-reference-floor finding
    schema2 = _schema([{"id": "f1", "name": "F1", "type": "text",
                        "help": {"instructions": "ok guidance here x"}}])
    schema2["form_metadata"]["details"] = "Anything."
    rules2 = [f.rule for f in lint_schema(schema2)]
    assert "help-details-no-reference-floor" in rules2


def test_lint_containment_passes_verbatim_excerpt():
    booklet = ("a. Tax treaty benefit. Certain nonresident aliens must get "
               "an ITIN to claim tax treaty benefits even if they don" +
               CURLY_APOS + "t have to file a return.")
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": "## a. Tax treaty benefit\n"
                             "Certain nonresident aliens must get an ITIN to "
                             "claim tax treaty benefits even if they don't "
                             "have to file a return."}},
    ], booklet=booklet))
    assert "help-details-not-contained" not in _rules(findings)


def test_lint_oversize_and_headings_missing():
    big = ("word " * ((gc.DETAILS_INLINE_MAX_CHARS // 5) + 10)).strip()
    findings = lint_schema(_schema([
        {"id": "f1", "name": "F1", "type": "text",
         "help": {"instructions": "ok guidance here for coverage",
                  "details": big}},
    ], booklet=big))
    rules = _rules(findings)
    assert "help-details-oversize" in rules  # > the 20k inline budget
    assert "help-details-headings-missing" in rules  # long + zero headings


# --- wsao.4: pinned-normalization additions + furniture cleaner --------------

def test_normalization_folds_bullets_and_slash_wraps():
    """The wsao.4 additions to the PINNED spec (measured PDF artifacts, not
    paraphrase loosening): bullet glyphs fold to '-', slash-wraps join."""
    bullet = chr(0x2022)
    src = (bullet + " Form 1042-S, Foreign Person" + chr(0x2019) + "s income\n"
           + bullet + " Form 1099-INT, Interest Income")
    excerpt = "- Form 1042-S, Foreign Person's income - Form 1099-INT, Interest Income"
    assert gc.check_containment(excerpt, src).contained
    # slash-wrap: the booklet wraps AFTER slashes ("citizen/\nresident")
    assert (gc.normalize_for_containment("U.S. citizen/\nresident alien")
            == "u.s. citizen/resident alien")
    assert gc.check_containment("U.S. citizen/resident alien",
                                "U.S. citizen/\n resident alien").contained


def test_clean_booklet_furniture_strips_sidebars_and_footers_only():
    raw = ("identification \nCAUTION\n!\nCAUTION\n!\ndocuments. A copy of "
           "the ID is required.\n8\nInstructions for Form W-7 (Rev. December "
           "2024)\nTIP\nreal content line continues here.")
    cleaned = gc.clean_booklet_furniture(raw)
    assert "CAUTION" not in cleaned and "TIP" not in cleaned
    assert "Instructions for Form W-7" not in cleaned
    assert "\n8\n" not in cleaned
    assert "documents. A copy of the ID is required." in cleaned
    assert "real content line continues here." in cleaned
    # DOCUMENTED TRADEOFF (wsao.4 fresh-eyes): a line that is ONLY 1-3 digits
    # is treated as a page number and dropped -- a booklet whose body carries
    # a standalone bare-number line would lose it (none observed on w7; the
    # wsao.5 write path inherits this and must revisit if a real kit hits it).
    assert "100" not in gc.clean_booklet_furniture("above\n100\nbelow")
    # never-throws contract: truthy non-strings coerce to "" like siblings
    assert gc.clean_booklet_furniture([1, 2]) == ""
    assert gc.clean_booklet_furniture(42) == ""


# --- wsao.8: inline budget clamp + injection budget --------------------------

def test_clamp_details_inline_passthrough_is_byte_identical():
    small = "## a. Heading\nSome verbatim excerpt.\n\nAnother paragraph."
    assert gc.clamp_details_inline(small) is small


def test_clamp_details_inline_cuts_at_paragraph_and_indexes_dropped_topics():
    kept_para = "K" * 900
    dropped = ("## Exceptions 3-5\nDropped body one.\n\n"
               "## Military family rules\nDropped body two.")
    details = "\n\n".join([kept_para] * 25) + "\n\n" + dropped
    clamped = gc.clamp_details_inline(details, max_chars=10000)
    assert len(clamped) < len(details)
    # cut lands on a kept paragraph boundary; the index line names the
    # dropped headings and points at the secretary
    assert clamped.rstrip().endswith("]")
    assert "secretary holds the full official instructions" in clamped
    assert "Exceptions 3-5" in clamped and "Military family rules" in clamped
    assert "Dropped body one" not in clamped


def test_inline_injection_budget_tokens():
    slop = gc.INJECTION_BUDGET_SLOP_TOKENS
    assert gc.inline_injection_budget_tokens({"fields": [
        {"id": "a", "help": {"details": "x" * 8000}},
        {"id": "b", "help": {"details": "y" * 100}},
        {"id": "c"},
    ]}) == 2000 + slop  # max clamped details chars / 4 + index-tail slop
    # oversize details count at the CLAMP, not raw size
    assert gc.inline_injection_budget_tokens({"fields": [
        {"id": "a", "help": {"details": "x" * (gc.DETAILS_INLINE_MAX_CHARS + 9999)}},
    ]}) == gc.DETAILS_INLINE_MAX_CHARS // 4 + slop
    # no details anywhere -> 0, NO slop (window derivation stays pre-wsao.8
    # byte-identical for details-less forms)
    assert gc.inline_injection_budget_tokens({"fields": [{"id": "a"}]}) == 0
    assert gc.inline_injection_budget_tokens({}) == 0


def test_derive_compression_window_adds_injection_budget():
    from backend.adapters.live_ai_gemini import derive_compression_window
    base = derive_compression_window(
        "s" * 4000, None, window_headroom_tokens=599,
        trigger_margin_tokens=1500)
    bumped = derive_compression_window(
        "s" * 4000, None, window_headroom_tokens=599,
        trigger_margin_tokens=1500, injection_budget_tokens=5000)
    assert bumped["window"] == base["window"] + 5000
    assert bumped["trigger"] == base["trigger"] + 5000
    # default arg -> byte-identical to pre-wsao.8 derivation
    assert base == derive_compression_window(
        "s" * 4000, None, window_headroom_tokens=599,
        trigger_margin_tokens=1500, injection_budget_tokens=0)


def test_guidance_rules_are_warning_severity_only():
    findings = lint_schema(_schema([
        {"id": "a", "name": "A", "type": "text"},
    ]))
    for f in findings:
        if f.rule.startswith("help-"):
            assert f.severity == "WARNING"


def test_lint_never_throws_on_malformed_guidance_values():
    """The lint never-throws contract extends to the guidance rules (wsao.3
    Opus fresh-eyes): raw LLM drafts carry lists/numbers where strings belong
    -- a list-shaped instructions 500'd the editor lint route before the
    coercion guards."""
    schema = _schema([
        {"id": "a", "name": 7, "type": "text",
         "help": {"instructions": ["a", "list"], "details": 42}},
        {"id": "b", "name": "B", "type": "select",
         "options": [{"value": "x", "label": 9}],
         "help": {"instructions": "Select the one that applies to you."}},
        {"id": "c", "name": "C", "type": "text", "help": "not-a-dict"},
        # truthy NON-LIST options + present instructions: the restatement
        # path iterates options (fix-round-2 gap -- `or []` only guards
        # falsy values)
        {"id": "d", "name": "D", "type": "select", "options": 5,
         "help": {"instructions": "Pick the value from your notice."}},
    ])
    schema["form_metadata"]["booklet_text"] = 42  # non-string floor
    findings = lint_schema(schema)  # must not raise
    assert isinstance(findings, list)


def test_guidance_metrics_never_throws_on_malformed_values():
    import importlib.util, pathlib
    spec = importlib.util.spec_from_file_location(
        "eval_extraction_under_test",
        REPO / "scripts" / "authoring" / "eval_extraction.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod.guidance_metrics({
        "form_metadata": {"booklet_text": 42},
        "fields": [{"id": "a", "name": 7, "type": "text",
                    "help": {"instructions": 123, "details": ["x"]}}],
    })
    assert m["covered"] == 0 and m["containment_pct"] is None


# --- exit criterion: fires on the real w7 kit --------------------------------

# test_w7_kit_coverage_matches_reality was DELETED 2026-09-11 (bd
# polyglot-pdf-q3u5r). It read form-kits/w7/schema.json and asserted that
# kit's guidance coverage -- a claim about one form's CONTENT, which is the
# shape CLAUDE.md scar #10 says not to write. No kit is tracked now, so it
# could only fail. The lint RULE it exercised (help-instructions-missing) is
# covered by the synthetic tests in this file.

# --- the formula tripwire (bd polyglot-pdf-cf6v) -----------------------------

def test_identity_payload_golden_pin_forces_a_migration_decision():
    """CHANGING identity_payload INVALIDATES EVERY SHIPPED STAMP AT ONCE.

    Root cause of the W-7 wave (bd cf6v journal, 2026-08-07): bd
    polyglot-pdf-stkz appended the type token 25 minutes after PR #519 wrote
    the kit's 52 identity stamps. The change was self-justified by a "0 of 44
    provenance records exist" check that was true on its own branch and false
    at merge time -- and no test made the collision visible, so all 51
    guidance-carrying fields lit up stale with zero author edits.

    This pin makes any future formula change fail HERE, where the author can
    see the consequence. If you are editing identity_payload deliberately:
    every kit baked before your change will collapse to a kit-level
    guidance-identity-mass-drift finding until it is re-baked (that collapse
    is the designed containment, not a bug) -- update these golden strings in
    the SAME commit and say in it how shipped kits get re-stamped.
    """
    from backend.services.guidance_contract import identity_payload
    scalar = {"id": "a", "name": "Phone", "spoken_name": "phone number",
              "type": "text"}
    choice = {"id": "b", "name": "Status", "spoken_name": "marital status",
              "type": "radio",
              "options": [
                  {"label": "Married", "spoken_label": "married", "value": "m"},
                  {"label": "Single", "spoken_label": "single", "value": "s"}]}
    assert identity_payload(scalar) == '["Phone","phone number",[],"text"]'
    assert identity_payload(choice) == (
        '["Status","marital status",'
        '[["Married","married","m"],["Single","single","s"]],"choice"]')
