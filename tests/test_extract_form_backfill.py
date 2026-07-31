"""Tests for extract_form.py's pdf_position back-fill (bd polyglot-pdf-7a9.18,
extended by bd polyglot-pdf-5f41 to also back-fill per-OPTION pdf_position).

The original bug: the LLM emits a placeholder pdf_position {x:0,y:0,width:0,
height:0} that is a truthy dict, so the original `if field.get('pdf_position'):
continue` skipped back-fill and left the zeros -- the editor then could not map
the field to the PDF (click-to-jump dead). The fix back-fills when the position
is MISSING *or* DEGENERATE (non-positive width/height) from the deterministic
AcroForm dump.

bd 5f41 extends the same join to each field's options[]: a radio/checkbox_group
option's own widget rect is resolved the same way (name lookup is suffix-aware,
matching schema_lint._match_dump_names' exact-then-dot-boundary-suffix
convention), disambiguated by pdf_on_value when a name covers several widgets,
or resolved purely by pdf_on_value for the shared-field-name radio/combo-group
shape. `_backfill_positions` returns a mapping rather than a bare field count --
{"fields_filled", "options_filled", "unmatched"} at that point, and a fourth key
"model_pages_normalized" since bd polyglot-pdf-icyi (below), on EVERY return
path including the dump-unreadable one.

bd polyglot-pdf-icyi INVERTS the priority (maintainer decision 2026-07-29): the
deterministic dump rect now wins UNCONDITIONALLY wherever a widget resolves, at
both the field and option level. Trusting a model rect that merely LOOKED usable
(positive width/height) is what shipped the page-0 bug -- a fresh w7 extraction
emitted 48 rects with page=0 (the model mirroring the 0-based digest it was
shown), and since the editor matches pages 1..numPages by exact equality, every
text-field overlay silently vanished from the preview. Model coordinates survive
ONLY where no widget resolves (the future scanned/flat-PDF route), and a
0-based model page there is shifted up rather than discarded.

These tests pin that behavior with synthetic data (no PDF / LLM needed): a
degenerate-zero field and a missing-position field both get the dump rect; a
plausible-but-wrong model rect is OVERWRITTEN by the dump; a degenerate rect
with no dump match is dropped entirely.

Imports extract_form by file path (repo precedent: test_bd_safe.py); it adds
scripts/bakeoff to sys.path at import for acroform_dump/arm_llm_native, which is
harmless here since we never call those.
"""

import importlib.util
import json
import pathlib
import sys

import pytest


_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
_SCRIPT = _REPO / "scripts" / "authoring" / "extract_form.py"
spec = importlib.util.spec_from_file_location("extract_form", _SCRIPT)
ef = importlib.util.module_from_spec(spec)
sys.modules["extract_form"] = ef
spec.loader.exec_module(ef)


# --- _has_usable_position --------------------------------------------------- #

@pytest.mark.parametrize("pos,expected", [
    ({"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}, True),
    ({"page": 1, "x": 0, "y": 0, "width": 0, "height": 0}, False),   # the bug case
    ({"page": 1, "x": 10, "y": 20, "width": 0, "height": 8}, False), # zero width
    ({"page": 1, "x": 10, "y": 20, "width": 8, "height": 0}, False), # zero height
    ({"page": 1, "x": 10, "y": 20}, False),                          # missing w/h
    (None, False),
    ("not a dict", False),
    ({"width": "abc", "height": "def"}, False),                     # non-numeric
])
def test_has_usable_position(pos, expected):
    assert ef._has_usable_position(pos) is expected


# --- _backfill_positions ---------------------------------------------------- #

def _write_dump(tmp_path, name_to_rect):
    """Write a minimal acroform-dump JSON: {fields:[{name, widgets:[{rect}]}]}."""
    dump = {"fields": [
        {"name": n, "widgets": [{"rect": r}]} for n, r in name_to_rect.items()
    ]}
    p = tmp_path / "dump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)


def test_backfill_replaces_degenerate_zero_position(tmp_path):
    """The core bug: a field with an all-zero pdf_position is back-filled from the
    dump rect (page is +1'd: dump pages are 0-based, schema is 1-based)."""
    dump = _write_dump(tmp_path, {
        "topmostSubform[0].Page1[0].f1_47[0]": {
            "page": 0, "x": 100.0, "y": 200.0, "width": 8.0, "height": 8.0},
    })
    schema = {"fields": [{
        "id": "agent_ptin",
        "pdf_field_name": "topmostSubform[0].Page1[0].f1_47[0]",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 100.0, "y": 200.0, "width": 8.0, "height": 8.0}


def test_backfill_fills_missing_position(tmp_path):
    dump = _write_dump(tmp_path, {
        "fld": {"page": 2, "x": 5, "y": 6, "width": 7, "height": 9}})
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld"}]}  # no pdf_position
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["pdf_position"]["page"] == 3  # 2 + 1


def test_the_DUMP_RECT_WINS_over_a_plausible_model_position(tmp_path):
    """PRIORITY INVERSION (bd polyglot-pdf-icyi, maintainer decision 2026-07-29).

    This test previously asserted the OPPOSITE ("the LLM/human value wins when
    valid") and that is precisely what shipped the bug: a fresh w7 extraction
    emitted 48 model rects with page=0 (the model mirroring the 0-based digest
    it was shown). They had positive width/height, so they looked "usable" and
    the deterministic back-fill never replaced them -- and since the editor
    matches pages 1..numPages by exact equality, EVERY text-field overlay
    silently vanished from the PDF preview. Only the 6 choice fields drew,
    because their rects came from this dump path.

    The PDF's own widget geometry is ground truth and free to read, so it now
    overwrites the model unconditionally. The model also rounds (469.2 -> 469),
    so even a page-correct model rect is lossy."""
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 469.2, "y": 180.0, "width": 106.8, "height": 11.0}})
    # A model rect that looks entirely reasonable: positive w/h, rounded coords,
    # and the 0-based page that broke the real extraction.
    model = {"page": 0, "x": 469, "y": 180, "width": 107, "height": 11}
    schema = {"fields": [{"id": "a", "pdf_field_name": "fld",
                          "pdf_position": dict(model)}]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 1, "options_filled": 0, "unmatched": [],
         "model_pages_normalized": 0}
    # Unrounded coordinates AND the correct 1-based page, from the dump.
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 469.2, "y": 180.0, "width": 106.8, "height": 11.0}


