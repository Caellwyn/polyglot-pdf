"""Tests for scripts/authoring/overlay_field_guesses.py (bd polyglot-pdf-3ave).

The overlay is the SECOND review surface for field<->widget assignment. Its
companion, check_line_binding.py, is exact but narrow -- it can only judge a
field that states a line number and claims a widget on a printed marker row, so
it abstains entirely on a form like W-7 that prints no gutter markers. The
overlay covers precisely that gap: it draws the extractor's own guess onto each
widget so a human or vision model can ask the semantic question ("is this
'signature' actually on a phone box?") no numbering scheme can answer.

These pin the mechanics -- what gets drawn, from which fields, and that a
coverage gap is visually distinct from a mislabel. The judgement itself is the
reviewer's; there is no assertion here about a form being 'correct'.

ASCII only.
"""

import importlib.util
import json
import pathlib
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "scripts" / "authoring" / "overlay_field_guesses.py"
spec = importlib.util.spec_from_file_location("overlay_field_guesses", _SCRIPT)
ov = importlib.util.module_from_spec(spec)
sys.modules["overlay_field_guesses"] = ov
spec.loader.exec_module(ov)

_W7_PDF = _REPO / "form-kits" / "w7" / "form.pdf"
_W7_SCHEMA = _REPO / "form-kits" / "w7" / "schema.json"

needs_w7 = pytest.mark.skipif(not _W7_PDF.exists(), reason="w7 kit not present")

# i-90 stores XFA LEAF names against fully-qualified widgets, so it is the only
# real fixture that exercises resolution end to end. READ-ONLY: never write into
# form-kits/ -- i-90 is the verified golden copy used for demos.
_I90_PDF = _REPO / "form-kits" / "i-90" / "form.pdf"
_I90_SCHEMA = _REPO / "form-kits" / "i-90" / "schema.json"
needs_i90 = pytest.mark.skipif(
    not _I90_PDF.exists(), reason="i-90 kit not present")

pytest.importorskip("fitz", reason="PyMuPDF required to render the overlay")


def _unmodeled_widget_count(schema, pdf_path=None):
    """How many of the PDF's widgets no field/option in `schema` claims.

    The w7 coverage gap is not a constant: it was 2 while the two "Other"
    write-ins (f1_04, f1_23) were deliberately unmodeled (bd ivh9), and is 0 now
    that the hand-verified gold models both (bd polyglot-pdf-edzu). Deriving it
    keeps these tests pinned to "the overlay agrees with the schema" rather than
    to a snapshot of how complete the schema happened to be (bd
    polyglot-pdf-lzyi).
    """
    import fitz  # already importorskip'd above

    claimed = set()
    for f in ov._iter_fields(schema):
        for name in [f.get("pdf_field_name")] + [
            o.get("pdf_field_name")
            for o in (f.get("options") or []) if isinstance(o, dict)
        ]:
            if isinstance(name, str) and name:
                claimed.add(name.split(".")[-1])

    doc = fitz.open(str(pdf_path or _W7_PDF))
    try:
        leaves = {w.field_name.split(".")[-1]
                  for page in doc for w in (page.widgets() or [])
                  if w.field_name}
    finally:
        doc.close()
    return len(leaves - claimed)


# --------------------------------------------------------------------------- #
# Which text gets drawn
# --------------------------------------------------------------------------- #

def test_label_mode_prefers_the_requested_key():
    f = {"id": "fld_x", "name": "Display Label", "spoken_name": "spoken label"}
    assert ov._label_for(f, "spoken") == "spoken label"
    assert ov._label_for(f, "name") == "Display Label"
    assert ov._label_for(f, "id") == "fld_x"


def test_label_falls_back_when_the_preferred_key_is_missing_or_blank():
    # spoken_name is the default mode; a blank one must not draw an empty plate.
    assert ov._label_for({"id": "fld_x", "spoken_name": "   "}, "spoken") == "fld_x"
    assert ov._label_for({"id": "fld_x"}, "spoken") == "fld_x"


def test_option_level_claims_are_drawn_with_their_value():
    """Choice fields carry their real widget identity on OPTIONS, not on the
    field -- if the overlay skipped those, every checkbox would look unclaimed."""
    schema = {"fields": [{
        "id": "reason", "spoken_name": "reason", "options": [
            {"value": "a_treaty", "pdf_field_name": "top.c1_2[0]"},
            {"value": "b_filing", "pdf_field_name": "top.c1_3[0]"},
        ],
    }]}
    claims = ov._claims(schema, "spoken")
    assert claims["top.c1_2[0]"] == ["reason=a_treaty"]
    assert claims["top.c1_3[0]"] == ["reason=b_filing"]


