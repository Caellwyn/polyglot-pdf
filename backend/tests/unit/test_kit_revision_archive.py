"""Kit revision archive (bd polyglot-pdf-w3zw).

Kit storage is ONE slot per kit_id, so republishing used to destroy the schema
an old confirmation record was confirmed against -- the audit trail could name a
revision the store could no longer produce. These tests pin the three exit
criteria: the superseded schema stays retrievable by the marker its records
carry, an unchanged re-press does not re-archive, and archives stay invisible to
both catalogues.
"""
import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
from backend.services.form_kits import (
    FormKitNotFound,
    LocalFormKitStore,
    encode_marker,
)
from backend.utils.confirmation_logger import resolve_edition_marker


def _run(coro):
    # asyncio.run (not get_event_loop): the legacy accessor breaks when an
    # earlier test file has closed the main loop via its own asyncio.run --
    # these tests pass in isolation and fail in the full suite (bd
    # polyglot-pdf-r8gq, re-hit here).
    return asyncio.run(coro)


def _schema(*field_ids, edition=None, author_version=None):
    """A minimal schema whose ANSWERABLE SHAPE is driven by field_ids -- which
    is what the fingerprint marker keys on."""
    out = {
        "schema_version": "2",
        "fields": [{"id": fid, "type": "text"} for fid in field_ids],
    }
    meta = {}
    if edition is not None:
        meta["edition_date"] = edition
    if author_version is not None:
        meta["author_version"] = author_version
    if meta:
        out["form_metadata"] = meta
    return out


def _make_kit(root, kit_id, schema, meta=None):
    kit = root / kit_id
    kit.mkdir(parents=True, exist_ok=True)
    (kit / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit / "metadata.json").write_text(
        json.dumps(meta or {"status": "complete"}), encoding="utf-8"
    )
    return kit


# --- store primitives -------------------------------------------------------


def test_archived_revision_roundtrips_by_marker(tmp_path):
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    old = _schema("a", "b", edition="12/2024")

    _run(store.put_archived_revision("w7", "12/2024", old, {"status": "complete"}))

    assert _run(store.load_archived_revision("w7", "12/2024")) == old


def test_missing_archived_revision_is_not_found(tmp_path):
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    with pytest.raises(FormKitNotFound):
        _run(store.load_archived_revision("w7", "12/2024"))


def test_list_archived_markers_is_empty_not_error_without_archive(tmp_path):
    # "No superseded revisions" is the normal state of a fresh kit, not a fault.
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    assert _run(store.list_archived_markers("w7")) == []


@pytest.mark.parametrize("marker", [
    "12/2024",                  # a government edition date: contains a slash
    "sha256:1a2b3c4d5e6f",      # a fingerprint: contains a colon
    "../../etc/passwd",         # a traversal attempt
    "v2 (revised)",             # spaces and parens
    "..",                       # degenerate: dots only
    "",                         # degenerate: empty
])
def test_marker_encoding_is_a_safe_single_segment(tmp_path, marker):
    """Every marker must round-trip to SOME addressable archive dir, and none
    may escape the kit. A marker is kit-controlled and becomes a path segment,
    so it is untrusted exactly like a filename -- but it cannot be REJECTED
    (real markers contain '/' and ':'), so it is encoded instead."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    schema = _schema("x")

    _run(store.put_archived_revision("w7", marker, schema))

    segment = encode_marker(marker)
    assert "/" not in segment and "\\" not in segment and ".." not in segment
    assert segment  # never empty -> always addressable
    # It landed INSIDE the kit's archive dir, nowhere else.
    assert (tmp_path / "w7" / "_archive" / segment / "schema.json").exists()
    assert _run(store.load_archived_revision("w7", marker)) == schema


def test_archive_is_invisible_to_the_editor_catalogue(tmp_path):
    """Exit criterion 3. list_kit_files is the editor catalogue's source of
    truth; the archive must not appear as a kit or as a kit file."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    _run(store.put_archived_revision("w7", "12/2024", _schema("a", "b")))

    files = _run(store.list_kit_files())
    assert set(files) == {"w7"}                      # no "_archive" pseudo-kit
    assert files["w7"] == ["metadata.json", "schema.json"]  # no nested entries
    assert "_archive" not in _run(store.list_kit_ids())