def test_a_model_position_survives_only_when_NO_widget_resolves(tmp_path):
    """The documented fallback route (bd polyglot-pdf-icyi): keep model-supplied
    coordinates when the PDF has no widget to derive them from. Rare on
    AcroForms (all 4 real kits resolve 486/486 widgets), but it is the path a
    future scanned/flat-PDF extraction would depend on, so it must not be
    deleted along with the trust inversion."""
    dump = _write_dump(tmp_path, {"other_widget": {
        "page": 0, "x": 1, "y": 2, "width": 3, "height": 4}})
    model = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{"id": "a", "pdf_field_name": "no_such_widget",
                          "pdf_position": dict(model)}]}
    result = ef._backfill_positions(schema, dump)
    assert result["fields_filled"] == 0
    assert schema["fields"][0]["pdf_position"] == model   # kept verbatim


def test_a_degenerate_position_is_DROPPED_when_no_widget_resolves(tmp_path):
    """No widget AND no usable model rect: ship NO pdf_position rather than a
    zero-size placeholder, which reads as a real position to every downstream
    consumer (the editor's overlay-block reason then says 'no position
    recorded', which is the truth)."""
    dump = _write_dump(tmp_path, {"other": {
        "page": 0, "x": 1, "y": 2, "width": 3, "height": 4}})
    schema = {"fields": [{"id": "a", "pdf_field_name": "no_such_widget",
                          "pdf_position": {"page": 1, "x": 0, "y": 0,
                                           "width": 0, "height": 0}}]}
    ef._backfill_positions(schema, dump)
    assert "pdf_position" not in schema["fields"][0]


def test_positions_carry_only_the_five_real_keys(tmp_path):
    """A written pdf_position holds page/x/y/width/height and NOTHING else.

    Guards a regression from this bead's own first draft: an earlier version
    tagged deterministic rects with a marker KEY so page normalization could
    tell them from model rects -- and that marker leaked into every kit and
    every dict-equality assertion. The set of deterministic positions is now
    tracked by identity instead, writing nothing into the data."""
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 5, "y": 6, "width": 7, "height": 9},
        "opt1": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [
        {"id": "a", "pdf_field_name": "fld"},
        {"id": "b", "options": [{"value": "v", "pdf_field_name": "opt1"}]},
    ]}
    ef._backfill_positions(schema, dump)
    expected_keys = {"page", "x", "y", "width", "height"}
    assert set(schema["fields"][0]["pdf_position"]) == expected_keys
    assert set(schema["fields"][1]["options"][0]["pdf_position"]) == expected_keys
    # ...and the deterministic pages stayed 1-based (never double-shifted)
    assert schema["fields"][0]["pdf_position"]["page"] == 1
    assert schema["fields"][1]["options"][0]["pdf_position"]["page"] == 1


def test_deterministic_pages_are_never_shifted_by_normalization(tmp_path):
    """THE ORDERING TRAP this bead's design has to avoid: dump rects are already
    1-based, so if the page-base normalization treated them as model-supplied,
    a schema containing any genuine 0-based model page would shift the
    deterministic ones too and push them off the document. _backfill_positions
    runs normalization itself with the identity set, so this cannot happen."""
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 5, "y": 6, "width": 7, "height": 9}})
    schema = {"fields": [
        {"id": "deterministic", "pdf_field_name": "fld"},
        # no widget resolves -> keeps its model rect, which IS 0-based
        {"id": "model_only", "pdf_field_name": "absent",
         "pdf_position": {"page": 0, "x": 1, "y": 2, "width": 3, "height": 4}},
    ]}
    result = ef._backfill_positions(schema, dump)
    assert result["model_pages_normalized"] == 1        # only the model one
    assert schema["fields"][0]["pdf_position"]["page"] == 1   # dump: unchanged
    assert schema["fields"][1]["pdf_position"]["page"] == 1   # model: 0 -> 1