def test_claims_walk_nested_parts_and_sections():
    schema = {"parts": [{"sections": [{"fields": [
        {"id": "a", "spoken_name": "alpha", "pdf_field_name": "w1"},
    ]}]}]}
    assert ov._claims(schema, "spoken") == {"w1": ["alpha"]}


def test_groups_of_one_is_not_a_multiclaim():
    """A standalone checkbox restating its widget at BOTH field level and on its
    single option is the benign groups-of-one convention -- schema_lint
    explicitly carves it out (backend/services/schema_lint.py, _check_dump_claims).
    Flagging it orange would make the multiclaim signal lie."""
    schema = {"fields": [{
        "id": "cb", "spoken_name": "Checkbox", "pdf_field_name": "w9",
        "options": [{"value": "yes", "pdf_field_name": "w9"}],
    }]}
    assert ov._claims(schema, "spoken") == {"w9": ["Checkbox=yes"]}


def test_two_options_of_one_field_ARE_a_multiclaim():
    """schema_lint._check_dump_claims raises dump-widget-multiclaim for this too
    -- see backend/tests/test_schema_lint.py::test_dump_multiclaim_by_two_options
    _of_one_field, which calls it 'the shipped-f1040 class of bug' (selecting one
    option would tick both widgets). Keying on OWNER ALONE collapsed these into
    one entry and blinded the overlay to a live, separately-tested defect."""
    schema = {"fields": [{
        "id": "g", "spoken_name": "G", "options": [
            {"value": "x", "pdf_field_name": "W1"},
            {"value": "y", "pdf_field_name": "W1"},
        ],
    }]}
    assert ov._claims(schema, "spoken") == {"W1": ["G=x", "G=y"]}


def test_an_option_valued_field_does_not_collide_with_the_field_level_key():
    """`kind` must come from the option's INDEX, not its value. With a
    value-derived key, an option whose value is literally "field" produces the
    same key as the field-level claim and OVERWRITES it -- collapsing an
    option+option ERROR into a benign-looking single claim. Nothing else catches
    it: "field" is a legal option slug, so no lint rule fires on the value
    itself, while lint DOES raise dump-widget-multiclaim for the shape."""
    schema = {"fields": [{
        "id": "g", "spoken_name": "G", "pdf_field_name": "W1", "options": [
            {"value": "field", "pdf_field_name": "W1"},
            {"value": "other", "pdf_field_name": "W1"},
        ],
    }]}
    labels = ov._claims(schema, "spoken")["W1"]
    assert len(labels) > 1, "an option valued 'field' erased the multiclaim"
    assert "G=field" in labels and "G=other" in labels


def test_options_with_no_value_still_register_as_distinct_claimants():
    """Two valueless options on one widget are still an ERROR shape; the
    index-based key keeps them distinct even with nothing to display."""
    schema = {"fields": [{
        "id": "g", "spoken_name": "G", "options": [
            {"pdf_field_name": "W1"},
            {"pdf_field_name": "W1"},
        ],
    }]}
    assert len(ov._claims(schema, "spoken")["W1"]) == 2


def test_an_option_under_an_id_less_container_is_still_excluded():
    """The option-dict scan must recurse the RAW schema, not iterate the fields
    the walker yields: an options list can hang off a container with no `id`,
    which the walker skips. Those options were then missed by the exclusion and
    later yielded as fields, inventing a FALSE multiclaim against whatever else
    claims the widget."""
    schema = {"fields": [
        {"id": "Real", "spoken_name": "Real", "pdf_field_name": "W1"},
        {"group": {"options": [
            {"id": "o1", "value": "x", "pdf_field_name": "W1"},
        ]}},
    ]}
    assert ov._claims(schema, "spoken") == {"W1": ["Real"]}


def test_a_field_id_colliding_with_some_options_id_is_not_dropped():
    """The option-dict exclusion must key on object IDENTITY, not id string.
    Option ids are short generic slugs (`yes`, `no`, `other`), so a string-based
    exclusion silently dropped a genuine top-level field with a colliding id --
    rendering its widget as a FALSE coverage gap (blue)."""
    schema = {"fields": [
        {"id": "yes", "spoken_name": "Consent", "pdf_field_name": "WREAL"},
        {"id": "other", "spoken_name": "Other", "options": [
            {"id": "yes", "value": "y", "pdf_field_name": "WOPT"},
        ]},
    ]}
    claims = ov._claims(schema, "spoken")
    assert claims["WREAL"] == ["Consent"], "a real field vanished on an id collision"
    assert claims["WOPT"] == ["Other=y"]