def test_archive_is_invisible_to_the_client_manifest(tmp_path):
    """Exit criterion 3, second catalogue: the voice app's manifest."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a"))
    _run(store.put_archived_revision("w7", "12/2024", _schema("a", "b")))

    manifest = _run(store.load_manifest())
    assert [f["id"] for f in manifest["forms"]] == ["w7"]


# --- the promotion-route hook ----------------------------------------------


def _archive_hook(store, kit_id, meta):
    from backend.routes.editor_kit_routes import _archive_published_revision

    return _run(_archive_published_revision(store, kit_id, meta))


def test_revert_archives_the_published_revision_under_its_own_marker(tmp_path):
    """Exit criterion 1. The marker must come from the SUPERSEDED revision's own
    schema, so it matches what that revision's confirmation records carry."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", published)

    marker = _archive_hook(store, "w7", {"status": "complete"})

    assert marker == "12/2024"
    assert _run(store.load_archived_revision("w7", "12/2024")) == published


def test_fingerprint_era_revision_archives_under_its_fingerprint(tmp_path):
    """A firm's custom form has no government edition, so its records carry a
    sha256 fingerprint -- the archive must key on that SAME value, or those
    records become unresolvable."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b")  # no edition_date
    _make_kit(tmp_path, "acme-intake", published)
    expected = resolve_edition_marker(None, published)
    assert expected.startswith("sha256:")

    marker = _archive_hook(store, "acme-intake", {"status": "complete"})

    assert marker == expected
    assert _run(store.load_archived_revision("acme-intake", expected)) == published


def test_reverting_twice_without_a_schema_change_archives_once(tmp_path):
    """Exit criterion 2: an idempotent revert->republish cycle that did not
    change the answerable shape must not pile up duplicate archive copies."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a", "b", edition="12/2024"))

    first = _archive_hook(store, "w7", {"status": "complete"})
    second = _archive_hook(store, "w7", {"status": "complete"})

    assert first == "12/2024"
    assert second is None  # already archived -> no second copy
    assert _run(store.list_archived_markers("w7")) == [encode_marker("12/2024")]


def test_a_changed_revision_archives_alongside_the_earlier_one(tmp_path):
    """Two genuinely different revisions must BOTH stay retrievable -- the
    second archive must not overwrite the first."""
    store = LocalFormKitStore(tmp_path)
    rev_a = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", rev_a)
    _archive_hook(store, "w7", {"status": "complete"})

    # A new revision is published, then itself superseded.
    rev_b = _schema("a", "b", "c", edition="01/2026")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_b), encoding="utf-8")
    _archive_hook(store, "w7", {"status": "complete"})

    assert _run(store.load_archived_revision("w7", "12/2024")) == rev_a
    assert _run(store.load_archived_revision("w7", "01/2026")) == rev_b


def test_archive_failure_does_not_block_the_revert(tmp_path):
    """A kit whose schema cannot be read must still be revertible: failing the
    revert would strand it published-and-uneditable, which is worse than a
    missing archive entry (which is logged loudly)."""
    store = LocalFormKitStore(tmp_path)
    kit = tmp_path / "w7"
    kit.mkdir()
    (kit / "metadata.json").write_text(json.dumps({"status": "complete"}), encoding="utf-8")
    # No schema.json at all.

    assert _archive_hook(store, "w7", {"status": "complete"}) is None