def test_every_shipped_kit_has_in_range_pages_and_real_rects():
    """REAL-KIT REGRESSION (bd polyglot-pdf-icyi): the shipped kits' field
    positions must land on a page the document actually has, and match the PDF's
    own widget geometry.

    This is the test that would have caught the bug from the outside: a fresh w7
    extraction shipped 48 of 54 fields on page 0, which the editor's PDF preview
    matches against 1..numPages by exact equality -- so every text-field overlay
    silently vanished and only the 6 dump-derived choice fields drew. Nothing in
    the suite noticed, because the schema was internally well-formed.

    Skips a kit whose PDF or schema is absent from the checkout rather than
    failing (the same degrade-quietly convention the other real-kit guards use);
    fields whose widget name does not resolve are also skipped -- an unclaimed
    widget is a different concern (the coverage ledger's)."""
    fitz = pytest.importorskip("fitz")
    kits_root = _REPO / "form-kits"
    if not kits_root.is_dir():
        pytest.skip("form-kits/ not present in this checkout")

    checked_kits = 0
    for kit in sorted(p for p in kits_root.iterdir() if p.is_dir()):
        schema_path = kit / "schema.json"
        # form.pdf BY CONVENTION, never glob order: a kit can ship extra PDFs
        # (i-90 has i-90-annotated.pdf), and comparing geometry against the
        # wrong document would make this guard -- the only automated evidence
        # behind "positions match the real PDF" -- silently meaningless. Every
        # other tool hard-codes form.pdf (backfill_option_positions.py does);
        # match it, and SKIP rather than guess when it is absent (fresh-eyes
        # Opus round 2).
        form_pdf = kit / "form.pdf"
        if not schema_path.exists() or not form_pdf.exists():
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        doc = fitz.open(form_pdf)
        page_count = doc.page_count
        real: dict = {}
        for pno in range(page_count):
            for w in doc.load_page(pno).widgets() or []:
                real.setdefault(w.field_name, (
                    pno + 1, round(w.rect.x0, 2), round(w.rect.y0, 2),
                    round(w.rect.width, 2), round(w.rect.height, 2)))

        def _widget_for(claim):
            """The widget rect for a schema-side pdf_field_name claim.

            SUFFIX-AWARE, matching what the extractor itself does
            (schema_lint._match_dump_names' exact-then-dot-boundary-suffix
            rule). Exact-match-only skipped 100% of i-90's 132 fields -- the
            schema stores the XFA LEAF (P1_Line1_AlienNumber[0]) while the PDF
            widget carries the fully-qualified path
            (form1[0].#subform[0].P1_Line1_AlienNumber[0]) -- so this guard
            verified NOTHING on the largest, most XFA-complex kit while
            appearing to pass (fresh-eyes Opus round 3). A guard weaker than
            the code it guards is decoration."""
            if not claim:
                return None
            hit = real.get(claim)
            if hit:
                return hit
            for name, rect in real.items():
                if name.endswith("." + claim):
                    return rect
            return None

        bad_pages, wrong_rects, compared = [], [], 0
        for field in schema.get("fields") or []:
            pos = field.get("pdf_position")
            if not isinstance(pos, dict):
                continue  # no position recorded: not this test's concern
            page = pos.get("page")
            if (not isinstance(page, int) or isinstance(page, bool)
                    or page < 1 or page > page_count):
                bad_pages.append((field.get("id"), page))
                continue
            expected = _widget_for(field.get("pdf_field_name"))
            if not expected:
                continue  # unresolved widget name: the ledger's concern
            compared += 1
            got = (page, pos["x"], pos["y"], pos["width"], pos["height"])
            # TOLERANCE, not equality. Sized to the worst case MEASURED with
            # this exact arithmetic (expected rounded to 2dp, `got` as stored)
            # over the committed kits this guard reads:
            #   f1040 0.0000pt / 163 fields  (already dump-derived, exact)
            #   i-90  0.0050pt / 114 fields  (today's dump rounds to TWO
            #                                 decimals: round(r.x0, 2))
            #   w7    0.0500pt /  54 fields  (rects written by an OLDER
            #                                 one-decimal dump)
            # So 0.06 is the right ceiling for a guard over COMMITTED data, and
            # one-decimal rounding is real but HISTORICAL. Getting this number
            # honest took FOUR passes: v1 asserted the wrong basis (blamed the
            # current dump), tightening to 0.01 then false-failed on w7's legacy
            # values, and the figures quoted after THAT were still wrong because
            # i-90 was contributing 0 comparisons (see _widget_for). Every
            # number above is now measured, not reasoned. The bug this exists to
            # catch is orders of magnitude beyond any of them: a model rect
            # rounds to WHOLE points (469.2 -> 469) or lands on the wrong page.
            if got[0] != expected[0] or any(
                    abs(g - e) > 0.06 for g, e in zip(got[1:], expected[1:])):
                wrong_rects.append((field.get("id"), got, expected))

        assert not bad_pages, (
            f"{kit.name}: pdf_position.page out of range 1..{page_count} "
            f"(the editor preview draws NOTHING for these): {bad_pages[:10]}")
        assert not wrong_rects, (
            f"{kit.name}: pdf_position does not match the PDF's own widget "
            f"rect -- positions must be deterministic, not model-authored: "
            f"{wrong_rects[:5]}")
        # NON-VACUITY FLOOR: a kit with a schema, a form.pdf and positioned
        # fields MUST yield real comparisons. Without this the guard passed
        # while comparing 0 of i-90's 132 fields (fresh-eyes Opus round 3) --
        # silent success is the failure mode a regression guard must not have.
        positioned = sum(1 for f in schema.get("fields") or []
                         if isinstance(f.get("pdf_position"), dict))
        if positioned:
            assert compared, (
                f"{kit.name}: {positioned} field(s) carry a pdf_position but "
                f"NONE resolved to a PDF widget -- this guard is verifying "
                f"nothing on this kit (widget-name matching is broken)")
        checked_kits += 1

    if not checked_kits:
        pytest.skip("no kit with both a schema and a form PDF in this checkout")


def test_the_page_zero_bug_cannot_survive_the_backfill(tmp_path):
    """MUTATION PIN, through the REAL code path (bd polyglot-pdf-icyi).

    The real-kit guard above only inspects kits PRESENT in the checkout, and the
    kit that actually shipped this bug was untracked scratch -- so that guard
    alone proves nothing. This one reproduces the exact production shape (a
    1-page form where the model claimed page 0 with plausible rounded rects) and
    drives it through _backfill_positions, asserting the page-0 fields cannot
    come out the other side. If the trust inversion is ever reverted, this fails.
    """
    dump = _write_dump(tmp_path, {
        "f_text": {"page": 0, "x": 469.2, "y": 180.0,
                   "width": 106.8, "height": 11.0},
        "f_check": {"page": 0, "x": 453.6, "y": 97.75,
                    "width": 8.0, "height": 8.0},
    })
    schema = {"fields": [
        # the 48-field majority shape: model rect, rounded, page 0
        {"id": "text_like_v3", "pdf_field_name": "f_text",
         "pdf_position": {"page": 0, "x": 469, "y": 180,
                          "width": 107, "height": 11}},
        # the 6-field minority that kept working: no model rect at all
        {"id": "checkbox_like_v3", "pdf_field_name": "f_check"},
    ]}
    ef._backfill_positions(schema, dump)

    pages = [f["pdf_position"]["page"] for f in schema["fields"]]
    assert pages == [1, 1], f"a page-0 position survived the back-fill: {pages}"
    # and the previously-rounded field now carries the PDF's real precision
    assert schema["fields"][0]["pdf_position"]["width"] == 106.8


def test_every_return_path_carries_all_four_keys(tmp_path):
    """The return shape must not be only sometimes-four-keyed: the OSError early
    return omitted model_pages_normalized, so a caller indexing it directly
    would KeyError on the error path alone (fresh-eyes Opus round 3)."""
    expected_keys = {"fields_filled", "options_filled", "unmatched",
                     "model_pages_normalized"}
    # error path: no such dump file
    assert set(ef._backfill_positions({}, str(tmp_path / "nope.json"))) \
        == expected_keys
    # success path
    dump = _write_dump(tmp_path, {
        "fld": {"page": 0, "x": 1, "y": 2, "width": 3, "height": 4}})
    assert set(ef._backfill_positions(
        {"fields": [{"id": "a", "pdf_field_name": "fld"}]}, dump)) \
        == expected_keys