def test_an_option_carrying_its_own_id_is_not_a_second_owner():
    """_iter_fields yields ANY dict with a string id, so an option with an `id`
    is also yielded as a field. Its claim belongs to the parent field -- counting
    it twice would invent a multiclaim that does not exist."""
    schema = {"fields": [{
        "id": "f1", "spoken_name": "F",
        "options": [{"id": "opt1", "value": "yes", "pdf_field_name": "w1"}],
    }]}
    assert ov._claims(schema, "spoken") == {"w1": ["F=yes"]}


def test_a_multiclaimed_widget_keeps_every_claimant():
    """Two fields claiming ONE widget is a real defect (dump-widget-multiclaim)
    and precisely the shape this overlay exists to surface. A first-wins collapse
    would draw a plausible single label and HIDE the collision."""
    schema = {"fields": [
        {"id": "a", "spoken_name": "A", "pdf_field_name": "w1"},
        {"id": "b", "spoken_name": "B", "pdf_field_name": "w1"},
    ]}
    assert ov._claims(schema, "spoken") == {"w1": ["A", "B"]}


@needs_w7
def test_a_multiclaim_is_counted_and_drawn_distinctly(tmp_path):
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    base = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "a.pdf"), "spoken")
    assert base["multiclaimed"] == 0  # the shipped gold is a clean bijection

    # Point a second field at a widget another field already claims.
    victim = next(f for f in ov._iter_fields(schema)
                  if isinstance(f.get("pdf_field_name"), str)
                  and f.get("pdf_field_name"))
    schema["fields"].append({
        "id": "intruder", "spoken_name": "intruder",
        "pdf_field_name": victim["pdf_field_name"],
    })
    after = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "b.pdf"), "spoken")
    assert after["multiclaimed"] == 1
    # It stays a labelled (drawn) widget -- a collision is not a coverage gap.
    assert after["unclaimed"] == base["unclaimed"]


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

@needs_w7
def test_renders_every_widget_and_reports_counts(tmp_path):
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    out = tmp_path / "review.pdf"
    result = ov.annotate(schema, str(_W7_PDF), str(out), "spoken")
    assert out.exists() and out.stat().st_size > 0
    # unclaimed == the widgets no field/option claims, and must match what the
    # schema actually leaves unmodeled. This asserted a literal 2 while the two
    # "Other" write-ins (f1_04, f1_23) were deliberately unmodeled (bd ivh9); the
    # gold now models BOTH -- reason_h_details claims f1_04, and
    # id_document_other_detail claims f1_23 -- which is exactly what bd
    # polyglot-pdf-edzu asked for. So the count is 0 because a coverage gap
    # CLOSED, not because resolution broke (bd polyglot-pdf-lzyi).
    assert result["unclaimed"] == _unmodeled_widget_count(schema)
    assert result["drawn"] > 0


@needs_w7
def test_an_unclaimed_widget_is_counted_separately_from_a_labelled_one(tmp_path):
    """Dropping a field must move exactly one widget from drawn -> unclaimed:
    a coverage gap and a mislabel are different bugs and must not look alike."""
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    base = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "a.pdf"), "spoken")

    dropped = None
    for f in list(ov._iter_fields(schema)):
        if isinstance(f.get("pdf_field_name"), str) and f.get("pdf_field_name"):
            dropped = f.pop("pdf_field_name")
            break
    assert dropped is not None
    after = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "b.pdf"), "spoken")
    assert after["unclaimed"] == base["unclaimed"] + 1
    assert after["drawn"] == base["drawn"] - 1


@needs_w7
def test_png_rasterization_is_opt_in(tmp_path):
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    no_png = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "a.pdf"), "spoken")
    assert no_png["pngs"] == []

    png_dir = tmp_path / "pages"
    with_png = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "b.pdf"),
                           "spoken", str(png_dir))
    assert with_png["pngs"]
    for p in with_png["pngs"]:
        assert pathlib.Path(p).exists()