def test_fieldless_schema_archives_nothing(tmp_path):
    """No edition date and no fingerprintable shape means no marker a
    confirmation record could name -- so there is nothing to key an archive on."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "empty-kit", {"schema_version": "2", "fields": []})

    assert _archive_hook(store, "empty-kit", {"status": "complete"}) is None
    assert _run(store.list_archived_markers("empty-kit")) == []


# --- retrieval: never hand back a confident WRONG revision ------------------


def _read_kit_revision():
    """The operator retrieval script as a module (it lives in scripts/, which is
    not a package on the default path)."""
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[3] / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    import read_kit_revision

    return read_kit_revision


def _resolve_revision(store, kit_id, marker):
    return _run(_read_kit_revision()._resolve(store, kit_id, marker))


def test_retrieval_refuses_to_guess_between_colliding_revisions(tmp_path):
    """A confirmation record carries the PLAIN marker, and an edition_date is
    not unique -- so when two archived revisions answer to it, the record alone
    cannot say which was confirmed against. Retrieval must say so, NOT return
    the first one: a confident wrong schema is the worst outcome for a legal
    record (fresh-eyes round 2, reproduced live against the shipped resolver).
    """
    AmbiguousRevision = _read_kit_revision().AmbiguousRevision

    store = LocalFormKitStore(tmp_path)
    rev_1 = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", rev_1)
    _archive_hook(store, "w7", {"status": "complete"})
    rev_2 = _schema("a", "b", "c", edition="12/2024")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")
    _archive_hook(store, "w7", {"status": "complete"})
    # A third, unrelated revision goes live so neither archived one is current.
    (tmp_path / "w7" / "schema.json").write_text(
        json.dumps(_schema("z", edition="01/2026")), encoding="utf-8"
    )

    with pytest.raises(AmbiguousRevision) as exc:
        _resolve_revision(store, "w7", "12/2024")
    assert len(exc.value.candidates) == 2


def test_retrieval_finds_a_LIVE_author_versioned_revision(tmp_path):
    """The reader must resolve through the SAME three ranks the record did.

    This tool closes the audit loop: a record names a marker, this produces the
    bytes. Its live-schema branch still called resolve_edition_marker with two
    arguments, so a currently-published edition-less kit recorded
    "2026-08-07" while the tool computed sha256:<hex> and exited 1 "No revision
    found" -- the audit trail naming a revision the retrieval could not
    produce, which is the exact failure the archive exists to prevent.

    Easy to miss because the ARCHIVE half was fixed and pinned in this same
    bead; only the live half lagged (Opus outer cross-surface review,
    reproduced end to end).
    """
    store = LocalFormKitStore(tmp_path)
    live = _schema("a", "b", author_version="2026-08-07")
    _make_kit(tmp_path, "acme", live)

    kind, found = _resolve_revision(store, "acme", "2026-08-07")

    assert kind == "current"
    assert found == live


def test_retrieval_of_a_live_author_versioned_kit_agrees_with_the_RECORD(tmp_path):
    """Pins the AGREEMENT rather than either side: whatever marker a
    confirmation record would carry for this schema must be the marker that
    retrieves it."""
    from backend.utils.confirmation_logger import resolve_edition_marker

    store = LocalFormKitStore(tmp_path)
    live = _schema("a", "b", author_version="2026-08-07")
    _make_kit(tmp_path, "acme", live)

    meta = live["form_metadata"]
    record_marker = resolve_edition_marker(
        meta.get("edition_date"), live, meta.get("author_version"),
    )
    assert record_marker == "2026-08-07"      # not a sha256: fingerprint

    kind, found = _resolve_revision(store, "acme", record_marker)
    assert (kind, found) == ("current", live)


def test_a_government_edition_still_outranks_a_stray_author_version(tmp_path):
    """The reader's precedence must match the record's, not merely include the
    new rank -- otherwise a kit carrying both retrieves under the wrong one."""
    store = LocalFormKitStore(tmp_path)
    live = _schema("a", edition="12/2024", author_version="2026-08-07")
    _make_kit(tmp_path, "w7", live)

    kind, found = _resolve_revision(store, "w7", "12/2024")
    assert (kind, found) == ("current", live)

    with pytest.raises(FormKitNotFound):
        _resolve_revision(store, "w7", "2026-08-07")


def test_retrieval_finds_the_only_revision_for_a_marker(tmp_path):
    """The unambiguous case still resolves -- exit criterion 1's happy path."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", published)
    _archive_hook(store, "w7", {"status": "complete"})
    (tmp_path / "w7" / "schema.json").write_text(
        json.dumps(_schema("a", "b", "c", edition="01/2026")), encoding="utf-8"
    )

    source, schema = _resolve_revision(store, "w7", "12/2024")

    assert schema == published
    assert source.startswith("archive")


def test_retrieval_prefers_the_live_schema_when_it_still_matches(tmp_path):
    """A kit never revised since the record was written resolves to the live
    schema -- and one revision recorded under two segments is not an ambiguity."""
    store = LocalFormKitStore(tmp_path)
    published = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", published)
    _archive_hook(store, "w7", {"status": "complete"})

    source, schema = _resolve_revision(store, "w7", "12/2024")

    assert schema == published
    assert source == "current"


