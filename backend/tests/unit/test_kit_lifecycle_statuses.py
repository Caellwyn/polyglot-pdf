"""Kit lifecycle statuses: unpublished + replace-current publish
(bd polyglot-pdf-6dz0).

A form has ONE live version. Retiring a published revision must hide it from
clients WITHOUT letting it become editable again -- its schema is what earlier
confirmation records were confirmed against (bd polyglot-pdf-w3zw), so an
editable retired revision would make the archive pointless.

The three exit criteria pinned here:
  1. Republishing a changed revision leaves exactly ONE catalogue entry.
  2. Unpublish hides the kit, keeps its files, blocks schema edits, and is
     reversible through the publish gate.
  3. Cross-kit "replace current" retires the superseded kit and leaves the new
     one as the only entry for that form.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import LocalFormKitStore


def _run(coro):
    # asyncio.run, never get_event_loop: the legacy accessor breaks once an
    # earlier test file has closed the main loop (bd polyglot-pdf-r8gq).
    return asyncio.run(coro)


# Reuse the fixture the editor-route suite already proves clears the publish
# gate (validate + extraction_info + v2 stamp + lint), rather than maintaining a
# second copy that drifts out of validity -- as this file's first draft did.
from backend.tests.unit.test_editor_kit_routes import VALID_SCHEMA as _SCHEMA


def _make_kit(root, kit_id, status="complete", schema=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(
        json.dumps(schema or _SCHEMA), encoding="utf-8"
    )
    (kit / "metadata.json").write_text(
        json.dumps({"status": status, "label": kit_id}), encoding="utf-8"
    )
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
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )

    async def _no_drift(_store, _kit_id, _schema, _schema_file):
        return 0, None

    monkeypatch.setattr(ekr, "_sweep_drifted_translations", _no_drift)
    return TestClient(app), store, tmp_path


HDR = {"X-Editor-Token": "edit-tok"}          # editor tier
AUTH_HDR = {"X-Editor-Token": "auth-tok"}    # author tier


def _status(client, kit_id, status, replaces=None, headers=None):
    """POST a status change, defaulting to the token the transition REQUIRES.

    Publishing and unpublishing are author actions (bd polyglot-pdf-hqztg);
    everything else an editor may do. Defaulting by transition keeps these
    tests about the GATE rather than about authentication -- a test that wants
    to prove the role rule itself passes `headers` explicitly.
    """
    body = {"status": status}
    if replaces:
        body["replaces_kit_id"] = replaces
    if headers is None:
        # Keyed on the target status. A revert of a LIVE kit is also an author
        # action, but this helper cannot see the current status -- those tests
        # pass `headers=AUTH_HDR` explicitly, which is clearer at the call site
        # than a lookup here would be.
        #
        # CAUTION, learned the hard way (Opus fresh-eyes round 2): this default
        # is a CONVENIENCE, not a statement of the rule. It once sent every
        # unpublish with the author token while the route accepted an editor's
        # -- so the suite read as though editor-unpublish were refused when it
        # was not, and the gap was invisible. Any test that means to pin WHO may
        # perform a transition must pass `headers` explicitly.
        headers = AUTH_HDR if status in ("complete", "unpublished") else HDR
    return client.post(f"/api/editor/kits/{kit_id}/status", json=body, headers=headers)


# --- author version at the publish gate (bd polyglot-pdf-xzw5) --------------


def _no_edition_schema():
    """The publish-gate fixture MINUS its government edition date."""
    schema = json.loads(json.dumps(_SCHEMA))
    meta = dict(schema.get("form_metadata") or {})
    meta.pop("edition_date", None)
    schema["form_metadata"] = meta
    return schema


def test_publishing_a_kit_with_no_edition_date_requires_an_author_version(client):
    """Without this, every confirmation on a custom form names a bare sha256
    fingerprint no one can read back in a dispute."""
    c, store, root = client
    _make_kit(root, "custom", status="draft", schema=_no_edition_schema())

    resp = _status(c, "custom", "complete")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    # The prefix is a CONTRACT, not decoration: the editor opens its version
    # dialog on exactly this token rather than re-deriving whether a kit needs
    # one (the catalogue listing deliberately does not read every schema).
    # Substring-matching the prose instead would break on any reword.
    assert detail.startswith("AUTHOR_VERSION_REQUIRED:"), detail
    assert "author version" in detail
    assert _run(store.load_metadata("custom"))["status"] == "draft"


def test_a_supplied_author_version_is_PERSISTED_into_the_served_schema(client):
    """The marker must land in the SCHEMA, not just pass validation: the voice
    path reads form_metadata off the schema it was served. This route otherwise
    never writes the schema, so a validated-then-discarded value would leave the
    published kit still fingerprint-only."""
    c, store, root = client
    _make_kit(root, "custom", status="draft", schema=_no_edition_schema())

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-07"


@pytest.mark.parametrize("raw,expected", [
    ("  2026-08-07  ", "2026-08-07"),   # trimmed
    ("v2026-08-07", "2026-08-07"),      # leading v stripped
    ("V2026-08-07", "2026-08-07"),      # ...case-insensitively
    ("v2", "2"),                        # short form still normalized
    ("version-3", "version-3"),         # a WORD starting with v is untouched
])
def test_author_version_is_normalized(client, raw, expected):
    """Strip a leading v/V only when a digit follows -- otherwise "version-3"
    would silently become "ersion-3"."""
    c, store, root = client
    _make_kit(root, "custom", status="draft", schema=_no_edition_schema())

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": raw}, headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == expected


def test_a_government_edition_date_needs_no_author_version(client):
    """The box never appears for an official form, so publishing one must not
    start demanding a field the client does not send."""
    c, store, root = client
    _make_kit(root, "w7", status="draft")   # _SCHEMA carries edition_date

    resp = _status(c, "w7", "complete")

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_an_author_version_is_IGNORED_when_a_government_edition_exists(client):
    """The government marker wins the precedence, so a stray author_version
    must not be written into an official form's schema and mislead a reader."""
    c, store, root = client
    _make_kit(root, "w7", status="draft")

    resp = c.post("/api/editor/kits/w7/status",
                  json={"status": "complete", "author_version": "mine"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("w7", "schema.json"))
    assert "author_version" not in (saved.get("form_metadata") or {})


def test_a_published_author_version_CANNOT_be_changed(client):
    """It is what existing confirmation records name (maintainer decision
    2026-08-08). Changing it would silently re-point them at a revision those
    clients never saw -- the hazard the retired-kit write-lock exists for."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-01-01"
    # PUBLISHED is the precondition, not merely "has a version" -- a draft
    # carrying a version from a failed publish has no records to protect.
    _make_kit(root, "custom", status="complete", schema=schema)

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-12-31"},
                  headers=AUTH_HDR)

    assert resp.status_code == 409, resp.text
    assert "2026-01-01" in resp.json()["detail"]
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-01-01"


def test_republishing_keeps_the_original_author_version(client):
    """A re-press of Mark complete (or a republish after retirement) must not
    require re-typing the version, nor change it."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-01-01"
    _make_kit(root, "custom", status="draft", schema=schema)

    resp = _status(c, "custom", "complete")   # no author_version supplied

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-01-01"


def test_a_BROKEN_schema_reports_its_own_defect_not_the_version_prompt(client):
    """ORDERING: the version gate runs AFTER validate/lint, never before.

    Both refusals are 422s on the same request, so whichever runs first is the
    one the author sees. My first version ran the version gate first, and an
    author with a structurally broken schema was told to supply a version --
    hiding the actual defect behind an unrelated prompt. The schema-quality
    gates report what is WRONG; this one asks for something EXTRA, so it must
    come last.

    Pins the ordering directly rather than relying on the neighbouring suite,
    where the two tests that caught this only fail incidentally.
    """
    c, _store, root = client
    broken = json.loads(json.dumps(_no_edition_schema()))
    broken["fields"] = "not-a-list"   # fails FormSchema validation outright
    _make_kit(root, "custom", status="draft", schema=broken)

    # No author_version supplied: BOTH gates would refuse. The schema one wins.
    resp = _status(c, "custom", "complete")

    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "cannot be marked complete" in detail, detail
    assert "author version" not in detail, (
        "the version prompt masked the real schema error: " + detail
    )


def test_a_FAILED_publish_does_not_lock_the_version_forever(client):
    """The version is written before the translation sweep, and that sweep
    routinely refuses ("N of M translations complete") -- leaving the kit in
    DRAFT with a version on disk. Locking on the value's mere presence made
    that failed attempt permanent: the author's corrected retry was refused,
    citing confirmation records that do not exist, on a kit the route
    explicitly expects them to re-press (Opus fresh-eyes, reproduced).
    """
    c, store, root = client
    schema = _no_edition_schema()
    # Exactly the state a sweep-refused publish leaves behind.
    schema["form_metadata"]["author_version"] = "typo-verison"
    _make_kit(root, "custom", status="draft", schema=schema)

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-07"


def test_a_draft_carrying_a_version_republishes_without_retyping_it(client):
    """The other half of the retry path: re-pressing Mark complete with nothing
    new must keep the version already on disk, not demand it again."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-08-07"
    _make_kit(root, "custom", status="draft", schema=schema)

    resp = _status(c, "custom", "complete")

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-07"


def test_the_ARCHIVE_is_keyed_on_the_same_marker_a_RECORD_names(client):
    """The archive exists so a confirmation record's marker can retrieve the
    exact bytes that client confirmed against. If the two disagree the whole
    mechanism silently fails -- the bytes are on disk under a key nobody holds.

    The archive resolver omitted author_version, so an edition-less kit archived
    under sha256:... while its records named "2026-08-07" (Opus fresh-eyes ran
    this end to end and got NOT FOUND). Pins the AGREEMENT, not either half.
    """
    c, store, root = client
    schema = _no_edition_schema()
    _make_kit(root, "custom", status="draft", schema=schema)

    # Publish with a version, then retire it -- retirement is what archives.
    assert c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR).status_code == 200
    assert _status(c, "custom", "unpublished").status_code == 200

    published = _run(store.load_schema("custom", "schema.json"))
    # The marker a confirmation record would carry for this revision...
    from backend.utils.confirmation_logger import resolve_edition_marker
    meta_block = published["form_metadata"]
    record_marker = resolve_edition_marker(
        meta_block.get("edition_date"), published, meta_block.get("author_version"),
    )
    assert record_marker == "2026-08-07"
    # ...must be the key the archive is retrievable by.
    archived = _run(store.load_archived_revision_or_none("custom", record_marker))
    assert archived is not None, (
        "archived bytes are unreachable by the marker its records name"
    )
    assert archived["form_metadata"]["author_version"] == "2026-08-07"


@pytest.mark.parametrize("stored,supplied", [
    # Supplied side unnormalized -- fixed by hoisting normalization ahead of
    # the comparison (Opus fresh-eyes reproduced the false 409 live).
    ("2026-01-01", "v2026-01-01"),
    ("2026-01-01", "  2026-01-01  "),
    # STORED side unnormalized: reachable because a schema can arrive from
    # outside this route (hand-edited, or onboarded via git), and this route
    # is not the only thing that can put bytes in a kit. Normalizing only the
    # supplied side would 409 these as changes.
    ("v2026-01-01", "2026-01-01"),
    ("  2026-01-01  ", "2026-01-01"),
    # Both sides unnormalized, spelled differently.
    ("v2026-01-01", "  2026-01-01  "),
])
def test_republishing_an_EQUIVALENT_version_is_not_a_change(client, stored, supplied):
    """Equivalent-after-normalization is the SAME revision, so a republish must
    not 409 as if the author changed it -- a refusal they could not have
    satisfied, since no other spelling was available to them.

    Both sides go through the rule: normalizing only one leaves the other free
    to differ, and a stored value can arrive from outside this route.
    """
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = stored
    _make_kit(root, "custom", status="complete", schema=schema)

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": supplied},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text


def test_a_GENUINELY_different_version_is_still_refused(client):
    """The other half: normalizing both sides must not blur a real change into
    an accepted republish."""
    c, _store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-01-01"
    _make_kit(root, "custom", status="complete", schema=schema)

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-12-31"},
                  headers=AUTH_HDR)

    assert resp.status_code == 409, resp.text


def test_a_PUBLISHED_kit_with_no_version_refuses_to_gain_one(client):
    """The version write is the only schema write on this route, and a
    published kit's bytes are what its confirmation records were confirmed
    against. Accepting a version here rewrote them IN PLACE with no archive --
    the exact case the write-lock on all six sibling routes prevents (Opus
    fresh-eyes: "SCHEMA REWRITTEN IN PLACE WHILE WRITE-LOCKED: True").
    """
    c, store, root = client
    # A legacy kit: live, no edition date, no version.
    _make_kit(root, "legacy", status="complete", schema=_no_edition_schema())
    before = _run(store.load_schema("legacy", "schema.json"))

    resp = c.post("/api/editor/kits/legacy/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == 409, resp.text
    assert "already published without a version" in resp.json()["detail"]
    # The published bytes are untouched.
    assert _run(store.load_schema("legacy", "schema.json")) == before


def test_that_legacy_kit_CAN_be_versioned_by_republishing_it(client):
    """The refusal above must not be a dead end: the documented route (revert
    to draft, publish again) has to actually work, or a legacy kit could never
    gain a version at all."""
    c, store, root = client
    _make_kit(root, "legacy", status="complete", schema=_no_edition_schema())

    # Reverting a LIVE kit is the author's unlock (bd polyglot-pdf-hqztg).
    assert _status(c, "legacy", "draft", headers=AUTH_HDR).status_code == 200
    resp = c.post("/api/editor/kits/legacy/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("legacy", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-07"


def test_a_RETIRED_edition_less_kit_can_still_return_to_service(client):
    """A retired kit is serving nobody, and republish is its ONE documented
    route back (bd polyglot-pdf-6dz0 makes unpublished -> draft a hard 409).

    Scoping the "already published without a version" refusal to write-locked
    kits GENERALLY closed every exit for an edition-less retired kit -- and the
    409 it emitted told the author to revert to draft, which the API forbids.
    Bricked exactly the kit class this bead exists to serve (Opus fresh-eyes
    round 3, reproduced across all four exits).
    """
    c, store, root = client
    _make_kit(root, "retired", status="unpublished", schema=_no_edition_schema())

    resp = c.post("/api/editor/kits/retired/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("retired"))["status"] == "complete"
    saved = _run(store.load_schema("retired", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-07"


@pytest.mark.parametrize("status,expected", [
    # LIVE: accepting a version would rewrite bytes that records name.
    ("complete", 409),
    # RETIRED: serving nobody; republish is the documented way back.
    ("unpublished", 200),
    # DRAFT: not published at all, nothing to protect.
    ("draft", 200),
])
def test_adding_a_version_is_refused_ONLY_for_a_currently_live_kit(
    client, status, expected,
):
    """Enumerates the whole status dimension rather than sampling it. The
    round-2 fix keyed on "write-locked", which lumps `unpublished` in with
    `complete` -- a distinction that only shows up if every value is tried."""
    c, _store, root = client
    _make_kit(root, "k", status=status, schema=_no_edition_schema())

    resp = c.post("/api/editor/kits/k/status",
                  json={"status": "complete", "author_version": "2026-08-07"},
                  headers=AUTH_HDR)

    assert resp.status_code == expected, resp.text


def test_a_whitespace_only_author_version_is_refused(client):
    """Mirrors the blank-edition rule: whitespace names no revision."""
    c, _store, root = client
    _make_kit(root, "custom", status="draft", schema=_no_edition_schema())

    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "   "},
                  headers=AUTH_HDR)

    assert resp.status_code == 422, resp.text


# --- the status model itself ------------------------------------------------


def test_unpublished_is_write_locked_but_not_complete():
    """The property every write gate now asks about. An unpublished kit is NOT
    complete, so a `== "complete"` check would let a write through -- which is
    exactly how the third status could silently reopen the lock."""
    assert ekr._is_write_locked({"status": "unpublished"})
    assert ekr._is_write_locked({"status": "complete"})
    assert not ekr._is_write_locked({"status": "draft"})
    assert ekr._status_of({"status": "unpublished"}) == "unpublished"


# --- criterion 2: unpublish hides, locks, and is reversible ------------------


def test_unpublish_hides_the_kit_but_keeps_its_files(client):
    c, store, root = client
    _make_kit(root, "w7")

    resp = _status(c, "w7", "unpublished")

    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "unpublished"
    # Hidden from the CLIENT manifest gate (complete-only), files intact.
    meta = _run(store.load_metadata("w7"))
    assert meta["status"] == "unpublished"
    assert (root / "w7" / "schema.json").exists()
    assert (root / "w7" / "form.pdf").exists()


def test_unpublished_kit_refuses_schema_edits(client):
    """The load-bearing half: hidden is not enough. A retired revision's bytes
    are what earlier confirmations point at, so they must stay frozen."""
    c, _store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 409
    assert "unpublished" in resp.json()["detail"].lower()


def test_unpublished_kit_cannot_be_reverted_to_draft(client):
    """Draft is editable, so allowing this would bypass the write-lock
    entirely -- the retired bytes could then be rewritten in place."""
    c, _store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = _status(c, "w7", "draft")

    assert resp.status_code == 409
    assert "cannot be reverted to draft" in resp.json()["detail"]


def test_unpublished_kit_returns_to_service_through_the_publish_gate(client):
    c, store, root = client
    _make_kit(root, "w7", status="unpublished")

    resp = _status(c, "w7", "complete")

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_republishing_a_retired_kit_still_runs_the_publish_gate(client):
    """The load-bearing half of "republish THROUGH THE NORMAL GATE".

    Asserting 200 + a status flip is satisfied by a bare metadata write, so it
    cannot tell a gated republish from an ungated one: a mutation exempting
    retired kits from every gate left 245 tests green, while the same mutation
    on the draft path reddened 16 (Opus fresh-eyes). A retired revision going
    back into service is exactly when the gates matter most -- it is about to
    be served to clients again.
    """
    c, store, root = client
    # Retired AND missing its PDF: the first publish gate must refuse it.
    kit = root / "w7"
    kit.mkdir()
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "unpublished", "label": "w7"}), encoding="utf-8"
    )

    resp = _status(c, "w7", "complete")

    assert resp.status_code == 409, resp.text
    assert "form PDF" in resp.json()["detail"]
    # ...and it stays retired rather than sliding back into service ungated.
    assert _run(store.load_metadata("w7"))["status"] == "unpublished"


def test_republishing_a_retired_kit_is_refused_by_the_lint_gate_too(client):
    """Not just the cheap PDF check -- the whole gate chain applies. Pins that
    the republish path shares the draft path's gates rather than a subset."""
    c, store, root = client
    broken = json.loads(json.dumps(_SCHEMA))
    # A field naming no PDF widget is a LINT error (field-unbacked) that still
    # passes FormSchema validation -- which is the point. The first version of
    # this test used duplicate option values, and those are rejected by the
    # Pydantic v2 model validator BEFORE lint ever runs: it passed on the
    # validate gate while claiming to pin the lint one, and survived deleting
    # the lint gate outright (Opus fresh-eyes). Assert the exact gate, not
    # "some 4xx".
    broken["fields"][0].pop("pdf_field_name")
    _make_kit(root, "w7", status="unpublished", schema=broken)

    resp = _status(c, "w7", "complete")

    assert resp.status_code == 409, resp.text
    assert "lint error" in resp.json()["detail"]
    assert _run(store.load_metadata("w7"))["status"] == "unpublished"


def test_unpublishing_a_draft_is_refused(client):
    """Only a live kit can be retired; anything else is a confused request."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _status(c, "w7", "unpublished")

    assert resp.status_code == 409
    assert "Only a published form can be unpublished" in resp.json()["detail"]


def test_unpublishing_archives_the_retired_revision(client):
    """Retiring is a supersede: the bytes must be archived, exactly as a
    revert-to-draft archives them (bd polyglot-pdf-w3zw)."""
    c, store, root = client
    _make_kit(root, "w7")

    _status(c, "w7", "unpublished")

    assert _run(store.list_archived_markers("w7")), "no archive written"
    assert _run(store.load_archived_revision("w7", "12/2024")) == _SCHEMA


# --- criterion 3: cross-kit replace-current ---------------------------------


def test_replace_current_retires_the_superseded_kit(client):
    c, store, root = client
    _make_kit(root, "w7-2024")                       # the outgoing live kit
    _make_kit(root, "w7-2026", status="draft")       # the incoming revision

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 200, resp.text
    assert resp.json()["supersededKitId"] == "w7-2024"
    # Exactly one live kit for the form; the old one retired, files intact.
    assert _run(store.load_metadata("w7-2026"))["status"] == "complete"
    assert _run(store.load_metadata("w7-2024"))["status"] == "unpublished"
    assert (root / "w7-2024" / "schema.json").exists()


def test_replace_current_archives_the_superseded_revision(client):
    c, store, root = client
    _make_kit(root, "w7-2024")
    _make_kit(root, "w7-2026", status="draft")

    _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert _run(store.list_archived_markers("w7-2024")), "outgoing kit not archived"


def test_a_kit_cannot_replace_itself(client):
    """Same-kit republish already replaces its own entry; naming itself is a
    confused request, and honouring it would archive-and-retire the very kit
    being published."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _status(c, "w7", "complete", replaces="w7")

    assert resp.status_code == 409
    assert "cannot replace itself" in resp.json()["detail"]


def test_replacing_a_kit_that_is_not_live_is_refused(client):
    c, _store, root = client
    _make_kit(root, "w7-2024", status="draft")
    _make_kit(root, "w7-2026", status="draft")

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 409
    assert "not published" in resp.json()["detail"]


def test_replaces_is_ignored_when_the_request_is_not_a_publish(client):
    """A supersede retires a live kit, so it may fire ONLY as part of putting a
    replacement into service. Left ungated it also fires on an unpublish or a
    revert, retiring the outgoing kit when nothing takes its place -- the form
    would then have NO live version. A mutation removing the publish condition
    survived every other test in this file, so pin it directly.
    """
    c, store, root = client
    _make_kit(root, "w7-2024")                 # live, and named as the outgoing
    _make_kit(root, "w7-2026")                 # live, the one being retired

    # Retiring w7-2026 must not touch w7-2024, whatever replaces_kit_id says.
    resp = _status(c, "w7-2026", "unpublished", replaces="w7-2024")

    assert resp.status_code == 200, resp.text
    assert resp.json()["supersededKitId"] is None
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


def test_a_failed_incoming_write_leaves_the_outgoing_kit_live(client):
    """The ordering that matters: the outgoing kit is retired only AFTER the
    incoming one is actually live.

    The publish GATES protect against a validation failure, but not against the
    final metadata write failing. Retiring first and then failing there leaves
    the form with ZERO live versions -- worse than the two-entry state the
    supersede fixes. Publishing first makes the failure mode two live entries:
    visible, and fixable by unpublishing the old one (fresh-eyes finding).
    """
    from backend.services.form_kits import FormKitStoreError

    c, store, root = client
    _make_kit(root, "w7-2024")
    _make_kit(root, "w7-2026", status="draft")

    real_put = store.put_metadata
    calls = {"n": 0}

    async def _fail_incoming(kit_id, metadata):
        # Fail the INCOMING kit's own status write, after every gate passed.
        if kit_id == "w7-2026":
            calls["n"] += 1
            raise FormKitStoreError("simulated store failure")
        return await real_put(kit_id, metadata)

    store.put_metadata = _fail_incoming  # type: ignore[method-assign]
    try:
        resp = _status(c, "w7-2026", "complete", replaces="w7-2024")
    finally:
        store.put_metadata = real_put  # type: ignore[method-assign]

    assert resp.status_code == 502
    assert calls["n"] == 1, "the incoming write was never attempted"
    # The form still has its live version -- the outgoing kit was NOT retired.
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


def test_a_failed_publish_leaves_the_outgoing_kit_live(client):
    """Ordering guard: the outgoing kit is retired only AFTER the incoming one
    clears every gate. Retiring first and then failing would leave the form
    with NO live version -- worse than the two-entry state being fixed."""
    c, store, root = client
    _make_kit(root, "w7-2024")
    # An incoming kit with no PDF fails the publish gate.
    kit = root / "w7-2026"
    kit.mkdir()
    (kit / "schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps({"status": "draft"}), encoding="utf-8"
    )

    resp = _status(c, "w7-2026", "complete", replaces="w7-2024")

    assert resp.status_code == 409
    # The form still has exactly one live version -- the old one.
    assert _run(store.load_metadata("w7-2024"))["status"] == "complete"


# --- criterion 1: one entry per form after a same-kit republish -------------


def test_same_kit_republish_needs_no_replace_flag(client):
    """One kit_id is one catalogue slot, so a kit always replaces itself --
    the checkbox exists only for the cross-kit case."""
    c, store, root = client
    _make_kit(root, "w7")

    # revert -> edit -> republish, the only route to a new revision
    # Reverting a LIVE kit is the author's unlock (bd polyglot-pdf-hqztg).
    assert _status(c, "w7", "draft", headers=AUTH_HDR).status_code == 200
    changed = json.loads(json.dumps(_SCHEMA))
    changed["fields"].append({
        "id": "f2", "name": "Field 2", "spoken_name": "field two",
        "type": "text", "section_id": "s1", "pdf_field_name": "f2[0]",
        "help": {"instructions": "Second field."},
    })
    changed["sections"][0]["fields"].append("f2")
    (root / "w7" / "schema.json").write_text(json.dumps(changed), encoding="utf-8")
    assert _status(c, "w7", "complete").status_code == 200

    # Still exactly one kit dir serving this form, now holding the new revision.
    assert _run(store.load_metadata("w7"))["status"] == "complete"
    assert len(_run(store.load_schema("w7"))["fields"]) == 2
    # ...and the superseded revision is retrievable, not gone.
    assert _run(store.list_archived_markers("w7"))


# --- the author approval round (bd polyglot-pdf-hqztg) -----------------------
#
# Editors are SUBCONTRACTORS. Marking a form ready must not release it: an
# editor submits, an author reviews and publishes. The rule is enforced PER
# TRANSITION inside one route -- the s18 plan's insight (epic polyglot-pdf-4qul
# C9), with the mapping reversed by maintainer decision 2026-08-11.


def test_an_editor_can_SUBMIT_a_draft_for_review(client):
    c, store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _status(c, "w7", "submitted", headers=HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "submitted"


def test_an_editor_CANNOT_publish(client):
    """Exit criterion 1 + 3: the editor cannot make a kit deployable on their
    own, and it is refused SERVER-side rather than merely hidden in the UI."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")

    resp = _status(c, "w7", "complete", headers=HDR)

    assert resp.status_code == 403, resp.text
    assert "author" in resp.json()["detail"].lower()
    # Still awaiting review -- nothing was released.
    assert _run(store.load_metadata("w7"))["status"] == "submitted"


def test_an_AUTHOR_publishes_a_submitted_kit(client):
    """Exit criterion 2."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")

    resp = _status(c, "w7", "complete", headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_a_SUBMITTED_kit_is_write_locked(client):
    """If an editor could keep editing after submitting, the author would
    review one thing and approve another. Submitting freezes it; the editor
    reopens it deliberately via Revert to draft."""
    c, _store, root = client
    _make_kit(root, "w7", status="submitted")

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 409
    assert "submitted" in resp.json()["detail"].lower()


def test_an_editor_reopens_their_OWN_submitted_work(client):
    """The deliberate-unlock gate: an editor is not stuck after submitting --
    Revert to draft is theirs, because a submitted kit was never live."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")

    resp = _status(c, "w7", "draft", headers=HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "draft"


def test_an_editor_CANNOT_reopen_a_LIVE_kit(client):
    """The other half: reaching back into a published form is the author's
    unlock. A submitted kit was never served; a complete one was."""
    c, store, root = client
    _make_kit(root, "w7", status="complete")

    resp = _status(c, "w7", "draft", headers=HDR)

    assert resp.status_code == 403, resp.text
    assert "author" in resp.json()["detail"].lower()
    assert _run(store.load_metadata("w7"))["status"] == "complete"


@pytest.mark.parametrize("current", ["submitted", "complete", "unpublished"])
def test_only_a_DRAFT_can_be_submitted(client, current):
    """Submitting anything else is a confused request: it is already awaiting
    review, or live, or retired. Enumerated rather than sampled -- the status
    dimension is exactly where this bead's siblings kept losing a value."""
    c, _store, root = client
    _make_kit(root, "w7", status=current)

    resp = _status(c, "w7", "submitted", headers=HDR)

    assert resp.status_code == 409, resp.text


def test_a_SUBMITTED_kit_is_not_deployable(client):
    """Exit criterion 1's other half: deploy gates on complete, so a submitted
    kit must not read as complete to ANY downstream consumer."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")

    meta = _run(store.load_metadata("w7"))
    # The deploy scripts grep for exactly this; a submitted kit must not match.
    assert meta["status"] != "complete"
    assert ekr._is_write_locked(meta), "submitted must be write-locked"


# --- the editing lock (bd polyglot-pdf-hqztg) --------------------------------
#
# ROLE-scoped: two shared tokens mean the server can say "an editor holds this"
# but never WHICH editor (bd polyglot-pdf-ijntk lifts that). An author can
# always take a lock back from an editor and never the reverse -- which is also
# the stale-lock release, since a timer that steals from someone actively
# working is worse than a human deciding to take it.


def _lock(c, kit_id, headers):
    return c.post(f"/api/editor/kits/{kit_id}/lock", headers=headers)


def _unlock(c, kit_id, headers):
    return c.delete(f"/api/editor/kits/{kit_id}/lock", headers=headers)


def test_taking_a_free_lock_succeeds(client):
    c, store, root = client
    _make_kit(root, "w7", status="draft")

    resp = _lock(c, "w7", HDR)

    assert resp.status_code == 200, resp.text
    assert resp.json()["heldBy"] == "editor"
    assert resp.json()["preempted"] is False
    assert _run(store.load_metadata("w7"))["editing_lock"] == {"role": "editor"}


def test_an_AUTHOR_can_take_a_lock_back_from_an_editor(client):
    """The rule the maintainer asked for: authors can steal it back."""
    c, store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200

    resp = _lock(c, "w7", AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert resp.json()["heldBy"] == "author"
    # Reported, so the UI can SAY it took the kit rather than silently winning.
    assert resp.json()["preempted"] is True
    assert _run(store.load_metadata("w7"))["editing_lock"] == {"role": "author"}


def test_an_EDITOR_cannot_take_a_lock_from_an_author(client):
    """Preemption is one-way. An author mid-review must not have the form
    pulled out from under them."""
    c, store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", AUTH_HDR).status_code == 200

    resp = _lock(c, "w7", HDR)

    assert resp.status_code == 409, resp.text
    assert "author is working on this form" in resp.json()["detail"]
    assert _run(store.load_metadata("w7"))["editing_lock"] == {"role": "author"}


def test_a_preempted_editor_DISCOVERS_it_on_their_next_save(client):
    """There is no channel from server to editor, so the next save IS the
    notification -- a 409 explaining what happened, not a silent overwrite of
    the version the author is reviewing."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200
    assert _lock(c, "w7", AUTH_HDR).status_code == 200   # author takes it back

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 409, resp.text
    assert "author is working on this form" in resp.json()["detail"]


def test_the_lock_holder_can_still_save(client):
    """The lock must not block the person holding it."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 200, resp.text


def test_an_UNLOCKED_kit_saves_freely(client):
    """No lock means no new obstacle -- the lock is opt-in, and a kit nobody
    has taken behaves exactly as it did before this bead."""
    c, _store, root = client
    _make_kit(root, "w7", status="draft")

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 200, resp.text


def test_releasing_a_lock_frees_the_kit(client):
    c, store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200

    resp = _unlock(c, "w7", HDR)

    assert resp.status_code == 200, resp.text
    assert resp.json()["heldBy"] is None
    assert "editing_lock" not in _run(store.load_metadata("w7"))


def test_an_AUTHOR_can_release_an_editors_abandoned_lock(client):
    """The stale-lock escape. Someone closes their laptop and goes on holiday;
    an author clears it rather than waiting for a timer."""
    c, store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200

    resp = _unlock(c, "w7", AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert "editing_lock" not in _run(store.load_metadata("w7"))


def test_an_EDITOR_cannot_release_an_authors_lock(client):
    c, store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", AUTH_HDR).status_code == 200

    resp = _unlock(c, "w7", HDR)

    assert resp.status_code == 409, resp.text
    assert _lock_holder_of(store, "w7") == "author"


def _lock_holder_of(store, kit_id):
    return (_run(store.load_metadata(kit_id)).get("editing_lock") or {}).get("role")


def test_the_lock_does_not_disturb_other_metadata(client):
    """Read-merge-write, like every other metadata writer here: taking a lock
    must not drop the label, the status, or an author version."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")

    assert _lock(c, "w7", AUTH_HDR).status_code == 200

    meta = _run(store.load_metadata("w7"))
    assert meta["status"] == "submitted"
    assert meta["label"] == "w7"


# --- the lock covers EVERY schema-writing route ------------------------------


def _schema_writing_routes():
    """Derive the route list from the SHIPPED module, never a hand-typed one.

    bd polyglot-pdf-6dz0 shipped a guard on one of six sibling routes and 6x1j
    did the same; both times a reviewer found the other five. Enumerating from
    the source means a NEW schema-writing route added later without the lock
    fails this test instead of shipping unguarded.
    """
    import inspect
    src = inspect.getsource(ekr).splitlines()
    # Split on TOP-LEVEL function definitions, not on @router. decorators: a
    # decorator-delimited span runs past its own function into the next one's
    # helpers, which credited three routes with put_schema calls belonging to
    # their neighbours (caught by this very test failing on its first run).
    starts = [i for i, l in enumerate(src)
              if l.startswith("async def ") or l.startswith("def ")]
    out = []
    for idx, i in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(src)
        body = "\n".join(src[i:end])
        if "await store.put_schema(" not in body:
            continue
        # Routes only -- a @router. decorator on one of the lines just above.
        if "@router." not in "\n".join(src[max(0, i - 6):i]):
            continue
        name = src[i].split("(")[0].replace("async def ", "").replace("def ", "").strip()
        out.append((name, body))
    return out


def test_EVERY_schema_write_is_DOMINATED_by_the_editing_lock():
    """The property, and it is about ORDER, not mention.

    The first version asserted `"_require_edit_lock" not in body` -- a
    substring test over the whole function. That proves the helper is named
    SOMEWHERE, not that it runs before every write. set_editor_kit_status has
    TWO put_schema calls and one guard, and the guard sat between them: it
    passed this test while an editor could rewrite a schema out from under an
    author holding the lock (Opus fresh-eyes reproduced it end to end).

    Now every put_schema must be PRECEDED by a guard in the same function.
    """
    import inspect
    src = inspect.getsource(ekr).splitlines()
    starts = [i for i, l in enumerate(src)
              if l.startswith("async def ") or l.startswith("def ")]

    # Helpers that write a schema are included too, not only @router. functions
    # -- the route-only filter meant a new helper-level writer would be
    # invisible to this test. Anything genuinely exempt is allowlisted WITH a
    # reason, so the exemption is a decision on the record rather than a gap.
    ALLOWED = {
        # Runs INSIDE the publish path, after that route's own guard, on the
        # schema object that route already holds.
        "_sweep_drifted_translations",
    }

    offenders = []
    for idx, i in enumerate(starts):
        end_i = starts[idx + 1] if idx + 1 < len(starts) else len(src)
        body = src[i:end_i]
        name = src[i].split("(")[0].replace("async def ", "").replace("def ", "").strip()
        writes = [j for j, l in enumerate(body) if "await store.put_schema(" in l]
        if not writes or name in ALLOWED:
            continue
        guards = [j for j, l in enumerate(body) if "_require_edit_lock(" in l]
        first_guard = min(guards) if guards else None
        for w in writes:
            if first_guard is None or first_guard > w:
                offenders.append(f"{name} (write at +{w}, guard at "
                                 f"{'none' if first_guard is None else f'+{first_guard}'})")

    assert offenders == [], (
        "these schema writes are not dominated by an editing-lock check: "
        + "; ".join(offenders)
    )


def test_the_lock_property_test_covers_the_routes_it_claims_to():
    """A guard against the enumeration silently matching nothing -- a detection
    that finds zero writers would pass the test above vacuously."""
    import inspect
    src = inspect.getsource(ekr)
    assert src.count("await store.put_schema(") >= 7, (
        "expected at least 7 schema writes in this module; the detection above "
        "may have stopped matching"
    )


def test_the_enumeration_is_anchored_to_a_REAL_refusal(client):
    """The property test above proves every schema writer CALLS the guard.
    This drives one end to end, so "calls it" cannot drift from "refuses".

    Uses PUT /schema rather than repair: repair is author-only, so an editor
    can never reach its lock check at all -- my first version of this test
    asserted a 409 against a route that 403s first, which would have proved
    nothing about the lock.
    """
    c, _store, root = client
    _make_kit(root, "w7", status="draft")
    assert _lock(c, "w7", HDR).status_code == 200
    assert _lock(c, "w7", AUTH_HDR).status_code == 200   # author takes it back

    resp = c.put("/api/editor/kits/w7/schema",
                 json={"fields": [{"id": "f1"}]}, headers=HDR)

    assert resp.status_code == 409, resp.text
    assert "author is working on this form" in resp.json()["detail"]


# --- rejection clears the version (bd polyglot-pdf-hqztg) --------------------


def test_REJECTING_a_submitted_kit_clears_its_author_version(client):
    """A submitted kit was never live, so no confirmation record names its
    version -- nothing to protect, and the next publish asks again."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-08-11"
    _make_kit(root, "custom", status="submitted", schema=schema)

    resp = _status(c, "custom", "draft", headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert "author_version" not in saved["form_metadata"]


def test_reopening_a_PUBLISHED_kit_KEEPS_its_author_version(client):
    """The other side of the scoping, and the one that matters. Records DO
    name a published kit's version, so clearing it would let the next publish
    invent a different marker for a revision clients already confirmed against
    -- exactly the re-pointing the xzw5 immutability lock exists to prevent."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-01-01"
    _make_kit(root, "custom", status="complete", schema=schema)

    resp = _status(c, "custom", "draft", headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-01-01"


def test_a_rejected_kit_can_be_versioned_AGAIN_on_resubmission(client):
    """The cleared version must not leave the kit unpublishable: the author is
    asked for one again, and a NEW value is accepted (the immutability lock
    must not fire on a version that was never published)."""
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-08-11"
    _make_kit(root, "custom", status="submitted", schema=schema)

    assert _status(c, "custom", "draft", headers=AUTH_HDR).status_code == 200
    resp = c.post("/api/editor/kits/custom/status",
                  json={"status": "complete", "author_version": "2026-12-25"},
                  headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-12-25"


def test_rejecting_a_kit_with_NO_version_is_a_clean_noop(client):
    """A government-edition kit has no author version to clear; the reject must
    not touch its schema or fail."""
    c, store, root = client
    _make_kit(root, "w7", status="submitted")
    before = _run(store.load_schema("w7", "schema.json"))

    resp = _status(c, "w7", "draft", headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_schema("w7", "schema.json")) == before


def test_an_editor_cannot_REJECT_out_from_under_an_author(client):
    """The lock must dominate EVERY write in the status route, not just the
    last one.

    This route has two put_schema calls -- the rejection clear and the
    author-version persistence -- and the guard originally sat between them.
    submitted -> draft is editor-allowed, so an editor reached the first write
    while an AUTHOR held the lock: it rewrote the schema under the reviewer AND
    flipped the kit out of write-locked `submitted`, permitting every later
    editor write too (Opus fresh-eyes, reproduced end to end).
    """
    c, store, root = client
    schema = _no_edition_schema()
    schema["form_metadata"]["author_version"] = "2026-08-11"
    _make_kit(root, "custom", status="submitted", schema=schema)
    assert _lock(c, "custom", AUTH_HDR).status_code == 200   # author reviewing

    resp = _status(c, "custom", "draft", headers=HDR)        # editor reopens

    assert resp.status_code == 409, resp.text
    assert "author is working on this form" in resp.json()["detail"]
    # Nothing moved: still submitted, version intact.
    assert _run(store.load_metadata("custom"))["status"] == "submitted"
    saved = _run(store.load_schema("custom", "schema.json"))
    assert saved["form_metadata"]["author_version"] == "2026-08-11"


def test_the_lock_still_permits_the_HOLDER_to_reject(client):
    """The guard must not block the person holding the kit -- an editor who
    holds their own submission can still reopen it."""
    c, store, root = client
    _make_kit(root, "custom", status="submitted", schema=_no_edition_schema())
    assert _lock(c, "custom", HDR).status_code == 200

    resp = _status(c, "custom", "draft", headers=HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("custom"))["status"] == "draft"


def test_an_editor_CANNOT_UNPUBLISH_a_LIVE_kit(client):
    """The twin of test_an_editor_CANNOT_reopen_a_LIVE_kit, and its absence is
    why the hole shipped.

    Unpublishing takes a form away from every client, and for an editor it is a
    ONE-WAY door: revert-to-draft then 409s (the 6dz0 immutability rule) and
    republishing 403s, so a subcontractor could pull a live form and be unable
    to restore it. The role gate originally checked only `draft` while its
    comment claimed "complete -> anything" was covered (Opus fresh-eyes round 2,
    reproduced end to end).
    """
    c, store, root = client
    _make_kit(root, "w7", status="complete")

    resp = _status(c, "w7", "unpublished", headers=HDR)

    assert resp.status_code == 403, resp.text
    assert "author" in resp.json()["detail"].lower()
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_an_AUTHOR_can_still_unpublish(client):
    """The gate must not block the role that is supposed to do this."""
    c, store, root = client
    _make_kit(root, "w7", status="complete")

    resp = _status(c, "w7", "unpublished", headers=AUTH_HDR)

    assert resp.status_code == 200, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "unpublished"


@pytest.mark.parametrize("target", ["draft", "unpublished"])
def test_NEITHER_live_kit_transition_is_open_to_an_editor(client, target):
    """Enumerated over both destinations rather than sampled: checking one of
    the two is exactly how the unpublish half was missed."""
    c, store, root = client
    _make_kit(root, "w7", status="complete")

    resp = _status(c, "w7", target, headers=HDR)

    assert resp.status_code == 403, resp.text
    assert _run(store.load_metadata("w7"))["status"] == "complete"


def test_a_supersede_honours_the_OUTGOING_kit_s_lock(client):
    """The guard at the top of the route only sees the INCOMING kit, so a
    supersede archived and retired a SECOND kit no guard had checked (Opus
    fresh-eyes round 2). Role-scoped locks make it inert today; it becomes a
    live hole the moment bd polyglot-pdf-ijntk lands."""
    c, store, root = client
    _make_kit(root, "w7-2024", status="complete")
    _make_kit(root, "w7-2026", status="draft")
    # An AUTHOR is working on the outgoing kit...
    assert _lock(c, "w7-2024", AUTH_HDR).status_code == 200

    # ...and an EDITOR-held supersede must not retire it under them. (Publishing
    # is author-only, so this drives the guard directly rather than the route.)
    holder = ekr._lock_holder(_run(store.load_metadata("w7-2024")))
    assert holder == "author"
    assert ekr._lock_refusal(holder, "editor") is not None, (
        "an editor must be refused the outgoing kit while an author holds it"
    )
    # And the route calls that check -- pinned by the property test above plus
    # this explicit assertion that the call exists on the supersede path.
    import inspect
    src = inspect.getsource(ekr.set_editor_kit_status)
    assert "_require_edit_lock(superseded_meta, role)" in src, (
        "the supersede path must check the OUTGOING kit's lock"
    )