def test_missing_schema_is_a_usage_error_not_a_crash(tmp_path, capsys):
    rc = ov.main(["--schema", str(tmp_path / "nope.json"),
                  "--pdf", str(_W7_PDF), "--out", str(tmp_path / "o.pdf")])
    capsys.readouterr()
    assert rc == 2


def test_an_unreadable_pdf_is_a_usage_error_not_a_traceback(tmp_path, capsys):
    """The docstring promises '2 = usage/IO error'; only the schema read was
    guarded, so a bad --pdf raised a raw traceback instead."""
    schema = tmp_path / "s.json"
    schema.write_text(json.dumps({"fields": []}), encoding="utf-8")
    rc = ov.main(["--schema", str(schema),
                  "--pdf", str(tmp_path / "does-not-exist.pdf"),
                  "--out", str(tmp_path / "o.pdf")])
    capsys.readouterr()
    assert rc == 2


@needs_w7
def test_an_unwritable_out_path_exits_two(tmp_path, capsys):
    """Goes through main() so the rc==2 WIRING is pinned, not just annotate()'s
    error dict -- the previous version asserted the dict only, so flipping
    main()'s `return 2` to 0 would not have failed it."""
    schema_path = tmp_path / "s.json"
    schema_path.write_text(_W7_SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    out = tmp_path / "no-such-dir" / "deep" / "o.pdf"  # parent does not exist
    rc = ov.main(["--schema", str(schema_path), "--pdf", str(_W7_PDF),
                  "--out", str(out)])
    capsys.readouterr()
    assert rc == 2


@needs_w7
def test_an_unwritable_png_dir_exits_two(tmp_path, capsys):
    """--png-dir runs AFTER the review PDF is saved; a failure there must still
    exit 2 rather than traceback on a half-completed run."""
    schema_path = tmp_path / "s.json"
    schema_path.write_text(_W7_SCHEMA.read_text(encoding="utf-8"), encoding="utf-8")
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("i am a file", encoding="utf-8")  # makedirs must fail
    rc = ov.main(["--schema", str(schema_path), "--pdf", str(_W7_PDF),
                  "--out", str(tmp_path / "o.pdf"), "--png-dir", str(blocker)])
    capsys.readouterr()
    assert rc == 2


# --------------------------------------------------------------------------- #
# Schema-name -> widget-name resolution (bd polyglot-pdf-wjxs)
# --------------------------------------------------------------------------- #

def test_a_leaf_claim_resolves_to_the_fully_qualified_widget():
    """Schemas may store the XFA LEAF while the PDF carries the full path. i-90
    does exactly this, and matching raw strings missed 146 of 189 claims --
    reported as 152 widgets falsely 'unclaimed' on a correctly bound kit."""
    claimants = {"P1_Line1_AlienNumber[0]": {("fld_a", "field"): "A"}}
    widgets = ["form1[0].#subform[0].P1_Line1_AlienNumber[0]", "other[0]"]
    out = ov._resolve_claimants(claimants, widgets)
    assert list(out) == ["form1[0].#subform[0].P1_Line1_AlienNumber[0]"]


def test_resolution_requires_a_DOT_boundary():
    """A bare endswith would let 'x_name[0]' claim 'prefix_x_name[0]'. Same
    convention as schema_lint._match_dump_names and pdf_fill_routes.find_widget."""
    claimants = {"name[0]": {("fld_a", "field"): "A"}}
    assert ov._resolve_claimants(claimants, ["prefix_name[0]"]) == {
        "name[0]": {("fld_a", "field"): "A"}  # unresolved: kept, draws nothing
    }
    assert list(ov._resolve_claimants(claimants, ["a.name[0]"])) == ["a.name[0]"]


def test_one_claim_labels_EVERY_widget_it_resolves_to():
    """A leaf repeated across pages (a signature block on each page, say) matches
    several fully-qualified widgets, and all of them belong to that field -- so
    all of them get labelled.

    Pinned because no shipped kit has a repeated leaf today, so nothing else
    exercises it: truncating the fan-out to the first match left all 27 tests AND
    all three real kits green. The rule would be missing exactly when a future
    kit first needs it.
    """
    claimants = {"P1_Signature[0]": {("sig", "field"): "Signature"}}
    widgets = ["form1[0].Page1[0].P1_Signature[0]",
               "form1[0].Page2[0].P1_Signature[0]",
               "form1[0].Page1[0].Other[0]"]
    out = ov._resolve_claimants(claimants, widgets)
    assert sorted(out) == ["form1[0].Page1[0].P1_Signature[0]",
                           "form1[0].Page2[0].P1_Signature[0]"]
    for labels in out.values():
        assert labels == {("sig", "field"): "Signature"}


def test_an_exact_match_wins_over_a_suffix_match():
    claimants = {"f[0]": {("fld_a", "field"): "A"}}
    out = ov._resolve_claimants(claimants, ["f[0]", "sub.f[0]"])
    assert list(out) == ["f[0]"]


@needs_i90
def test_annotate_ITSELF_resolves_before_collapsing(tmp_path):
    """The bead's central invariant, asserted where it actually matters.

    The helper-level test below composes the call order by hand, so it proves the
    two helpers compose correctly but CANNOT see annotate() calling them the
    wrong way round -- reverting annotate() to collapse-then-resolve left all 26
    tests green while i-90 regressed to 1 false multiclaim. This closes that:
    i-90 writes P7_checkbox7Extend[0]'s field claim as the full path and its
    single option as the bare leaf, so collapsing first splits the benign
    groups-of-one pair and re-merges it into a phantom collision.

    Reads the kit; writes only to tmp_path (form-kits/ is read-only).
    """
    schema = json.loads(_I90_SCHEMA.read_text(encoding="utf-8"))
    result = ov.annotate(schema, str(_I90_PDF), str(tmp_path / "review.pdf"))

    assert result["multiclaimed"] == 0, (
        "a correctly-bound widget was flagged as multiclaimed -- annotate() is "
        "collapsing before it resolves")
    # ...and resolution genuinely happened: without it this kit reports 43
    # labelled / 152 unclaimed instead.
    assert result["drawn"] == 188
    assert result["unclaimed"] == 7


def test_resolution_happens_BEFORE_the_multiclaim_collapse():
    """The ordering bug this fix originally introduced. A field-level claim and
    its option-level twin can be written as two DIFFERENT schema strings that
    resolve to the SAME widget -- the benign groups-of-one carve-out can only see
    that once they share a key. Collapsing first re-creates the pair afterwards
    and reports a false multiclaim: i-90's P7_checkbox7Extend[0] did exactly
    that until resolution moved ahead of the collapse."""
    claimants = {
        # field level, written as the full path...
        "form1[0].#subform[5].P7_checkbox7Extend[0]": {("cb", "field"): "cb"},
        # ...and the option, written as the bare leaf.
        "P7_checkbox7Extend[0]": {("cb", "option[0]"): "cb=yes"},
    }
    widgets = ["form1[0].#subform[5].P7_checkbox7Extend[0]"]
    collapsed = ov._collapse_claimants(ov._resolve_claimants(claimants, widgets))
    assert collapsed == {"form1[0].#subform[5].P7_checkbox7Extend[0]": ["cb=yes"]}, \
        "the benign groups-of-one pair was re-created as a multiclaim"


def test_a_genuine_multiclaim_still_survives_resolution():
    """Two DIFFERENT fields whose distinct schema strings resolve to one widget
    must still merge into a flagged collision -- resolution must not hide it."""
    claimants = {
        "A[0]": {("fld_a", "field"): "A"},
        "sub.A[0]": {("fld_b", "field"): "B"},
    }
    widgets = ["sub.A[0]"]
    collapsed = ov._collapse_claimants(ov._resolve_claimants(claimants, widgets))
    assert sorted(collapsed["sub.A[0]"]) == ["A", "B"]


@needs_w7
def test_resolution_leaves_a_fully_qualified_kit_unchanged(tmp_path):
    """w7 already stores fully-qualified names, so resolution must be a no-op
    there -- the guard that this fix helps i-90 without disturbing the others.

    Output goes to tmp_path: form-kits/ is READ-ONLY (maintainer constraint --
    i-90 in particular is the verified golden copy used for demos)."""
    schema = json.loads(_W7_SCHEMA.read_text(encoding="utf-8"))
    result = ov.annotate(schema, str(_W7_PDF), str(tmp_path / "review.pdf"))
    # Derived, not a literal: what this test guards is that resolution is a
    # NO-OP on an already-fully-qualified kit, so the overlay's coverage must
    # equal the schema's own -- whatever that happens to be. (It was 2 unmodeled
    # write-ins under bd ivh9; the gold now models both, bd polyglot-pdf-edzu.)
    assert result["unclaimed"] == _unmodeled_widget_count(schema)
    assert result["multiclaimed"] == 0