def test_an_unrelated_marker_that_encodes_with_a_dash_run_is_not_a_sibling(tmp_path):
    """encode_marker collapses ANY run of unsafe characters to one "-", so an
    ordinary marker like "12/2024//rev2" encodes to "12-2024--rev2" and would
    look like a fingerprint-disambiguated sibling of "12/2024" under a naive
    "--" prefix test -- reporting a FALSE ambiguity for two genuinely unrelated
    revisions (fresh-eyes round 3, reproduced live). Only a real encoded
    sha256 fingerprint suffix counts as a sibling.
    """
    store = LocalFormKitStore(tmp_path)
    only = _schema("a", edition="12/2024")
    _make_kit(tmp_path, "w7", only)
    _run(store.put_archived_revision("w7", "12/2024", only))
    # An unrelated revision whose raw marker merely ENCODES with a "--" run.
    _run(store.put_archived_revision("w7", "12/2024//rev2", _schema("z")))
    # Nothing live matches, so only the archive answers.
    (tmp_path / "w7" / "schema.json").write_text(
        json.dumps(_schema("q", edition="09/2030")), encoding="utf-8"
    )

    source, schema = _resolve_revision(store, "w7", "12/2024")

    assert schema == only  # resolved, NOT reported ambiguous
    assert source == "archive:12-2024"


def test_sibling_suffix_matches_the_real_fingerprint_format(tmp_path):
    """The sibling detector keys on the ENCODED shape of
    resolve_edition_marker's fingerprint. If that format changes, siblings stop
    being FOUND -- and a missed sibling drops the candidate count to 1, so
    retrieval hands back a single revision as if it were unambiguous. Pin the
    coupling rather than trusting the two to stay in step."""
    fingerprint = resolve_edition_marker(None, _schema("a", "b"))
    assert fingerprint.startswith("sha256:")

    rkr = _read_kit_revision()
    encoded_suffix = encode_marker(fingerprint)
    assert rkr._might_be_sibling_of(f"12-2024--{encoded_suffix}", "12-2024")
    # ...and a non-fingerprint suffix is not a sibling candidate at all.
    assert not rkr._might_be_sibling_of("12-2024--rev2", "12-2024")


@pytest.mark.parametrize("base_len", [8, 50, 106, 107, 108, 127, 128, 200])
def test_a_genuine_sibling_is_found_at_every_length(base_len):
    """The direction that MATTERS for correctness: a real sibling must never be
    missed. Over-matching only adds an ambiguity candidate (safe); UNDER-matching
    drops the count to 1 and returns one revision as if unambiguous, which on a
    legal surface is the outcome that must never happen -- verified in review by
    stubbing the detector to False, which silently resolved to the first
    revision alone."""
    from backend.services.form_kits import encode_marker as enc, sibling_marker

    rkr = _read_kit_revision()
    mine = "E" * base_len
    fp = "sha256:1a2b3c4d5e6f"

    assert rkr._might_be_sibling_of(sibling_marker(mine, fp), enc(mine)), (
        f"a real sibling was missed at base_len={base_len}"
    )


def test_an_unrelated_marker_never_yields_a_schema(tmp_path):
    """The impostor cases -- a shorter prefix marker, and one ending in our own
    digest -- must never produce a RESOLVED schema.

    The detector is deliberately loose, so an impostor may become an ambiguity
    CANDIDATE; what must never happen is a wrong schema returned at exit 0.
    Assert the outcome (no resolution), not the mechanism -- earlier versions of
    these tests asserted an exact-match property that three successive designs
    each failed to deliver.
    """
    import hashlib

    from backend.services.form_kits import FormKitNotFound

    victim = "12/2024"
    tag = hashlib.sha256(victim.encode("utf-8")).hexdigest()[:8]
    for attacker in (
        "12/20",                                    # a shorter prefix of ours
        f"TOTALLY-UNRELATED-{tag}",                 # ends in our digest
        "Q" * 98 + "-" + tag,                       # ...and at budget length
    ):
        root = tmp_path / f"kits_{abs(hash(attacker))}"
        root.mkdir()
        store = LocalFormKitStore(root)
        _make_kit(root, "w7", _schema("a", edition=attacker))
        _archive_hook(store, "w7", {"status": "complete"})
        (root / "w7" / "schema.json").write_text(
            json.dumps(_schema("a", "b", "c", edition=attacker)), encoding="utf-8"
        )
        _archive_hook(store, "w7", {"status": "complete"})
        # Nothing was EVER archived under the victim's marker.
        (root / "w7" / "schema.json").write_text(
            json.dumps(_schema("z", edition="09/2030")), encoding="utf-8"
        )

        rkr = _read_kit_revision()
        with pytest.raises((FormKitNotFound, rkr.AmbiguousRevision)):
            _resolve_revision(store, "w7", victim)


