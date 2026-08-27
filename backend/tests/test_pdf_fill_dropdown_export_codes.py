"""End-to-end: a dropdown's option.value must PRINT correctly (bd polyglot-pdf-4we6j).

A select has no fill branch of its own -- it falls to the scalar path, so the
filler writes str(option.value) verbatim into the combobox and never consults
pdf_on_value. PyMuPDF does NOT validate that write against the widget's /Opt
choice list, so any string is accepted silently and then clipped by the box at
render time. That is the same shape as the comb bug (bd br7t): the stored value
round-trips perfectly while the printed page is wrong.

So these tests assert on RENDERED text (page.get_text over the widget rect),
never on widget.field_value -- reading the value back is exactly the check this
class of bug defeats.

Drives the REAL /fill-pdf route against the on-disk i-90_v2 kit, using the
kit's OWN schema_edited.json (the artifact the editor publishes), so a
regression in the lint/repair carve-out that let a slug back into .value would
surface here as a mis-printed form rather than as a green unit test.

ASCII only.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf

# The kit is GITIGNORED, so in a worktree it exists only in the main checkout.
# Resolve the repo root via the git common dir (the main checkout's .git) and
# fall back to the plain parent walk, so this runs from either location rather
# than skipping silently -- a skip here reads as "green" while proving nothing.
def _kit_root() -> Path:
    here = Path(__file__).resolve()
    candidates = [here.parents[2]]
    try:
        import subprocess
        common = subprocess.run(
            ["git", "-C", str(here.parents[2]),
             "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, timeout=15,
        ).stdout.strip()
        if common:
            candidates.append(Path(common).parent)
    except Exception:
        pass
    for root in candidates:
        if (root / "form-kits" / "i-90_v2" / "form.pdf").exists():
            return root / "form-kits" / "i-90_v2"
    return candidates[0] / "form-kits" / "i-90_v2"


_KIT_ROOT = _kit_root()
_SCHEMA = _KIT_ROOT / "schema_edited.json"

pytestmark = pytest.mark.skipif(
    not (_KIT_ROOT / "form.pdf").exists() or not _SCHEMA.exists(),
    reason="i-90_v2 kit not present (gitignored; lives in the main checkout)",
)

# Mailing-address state: a 36x18pt combobox that can hold "WY" but not
# "wyoming" -- the measured case from the bead.
_STATE_FIELD = "mail_state"
_STATE_SUFFIX = "P1_Line6e_State[0]"


def _schema() -> dict:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def _widget_by_suffix(doc, suffix: str):
    for pno in range(doc.page_count):
        for w in doc[pno].widgets() or []:
            if w.field_name and w.field_name.endswith(suffix):
                return w, doc[pno]
    return None, None


def _rendered_text(pdf_bytes: bytes, suffix: str) -> str:
    """The text actually PRINTED inside the widget's box."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        widget, page = _widget_by_suffix(doc, suffix)
        assert widget is not None, f"widget {suffix} not found in the filled PDF"
        raw = page.get_text("text", clip=widget.rect)
    finally:
        doc.close()
    return "".join(raw.split())


@pytest.fixture(autouse=True)
def _point_the_kit_store_at_this_kit(monkeypatch):
    """The kit store resolves FORM_KITS_LOCAL_ROOT, which defaults to the
    CHECKOUT's form-kits/. In a worktree that directory does not hold this
    (gitignored) kit, so the route 404s. Point the store at wherever the kit
    actually is, and clear the settings cache so the override takes effect
    (get_settings is lru_cached).
    """
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")

    # Settings is a plain BaseModel whose field defaults call os.getenv at
    # CLASS-DEFINITION time, so setting the env var here is too late and
    # cache_clear() cannot help -- patch the resolved value on the instance.
    # Both lru_caches must be cleared too: the store is built FROM settings,
    # so clearing only settings leaves the old store in place.
    from backend.config import get_settings
    from backend.services.form_kits import get_form_kit_store

    for cached in (get_settings, get_form_kit_store):
        cached.cache_clear()
    monkeypatch.setattr(
        get_settings(), "FORM_KITS_LOCAL_ROOT", str(_KIT_ROOT.parent),
        raising=True,
    )
    monkeypatch.setattr(get_settings(), "FORM_KITS_MODE", "local", raising=True)
    get_form_kit_store.cache_clear()
    yield
    for cached in (get_settings, get_form_kit_store):
        cached.cache_clear()


def _fill(field_values: dict) -> bytes:
    resp = asyncio.run(fill_pdf(PDFFillRequest(
        kit_id="i-90_v2",
        pdf_filename="form.pdf",
        field_values=field_values,
        form_schema=_schema(),
    )))
    assert resp.status_code == 200
    return resp.body


