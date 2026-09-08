"""A SELECT fills its combobox from option.pdf_on_value (bd polyglot-pdf-g2fpr).

The v2 contract says option.value is a semantic slug and widget identity lives
in pdf_on_value. Radios implemented that; selects never did -- the filler wrote
str(value) verbatim, so a select's value HAD to be the PDF export code, and a
slug printed clipped ('wyoming' -> 'wyomin'). This gives selects the channel.

Asserted on RENDERED text (page.get_text over the widget rect), never on the
stored field_value: a wrong string stores fine and only the render shows it.

CI-runnable: builds its own combobox with fitz in a temp kit dir, so it does not
depend on the gitignored i-90_v2 kit the sibling test needs.

ASCII only.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

from backend.routes.pdf_fill_routes import PDFFillRequest, fill_pdf  # noqa: E402

_KIT = "g2fpr_kit"
_WIDGET = "state[0]"
_CODES = ["AL", "AK", "WY"]


def _build_kit(root: Path) -> None:
    """One combobox, 36x18pt like the i-90 state box, /Opt = bare codes."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    w = fitz.Widget()
    w.field_name = _WIDGET
    w.field_type = fitz.PDF_WIDGET_TYPE_COMBOBOX
    w.choice_values = list(_CODES)
    w.rect = fitz.Rect(100, 200, 136, 218)
    page.add_widget(w)
    kit = root / _KIT
    kit.mkdir(parents=True)
    doc.save(str(kit / "form.pdf"))
    doc.close()


def _schema(options: list) -> dict:
    return {
        "form_metadata": {"title": "T", "form_number": "T-1", "version": "1",
                          "language": "en"},
        "fields": [{"id": "state", "name": "state", "spoken_name": "state",
                    "type": "select", "pdf_field_name": _WIDGET,
                    "options": options}],
        "sections": [{"id": "s", "label": "S", "order": 1, "fields": ["state"]}],
    }


NEW_SHAPE = [{"value": "alabama", "label": "Alabama (AL)", "pdf_on_value": "AL"},
             {"value": "alaska", "label": "Alaska (AK)", "pdf_on_value": "AK"},
             {"value": "wyoming", "label": "Wyoming (WY)", "pdf_on_value": "WY"}]
LEGACY_SHAPE = [{"value": c, "label": c} for c in _CODES]


@pytest.fixture
def kit_root(tmp_path, monkeypatch):
    _build_kit(tmp_path)
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")
    from backend.config import get_settings
    from backend.services.form_kits import get_form_kit_store
    for cached in (get_settings, get_form_kit_store):
        cached.cache_clear()
    monkeypatch.setattr(get_settings(), "FORM_KITS_LOCAL_ROOT", str(tmp_path),
                        raising=True)
    monkeypatch.setattr(get_settings(), "FORM_KITS_MODE", "local", raising=True)
    get_form_kit_store.cache_clear()
    yield tmp_path
    for cached in (get_settings, get_form_kit_store):
        cached.cache_clear()


def _fill(schema: dict, value: str) -> bytes:
    resp = asyncio.run(fill_pdf(PDFFillRequest(
        kit_id=_KIT, pdf_filename="form.pdf",
        field_values={"state": value}, form_schema=schema)))
    assert resp.status_code == 200, resp.body
    return resp.body