def test_an_unrelated_prefix_marker_resolves_to_not_found(tmp_path):
    """End to end: the prefix bleed must surface as an honest NOT FOUND, never
    as another revision's schema."""
    from backend.services.form_kits import FormKitNotFound

    store = LocalFormKitStore(tmp_path)
    # Two distinct revisions under "12/20" -- and NONE under "12/2024".
    rev_1 = _schema("a", edition="12/20")
    _make_kit(tmp_path, "w7", rev_1)
    _archive_hook(store, "w7", {"status": "complete"})
    rev_2 = _schema("a", "b", edition="12/20")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")
    _archive_hook(store, "w7", {"status": "complete"})
    # Live schema is unrelated, so nothing answers to "12/2024" at all.
    (tmp_path / "w7" / "schema.json").write_text(
        json.dumps(_schema("z", edition="09/2030")), encoding="utf-8"
    )

    with pytest.raises(FormKitNotFound):
        _resolve_revision(store, "w7", "12/2024")


@pytest.mark.parametrize("raw", ["12/2024", "12//2024", "12/2024/", "12-2024-", "a"])
def test_sibling_round_trips_for_markers_with_dash_runs(tmp_path, raw):
    """The split point (rfind('--')) must survive markers that themselves
    encode with dashes or trailing dash runs -- otherwise the reader mis-splits
    a legitimate sibling and loses it."""
    from backend.services.form_kits import encode_marker as enc, sibling_marker

    rkr = _read_kit_revision()
    sib = sibling_marker(raw, "sha256:1a2b3c4d5e6f")
    assert rkr._might_be_sibling_of(sib, enc(raw)), f"round trip failed for {raw!r}"


def test_sibling_marker_never_exceeds_the_segment_cap():
    """The 8-char base floor must not push the segment past the cap -- the one
    input the floor exists for is a pathological fingerprint."""
    from backend.services.form_kits import _MARKER_MAX_LEN, sibling_marker

    assert len(sibling_marker("12/2024", "f" * 200)) <= _MARKER_MAX_LEN
    assert len(sibling_marker("E" * 300, "sha256:1a2b3c4d5e6f")) <= _MARKER_MAX_LEN


def test_retrieval_of_an_unknown_marker_is_not_found(tmp_path):
    """Absent must stay absent -- never silently the nearest sibling."""
    from backend.services.form_kits import FormKitNotFound

    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a", edition="12/2024"))

    with pytest.raises(FormKitNotFound):
        _resolve_revision(store, "w7", "07/1999")


# --- the REAL route: the archive must actually be WIRED IN ------------------
# The helper tests above all call _archive_published_revision directly, so they
# stay green even if the status route never calls it (verified by mutation:
# deleting the call site left all of them passing). These drive the actual HTTP
# endpoint, which is the only thing that pins the WIRING.


@pytest.fixture()
def route_client(tmp_path, monkeypatch):
    from backend.tests.unit.test_editor_kit_routes import _settings

    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    return TestClient(app), store, tmp_path


def test_revert_to_draft_route_archives_the_published_revision(route_client):
    """THE wiring test (exit criterion 1, end to end): POST status=draft on a
    published kit must leave its schema retrievable under its own marker."""
    client, store, root = route_client
    published = _schema("a", "b", edition="12/2024")
    _make_kit(root, "w7", published, {"status": "complete"})

    # AUTHOR token: reopening a LIVE kit is the author's unlock (bd
    # polyglot-pdf-hqztg). What this test pins -- that the revert archives the
    # published revision -- is unchanged by who performs it.
    resp = client.post(
        "/api/editor/kits/w7/status",
        json={"status": "draft"},
        headers={"X-Editor-Token": "auth-tok"},
    )

    assert resp.status_code == 200, resp.text
    # The published bytes survive the revert, keyed by the marker its
    # confirmation records carry.
    assert _run(store.load_archived_revision("w7", "12/2024")) == published