def _options(field_id: str) -> list:
    """This field's options, read from the schema's top-level fields[] only.

    Deliberately NOT a recursive walk: an id-colliding node elsewhere in the
    schema (_ignored_fields, supplements, _bakeoff) would otherwise be picked
    up by iteration order and silently validate the WRONG field's options.
    Scoped to fields[] -- the list the filler actually resolves against -- and
    asserts the id is unique there, so an ambiguity fails loudly instead.
    """
    fields = _schema().get("fields") or []
    hits = [f for f in fields
            if isinstance(f, dict) and f.get("id") == field_id]
    assert len(hits) == 1, (
        "expected exactly one top-level field with id=%r, found %d"
        % (field_id, len(hits))
    )
    return hits[0].get("options") or []


def test_source_state_widget_is_a_combobox_that_cannot_hold_a_full_name():
    """Precondition -- without it these tests could pass without exercising
    anything: the box must be too narrow for a spelled-out state name."""
    doc = fitz.open(str(_KIT_ROOT / "form.pdf"))
    try:
        widget, _ = _widget_by_suffix(doc, _STATE_SUFFIX)
        assert widget is not None
        assert widget.field_type_string == "ComboBox"
        assert widget.rect.width <= 40, widget.rect.width
    finally:
        doc.close()


def test_every_state_option_prints_its_code_in_full():
    """The headline property, over the WHOLE option set rather than a sample.

    Each option's stored value is written verbatim, so every one of them must
    render intact. A carve-out regression that let a minted slug
    ('wyoming_wy') back into .value shows up here as clipped output.
    """
    options = _options(_STATE_FIELD)
    assert len(options) >= 50, f"expected the full state list, got {len(options)}"

    clipped = []
    for opt in options:
        value = opt["value"]
        printed = _rendered_text(_fill({_STATE_FIELD: value}), _STATE_SUFFIX)
        if printed != value:
            clipped.append((value, printed))
    assert not clipped, (
        "these dropdown values did not print intact (stored fine, rendered "
        "wrong -- the silent failure mode): %r" % clipped[:10]
    )


def test_a_spelled_out_state_name_would_print_clipped():
    """Pins the FAILURE this design prevents, so the guard above cannot go
    vacuous: if the box ever grew wide enough to hold 'wyoming', the test
    above would stop proving anything and this one goes red to say so.
    """
    printed = _rendered_text(_fill({_STATE_FIELD: "wyoming"}), _STATE_SUFFIX)
    assert printed != "wyoming", (
        "the state box now fits a full name; the export-code requirement (and "
        "the test above) no longer proves what it claims -- re-derive it"
    )


def test_ignored_field_selects_would_also_pass_the_gate_if_promoted():
    """The kit has 6 select fields, but 2 (interp_state, prep_state) live under
    _ignored_fields, which lint and repair never walk.

    Those two therefore pass "lints clean" VACUOUSLY -- not because the
    carve-out protects them. If they are ever promoted back into fields[]
    (they are real interpreter/preparer address fields), that promotion would
    be the first time their option values pass through this logic. Pin it now,
    so a promotion cannot silently reintroduce 124 blocking errors.
    """
    schema = _schema()
    promoted = json.loads(json.dumps(schema))
    extra = [
        e["field"] for e in promoted.get("_ignored_fields", [])
        if isinstance(e, dict) and isinstance(e.get("field"), dict)
        and e["field"].get("type") == "select"
    ]
    assert len(extra) == 2, (
        "expected interp_state + prep_state under _ignored_fields, got %r"
        % [f.get("id") for f in extra]
    )
    promoted["fields"].extend(extra)

    from backend.services.schema_lint import SEVERITY_ERROR, lint_schema
    dump = json.loads(
        (_KIT_ROOT / "tmpalrg958q_acroform.json").read_text(encoding="utf-8"))
    errors = [f for f in lint_schema(promoted, dump)
              if f.severity == SEVERITY_ERROR]
    assert not errors, (
        "promoting the ignored selects would block the publish gate: %r"
        % [(f.rule, f.path) for f in errors[:5]]
    )


def test_height_dropdowns_print_their_codes():
    """The other two selects on this form, so the property covers every
    dropdown the kit actually has, not just the state ones."""
    for field_id, suffix in (
        ("height_feet", "P3_Line8_HeightFeet[0]"),
        ("height_inches", "P3_Line8_HeightInches[0]"),
    ):
        options = _options(field_id)
        assert options, f"{field_id} has no options"
        for opt in options:
            value = opt["value"]
            printed = _rendered_text(_fill({field_id: value}), suffix)
            assert printed == value, (
                f"{field_id}={value!r} printed as {printed!r}"
            )