def test_a_bogus_option_widget_name_is_reported_even_with_a_model_position(tmp_path):
    """BEHAVIOR CHANGE, deliberately pinned (bd polyglot-pdf-icyi, fresh-eyes).

    Inverting the trust removed an early `continue` that skipped any option
    already carrying a "usable" position. A side effect: an option whose
    pdf_field_name resolves to NOTHING, but which the model gave a plausible
    rect, used to be skipped silently -- never resolved, never reported. It is
    now attempted, fails, and lands in `unmatched`, surfacing a coverage gap
    that previously hid. That is the better behavior (a bogus widget name is
    exactly what the unmatched list exists to reveal), but it is a real delta
    from the old contract, so it gets a test rather than living undocumented.

    The stale model rect is deliberately LEFT in place: it is still "usable",
    and dropping a position we cannot replace would only trade a possibly-wrong
    overlay for no overlay at all."""
    dump = _write_dump(tmp_path, {
        "real_widget": {"page": 0, "x": 1, "y": 2, "width": 3, "height": 4}})
    model_rect = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "a", "pdf_field_name": "bogus",
                     "pdf_position": dict(model_rect)}],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["unmatched"] == [{
        "field_id": "f", "option_value": "a",
        "reason": "pdf_field_name 'bogus' not found in dump"}]
    # the unreplaceable model rect survives -- a wrong overlay beats none
    assert schema["fields"][0]["options"][0]["pdf_position"] == model_rect


# --- _normalize_model_page_base (the no-widget fallback's page base) --------- #

def test_model_page_zero_base_is_shifted_not_discarded():
    """A model that mirrors the 0-based digest base is off by an ordinal
    convention, not wrong about geometry (maintainer decision 2026-07-29): if
    any model page is 0, shift every model page up by one."""
    schema = {"fields": [
        {"id": "a", "pdf_position": {"page": 0, "x": 1, "y": 2,
                                     "width": 3, "height": 4}},
        {"id": "b", "pdf_position": {"page": 1, "x": 5, "y": 6,
                                     "width": 7, "height": 8}},
        {"id": "c", "options": [{"value": "v", "pdf_position": {
            "page": 0, "x": 9, "y": 9, "width": 9, "height": 9}}]},
    ]}
    assert ef._normalize_model_page_base(schema) == 3
    assert schema["fields"][0]["pdf_position"]["page"] == 1
    assert schema["fields"][1]["pdf_position"]["page"] == 2
    assert schema["fields"][2]["options"][0]["pdf_position"]["page"] == 1


@pytest.mark.parametrize("raw", [0, 0.0, "0", " 0 ", "0.0", " 0.0 "])
def test_a_zero_page_normalizes_whatever_JSON_TYPE_it_arrives_as(raw):
    """THE BUG THIS BEAD EXISTS TO KILL, reachable through the fallback until now
    (bd polyglot-pdf-icyi, fresh-eyes Opus round).

    A model returns raw JSON, so a 0-based page can arrive as 0, 0.0 or "0" --
    all three mean page one under the model's base, and all three paint NOWHERE
    if they survive (the editor matches 1..numPages by exact equality, and
    PDFPosition coerces 0.0/"0" to a bare 0). The first version gated on
    `page == 0` (True for 0.0, False for "0") then shifted only `int`, so 0.0
    tripped the gate WITHOUT shifting and "0" did neither -- shipping an
    unnormalized page 0 silently, on the very code path added to prevent it. The
    skip was excused as "lint names it", which is false: no lint rule reads
    pdf_position at all."""
    schema = {"fields": [{"id": "a", "pdf_position": {
        "page": raw, "x": 1, "y": 2, "width": 3, "height": 4}}]}
    assert ef._normalize_model_page_base(schema) == 1
    # a REAL int, so downstream page matching (exact equality) works
    assert schema["fields"][0]["pdf_position"]["page"] == 1


@pytest.mark.parametrize("raw,want", [
    (0, 0), (0.0, 0), ("0", 0), (" 0 ", 0), ("0.0", 0), (" 0.0 ", 0),
    (1, 1), (1.0, 1), ("1", 1), ("1.0", 1), (3, 3), ("2.0", 2),
    # non-integral: no sane +1 exists
    ("abc", None), ("", None), (None, None), (1.5, None), ("1.5", None),
    (True, None), (False, None), ([], None), ({}, None),
])
def test_as_page_int_accepts_every_integral_json_form(raw, want):
    """The page-coercion contract, pinned directly (bd polyglot-pdf-icyi).

    Two rounds of review each found another integral shape escaping: first 0.0
    and "0" (the gate/shift type mismatch), then "0.0" (int() rejects a decimal
    string). Every escape shipped an unnormalized page 0, which paints NOWHERE.
    Enumerated here so the next shape has to be added deliberately."""
    assert ef._as_page_int(raw) == want


@pytest.mark.parametrize("raw", ["abc", None, 1.5, True, [], {}])
def test_a_non_integral_page_is_left_alone_and_never_crashes(raw):
    """Only INTEGRAL pages shift; anything else has no sane +1 and is left as-is
    (a second field carries the page 0 that arms the pass)."""
    schema = {"fields": [
        {"id": "junk", "pdf_position": {"page": raw, "x": 1, "y": 2,
                                        "width": 3, "height": 4}},
        {"id": "armer", "pdf_position": {"page": 0, "x": 1, "y": 2,
                                         "width": 3, "height": 4}},
    ]}
    ef._normalize_model_page_base(schema)          # must not raise
    assert schema["fields"][0]["pdf_position"]["page"] == raw
    assert schema["fields"][1]["pdf_position"]["page"] == 1


def test_an_ALIASED_position_dict_is_shifted_only_once():
    """One dict referenced from two fields must not shift twice -- two pages off
    is exactly the off-the-document failure the exempt set exists to prevent
    (fresh-eyes Opus round). Collection dedupes by identity."""
    shared = {"page": 0, "x": 1, "y": 2, "width": 3, "height": 4}
    schema = {"fields": [{"id": "a", "pdf_position": shared},
                         {"id": "b", "pdf_position": shared}]}
    assert ef._normalize_model_page_base(schema) == 1
    assert shared["page"] == 1