def test_two_revisions_sharing_one_edition_date_both_survive(tmp_path):
    """An author may edit fields WITHOUT bumping the government edition string,
    producing two different revisions under one marker. A marker is therefore
    not a unique key: skipping on the marker NAME alone destroyed the second
    revision and made retrieval return the FIRST one -- a wrong answer, which
    for a legal record is worse than a missing one (fresh-eyes, reproduced live).
    """
    store = LocalFormKitStore(tmp_path)
    rev_1 = _schema("a", "b", edition="12/2024")
    _make_kit(tmp_path, "w7", rev_1)
    _archive_hook(store, "w7", {"status": "complete"})

    # Same edition_date, different answerable shape.
    rev_2 = _schema("a", "b", "c", edition="12/2024")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")
    second = _archive_hook(store, "w7", {"status": "complete"})

    # The first revision is untouched...
    assert _run(store.load_archived_revision("w7", "12/2024")) == rev_1
    # ...and the second was NOT silently dropped.
    assert second is not None
    assert _run(store.load_archived_revision("w7", second)) == rev_2


@pytest.mark.parametrize("marker_len", [10, 60, 114, 120, 127, 128, 140, 300])
def test_colliding_revisions_survive_at_every_marker_length(tmp_path, marker_len):
    """The sibling suffix must survive segment-length truncation AT EVERY
    LENGTH, not just short ones.

    Joining the raw marker and truncating afterwards loses the fingerprint on a
    long edition_date: at >=128 the sibling encodes IDENTICALLY to the base and
    the second revision OVERWRITES the first on disk (retrieval then hands back
    the wrong schema, with the original gone); just under that the suffix
    survives mangled, so the reader's fingerprint pattern misses it and the
    sibling is invisible. edition_date is unbounded free text, so both are
    reachable. Parametrized over the WHOLE dimension because the bug lives in
    specific bands (fresh-eyes on this bead reproduced 115-127 and >=128).
    """
    edition = "E" * marker_len
    store = LocalFormKitStore(tmp_path)
    rev_1 = _schema("a", "b", edition=edition)
    _make_kit(tmp_path, "w7", rev_1)
    _archive_hook(store, "w7", {"status": "complete"})

    rev_2 = _schema("a", "b", "c", edition=edition)
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")
    second = _archive_hook(store, "w7", {"status": "complete"})

    # BOTH revisions must still exist -- neither overwritten.
    markers = _run(store.list_archived_markers("w7"))
    assert len(markers) == 2, f"a revision was lost at marker_len={marker_len}"
    assert _run(store.load_archived_revision("w7", edition)) == rev_1
    assert second is not None
    assert _run(store.load_archived_revision("w7", second)) == rev_2

    # Move the LIVE schema to an unrelated revision first. Otherwise the live
    # copy answers to this marker too and supplies a second candidate on its
    # own -- so AmbiguousRevision would be raised whether or not the sibling
    # was ever found, and this assertion would pass over a broken band (it did:
    # the writer's trimmed base made siblings invisible to the reader at >=108
    # chars while this test stayed green). Isolate the ARCHIVE lookup.
    (tmp_path / "w7" / "schema.json").write_text(
        json.dumps(_schema("z", edition="01/2030")), encoding="utf-8"
    )
    rkr = _read_kit_revision()
    with pytest.raises(rkr.AmbiguousRevision) as exc:
        _resolve_revision(store, "w7", edition)
    # Exactly the two ARCHIVED revisions -- proving the sibling was visible.
    assert len(exc.value.candidates) == 2, (
        f"the sibling was invisible to retrieval at marker_len={marker_len}"
    )


