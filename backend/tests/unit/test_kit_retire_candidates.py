"""Suggested retire candidates on publish (bd polyglot-pdf-bdedm).

The maintainer's decision, and the reason it is not auto-retire: the only
same-form signals available are unreliable. `form_number` is explicitly NOT
unique -- a standard W-7 and a firm's own W-7 variant share it, which is
precisely the firm-tier case -- and the label is free text an author can rename.
A wrong auto-guess would retire ANOTHER FIRM'S live form.

So the system suggests, and a human confirms. These tests pin both halves: that
a plausible candidate IS offered with enough detail to judge it, and that
nothing is ever retired without an explicit tick.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import LocalFormKitStore

from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _run(coro):
    return asyncio.run(coro)


def _schema(form_number=None, edition=None, author_version=None):
    s = json.loads(json.dumps(_SCHEMA))
    meta = dict(s.get("form_metadata") or {})
    for key, value in (("form_number", form_number),
                       ("edition_date", edition),
                       ("author_version", author_version)):
        if value is None:
            meta.pop(key, None)
        else:
            meta[key] = value
    s["form_metadata"] = meta
    return s


def _make_kit(root, kit_id, status="complete", label=None, schema=None, published_at=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(
        json.dumps(schema if schema is not None else _SCHEMA), encoding="utf-8")
    meta = {"status": status, "label": label or kit_id}
    if published_at:
        meta["published_at"] = published_at
    (kit / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    (kit / "form.pdf").write_bytes(b"%PDF-1.7 test")
    return kit


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok"))

    # Same stub the lifecycle fixture uses: the publish gate refuses on
    # translation coverage otherwise, and the metered per-language sweep is not
    # what these tests are about.
    async def _no_drift(_store, _kit_id, _schema, _schema_file):
        return 0, None

    monkeypatch.setattr(ekr, "_sweep_drifted_translations", _no_drift)
    return TestClient(app), store, tmp_path


AUTH = {"X-Editor-Token": "auth-tok"}
EDIT = {"X-Editor-Token": "edit-tok"}


def _candidates(c, kit_id, headers=AUTH):
    return c.get(f"/api/editor/kits/{kit_id}/retire-candidates", headers=headers)


# --- what gets suggested ----------------------------------------------------


def test_a_live_kit_with_the_SAME_form_number_is_suggested(client):
    c, _store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7 (2025)",
              schema=_schema(form_number="W-7", edition="01/2025"))
    _make_kit(root, "w7-old", status="complete", label="W-7 (ITIN)",
              schema=_schema(form_number="W-7", edition="12/2024"))

    resp = _candidates(c, "w7-new")

    assert resp.status_code == 200, resp.text
    cands = resp.json()["candidates"]
    assert [x["kitId"] for x in cands] == ["w7-old"]
    assert cands[0]["matchedOn"] == "form_number"
    # Enough to tell two same-numbered kits apart.
    assert cands[0]["label"] == "W-7 (ITIN)"
    assert cands[0]["formNumber"] == "W-7"
    assert cands[0]["edition"] == "12/2024"
    assert cands[0]["editionKind"] == "edition_date"


def test_a_DIFFERENT_form_number_is_not_suggested(client):
    """A declared mismatch DECIDES, even when the labels are identical.

    The earlier version of this test gave the two kits different labels, so the
    empty result came from the LABEL branch failing -- the number mismatch was
    never what rejected it. It was the only named guard for this behaviour and
    it guarded nothing, which is how the fall-through survived three review
    rounds (Opus fresh-eyes round 4).
    """
    c, _store, root = client
    _make_kit(root, "w7-new", status="draft", label="Tax Form",
              schema=_schema(form_number="W-7"))
    _make_kit(root, "i90", status="complete", label="Tax Form",
              schema=_schema(form_number="I-90"))

    assert _candidates(c, "w7-new").json()["candidates"] == [], (
        "a matching label overrode two DIFFERENT declared form numbers")


def test_an_IDENTICAL_label_is_suggested_when_numbers_are_absent(client):
    """Label similarity is the fallback signal, and it is EXACT match only --
    neither kit here declares a form number, which is the state both real kits
    were in before this bead."""
    c, _store, root = client
    _make_kit(root, "intake-new", status="draft", label="Client Intake",
              schema=_schema())
    _make_kit(root, "intake-old", status="complete", label="Client Intake",
              schema=_schema())

    cands = _candidates(c, "intake-new").json()["candidates"]

    assert [x["kitId"] for x in cands] == ["intake-old"]
    assert cands[0]["matchedOn"] == "label"


# Real USCIS/IRS form families. Each pair is a BASE FORM and a genuinely
# different variant -- several (I-130A, I-864A) are supplements filed ALONGSIDE
# the base, so suggesting one to retire the other could break a live filing.
# A containment-with-slack rule matched EVERY pair here, at every slack value
# my earlier tests exercised (Opus fresh-eyes round 1).
@pytest.mark.parametrize("base,variant", [
    ("I-130", "I-130A"),
    ("I-864", "I-864A"),
    ("I-864", "I-864EZ"),
    ("I-129", "I-129F"),
    ("I-131", "I-131A"),
    ("I-765", "I-765V"),
    ("Form 1040", "Form 1040-X"),
    ("Form 1099", "Form 1099-MISC"),
    ("W-8BEN", "W-8BEN-E"),
    ("Form 941", "Form 941-X"),
])
def test_a_SIBLING_form_is_never_suggested(client, base, variant):
    """The failure this whole flow exists to prevent, by name -- via the LABEL
    path, where neither kit declares a number."""
    c, _store, root = client
    _make_kit(root, "new-kit", status="draft", label=base, schema=_schema())
    _make_kit(root, "live-kit", status="complete", label=variant, schema=_schema())

    assert _candidates(c, "new-kit").json()["candidates"] == [], (
        f"publishing {base!r} suggested retiring {variant!r}, a different form")


@pytest.mark.parametrize("base,variant", [
    ("I-130", "I-130A"),
    ("I-864", "I-864A"),
    ("I-864", "I-864EZ"),
    ("I-129", "I-129F"),
    ("I-131", "I-131A"),
    ("I-765", "I-765V"),
    ("Form 1040", "Form 1040-X"),
    ("Form 1099", "Form 1099-MISC"),
    ("W-8BEN", "W-8BEN-E"),
    ("Form 941", "Form 941-X"),
])
def test_a_SIBLING_form_is_never_suggested_WITH_declared_numbers(client, base, variant):
    """The same pairs, with the numbers real kits actually carry AND an
    identical label.

    This is the production shape -- f1040, i-90 and w7 all declare a
    form_number -- and it was entirely unguarded: the label parametrization
    above passes `_schema()` with no number on either kit, so it only ever
    exercised the label branch. With numbers declared, a differing number used
    to fall THROUGH to the label, and an identical label then suggested
    retiring the sibling (Opus fresh-eyes round 4, reproduced).
    """
    c, _store, root = client
    _make_kit(root, "new-kit", status="draft", label="Immigration Packet",
              schema=_schema(form_number=base))
    _make_kit(root, "live-kit", status="complete", label="Immigration Packet",
              schema=_schema(form_number=variant))

    assert _candidates(c, "new-kit").json()["candidates"] == [], (
        f"{base!r} suggested retiring {variant!r} -- the declared numbers "
        "differ, and a matching label must not override that")


@pytest.mark.parametrize("other_label", [
    "Employment History",          # nothing in common
    "Client Questionnaire",        # SHARES the first word -- a loose matcher bites
    "Clientele Survey",            # shares a prefix of the first word
    "Client Intake Addendum B",    # a genuinely different form, same family
    "Client Intake Sheet",         # a RENAME -- and still not suggested; see below
])
def test_an_unrelated_label_is_not_suggested(client, other_label):
    """Parametrized over the SHAPES a too-loose matcher would accept, not one
    obviously-different string. A first-letter or shared-prefix rule passes the
    naive case and still suggests retiring a live unrelated form -- the exact
    mistake this flow exists to prevent, and a mutation to that effect survived
    a single-case version of this test.

    "Client Intake Addendum B" is the honest hard case: it IS related, and it is
    still not this form. Containment says no, and that is the answer we want --
    a missed suggestion costs a manual retire; a wrong one costs a live form.
    """
    c, _store, root = client
    _make_kit(root, "a", status="draft", label="Client Intake", schema=_schema())
    _make_kit(root, "b", status="complete", label=other_label, schema=_schema())

    assert _candidates(c, "a").json()["candidates"] == [], (
        f"{other_label!r} was suggested as a retirement candidate for "
        "'Client Intake'")


# --- what must NOT be suggested ---------------------------------------------


@pytest.mark.parametrize("status", ["draft", "submitted", "unpublished"])
def test_only_LIVE_kits_are_suggested(client, status):
    """A draft is not competing for the catalogue slot; a submitted kit was
    never live; an unpublished one has nothing left to retire."""
    c, _store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7",
              schema=_schema(form_number="W-7"))
    _make_kit(root, "w7-other", status=status, label="W-7 old",
              schema=_schema(form_number="W-7"))

    assert _candidates(c, "w7-new").json()["candidates"] == []


def test_the_kit_being_published_never_suggests_ITSELF(client):
    """A republish of the same kit needs no flag -- one kit_id is one catalogue
    slot, so it already replaces itself (bd polyglot-pdf-6dz0)."""
    c, _store, root = client
    _make_kit(root, "w7", status="complete", label="W-7",
              schema=_schema(form_number="W-7"))

    assert _candidates(c, "w7").json()["candidates"] == []


def test_a_candidate_whose_schema_is_unreadable_is_SKIPPED(client):
    """Not surfaced with unknowns: a candidate the author cannot describe is
    one they cannot judge, and an informed confirmation is the entire point."""
    c, _store, root = client
    # The labels must MATCH and be long enough to clear the 3-char floor, so
    # the label path would suggest this candidate even with no readable schema.
    # Only the skip can exclude it.
    #
    # My first fixture used "W-7" for both, which normalises to "w7" -- two
    # characters, under the floor -- so the label path never fired and the
    # candidate fell out for the wrong reason AGAIN. The mutation stayed green
    # and told me so.
    _make_kit(root, "w7-new", status="draft", label="W-7 ITIN Application",
              schema=_schema(form_number="W-7"))
    broken = _make_kit(root, "w7-old", status="complete", label="W-7 ITIN Application",
                       schema=_schema(form_number="W-7"))
    (broken / "schema.json").write_text("{ not json", encoding="utf-8")

    assert _candidates(c, "w7-new").json()["candidates"] == []


# --- who may ask ------------------------------------------------------------


def test_an_EDITOR_cannot_list_retire_candidates(client):
    """Author-only, matching the publish it feeds: an editor cannot publish, so
    this would be a control they cannot use -- and the list is itself a
    statement about which kits exist."""
    c, _store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7",
              schema=_schema(form_number="W-7"))
    _make_kit(root, "w7-old", status="complete", label="W-7 old",
              schema=_schema(form_number="W-7"))

    assert _candidates(c, "w7-new", headers=EDIT).status_code in (401, 403)


def test_an_unknown_kit_404s(client):
    c, _store, _root = client
    assert _candidates(c, "never-existed").status_code == 404


# --- the marker shown to the author -----------------------------------------


def test_an_author_version_kit_shows_that_version(client):
    """Same precedence as the archive marker: edition_date, then
    author_version -- so what the author reads matches what the records name."""
    c, _store, root = client
    _make_kit(root, "custom-new", status="draft", label="Intake",
              schema=_schema(form_number="INTAKE"))
    _make_kit(root, "custom-old", status="complete", label="Intake old",
              schema=_schema(form_number="INTAKE", author_version="2026-01-01"))

    cands = _candidates(c, "custom-new").json()["candidates"]

    assert cands[0]["edition"] == "2026-01-01"
    assert cands[0]["editionKind"] == "author_version"


def test_edition_date_WINS_over_author_version(client):
    c, _store, root = client
    _make_kit(root, "a", status="draft", label="X", schema=_schema(form_number="X"))
    _make_kit(root, "b", status="complete", label="X old",
              schema=_schema(form_number="X", edition="12/2024",
                             author_version="2026-01-01"))

    cands = _candidates(c, "a").json()["candidates"]

    assert cands[0]["edition"] == "12/2024"
    assert cands[0]["editionKind"] == "edition_date"


def test_a_kit_with_no_marker_falls_back_to_its_publish_date(client):
    """Still give the author a date to tell two candidates apart."""
    c, _store, root = client
    _make_kit(root, "a", status="draft", label="X", schema=_schema(form_number="X"))
    _make_kit(root, "b", status="complete", label="X old",
              schema=_schema(form_number="X"), published_at="2026-02-03T10:00:00Z")

    cands = _candidates(c, "a").json()["candidates"]

    assert cands[0]["edition"] == "2026-02-03T10:00:00Z"
    assert cands[0]["editionKind"] == "published"


# --- suggesting is not retiring ---------------------------------------------


def test_listing_candidates_RETIRES_NOTHING(client):
    """The route is a read. Nothing is retired until the author ticks a box and
    the status route receives replaces_kit_id."""
    c, store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7",
              schema=_schema(form_number="W-7"))
    _make_kit(root, "w7-old", status="complete", label="W-7 old",
              schema=_schema(form_number="W-7"))

    assert _candidates(c, "w7-new").status_code == 200

    assert _run(store.load_metadata("w7-old"))["status"] == "complete"


# --- exit criterion 2, end to end -------------------------------------------


def test_ticking_a_candidate_RETIRES_EXACTLY_that_kit(client):
    """The bead's criterion 2, driven all the way through rather than assumed.

    The suggestion route and the dialog were each tested in isolation, and
    neither proved the thing that matters: that the id an author ticks reaches
    the publish and retires THAT kit, leaving the new one as the only live
    entry for the form, with the old one's files intact.
    """
    c, store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7 2025",
              schema=_schema(form_number="W-7", edition="01/2025"))
    old = _make_kit(root, "w7-old", status="complete", label="W-7 2024",
                    schema=_schema(form_number="W-7", edition="12/2024"))

    # The author is offered it...
    cands = _candidates(c, "w7-new").json()["candidates"]
    assert [x["kitId"] for x in cands] == ["w7-old"]

    # ...ticks it, and publishes.
    resp = c.post("/api/editor/kits/w7-new/status",
                  json={"status": "complete", "replaces_kit_id": "w7-old"},
                  headers=AUTH)
    assert resp.status_code == 200, resp.text

    assert _run(store.load_metadata("w7-old"))["status"] == "unpublished"
    assert _run(store.load_metadata("w7-new"))["status"] == "complete"
    # Files intact -- retiring is not deleting.
    assert (old / "schema.json").exists()
    assert (old / "form.pdf").exists()
    # ...and it is no longer offered as a candidate to anything.
    _make_kit(root, "w7-third", status="draft", label="W-7 2026",
              schema=_schema(form_number="W-7"))
    later = _candidates(c, "w7-third").json()["candidates"]
    assert [x["kitId"] for x in later] == ["w7-new"]


def test_ticking_NOTHING_retires_nothing(client):
    """The other half of criterion 2, and the common case: an author may just
    be adding a form."""
    c, store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7 2025",
              schema=_schema(form_number="W-7", edition="01/2025"))
    _make_kit(root, "w7-old", status="complete", label="W-7 2024",
              schema=_schema(form_number="W-7", edition="12/2024"))

    resp = c.post("/api/editor/kits/w7-new/status",
                  json={"status": "complete"}, headers=AUTH)
    assert resp.status_code == 200, resp.text

    assert _run(store.load_metadata("w7-old"))["status"] == "complete"
    assert _run(store.load_metadata("w7-new"))["status"] == "complete"


def test_form_number_WINS_over_a_matching_label(client):
    """The documented precedence, pinned. No earlier fixture matched on BOTH,
    so swapping the two branches left all 31 tests green -- and `matchedOn` is
    what the dialog renders as "Same form number" vs "Similar name", the
    author's cue for how much to trust the suggestion (Opus fresh-eyes round 2).
    """
    c, _store, root = client
    _make_kit(root, "w7-new", status="draft", label="W-7 ITIN Application",
              schema=_schema(form_number="W-7"))
    _make_kit(root, "w7-old", status="complete", label="W-7 ITIN Application",
              schema=_schema(form_number="W-7"))

    cands = _candidates(c, "w7-new").json()["candidates"]

    assert [x["kitId"] for x in cands] == ["w7-old"]
    assert cands[0]["matchedOn"] == "form_number"


@pytest.mark.parametrize("label", ["W-7", "W-2", "W-4", "W-9", "I-9"])
def test_a_SHORT_form_label_still_matches(client, label):
    """The commonest real labels in this domain are 2-3 characters normalised.

    A 3-character floor silently killed all of them: two kits both labelled
    "W-7" with no form_number produced NO candidate, so an author published a
    second live W-7 believing there was no older version -- the state bd
    polyglot-pdf-6dz0 exists to prevent (Opus fresh-eyes round 3).
    """
    c, _store, root = client
    _make_kit(root, "new-kit", status="draft", label=label, schema=_schema())
    _make_kit(root, "live-kit", status="complete", label=label, schema=_schema())

    cands = _candidates(c, "new-kit").json()["candidates"]

    assert [x["kitId"] for x in cands] == ["live-kit"], (
        f"two kits both labelled {label!r} produced no suggestion")


def test_a_DEGENERATE_one_character_label_does_not_match(client):
    """What the floor is actually for. Two kits each labelled "X" are not
    evidence of anything."""
    c, _store, root = client
    _make_kit(root, "new-kit", status="draft", label="X", schema=_schema())
    _make_kit(root, "live-kit", status="complete", label="X", schema=_schema())

    assert _candidates(c, "new-kit").json()["candidates"] == []


def test_a_traversing_kit_id_is_refused_not_resolved(client):
    """This route was the only one in the file that never validated its own
    path parameter."""
    c, _store, _root = client

    resp = c.get("/api/editor/kits/..%2F..%2Fetc/retire-candidates", headers=AUTH)

    assert resp.status_code in (400, 404), resp.text