def test_model_pages_are_untouched_when_none_is_zero():
    """Already 1-based: shifting would push the last page off the document."""
    schema = {"fields": [{"id": "a", "pdf_position": {
        "page": 1, "x": 1, "y": 2, "width": 3, "height": 4}}]}
    assert ef._normalize_model_page_base(schema) == 0
    assert schema["fields"][0]["pdf_position"]["page"] == 1


def test_normalize_never_throws_on_junk():
    for junk in ({"fields": "nope"}, {"fields": [None, 5, "x"]}, {},
                 {"fields": [{"id": "a", "pdf_position": "not a dict"}]},
                 {"fields": [{"id": "a", "pdf_position": {"page": None}},
                             {"id": "b", "pdf_position": {"page": 0,
                                                          "x": 1, "y": 1,
                                                          "width": 1,
                                                          "height": 1}}]}):
        ef._normalize_model_page_base(junk)   # must not raise


def test_backfill_uses_first_option_widget_for_consolidated_field(tmp_path):
    """A consolidated options[] field (no top-level pdf_field_name) takes the rect
    of its first option's widget."""
    dump = _write_dump(tmp_path, {
        "opt1": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "radio",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
        "options": [{"value": "a", "pdf_field_name": "opt1"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # The field's own position AND its single option's position both resolve to
    # the same "opt1" widget rect (one join, both levels backfilled).
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": [],
         "model_pages_normalized": 0}
    # Full rect, incl. the page +1 (dump page 0 -> schema page 1).
    assert schema["fields"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}
    assert schema["fields"][0]["options"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}


def test_backfill_prefers_top_level_pdf_field_name_over_options(tmp_path):
    """When a field has BOTH a top-level pdf_field_name and options[], the
    top-level name wins (the options branch only runs when pfn is absent)."""
    dump = _write_dump(tmp_path, {
        "top": {"page": 0, "x": 10, "y": 10, "width": 8, "height": 8},
        "opt1": {"page": 0, "x": 99, "y": 99, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "f", "pdf_field_name": "top",
        "options": [{"value": "a", "pdf_field_name": "opt1"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # The field resolves via its own "top" name; the option independently
    # resolves via its own "opt1" name -- the two levels don't share a value.
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["pdf_position"]["x"] == 10  # top, not opt1
    assert schema["fields"][0]["options"][0]["pdf_position"]["x"] == 99  # opt1


def test_backfill_leaves_degenerate_when_no_dump_match(tmp_path):
    """If a degenerate field's pdf_field_name is absent from the dump, it stays
    degenerate (we can't do better) and is NOT counted as filled."""
    dump = _write_dump(tmp_path, {"other": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}})
    schema = {"fields": [{
        "id": "a", "pdf_field_name": "missing",
        "pdf_position": {"page": 1, "x": 0, "y": 0, "width": 0, "height": 0},
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result == {"fields_filled": 0, "options_filled": 0, "unmatched": [],
         "model_pages_normalized": 0}
    # bd polyglot-pdf-icyi: the degenerate placeholder is now REMOVED rather
    # than left in place. A zero-size rect is indistinguishable from a real
    # position to downstream consumers, so absence is the honest encoding --
    # the editor then reports "no position recorded for this field".
    assert "pdf_position" not in schema["fields"][0]


# --- option-level pdf_position back-fill (bd polyglot-pdf-5f41) -------------- #

def _write_widget_dump(tmp_path, fields):
    """Write a dump {fields:[{name, widgets:[{rect[, on_value]}, ...]}]}."""
    p = tmp_path / "dump.json"
    p.write_text(json.dumps({"fields": fields}), encoding="utf-8")
    return str(p)


def test_backfill_option_single_widget_via_own_pdf_field_name(tmp_path):
    """A radio option with its own pdf_field_name resolving to exactly ONE
    dump widget takes that widget's rect. Name resolution is suffix-aware
    (schema stores the XFA leaf, dump stores the fully-qualified path)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "form1[0].#subform[0].P1_checkbox4[0]",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ])
    schema = {"fields": [{
        "id": "p1_checkbox4", "type": "radio",
        "options": [{"value": "yes", "pdf_field_name": "P1_checkbox4[0]"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # fields_filled=1: the positionless field ALSO resolves via its first
    # option's widget (the pre-5f41 consolidated-field convention).
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["options"][0]["pdf_position"] == {
        "page": 1, "x": 1, "y": 2, "width": 8, "height": 8}


def test_backfill_option_multi_widget_disambiguated_by_on_value(tmp_path):
    """When an option's pdf_field_name resolves to SEVERAL dump widgets (a
    shared alias), pdf_on_value picks the matching widget's rect."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "shared[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 1, "width": 8, "height": 8}, "on_value": "1"},
            {"rect": {"page": 0, "x": 2, "y": 2, "width": 8, "height": 8}, "on_value": "2"},
        ]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "b", "pdf_field_name": "shared[0]", "pdf_on_value": "2"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # fields_filled=1: the positionless field takes the group's FIRST widget
    # (first-wins field convention); the option picks its on_value match.
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["options"][0]["pdf_position"]["x"] == 2


def test_backfill_shared_field_name_radio_group_by_on_value(tmp_path):
    """The documented shared-name radio-group shape (form_models.py
    FieldOption.pdf_on_value docstring): the option carries NO pdf_field_name of
    its own, only pdf_on_value, and the FIELD's pdf_field_name names the shared
    TOGGLE-widget group (each widget carries an on_value)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "P3_Line8_HeightFeet[0]", "widgets": [
            {"rect": {"page": 0, "x": 5, "y": 5, "width": 8, "height": 8}, "on_value": "2"},
            {"rect": {"page": 0, "x": 6, "y": 6, "width": 8, "height": 8}, "on_value": "3"},
        ]},
    ])
    schema = {"fields": [{
        "id": "p3_line8_heightfeet", "type": "select",
        "pdf_field_name": "P3_Line8_HeightFeet[0]",
        "options": [
            {"value": "2", "label": "2", "pdf_on_value": "2"},
            {"value": "3", "label": "3", "pdf_on_value": "3"},
        ],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 2
    assert result["unmatched"] == []
    opts = schema["fields"][0]["options"]
    assert opts[0]["pdf_position"]["x"] == 5
    assert opts[1]["pdf_position"]["x"] == 6


def test_option_dump_rect_also_wins_over_an_existing_position(tmp_path):
    """The OPTION level inverts with the field level (bd polyglot-pdf-icyi).

    This previously pinned the opposite ("LLM/human value wins when valid").
    Option rects are how the choice fields kept working through the page-0 bug,
    and they must stay deterministic for the same reason: the PDF's widget
    geometry is ground truth, and a model rect is at best a rounded copy."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "opt1", "widgets": [
            {"rect": {"page": 0, "x": 999, "y": 999, "width": 1, "height": 1}}]},
    ])
    stale = {"page": 1, "x": 10, "y": 20, "width": 8, "height": 8}
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "a", "pdf_field_name": "opt1", "pdf_position": dict(stale)}],
    }]}
    result = ef._backfill_positions(schema, dump)
    # BOTH levels now re-derive from the dump: the field takes the option's
    # widget rect (pre-5f41 convention) and the option takes its own.
    assert result == {"fields_filled": 1, "options_filled": 1, "unmatched": [],
         "model_pages_normalized": 0}
    assert schema["fields"][0]["options"][0]["pdf_position"] == {
        "page": 1, "x": 999, "y": 999, "width": 1, "height": 1}
    assert schema["fields"][0]["options"][0]["pdf_position"] != stale