def test_repeating_the_same_colliding_revision_still_skips(tmp_path):
    """The disambiguated sibling must itself stay idempotent -- a repeated
    revert of the SAME revision must not pile up copies."""
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "w7", _schema("a", edition="12/2024"))
    _archive_hook(store, "w7", {"status": "complete"})
    rev_2 = _schema("a", "b", edition="12/2024")
    (tmp_path / "w7" / "schema.json").write_text(json.dumps(rev_2), encoding="utf-8")

    first = _archive_hook(store, "w7", {"status": "complete"})
    again = _archive_hook(store, "w7", {"status": "complete"})

    assert first is not None
    assert again is None  # same bytes already archived -> no third copy
    assert len(_run(store.list_archived_markers("w7"))) == 2


@pytest.mark.parametrize("locked_status", ["complete", "unpublished"])
def test_every_schema_writing_editor_route_refuses_a_published_kit(
    route_client, locked_status,
):
    """The PROPERTY the archive's placement depends on: no editor route may
    change a WRITE-LOCKED kit's ANSWERABLE SHAPE (field ids/types/option values
    -- what the revision marker is computed from), so retirement is genuinely
    the last moment the superseded revision's bytes exist.

    Parametrized over EVERY write-locked status, not one sample: this test
    hardcoded "complete", so when bd polyglot-pdf-6dz0 added `unpublished`,
    five of the six gates could be reverted to the old two-value check with the
    entire 1779-test suite still green (Opus fresh-eyes). A property test that
    fixes one value of the dimension it claims to cover is pinning a sample,
    not a property.

    Stated precisely, because "cannot be written by ANY route" is FALSE: the
    /status drift sweep does write schema.json on a complete->complete re-press.
    That write only bakes translation metadata, which resolve_edition_marker
    deliberately excludes from the fingerprint, so it cannot produce a new
    revision -- see test_drift_sweep_write_does_not_change_the_revision_marker.

    Pinning the property rather than the one route found missing it: the extract
    route had no complete-gate, which silently falsified the design premise. A
    new SHAPE-writing route added later must gate or fail this test.
    """
    client, _store, root = route_client
    _make_kit(root, "w7", _schema("a", edition="12/2024"), {"status": locked_status})
    (root / "w7" / "form.pdf").write_bytes(b"%PDF-1.7 test")
    hdr = {"X-Editor-Token": "edit-tok"}
    author = {"X-Editor-Token": "auth-tok"}

    # Every route that can write schema.json for an EXISTING kit.
    assert client.put("/api/editor/kits/w7/schema", json={"fields": []},
                      headers=hdr).status_code == 409
    assert client.post("/api/editor/kits/w7/repair", headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/translate-options",
                       headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/derive-divisions",
                       headers=author).status_code == 409
    assert client.post("/api/editor/kits/w7/regenerate-guidance",
                       headers=author).status_code == 409
    # The one this bead's review found ungated: force=true would have
    # overwritten the published schema in place, bypassing the archive.
    assert client.post("/api/editor/kits/w7/extract", data={"force": "true"},
                       headers=author).status_code == 409


def test_drift_sweep_write_does_not_change_the_revision_marker():
    """The carve-out the property test rests on: the /status drift sweep DOES
    write schema.json on a complete->complete re-press, but it only bakes
    translation metadata -- which resolve_edition_marker excludes from the
    fingerprint by design. So that write cannot create a revision the archive
    would need to preserve. If the sweep ever touched field shape, this fails.
    """
    before = _schema("a", "b")
    after = json.loads(json.dumps(before))
    # What the sweep actually persists: baked translations in the provenance
    # slot, plus per-option label translations.
    after.setdefault("_bakeoff", {}).setdefault("authoring", {})[
        "option_translation"
    ] = {"changed": True, "model": "gemini-x"}
    after["fields"][0]["label_translations"] = {"spanish": "campo uno"}
    after["fields"][0]["spoken_name"] = "field one"

    assert resolve_edition_marker(None, before) == resolve_edition_marker(None, after)


def test_revert_of_an_already_draft_kit_archives_nothing(route_client):
    """Only the complete -> draft transition supersedes a PUBLISHED revision; a
    draft->draft no-op must not manufacture archive entries."""
    client, store, root = route_client
    _make_kit(root, "w7", _schema("a", edition="12/2024"), {"status": "draft"})

    resp = client.post(
        "/api/editor/kits/w7/status",
        json={"status": "draft"},
        headers={"X-Editor-Token": "edit-tok"},
    )

    assert resp.status_code == 200, resp.text
    assert _run(store.list_archived_markers("w7")) == []