def _rendered(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for pno in range(doc.page_count):
            for w in doc[pno].widgets() or []:
                if w.field_name and w.field_name.endswith(_WIDGET):
                    return "".join(doc[pno].get_text("text", clip=w.rect).split())
    finally:
        doc.close()
    raise AssertionError("widget not found in the filled PDF")


def test_read_back_distinguishes_a_slug_from_a_code(kit_root):
    """Non-vacuity floor for everything below. A fitz-built box renders a
    whole slug (it fits its own appearance stream to the text), so the
    discriminator here is not clipping but IDENTITY: a select filled with the
    slug in the LEGACY shape prints the slug -- the very defect -- and never
    the code. If this ever printed 'AL', the criterion tests below would be
    proving nothing."""
    printed = _rendered(_fill(_schema(LEGACY_SHAPE), "alabama"))
    assert printed == "alabama"
    assert printed != "AL"


@pytest.mark.parametrize("slug,code", [("alabama", "AL"), ("alaska", "AK"),
                                       ("wyoming", "WY")])
def test_a_slug_valued_select_prints_its_pdf_on_value(kit_root, slug, code):
    """EXIT CRITERION 1. value is a slug, pdf_on_value is the code: the CODE
    prints. Parametrized over the whole option set, not a sample."""
    assert _rendered(_fill(_schema(NEW_SHAPE), slug)) == code


@pytest.mark.parametrize("code", _CODES)
def test_the_legacy_shape_still_prints_its_code(kit_root, code):
    """A kit not yet migrated (code in value, no pdf_on_value) must keep
    working mid-rollout -- the fallback is value verbatim."""
    assert _rendered(_fill(_schema(LEGACY_SHAPE), code)) == code


def test_an_empty_pdf_on_value_falls_back_to_the_value(kit_root):
    opts = [{"value": "AL", "label": "AL", "pdf_on_value": ""}]
    assert _rendered(_fill(_schema(opts), "AL")) == "AL"


def test_a_value_matching_no_option_is_written_verbatim_and_warned(kit_root, monkeypatch):
    """The stale-session shape: a pre-migration 'AL' resumed against a schema
    whose values are now slugs. It prints right here only because the old
    value equals the new pdf_on_value -- luck, not design -- so the filler must
    say so loudly. Never logs the value (bd hjo).

    Records the warning by replacing the module logger, not via
    structlog.testing.capture_logs: under the FULL suite an earlier test
    configures structlog with a cached logger, the capture processor never
    sees the call, and this test went green-in-isolation / red-in-suite.
    """
    from backend.routes import pdf_fill_routes as mod
    calls: list = []

    class _Rec:
        def warning(self, event, **kw):
            calls.append((event, kw))
        def __getattr__(self, name):          # debug/info/error: passthrough no-ops
            return lambda *a, **k: None

    monkeypatch.setattr(mod, "_log", _Rec())
    printed = _rendered(_fill(_schema(NEW_SHAPE), "AL"))
    assert printed == "AL"
    hits = [kw for ev, kw in calls if ev == "select_value_not_an_option"]
    assert len(hits) == 1, calls
    assert hits[0]["field_id"] == "state"
    assert hits[0]["option_count"] == 3
    # The VALUE must not appear anywhere in the event (bd hjo).
    assert "AL" not in {str(v) for k, v in hits[0].items() if k != "kit"}


def test_radio_and_text_paths_are_untouched(kit_root):
    """The select branch is scoped by type: a text field with the same widget
    still writes its value verbatim (the resolver must not run for it)."""
    schema = _schema(LEGACY_SHAPE)
    schema["fields"][0]["type"] = "text"
    del schema["fields"][0]["options"]
    assert _rendered(_fill(schema, "AK")) == "AK"


def test_legacy_plain_string_options_print_and_do_NOT_warn(kit_root, monkeypatch):
    """The second live option shape: options: ["AL", "AK", "WY"], where the
    string IS the value (schema_lint's optionValue() contract). Fresh-eyes
    (g2fpr.1) caught the dict-only match treating EVERY fill of such a select
    as a stale session -- a false warning on a working kit. It prints its
    code and stays silent."""
    from backend.routes import pdf_fill_routes as mod
    calls: list = []

    class _Rec:
        def warning(self, event, **kw):
            calls.append(event)
        def __getattr__(self, name):
            return lambda *a, **k: None

    monkeypatch.setattr(mod, "_log", _Rec())
    schema = _schema(list(_CODES))          # plain strings, not dicts
    assert _rendered(_fill(schema, "AK")) == "AK"
    assert "select_value_not_an_option" not in calls


@pytest.mark.parametrize("order", ["string-first", "dict-first"])
def test_a_mixed_shape_list_prefers_the_dict_match_whatever_the_order(order):
    """Fresh-eyes (g2fpr.1 round 2): the first string-option fix RETURNED on the
    first string hit, so ["AL", {"value": "AL", "pdf_on_value": "ZZ"}] resolved
    to "AL" while the reversed list resolved to "ZZ" -- an answer that depended
    on element order. A mixed-shape list is already anomalous (both models type
    options as homogeneous), but the resolver must not be order-sensitive.
    Pure-function check, both orders."""
    from backend.routes.pdf_fill_routes import resolve_select_fill_value
    d = {"value": "AL", "label": "Alabama (AL)", "pdf_on_value": "ZZ"}
    options = ["AL", d] if order == "string-first" else [d, "AL"]
    assert resolve_select_fill_value({"options": options}, "AL") == "ZZ"


# ---------------------------------------------------------------------------
# The READ side: /resume-form must invert the fill (cross-surface, g2fpr.1)
# ---------------------------------------------------------------------------
#
# The Opus cross-surface pass found the write side transformed and the read
# side verbatim: resume handed the PDF's export code ('AL') back as the field
# value, so a migrated select rendered EMPTY, marked confirmed, never re-asked,
# and the secretary read "AL" aloud. Three fresh-eyes rounds could not see it
# because no CI-present kit has a select -- test_resume_form_route's whole-form
# guarantee iterates w7/i-90/f1040, and w7/f1040 have zero selects while i-90
# skips. This is the CI-present select round-trip that guarantee could not be.

import base64

from backend.routes.pdf_fill_routes import ResumeUploadRequest, resume_form  # noqa: E402


def _publish_kit(root: Path, schema: dict) -> None:
    """resume_form loads the kit's OWN schema and live metadata (it never
    trusts an uploaded schema), so the temp kit needs both on disk."""
    kit = root / _KIT
    (kit / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit / "metadata.json").write_text(json.dumps({
        "kit_id": _KIT, "status": "complete", "pdf": "form.pdf",
        "schema": "schema.json",
    }), encoding="utf-8")


def _resume(pdf_bytes: bytes) -> dict:
    from backend.services.form_kits import get_form_kit_store
    get_form_kit_store.cache_clear()
    user = {"uid": None, "firm_id": "firm-a", "link_kit_id": _KIT,
            "is_client_link": True}
    return asyncio.run(resume_form(ResumeUploadRequest(
        kit_id=_KIT, pdf_filename="form.pdf",
        pdf_base64=base64.b64encode(pdf_bytes).decode("ascii")), user=user))


@pytest.mark.parametrize("slug", ["alabama", "alaska", "wyoming"])
def test_resume_hands_back_the_SLUG_not_the_export_code(kit_root, slug):
    """fill -> PDF -> resume must round-trip option.value, over the whole set."""
    schema = _schema(NEW_SHAPE)
    _publish_kit(kit_root, schema)
    pdf = _fill(schema, slug)
    assert _rendered(pdf) != slug, "floor: the PDF must hold the CODE, not the slug"
    resumed = _resume(pdf)
    assert resumed["field_values"]["state"] == slug


def test_resume_of_a_legacy_kit_returns_the_code_because_that_IS_its_value(kit_root):
    schema = _schema(LEGACY_SHAPE)
    _publish_kit(kit_root, schema)
    resumed = _resume(_fill(schema, "AK"))
    assert resumed["field_values"]["state"] == "AK"


def test_resume_inverse_is_pure_and_falls_back_verbatim():
    """The helper on its own: a code no option claims comes back untouched
    (the filler will then warn on it -- the stale-session shape)."""
    from backend.routes.pdf_fill_routes import resolve_select_resume_value
    opts = [{"value": "alabama", "pdf_on_value": "AL"}, "AK"]
    assert resolve_select_resume_value(opts, "AL") == "alabama"
    assert resolve_select_resume_value(opts, "AK") == "AK"      # string option
    assert resolve_select_resume_value(opts, "ZZ") == "ZZ"      # unclaimed
    assert resolve_select_resume_value(None, "AL") == "AL"      # no options


def test_resume_inverse_refuses_to_guess_between_options_sharing_a_code():
    """Cross-surface round 2 (bd polyglot-pdf-7dvpp): no gate enforces
    pdf_on_value uniqueness, and the migration copies /Opt codes verbatim, so
    two options CAN claim one code. Picking the first would resume the client
    with a choice they never made -- the radio arm drops on that ambiguity,
    and so must this."""
    from backend.routes.pdf_fill_routes import resolve_select_resume_value
    opts = [{"value": "alabama", "pdf_on_value": "AL"},
            {"value": "alabama_northern", "pdf_on_value": "AL"}]
    assert resolve_select_resume_value(opts, "AL") is None
    # A unique claimant still resolves; the ambiguity is per-code.
    opts.append({"value": "alaska", "pdf_on_value": "AK"})
    assert resolve_select_resume_value(opts, "AK") == "alaska"


def test_resume_DROPS_a_select_whose_code_is_claimed_twice_and_warns(kit_root, monkeypatch):
    """End to end: the kit publishes with the collision (nothing stops it
    today), the client picked the SECOND option, the PDF holds 'AL' -- resume
    must not hand back the first option marked confirmed. It drops the field
    and logs resume_conflicting_options, exactly as a several-ticked radio."""
    from backend.routes import pdf_fill_routes as mod
    calls: list = []

    class _Rec:
        def warning(self, event, **kw):
            calls.append((event, kw))
        def __getattr__(self, name):
            return lambda *a, **k: None

    colliding = [{"value": "alabama", "label": "Alabama", "pdf_on_value": "AL"},
                 {"value": "alabama_northern", "label": "Alabama (Northern)",
                  "pdf_on_value": "AL"},
                 {"value": "alaska", "label": "Alaska", "pdf_on_value": "AK"}]
    schema = _schema(colliding)
    _publish_kit(kit_root, schema)
    pdf = _fill(schema, "alabama_northern")
    assert _rendered(pdf) == "AL"                       # floor: the PDF holds the code
    monkeypatch.setattr(mod, "_log", _Rec())
    resumed = _resume(pdf)
    assert "state" not in resumed["field_values"], resumed["field_values"]
    events = [e for e, _ in calls]
    assert "resume_conflicting_options" in events