def test_backfill_option_unmatched_bogus_name_is_reported_not_guessed(tmp_path):
    """An option whose pdf_field_name matches NOTHING in the dump is recorded in
    `unmatched` (field id, option value, reason) -- never guessed at (e.g. by
    falling back to some other option's widget)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "real[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "radio",
        "options": [{"value": "a", "pdf_field_name": "totally_bogus_name[0]"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert "pdf_position" not in schema["fields"][0]["options"][0]
    assert result["unmatched"] == [{
        "field_id": "f", "option_value": "a",
        "reason": "pdf_field_name 'totally_bogus_name[0]' not found in dump",
    }]


def test_backfill_dropdown_options_silently_skipped_not_unmatched(tmp_path):
    """A shared-name group whose widgets carry NO on_value is a dropdown
    (combobox/listbox -- real precedent: i-90's P3_Line8_HeightFeet /
    HeightInches selects): its options are choice VALUES of one shared widget,
    not separate printed boxes. They are silently skipped -- no option
    pdf_position, and NOT reported as unmatched (Preview keeps painting the
    selected label at the field-level rect)."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "P3_Line8_HeightFeet[0]", "widgets": [
            {"rect": {"page": 0, "x": 5, "y": 5, "width": 40, "height": 12}}]},
    ])
    schema = {"fields": [{
        "id": "p3_line8_heightfeet", "type": "select",
        "pdf_field_name": "P3_Line8_HeightFeet[0]",
        "options": [
            {"value": "2", "label": "2", "pdf_on_value": "2"},
            {"value": "3", "label": "3", "pdf_on_value": "3"},
        ],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert result["unmatched"] == []
    assert all("pdf_position" not in o for o in schema["fields"][0]["options"])


def test_backfill_shared_field_name_unmatched_on_value_is_reported(tmp_path):
    """Shared-name shape where NO widget in the group carries the option's
    pdf_on_value: reported in `unmatched`, not silently skipped or guessed."""
    dump = _write_widget_dump(tmp_path, [
        {"name": "grp[0]", "widgets": [
            {"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}, "on_value": "1"}]},
    ])
    schema = {"fields": [{
        "id": "f", "type": "select", "pdf_field_name": "grp[0]",
        "options": [{"value": "9", "label": "9", "pdf_on_value": "9"}],
    }]}
    result = ef._backfill_positions(schema, dump)
    assert result["options_filled"] == 0
    assert result["unmatched"] == [{
        "field_id": "f", "option_value": "9",
        "reason": "no widget in 'grp[0]' group with on_value '9'",
    }]


# --- _backfill_unclaimed_widgets (bd polyglot-pdf-w0eq, P6.1c) --------------- #

def _write_logical_dump(tmp_path, name_to_logical):
    """Minimal dump carrying per-widget logical_type + a rect."""
    dump = {"fields": [
        {"name": n, "logical_type": lt,
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]}
        for n, lt in name_to_logical.items()
    ]}
    p = tmp_path / "ldump.json"
    p.write_text(json.dumps(dump), encoding="utf-8")
    return str(p)

def test_backfill_adds_a_field_for_an_unclaimed_widget(tmp_path):
    """The core coverage fix: a fillable dump widget NO field claims is added
    back as a basic field with its dump rect. Section filing is NOT done here
    (bd 6cfu.2): the field carries a placeholder section_id='' and the derived-
    division pass (pipeline step 3e) re-files every field right after."""
    dump = _write_logical_dump(tmp_path, {
        "claimed[0]": "text", "orphan[0]": "text"})
    schema = {
        "fields": [{"id": "a", "type": "text", "pdf_field_name": "claimed[0]"}],
        "sections": [{"id": "sec1", "page_numbers": [1], "fields": ["a"]}],
    }
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    added = [f for f in schema["fields"] if f["pdf_field_name"] == "orphan[0]"]
    assert len(added) == 1
    assert added[0]["type"] == "text"
    assert added[0]["section_id"] == ""  # step 3e (derivation) re-files it
    assert added[0]["pdf_position"]["page"] == 1  # the rect derivation needs
    # Pre-existing sections are left alone -- derivation owns them now.
    assert schema["sections"] == [
        {"id": "sec1", "page_numbers": [1], "fields": ["a"]}]


def test_backfill_types_a_checkbox_widget_as_v2_boolean_no_options(tmp_path):
    """A recovered checkbox is a v2 standalone boolean: type=checkbox carrying its
    widget in pdf_field_name, and NO options (options are forbidden on a v2
    checkbox -- a group would be checkbox_group)."""
    dump = _write_logical_dump(tmp_path, {"box[0]": "checkbox"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["type"] == "checkbox"
    assert f["pdf_field_name"] == "box[0]"
    assert "options" not in f  # a v2 checkbox is a boolean, not an options field


def test_backfill_types_a_lone_radio_widget_as_a_v2_checkbox(tmp_path):
    """A lone recovered radio widget (one dump entry, single toggle) is modeled as
    a v2 boolean checkbox -- NOT a 1-option radio, which v2 rejects (radio needs
    >=2 options). This is the round-2 fresh-eyes fix: the old code minted an
    invalid single-option radio that failed FormSchema.model_validate."""
    dump = _write_logical_dump(tmp_path, {"r[0]": "radio"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["type"] == "checkbox"
    assert "options" not in f


def test_backfill_excludes_decorative_buttons(tmp_path):
    """A button widget (reset/print) is NOT a coverage defect -- never backfilled."""
    dump = _write_logical_dump(tmp_path, {"btn[0]": "button"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 0


def test_acroform_dumper_type_names_cover_every_widget_type():
    """The button exclusion (and every logical_type-keyed rule downstream) only
    works if the REAL dumper NAMES every widget type instead of falling through to
    "unknown(N)" (bd polyglot-pdf-f31h -- PDF_WIDGET_TYPE_BUTTON was the one
    missing, so real buttons became "unknown(1)" and would be backfilled as fake
    text fields). Enumerate fitz's PDF_WIDGET_TYPE_* constants and assert
    _TYPE_NAMES maps every one EXCEPT UNKNOWN -- so a future PyMuPDF widget-type
    addition fails HERE, loudly, instead of silently re-opening the bug class."""
    import sys
    sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))
    try:
        import acroform_dump
        import fitz
    except ImportError:
        pytest.skip("acroform_dump / fitz not importable")
    # Buttons specifically (the f31h regression) map to the literal "button".
    assert acroform_dump._TYPE_NAMES.get(fitz.PDF_WIDGET_TYPE_BUTTON) == "button"
    # Completeness: every PDF_WIDGET_TYPE_* constant except UNKNOWN is mapped.
    constants = {
        name: getattr(fitz, name)
        for name in dir(fitz) if name.startswith("PDF_WIDGET_TYPE_")
    }
    missing = [
        name for name, val in constants.items()
        if name != "PDF_WIDGET_TYPE_UNKNOWN" and val not in acroform_dump._TYPE_NAMES
    ]
    assert not missing, (
        "acroform_dump._TYPE_NAMES is missing a mapping for: "
        + ", ".join(sorted(missing))
        + " -- these widgets would become 'unknown(N)' and slip past every "
        "logical_type-keyed rule (bd f31h)"
    )


def test_backfill_recovers_dropdowns_using_real_dumper_strings(tmp_path):
    """The dumper emits "combobox"/"listbox"/"signature" (not "combo"/"list") --
    round-3 fresh-eyes flagged the dict keys were dead. A recovered dropdown /
    signature widget becomes a v2-valid text field."""
    dump = _write_logical_dump(tmp_path, {
        "cmb[0]": "combobox", "lst[0]": "listbox", "sig[0]": "signature"})
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 3
    assert all(f["type"] == "text" for f in schema["fields"])


def test_backfill_excludes_machine_barcodes(tmp_path):
    """A PDF417/QR barcode widget (read-only text, but machine-generated -- name
    carries the marker) is NOT a coverage defect. The bug caught pre-PR: i-90's
    hidden PDF417 barcodes were wrongly backfilled as fake text fields."""
    dump = {"fields": [
        {"name": "form1[0].Page1[0].PDF417BarCode1[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8},
                      "read_only": True, "tu": "PDF417BarCode1"}]},
    ]}
    p = tmp_path / "bc.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 0


def test_backfill_never_touches_sections(tmp_path):
    """The derived world (bd 6cfu.2): backfill neither creates nor edits
    sections -- no 'recovered_fields' bucket, no page_numbers bookkeeping.
    The recovered field carries section_id='' and derive_and_apply (step 3e)
    files it into a derived section (or the 'To review (unplaced)' bucket if
    it somehow has no position), so nothing is orphaned."""
    dump = _write_logical_dump(tmp_path, {"orphan[0]": "text"})
    schema = {"fields": []}  # no 'sections' key at all
    assert ef._backfill_unclaimed_widgets(schema, dump) == 1
    f = schema["fields"][0]
    assert f["section_id"] == ""
    assert "sections" not in schema  # untouched -- derivation owns sections


def test_backfilled_fields_always_validate_as_v2(tmp_path):
    """Every backfilled type (checkbox/text) must be VALID under v2 strictness --
    the round-2 fresh-eyes gap: a backfilled radio got 1 option and failed
    FormSchema.model_validate ('radio requires at least 2 options'), and combo/
    list -> select would likewise need options a bare widget can't supply. Pin
    that a mixed dump yields a valid v2 schema. Uses the REAL dumper logical_type
    strings (combobox/listbox/signature), so it exercises the actual mapping keys."""
    import warnings
    from backend.models.form_models import FormSchema
    dump = _write_logical_dump(tmp_path, {
        "cb[0]": "checkbox", "rad[0]": "radio", "txt[0]": "text",
        "combo[0]": "combobox", "list[0]": "listbox", "sig[0]": "signature"})
    schema = {
        "schema_version": "2", "source": "pdf",
        "form_metadata": {"title": "T", "version": "1"},
        "sections": [{"id": "s", "label": "S", "order": 1,
                      "page_numbers": [1], "fields": []}],
        "fields": [],
    }
    assert ef._backfill_unclaimed_widgets(schema, dump) == 6
    # No options-bearing type was minted (all valid with zero options).
    assert {f["type"] for f in schema["fields"]} <= {"checkbox", "text"}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        FormSchema.model_validate(schema)  # raises if any field is v2-invalid


def test_backfill_positions_recovered_fields_one_based(tmp_path):
    """Recovered fields carry 1-based pdf_position pages from the 0-based dump
    rects -- the join key the derived-division pass files them by (bd 6cfu.2)."""
    dump = {"fields": [
        {"name": "a[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
        {"name": "b[0]", "logical_type": "text",
         "widgets": [{"rect": {"page": 2, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": []}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 2
    assert sorted(f["pdf_position"]["page"] for f in schema["fields"]) == [1, 3]
    assert "sections" not in schema


def test_backfill_degenerate_leaf_falls_back_to_id_for_labels(tmp_path):
    """A widget name whose leaf is empty (ends in '.') still gets non-empty
    name/spoken_name (falls back to the minted id, never blank)."""
    dump = {"fields": [
        {"name": "weird.", "logical_type": "text",
         "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}]},
    ]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [], "sections": [{"id": "s", "page_numbers": [1], "fields": []}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 1
    f = schema["fields"][0]
    assert f["name"] and f["spoken_name"]  # never blank


def test_backfill_is_a_noop_when_all_widgets_claimed(tmp_path):
    dump = _write_logical_dump(tmp_path, {"a[0]": "text"})
    schema = {"fields": [{"id": "a", "type": "text", "pdf_field_name": "a[0]"}],
              "sections": [{"id": "s", "page_numbers": [1], "fields": ["a"]}]}
    assert ef._backfill_unclaimed_widgets(schema, dump) == 0


def test_backfill_claim_is_suffix_aware(tmp_path):
    """A field claiming the bare leaf 'x[0]' covers the fully-qualified dump name
    'topmostSubform[0].Page1[0].x[0]' -- so it is NOT re-backfilled."""
    dump = {"fields": [{
        "name": "topmostSubform[0].Page1[0].x[0]", "logical_type": "text",
        "widgets": [{"rect": {"page": 0, "x": 1, "y": 2, "width": 8, "height": 8}}],
    }]}
    p = tmp_path / "d.json"; p.write_text(json.dumps(dump), encoding="utf-8")
    schema = {"fields": [{"id": "a", "type": "text", "pdf_field_name": "x[0]"}],
              "sections": [{"id": "s", "page_numbers": [1], "fields": ["a"]}]}
    assert ef._backfill_unclaimed_widgets(schema, str(p)) == 0


# --- 3c2 completion + the late position pass (bd polyglot-pdf-u4r0) ---------- #

def _family_dump(tmp_path, leaf="P2_checkbox3", n=3, page=0):
    """A dump holding ONE minable checkbox family: same leaf, distinct [n].

    group_candidates.find_group_candidates only mines BUTTON widgets
    (logical_type checkbox/radio) sharing a leaf base on one page with distinct
    indexes, so the fixture has to carry logical_type -- a bare rect dump never
    triggers completion and would make this test vacuous.
    """
    fields = []
    for i in range(n):
        fields.append({
            "name": f"form1[0].#subform[0].{leaf}[{i}]",
            "logical_type": "checkbox",
            "widgets": [{
                "rect": {"page": page, "x": 100.0 + 20 * i, "y": 200.0,
                         "width": 10.0, "height": 10.0},
                "type": "checkbox",
                "on_value": f"on{i}",
            }],
        })
    p = tmp_path / "dump.json"
    p.write_text(json.dumps({"fields": fields}), encoding="utf-8")
    return str(p)


def _family_pdf(tmp_path, leaf="P2_checkbox3", n=3):
    """A real 1-page PDF carrying ONE minable checkbox family."""
    fitz = pytest.importorskip("fitz")
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(n):
        w = fitz.Widget()
        w.field_name = f"{leaf}[{i}]"
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect = fitz.Rect(100 + 20 * i, 200, 110 + 20 * i, 210)
        page.add_widget(w)
    out = tmp_path / "form.pdf"
    doc.save(str(out))
    doc.close()
    return str(out)


def test_extract_gives_family_completed_options_a_position(tmp_path, monkeypatch):
    """THE u4r0 DEFECT, driven through the REAL extract() stage order.

    Asserted at the pipeline level on purpose. A first draft of this test called
    _backfill_positions / _complete_grouped_families directly and asserted the
    result -- and DISABLING the real 3d2 step left it green, because the test
    was performing the fix itself rather than checking the pipeline performs it.
    That is the same vacuity trap bd polyglot-pdf-icyi hit twice, so this drives
    extract() with the model arm stubbed: the only thing that can make the
    appended options positioned is the pipeline's own late pass.

    Setup: the stub models only member [0] of a 3-widget family -- the
    partial-grouping shape 3c2 exists to complete (bd qmxb / 0nxh). Steps 3a/3d
    and the guidance/translation stages are off or naturally inert here.
    """
    pdf = _family_pdf(tmp_path)
    out = str(tmp_path / "schema.json")

    def _stub_run(pdf_path, dump_path, model, **kw):
        return {
            "form_metadata": {"title": "T", "form_number": "T-1",
                              "version": "1", "language": "en"},
            "fields": [{
                "id": "grp", "name": "Group", "spoken_name": "group",
                "type": "checkbox_group",
                "options": [{"value": "a", "label": "A",
                             "pdf_field_name": "P2_checkbox3[0]"}],
            }],
        }

    monkeypatch.setattr(ef.arm_llm_native, "run", _stub_run)
    ef.extract(pdf, out, translate_options=False, enrich_guidance=False)

    schema = json.loads(pathlib.Path(out).read_text(encoding="utf-8"))
    grp = next(f for f in schema["fields"] if f["id"] == "grp")
    opts = grp.get("options") or []
    assert len(opts) == 3, (
        f"family completion did not append the 2 missing members -- this test "
        f"would be vacuous: {[o.get('value') for o in opts]}")

    for opt in opts:
        pos = opt.get("pdf_position")
        assert pos, (
            f"option {opt.get('value')} shipped with NO pdf_position -- a "
            "positionless option disables per-option painting for the WHOLE "
            "field (valuePainting.ts is all-or-nothing)")
        assert pos["page"] == 1, f"page {pos['page']} is not 1-based"
        assert pos["width"] > 0 and pos["height"] > 0

    # each option took ITS OWN widget rect, not a sibling's
    xs = sorted(o["pdf_position"]["x"] for o in opts)
    assert xs == [100.0, 120.0, 140.0], f"options took the wrong rects: {xs}"
