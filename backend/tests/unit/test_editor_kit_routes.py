"""
Unit tests for the token-gated /api/editor/* surface (bd polyglot-pdf-92qe.1).

Covers the three exit criteria:
1. Store write methods round-trip on LocalFormKitStore (put_schema, put_metadata,
   load_metadata, list_kit_files/list_kit_ids), with the GCS implementations
   covered via a mocked client.
2. Every /api/editor/* route is token-gated: 401 wrong/missing token, 503 when no
   token is configured; the editor kit list includes a DRAFT kit that the public
   manifest omits.
3. PUT schema + POST status round-trip through the routes (a saved edit is
   re-readable; a status flip preserves the other metadata keys), and the public
   /api/form-kits behavior is untouched (its own suite stays green).
"""
import asyncio
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import backend.routes.editor_kit_routes as ekr
import backend.routes.form_kit_routes as fkr
from backend.services.form_kits import (
    FormKitNotFound,
    FormKitStoreError,
    GCSFormKitStore,
    LocalFormKitStore,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# A minimal schema that validates against the canonical Pydantic FormSchema
# (source=pdf requires extraction_info) -- used by the mark-complete gate tests.
VALID_SCHEMA = {
    "source": "pdf",
    "form_metadata": {"title": "Test Form", "version": "unknown"},
    "sections": [{"id": "s1", "label": "Section 1", "order": 1, "fields": ["f1"]}],
    "fields": [
        {"id": "f1", "name": "Field 1", "spoken_name": "field one",
         "type": "text", "section_id": "s1"}
    ],
    "extraction_info": {
        "extracted_at": "2026-07-01T00:00:00Z",
        "extraction_confidence": 0.9,
        "extractor_version": "test",
        "manual_review_required": True,
    },
}


def _settings(editor=None, author=None):
    return SimpleNamespace(SCHEMA_EDITOR_TOKEN=editor, SCHEMA_AUTHOR_TOKEN=author)


def _make_kit(root, kit_id, *, status="draft", schema=None, label=None, extra_meta=None):
    kit_dir = root / kit_id
    kit_dir.mkdir()
    meta = {"status": status}
    if label:
        meta["label"] = label
    if extra_meta:
        meta.update(extra_meta)
    (kit_dir / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    if schema is not None:
        (kit_dir / "schema.json").write_text(json.dumps(schema), encoding="utf-8")
    (kit_dir / "form.pdf").write_bytes(b"%PDF-1.7 test")
    return kit_dir


# --- the auth dependency (wired through a real FastAPI app) -----------------


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient over ONLY the editor router, with a LocalFormKitStore on a
    tmp dir and both tokens configured. Auth runs through the real dependency
    wiring (no override), so 401/503 behavior is the deployed behavior."""
    app = FastAPI()
    app.include_router(ekr.router)
    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    return TestClient(app), store, tmp_path


def test_no_tokens_configured_is_503(client, monkeypatch):
    c, _store, _root = client
    monkeypatch.setattr(ekr, "get_settings", lambda: _settings())
    for path in ("/api/editor/session", "/api/editor/kits"):
        resp = c.get(path, headers={"X-Editor-Token": "anything"})
        assert resp.status_code == 503


def test_missing_or_wrong_token_is_401(client):
    c, _store, _root = client
    assert c.get("/api/editor/session").status_code == 401
    assert c.get(
        "/api/editor/session", headers={"X-Editor-Token": "wrong"}
    ).status_code == 401
    # Write routes too -- the gate is on every editor route.
    assert c.put(
        "/api/editor/kits/i-90/schema", json={"fields": []}
    ).status_code == 401
    assert c.post(
        "/api/editor/kits/i-90/status", json={"status": "draft"}
    ).status_code == 401


def test_session_reports_role_per_token(client):
    c, _store, _root = client
    r_editor = c.get("/api/editor/session", headers={"X-Editor-Token": "edit-tok"})
    assert r_editor.status_code == 200
    assert r_editor.json() == {"role": "editor"}
    r_author = c.get("/api/editor/session", headers={"X-Editor-Token": "auth-tok"})
    assert r_author.status_code == 200
    assert r_author.json() == {"role": "author"}


def test_editor_only_deployment_still_works(client, monkeypatch):
    # Only SCHEMA_EDITOR_TOKEN set (the polish-only deployment): editor code
    # works, author code does not exist -> 401.
    c, _store, _root = client
    monkeypatch.setattr(ekr, "get_settings", lambda: _settings(editor="edit-tok"))
    assert c.get(
        "/api/editor/session", headers={"X-Editor-Token": "edit-tok"}
    ).json() == {"role": "editor"}
    assert c.get(
        "/api/editor/session", headers={"X-Editor-Token": "auth-tok"}
    ).status_code == 401


def test_author_only_deployment_still_works(client, monkeypatch):
    # The symmetric case (fresh-eyes finding): only SCHEMA_AUTHOR_TOKEN set --
    # the author code works (role author), anything else is 401, and the
    # surface is NOT 503 (one configured token is enough to enable it).
    c, _store, _root = client
    monkeypatch.setattr(ekr, "get_settings", lambda: _settings(author="auth-tok"))
    r = c.get("/api/editor/session", headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200
    assert r.json() == {"role": "author"}
    assert c.get(
        "/api/editor/session", headers={"X-Editor-Token": "edit-tok"}
    ).status_code == 401


def test_require_author_role_rejects_editor():
    # The author gate (used by onboarding/extraction, bd 92qe.3) refuses the
    # editor role with 403 -- tested directly at the dependency level.
    with pytest.raises(HTTPException) as exc:
        _run(ekr.require_author_role("editor"))
    assert exc.value.status_code == 403
    assert _run(ekr.require_author_role("author")) == "author"


def test_non_ascii_access_code_is_401_not_500(client, monkeypatch):
    # hmac.compare_digest on str raises TypeError for non-ASCII (a pasted smart
    # quote); the compare must run over bytes so a malformed wrong code stays a
    # clean 401 (Codex P1, PR #279). Exercised at the dependency level (HTTP
    # headers are latin-1 on the wire; the failure mode is the decoded str).
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )
    with pytest.raises(HTTPException) as exc:
        # \u2019 = a right single "smart" quote; the escape keeps the
        # SOURCE ASCII (repo rule) while the runtime string is non-ASCII.
        _run(ekr.require_editor_role(x_editor_token="sm\u2019art-quote"))
    assert exc.value.status_code == 401
    # And a correct code containing non-ASCII still matches (bytes both sides).
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="caf\u00e9-tok")
    )
    assert _run(ekr.require_editor_role(x_editor_token="caf\u00e9-tok")) == "editor"


# --- store write methods: LocalFormKitStore round-trips ---------------------


def test_local_store_schema_write_roundtrip(tmp_path):
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    _run(store.put_schema("i-90", {"fields": [{"id": "a"}]}))
    assert _run(store.load_schema("i-90")) == {"fields": [{"id": "a"}]}
    # No temp files left behind by the atomic write.
    assert [p.name for p in (tmp_path / "i-90").iterdir()] == ["schema.json"]


def test_local_store_metadata_roundtrip(tmp_path):
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    assert _run(store.load_metadata("i-90")) is None  # absent -> None
    _run(store.put_metadata("i-90", {"label": "I-90", "status": "draft"}))
    assert _run(store.load_metadata("i-90")) == {"label": "I-90", "status": "draft"}


def test_local_store_unparseable_metadata_is_none(tmp_path):
    store = LocalFormKitStore(tmp_path)
    kit = tmp_path / "i-90"
    kit.mkdir()
    (kit / "metadata.json").write_text("{ not json", encoding="utf-8")
    assert _run(store.load_metadata("i-90")) is None
    (kit / "metadata.json").write_text(json.dumps(["a", "list"]), encoding="utf-8")
    assert _run(store.load_metadata("i-90")) is None


def test_local_store_list_kit_files_and_ids(tmp_path):
    store = LocalFormKitStore(tmp_path)
    _make_kit(tmp_path, "b-kit", schema={"fields": []})
    _make_kit(tmp_path, "a-kit")
    (tmp_path / "loose-file.txt").write_text("not a kit", encoding="utf-8")
    files = _run(store.list_kit_files())
    assert set(files) == {"a-kit", "b-kit"}
    assert files["b-kit"] == ["form.pdf", "metadata.json", "schema.json"]
    assert files["a-kit"] == ["form.pdf", "metadata.json"]
    assert _run(store.list_kit_ids()) == ["a-kit", "b-kit"]


def test_local_store_list_kit_files_missing_root(tmp_path):
    store = LocalFormKitStore(tmp_path / "absent")
    assert _run(store.list_kit_files()) == {}


def test_local_store_put_schema_sanitizes_filename(tmp_path):
    # A traversal schema_file must not escape the kit dir -- it degrades to the
    # conventional schema.json (same safe_filename guard as the read path).
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    (tmp_path / "outside.json").write_text("{}", encoding="utf-8")
    _run(store.put_schema("i-90", {"fields": []}, "../outside.json"))
    assert json.loads((tmp_path / "outside.json").read_text()) == {}  # untouched
    assert (tmp_path / "i-90" / "schema.json").exists()


# --- store write methods: GCS via a mocked client ----------------------------


class _FakeBlob:
    def __init__(self, name, registry):
        self.name = name
        self._registry = registry
        self.cache_control = None

    def upload_from_string(self, data, content_type=None):
        self._registry[self.name] = {
            "data": data,
            "content_type": content_type,
            "cache_control": self.cache_control,
        }

    def download_as_bytes(self):
        if self.name not in self._registry:
            raise _FakeNotFound(self.name)
        data = self._registry[self.name]["data"]
        return data.encode("utf-8") if isinstance(data, str) else data


class _FakeNotFound(Exception):
    pass


class _FakeBucket:
    def __init__(self, registry):
        self._registry = registry

    def blob(self, name):
        return _FakeBlob(name, self._registry)


def _gcs_store(registry, prefix="form-kits"):
    store = GCSFormKitStore.__new__(GCSFormKitStore)
    store.bucket_name = "bucket"
    store.prefix = prefix
    store._bucket = _FakeBucket(registry)
    store._not_found_exc = _FakeNotFound
    store._client = SimpleNamespace(
        list_blobs=lambda bucket_name, prefix: [
            SimpleNamespace(name=n) for n in sorted(registry) if n.startswith(prefix)
        ]
    )
    return store


def test_gcs_put_schema_uploads_json_no_cache():
    registry = {}
    store = _gcs_store(registry)
    _run(store.put_schema("i-90", {"fields": []}))
    entry = registry["form-kits/i-90/schema.json"]
    assert entry["content_type"] == "application/json"
    assert entry["cache_control"] == "no-cache"
    assert json.loads(entry["data"]) == {"fields": []}


def test_gcs_metadata_roundtrip_and_missing_is_none():
    registry = {}
    store = _gcs_store(registry)
    assert _run(store.load_metadata("i-90")) is None
    _run(store.put_metadata("i-90", {"status": "draft", "label": "I-90"}))
    assert _run(store.load_metadata("i-90")) == {"status": "draft", "label": "I-90"}


def test_gcs_list_kit_files_groups_by_kit():
    registry = {
        "form-kits/index.json": {"data": "{}"},          # manifest -> not a kit
        "form-kits/i-90/schema.json": {"data": "{}"},
        "form-kits/i-90/form.pdf": {"data": "x"},
        "form-kits/w-7/metadata.json": {"data": "{}"},
        "form-kits/deep/nested/file.json": {"data": "{}"},  # too deep -> ignored
    }
    store = _gcs_store(registry)
    files = _run(store.list_kit_files())
    assert files == {
        "i-90": ["form.pdf", "schema.json"],
        "w-7": ["metadata.json"],
    }


def test_gcs_upload_failure_maps_to_store_error():
    class _BoomBucket:
        def blob(self, name):
            raise RuntimeError("gcs down")

    store = GCSFormKitStore.__new__(GCSFormKitStore)
    store.bucket_name = "bucket"
    store.prefix = "form-kits"
    store._bucket = _BoomBucket()
    store._not_found_exc = _FakeNotFound
    with pytest.raises(FormKitStoreError):
        _run(store.put_schema("i-90", {"fields": []}))


def test_gcs_metadata_download_failure_maps_to_store_error():
    # A NON-NotFound storage failure (transient service error, permissions) on
    # the metadata read must surface as FormKitStoreError like every other GCS
    # method -- callers only catch that, so a raw google exception would become
    # an uncaught 500 (Codex P1, PR #279).
    class _BoomBlob:
        def download_as_bytes(self):
            raise RuntimeError("503 backend error")

    class _BoomBucket:
        def blob(self, name):
            return _BoomBlob()

    store = GCSFormKitStore.__new__(GCSFormKitStore)
    store.bucket_name = "bucket"
    store.prefix = "form-kits"
    store._bucket = _BoomBucket()
    store._not_found_exc = _FakeNotFound
    with pytest.raises(FormKitStoreError):
        _run(store.load_metadata("i-90"))


# --- the publish gate: WIP must never leak to the public surface ------------
# (Codex P1, PR #279: a lenient draft save over a manifest-listed kit's schema
# would stream to voice users immediately. Three-part fix under test here:
# the save-guard on complete kits, the public read gate honoring LIVE status
# on enforcing stores, and the public list filtering reverted kits.)


class _PublishedStore:
    """GCS-shaped fake: manifest lists the kit; live metadata is mutable."""

    allow_convention_fallback = False
    enforce_complete_on_public_reads = True

    def __init__(self, status="complete"):
        self.status = status
        self.saved = None

    async def load_manifest(self, manifest_file="index.json"):
        return {"forms": [{"id": "live-kit", "label": "Live",
                           "description": None,
                           "schemaFile": "schema.json",
                           "schemaPath": "/form-kits/live-kit/schema.json",
                           "pdfFile": "form.pdf",
                           "pdfPath": "/form-kits/live-kit/form.pdf"}]}

    async def list_kit_files(self):
        return {"live-kit": ["form.pdf", "metadata.json", "schema.json"]}

    async def load_metadata(self, kit_id):
        if self.status is None:
            return None
        return {"status": self.status, "label": "Live"}

    async def load_schema(self, kit_id, schema_file="schema.json"):
        return {"fields": []}

    async def load_pdf_bytes(self, kit_id, pdf_file="form.pdf"):
        return b"%PDF"

    async def put_schema(self, kit_id, schema, schema_file="schema.json"):
        self.saved = (kit_id, schema, schema_file)


def test_put_schema_refuses_published_kit(client, monkeypatch):
    # Saving over a COMPLETE kit would go live instantly -- refuse with the
    # revert-first message; the store write must never be reached.
    c, _store, _root = client
    store = _PublishedStore(status="complete")
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    r = c.put(
        "/api/editor/kits/live-kit/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    )
    assert r.status_code == 409
    assert "Revert it to draft" in r.json()["detail"]
    assert store.saved is None
    # After the revert, the same save lands.
    store.status = "draft"
    r2 = c.put(
        "/api/editor/kits/live-kit/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    )
    assert r2.status_code == 200
    assert store.saved is not None


def test_public_reads_honor_live_status_on_enforcing_store(monkeypatch):
    # GCS-shaped store: a kit reverted to draft unpublishes IMMEDIATELY --
    # the public schema/pdf reads 404 even though the manifest still lists it.
    store = _PublishedStore(status="draft")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)
    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("live-kit"))
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException) as exc2:
        _run(fkr.get_form_kit_pdf("live-kit"))
    assert exc2.value.status_code == 404
    # Complete -> served.
    store.status = "complete"
    assert json.loads(_run(fkr.get_form_kit_schema("live-kit")).body) == {"fields": []}
    # MISSING metadata on an enforcing store fails closed too (every
    # legitimately deployed/onboarded kit carries metadata.json).
    store.status = None
    with pytest.raises(HTTPException) as exc3:
        _run(fkr.get_form_kit_schema("live-kit"))
    assert exc3.value.status_code == 404


def test_public_read_metadata_store_error_fails_closed_502(monkeypatch):
    store = _PublishedStore(status="complete")

    async def _boom(kit_id):
        raise FormKitStoreError("metadata read failed")

    store.load_metadata = _boom
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)
    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("live-kit"))
    assert exc.value.status_code == 502


def test_public_list_filters_reverted_kits_on_enforcing_store(monkeypatch):
    store = _PublishedStore(status="draft")
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)
    assert _run(fkr.list_form_kits()).forms == []
    store.status = "complete"
    assert [f.id for f in _run(fkr.list_form_kits()).forms] == ["live-kit"]


def test_local_store_public_reads_stay_ungated(client):
    # Local mode is ungated by design: a draft kit's schema stays publicly
    # readable (dev serves drafts on purpose). The flag, not the status, gates.
    _c, store, root = client
    _make_kit(root, "draft-kit", status="draft", schema={"fields": []})
    import backend.routes.form_kit_routes as _fkr
    import pytest as _pytest
    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(_fkr, "get_form_kit_store", lambda: store)
        resp = _run(_fkr.get_form_kit_schema("draft-kit"))
        assert json.loads(resp.body) == {"fields": []}


# --- the editor list: drafts included (the manifest-bypass linchpin) --------


def test_editor_list_includes_draft_the_public_manifest_omits(client, monkeypatch):
    """GCS-shaped store: the public manifest lists only the COMPLETE kit, but the
    editor list (built from the storage listing) shows the draft too -- the whole
    point of the token-gated surface."""
    c, _local_store, _root = client

    class _GcsShapedStore:
        allow_convention_fallback = False  # GCS semantics

        async def load_manifest(self, manifest_file="index.json"):
            return {"forms": [{"id": "done-kit", "label": "Done",
                               "description": None,
                               "schemaFile": "schema.json",
                               "schemaPath": "/form-kits/done-kit/schema.json",
                               "pdfFile": "form.pdf",
                               "pdfPath": "/form-kits/done-kit/form.pdf"}]}

        async def list_kit_files(self):
            return {
                "done-kit": ["form.pdf", "metadata.json", "schema.json"],
                "draft-kit": ["form.pdf", "metadata.json", "schema.json"],
            }

        async def load_metadata(self, kit_id):
            return {"status": "complete" if kit_id == "done-kit" else "draft"}

        async def load_schema(self, kit_id, schema_file="schema.json"):
            return {"fields": []}

    store = _GcsShapedStore()
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    editor_ids = {
        k["id"]
        for k in c.get(
            "/api/editor/kits", headers={"X-Editor-Token": "edit-tok"}
        ).json()["kits"]
    }
    assert editor_ids == {"done-kit", "draft-kit"}

    public_ids = {f.id for f in _run(fkr.list_form_kits()).forms}
    assert public_ids == {"done-kit"}  # the draft is absent from the public list

    # And the draft's schema is servable via the EDITOR route while the PUBLIC
    # single-kit route refuses it (manifest allowlist, GCS fail-closed).
    r = c.get(
        "/api/editor/kits/draft-kit/schema", headers={"X-Editor-Token": "edit-tok"}
    )
    assert r.status_code == 200
    with pytest.raises(HTTPException) as exc:
        _run(fkr.get_form_kit_schema("draft-kit"))
    assert exc.value.status_code == 404


def test_editor_list_reflects_metadata_and_files(client):
    c, _store, root = client
    _make_kit(root, "polished", status="complete", schema=VALID_SCHEMA,
              label="Polished Form")
    _make_kit(root, "fresh")  # no schema yet (pre-extraction)
    resp = c.get("/api/editor/kits", headers={"X-Editor-Token": "edit-tok"})
    assert resp.status_code == 200
    by_id = {k["id"]: k for k in resp.json()["kits"]}
    assert by_id["polished"]["status"] == "complete"
    assert by_id["polished"]["label"] == "Polished Form"
    assert by_id["polished"]["hasSchema"] is True
    assert by_id["fresh"]["status"] == "draft"
    assert by_id["fresh"]["hasSchema"] is False
    assert by_id["fresh"]["hasPdf"] is True


def test_editor_list_survives_one_broken_kit(client):
    # A kit with unreadable metadata still lists (status unknown) -- one bad kit
    # must not hide the rest of the catalogue.
    c, _store, root = client
    _make_kit(root, "good-kit", schema={"fields": []})
    bad = root / "bad-kit"
    bad.mkdir()
    (bad / "metadata.json").write_text("{ not json", encoding="utf-8")
    resp = c.get("/api/editor/kits", headers={"X-Editor-Token": "edit-tok"})
    by_id = {k["id"]: k for k in resp.json()["kits"]}
    assert set(by_id) == {"good-kit", "bad-kit"}
    assert by_id["bad-kit"]["status"] == "unknown"


# --- editor single-kit reads -------------------------------------------------


def test_editor_schema_and_pdf_reads(client):
    c, _store, root = client
    _make_kit(root, "i-90", schema={"fields": [{"id": "a"}]})
    r = c.get("/api/editor/kits/i-90/schema", headers={"X-Editor-Token": "edit-tok"})
    assert r.status_code == 200
    assert r.headers["cache-control"] == "no-store"
    assert r.json() == {"fields": [{"id": "a"}]}
    p = c.get("/api/editor/kits/i-90/pdf", headers={"X-Editor-Token": "edit-tok"})
    assert p.status_code == 200
    assert p.headers["content-type"] == "application/pdf"
    assert p.content == b"%PDF-1.7 test"


def test_editor_reads_honor_custom_filenames_from_metadata(client):
    c, _store, root = client
    kit = root / "custom"
    kit.mkdir()
    (kit / "metadata.json").write_text(
        json.dumps({"schema": "custom.json", "pdf": "doc.pdf", "status": "draft"}),
        encoding="utf-8",
    )
    (kit / "custom.json").write_text(json.dumps({"fields": []}), encoding="utf-8")
    (kit / "doc.pdf").write_bytes(b"%PDF custom")
    r = c.get("/api/editor/kits/custom/schema", headers={"X-Editor-Token": "edit-tok"})
    assert r.status_code == 200
    p = c.get("/api/editor/kits/custom/pdf", headers={"X-Editor-Token": "edit-tok"})
    assert p.content == b"%PDF custom"


def test_editor_unknown_kit_404_and_bad_id_400(client):
    c, _store, root = client
    _make_kit(root, "i-90", schema={"fields": []})
    assert c.get(
        "/api/editor/kits/absent/schema", headers={"X-Editor-Token": "edit-tok"}
    ).status_code == 404
    # Traversal-shaped ids are rejected by the shared guard. (A literal "../x"
    # path segment never routes here, so use a same-segment traversal.)
    assert c.get(
        "/api/editor/kits/..%2Fsecret/schema", headers={"X-Editor-Token": "edit-tok"}
    ).status_code in (400, 404)
    r = c.put(
        "/api/editor/kits/bad id/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    )
    assert r.status_code == 400


def test_editor_schemaless_kit_schema_read_is_404(client):
    c, _store, root = client
    _make_kit(root, "fresh")  # PDF only
    r = c.get("/api/editor/kits/fresh/schema", headers={"X-Editor-Token": "edit-tok"})
    assert r.status_code == 404


# --- PUT schema: the hosted save ---------------------------------------------


def test_put_schema_roundtrip(client):
    c, store, root = client
    _make_kit(root, "i-90", schema={"fields": []})
    edited = {"fields": [{"id": "a", "spoken_name": "Alpha"}], "sections": []}
    r = c.put(
        "/api/editor/kits/i-90/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json=edited,
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "schemaFile": "schema.json"}
    # The saved edit is re-readable through the read route (the round trip).
    back = c.get("/api/editor/kits/i-90/schema", headers={"X-Editor-Token": "edit-tok"})
    assert back.json() == edited


def test_put_schema_writes_to_custom_filename(client):
    c, _store, root = client
    kit = root / "custom"
    kit.mkdir()
    (kit / "metadata.json").write_text(
        json.dumps({"schema": "custom.json", "status": "draft"}), encoding="utf-8"
    )
    (kit / "custom.json").write_text(json.dumps({"fields": []}), encoding="utf-8")
    r = c.put(
        "/api/editor/kits/custom/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": [{"id": "x"}]},
    )
    assert r.status_code == 200
    assert r.json()["schemaFile"] == "custom.json"
    assert json.loads((kit / "custom.json").read_text())["fields"] == [{"id": "x"}]


def test_put_schema_unknown_kit_is_404(client):
    c, _store, _root = client
    r = c.put(
        "/api/editor/kits/ghost/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    )
    assert r.status_code == 404


def test_put_schema_rejects_formless_bodies(client):
    c, _store, root = client
    _make_kit(root, "i-90", schema={"fields": []})
    # fields missing / not a list -> 422 (a body the editor could never reopen).
    for bad in ({}, {"fields": "abc"}, {"fields": {"a": 1}}):
        r = c.put(
            "/api/editor/kits/i-90/schema",
            headers={"X-Editor-Token": "edit-tok"},
            json=bad,
        )
        assert r.status_code == 422, bad
    # A non-object body is rejected by FastAPI's dict coercion itself.
    r = c.put(
        "/api/editor/kits/i-90/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json=["not", "an", "object"],
    )
    assert r.status_code == 422


# --- POST status: the publish gate -------------------------------------------


def test_status_flip_preserves_other_metadata(client):
    c, _store, root = client
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA,
              label="Form I-90", extra_meta={"description": "Green card"})
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 200
    meta = json.loads((root / "i-90" / "metadata.json").read_text())
    assert meta["status"] == "complete"
    assert meta["label"] == "Form I-90"          # preserved
    assert meta["description"] == "Green card"   # preserved


def test_status_revert_to_draft_is_unconditional(client):
    c, _store, root = client
    # Broken schema -- reverting to draft must still work (only PROMOTION gates).
    _make_kit(root, "broken", status="complete", schema={"fields": "oops"})
    r = c.post(
        "/api/editor/kits/broken/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "draft"},
    )
    assert r.status_code == 200
    meta = json.loads((root / "broken" / "metadata.json").read_text())
    assert meta["status"] == "draft"


def test_mark_complete_requires_a_schema(client):
    c, _store, root = client
    _make_kit(root, "fresh")  # no schema yet
    r = c.post(
        "/api/editor/kits/fresh/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409


def test_mark_complete_validates_against_form_contract(client):
    c, _store, root = client
    # Structurally-broken schema: promotion is refused with the validation detail
    # (the deploy would otherwise ship it to the voice app).
    _make_kit(root, "broken", schema={"fields": [{"id": "only-an-id"}]})
    r = c.post(
        "/api/editor/kits/broken/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 422
    assert "cannot be marked complete" in r.json()["detail"]
    # And a VALID schema promotes fine.
    _make_kit(root, "good", schema=VALID_SCHEMA)
    r2 = c.post(
        "/api/editor/kits/good/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r2.status_code == 200


def test_write_paths_fail_closed_on_metadata_store_error(client, monkeypatch):
    # metadata.status is the GUARD input for the publish gate -- a failed read
    # must be a 502, never degrade to None and let a save land on a possibly-
    # published kit (Codex P1 r2, PR #279).
    c, _store, _root = client

    class _MetaBoomStore:
        async def list_kit_files(self):
            return {"live-kit": ["form.pdf", "metadata.json", "schema.json"]}

        async def load_metadata(self, kit_id):
            raise FormKitStoreError("transient GCS failure")

        async def put_schema(self, *a, **k):
            raise AssertionError("write reached despite unreadable metadata")

        async def put_metadata(self, *a, **k):
            raise AssertionError("write reached despite unreadable metadata")

    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: _MetaBoomStore())
    r = c.put(
        "/api/editor/kits/live-kit/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    )
    assert r.status_code == 502
    r2 = c.post(
        "/api/editor/kits/live-kit/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "draft"},
    )
    assert r2.status_code == 502


def test_mark_complete_requires_a_pdf(client):
    # A complete kit ships to the voice app, which serves its PDF -- promoting
    # a PDF-less kit would deploy a form whose PDF read 404s (Codex P1 r2).
    c, _store, root = client
    kit = root / "no-pdf"
    kit.mkdir()
    (kit / "metadata.json").write_text(json.dumps({"status": "draft"}), encoding="utf-8")
    (kit / "schema.json").write_text(json.dumps(VALID_SCHEMA), encoding="utf-8")
    r = c.post(
        "/api/editor/kits/no-pdf/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409
    assert "PDF" in r.json()["detail"]


def test_mark_complete_requires_extraction_info_for_pdf_schema(client):
    # Pydantic v2 skips field validators for omitted defaults, so the model's
    # "extraction_info required for PDF forms" rule never fires on an ABSENT
    # value -- the publish gate enforces it explicitly (Codex P1 r2).
    c, _store, root = client
    schema = {k: v for k, v in VALID_SCHEMA.items() if k != "extraction_info"}
    _make_kit(root, "no-provenance", schema=schema)
    r = c.post(
        "/api/editor/kits/no-provenance/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 422
    assert "extraction_info" in r.json()["detail"]


def test_local_concurrent_writes_to_same_file_both_succeed(tmp_path):
    # Two overlapping saves of the SAME file must not collide on a shared temp
    # path (pid-only temp names did; per-write nonce fixes it -- Codex P1 r2).
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()

    async def _both():
        await asyncio.gather(
            store.put_schema("i-90", {"fields": [{"id": "a"}]}),
            store.put_schema("i-90", {"fields": [{"id": "b"}]}),
        )

    _run(_both())
    # One of the two payloads won (last-write-wins is fine); the file must be
    # intact valid JSON and no temp litter may remain.
    final = _run(store.load_schema("i-90"))
    assert final["fields"][0]["id"] in ("a", "b")
    assert [p.name for p in (tmp_path / "i-90").iterdir()] == ["schema.json"]


def test_status_rejects_unknown_values(client):
    c, _store, root = client
    _make_kit(root, "i-90", schema=VALID_SCHEMA)
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "published"},
    )
    assert r.status_code == 422
