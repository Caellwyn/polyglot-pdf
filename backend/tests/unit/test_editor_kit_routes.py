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


def _settings(editor=None, author=None, **overrides):
    base = dict(
        SCHEMA_EDITOR_TOKEN=editor,
        SCHEMA_AUTHOR_TOKEN=author,
        # Extraction knobs (bd 92qe.3) with test-friendly defaults.
        EXTRACTOR_MODEL="gemini-2.5-pro",
        EXTRACTOR_TIMEOUT_SEC=60.0,
        EXTRACTOR_MAX_PDF_MB=25.0,
        GEMINI_API_KEY="fake-key",
        # Default to AI Studio auth in tests (a key is present above); the
        # Vertex/ADC path is exercised explicitly where it matters (bd fyq4).
        VERTEXAI=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


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


def test_parse_extra_origins_accepts_semicolons_and_commas():
    # The value rides `gcloud run deploy --set-env-vars=A=1,B=2` where commas
    # separate PAIRS, so multi-origin values use semicolons in the deploy
    # scripts (bd 92qe.4); commas keep working for hand-set local env.
    from backend.config import parse_extra_origins

    assert parse_extra_origins(
        "https://a.web.app;https://a.firebaseapp.com"
    ) == ["https://a.web.app", "https://a.firebaseapp.com"]
    assert parse_extra_origins("https://a, https://b") == ["https://a", "https://b"]
    assert parse_extra_origins(None) == []
    assert parse_extra_origins(" ; , ") == []


# --- store write methods: LocalFormKitStore round-trips ---------------------


def test_local_store_schema_write_roundtrip(tmp_path):
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    _run(store.put_schema("i-90", {"fields": [{"id": "a"}]}))
    assert _run(store.load_schema("i-90")) == {"fields": [{"id": "a"}]}
    # No temp files left behind by the atomic write.
    assert [p.name for p in (tmp_path / "i-90").iterdir()] == ["schema.json"]


def test_local_store_json_artifact_roundtrip(tmp_path):
    # bd polyglot-pdf-v96b: the AcroForm dump is persisted as a kit artifact.
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    dump = {"fields": [{"name": "form1[0].a[0]"}], "field_count": 1}
    _run(store.put_json_artifact("i-90", dump, "acroform.json"))
    assert _run(store.load_json_artifact("i-90", "acroform.json")) == dump


def test_local_store_missing_artifact_is_not_found(tmp_path):
    from backend.services.form_kits import FormKitNotFound
    store = LocalFormKitStore(tmp_path)
    (tmp_path / "i-90").mkdir()
    with pytest.raises(FormKitNotFound):
        _run(store.load_json_artifact("i-90", "acroform.json"))


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


def test_gcs_json_artifact_roundtrip_and_missing_is_not_found():
    registry = {}
    store = _gcs_store(registry)
    with pytest.raises(FormKitNotFound):
        _run(store.load_json_artifact("i-90", "acroform.json"))
    dump = {"fields": [{"name": "form1[0].a[0]"}]}
    _run(store.put_json_artifact("i-90", dump, "acroform.json"))
    assert _run(store.load_json_artifact("i-90", "acroform.json")) == dump


def test_gcs_json_artifact_transient_error_is_store_error_not_raw():
    # Opus fallback (PR #323): a NON-NotFound GCS read error must be wrapped as
    # FormKitStoreError, not escape raw -- else _load_kit_dump (which catches
    # only FormKitNotFound/FormKitStoreError) would 500 the promotion gate. Drive
    # it through the REAL _fetch_bytes by making the blob download raise a
    # transient (non-NotFound) error.
    class _Transient(Exception):
        pass

    class _TransientBucket(_FakeBucket):
        def blob(self, name):
            b = _FakeBlob(name, self._registry)
            def _raise():
                raise _Transient("GCS unavailable")
            b.download_as_bytes = _raise
            return b

    registry = {"form-kits/i-90/acroform.json": {"data": "{}"}}
    store = _gcs_store(registry)
    store._bucket = _TransientBucket(registry)
    with pytest.raises(FormKitStoreError):
        _run(store.load_json_artifact("i-90", "acroform.json"))


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


# --- POST /lint: load-time findings for the editor (bd h76m.11, P4.3) --------


def test_lint_endpoint_is_token_gated(client):
    c, _store, _root = client
    # Missing/wrong token -> 401 (the gate is on every editor route).
    assert c.post("/api/editor/lint", json={"fields": []}).status_code == 401
    assert c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "wrong"},
        json={"fields": []},
    ).status_code == 401


def test_lint_clean_schema_reports_zero_findings(client):
    c, _store, _root = client
    r = c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=VALID_SCHEMA,
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"findings": [], "errorCount": 0, "warningCount": 0}


def test_lint_reports_findings_with_field_focus(client):
    # The core P4.3 exit criterion, at the endpoint: a defective draft comes
    # back as findings each carrying the field_id the panel focuses on click.
    c, _store, _root = client
    schema = {
        "source": "pdf",
        "form_metadata": {"title": "T", "version": "unknown"},
        "sections": [],
        "fields": [
            {"id": "picker", "type": "select",
             "options": [{"value": "alpha", "label": "Alpha"}]},
            {"id": "dep", "type": "text",
             "show_if": {"field": "picker", "operator": "is_selected",
                         "value": "alpha"}},
        ],
    }
    r = c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=schema,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["errorCount"] >= 1
    finding = next(f for f in body["findings"] if f["rule"] == "unknown-operator")
    assert finding["field_id"] == "dep"
    assert finding["severity"] == "ERROR"
    assert "path" in finding and "message" in finding


def test_lint_never_4xxs_on_a_malformed_draft(client):
    # A structurally-broken draft (the thing the contractor needs findings for)
    # must lint, not error: lint_schema never raises, so the route stays 200
    # with a condition-malformed finding rather than a 422.
    c, _store, _root = client
    schema = {
        "source": "pdf",
        "fields": [
            {"id": "bad", "type": "text", "show_if": "not-an-object"},
        ],
    }
    r = c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=schema,
    )
    assert r.status_code == 200
    body = r.json()
    assert any(f["rule"] == "condition-malformed" for f in body["findings"])


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


def test_mark_complete_lint_gate_409s_naming_findings(client):
    """bd h76m.5 (P2.1): zero lint ERRORs to promote. A schema that PARSES
    (duplicate option values are legal to Pydantic on a v1 schema -- the
    shipped-f1040 bug class) must still be refused at the publish gate, with
    the findings named so the editor can fix them."""
    from backend.models.form_models import FormSchema

    c, _store, root = client
    linty = json.loads(json.dumps(VALID_SCHEMA))  # deep copy
    linty["sections"][0]["fields"].append("picker")
    linty["fields"].append({
        "id": "picker", "name": "Picker", "spoken_name": "picker",
        "type": "select", "section_id": "s1",
        "options": [
            {"value": "same", "label": "A"},
            {"value": "same", "label": "B"},
        ],
    })
    # Sanity: this schema passes the Pydantic gate (v1 tolerance) -- the lint
    # gate is the ONLY thing standing between it and the voice app.
    FormSchema.model_validate(linty)

    _make_kit(root, "linty", schema=linty)
    r = c.post(
        "/api/editor/kits/linty/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "lint error" in detail
    assert "option-value-duplicate" in detail  # names the rule
    assert "picker" in detail                  # names the field
    # The kit stays draft.
    meta = json.loads((root / "linty" / "metadata.json").read_text())
    assert meta["status"] == "draft"


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


# --- author tier: onboarding + hosted extraction (bd polyglot-pdf-92qe.3) ----


PDF_BYTES = b"%PDF-1.7 fake acroform"


def _upload(c, token, filename="Form I-90.pdf", data=PDF_BYTES, label=None):
    form = {"label": label} if label else {}
    return c.post(
        "/api/editor/kits",
        headers={"X-Editor-Token": token},
        files={"pdf": (filename, data, "application/pdf")},
        data=form,
    )


def test_onboard_creates_kit_with_author_token(client):
    c, store, root = client
    r = _upload(c, "auth-tok")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "form-i-90"
    assert body["status"] == "draft"
    assert body["hasPdf"] is True and body["hasSchema"] is False
    # The kit landed in the store: pdf bytes + draft metadata.
    assert (root / "form-i-90" / "form.pdf").read_bytes() == PDF_BYTES
    meta = json.loads((root / "form-i-90" / "metadata.json").read_text())
    assert meta == {"label": "Form I 90", "status": "draft"}


def test_onboard_uniquifies_taken_ids_and_honors_label(client):
    c, _store, root = client
    _make_kit(root, "form-i-90")
    r = _upload(c, "auth-tok", label="My Custom Label")
    assert r.status_code == 200
    assert r.json()["id"] == "form-i-90-2"
    meta = json.loads((root / "form-i-90-2" / "metadata.json").read_text())
    assert meta["label"] == "My Custom Label"


def test_onboard_requires_author_role(client):
    c, _store, root = client
    r = _upload(c, "edit-tok")
    assert r.status_code == 403
    assert list(root.iterdir()) == []  # nothing was created


def test_onboard_rejects_non_pdf_and_oversize(client, monkeypatch):
    c, _store, root = client
    r = _upload(c, "auth-tok", filename="page.pdf", data=b"<html>not a pdf")
    assert r.status_code == 422
    monkeypatch.setattr(
        ekr, "get_settings",
        lambda: _settings(editor="edit-tok", author="auth-tok", EXTRACTOR_MAX_PDF_MB=0.00001),
    )
    r2 = _upload(c, "auth-tok")
    assert r2.status_code == 413
    assert list(root.iterdir()) == []


def test_concurrent_onboards_of_same_filename_both_persist(tmp_path, monkeypatch):
    # TOCTOU (fresh-eyes, reproduced): two concurrent uploads deriving the SAME
    # kit id must NOT silently collapse onto one kit -- both PDFs persist under
    # DISTINCT ids (the onboard lock serializes the list->derive->write window).
    # Direct async calls on ONE loop (asyncio.gather): the TestClient runs each
    # request on its own portal loop, which cannot exercise a shared lock.
    import io
    from starlette.datastructures import UploadFile as StarletteUploadFile

    store = LocalFormKitStore(tmp_path)
    monkeypatch.setattr(ekr, "get_form_kit_store", lambda: store)
    monkeypatch.setattr(
        ekr, "get_settings", lambda: _settings(editor="edit-tok", author="auth-tok")
    )

    def _upload_file(payload: bytes) -> StarletteUploadFile:
        return StarletteUploadFile(
            file=io.BytesIO(payload), filename="Form I-90.pdf"
        )

    async def _both():
        return await asyncio.gather(
            ekr.onboard_editor_kit(
                role="author", pdf=_upload_file(b"%PDF-1.7 AUTHOR-A"), label=None
            ),
            ekr.onboard_editor_kit(
                role="author", pdf=_upload_file(b"%PDF-1.7 AUTHOR-B"), label=None
            ),
        )

    results = asyncio.new_event_loop().run_until_complete(_both())
    ids = sorted(r.id for r in results)
    assert ids == ["form-i-90", "form-i-90-2"]
    stored = sorted((tmp_path / kid / "form.pdf").read_bytes() for kid in ids)
    assert stored == [b"%PDF-1.7 AUTHOR-A", b"%PDF-1.7 AUTHOR-B"]


def test_onboard_long_filename_truncates_instead_of_400(client):
    # A realistic long download name must onboard (truncated slug), never 400
    # with a baffling "Invalid kit id" (fresh-eyes, reproduced live).
    c, _store, root = client
    long_name = (
        "USCIS Form I-90 Application to Replace Permanent Resident Card "
        "(Green Card) - Official 2026 Edition Downloaded From Immigration "
        "Website.pdf"
    )
    r = _upload(c, "auth-tok", filename=long_name)
    assert r.status_code == 200, r.text
    kit_id = r.json()["id"]
    assert len(kit_id) <= 64
    assert (root / kit_id / "form.pdf").exists()


def _fake_extractor(schema_payload, exit_code=0, write_out=True, dump=None):
    """A subprocess.run stand-in that mimics extract_form.py: writes --out (and,
    when `dump` is given, the sibling <out-stem>_acroform.json under --keep-dump,
    matching the real extractor's --keep-dump behavior the route now requests)."""

    def _run(cmd, **kwargs):
        out_path = cmd[cmd.index("--out") + 1]
        if write_out:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(schema_payload, fh)
        if dump is not None:
            import os as _os
            stem = _os.path.splitext(out_path)[0]
            with open(stem + "_acroform.json", "w", encoding="utf-8") as fh:
                json.dump(dump, fh)
        return SimpleNamespace(
            returncode=exit_code,
            stdout=f"[OK] wrote {out_path} -- 2 fields",
            stderr="",
        )

    return _run


def test_extract_runs_and_stores_the_draft(client, monkeypatch):
    c, store, root = client
    _make_kit(root, "fresh")  # PDF, no schema
    # A clean v2 draft (validates + lint-clean): a standalone text field.
    draft = {
        "source": "pdf", "schema_version": "2",
        "form_metadata": {"title": "T", "version": "unknown"},
        "sections": [{"id": "s1", "label": "S1", "order": 1, "fields": ["a"]}],
        "fields": [{"id": "a", "name": "A", "spoken_name": "a", "type": "text",
                    "section_id": "s1", "pdf_field_name": "form1[0].a[0]"}],
        "extraction_info": {"extracted_at": "2026-07-05T00:00:00Z",
                            "extraction_confidence": 0.9,
                            "extractor_version": "t", "manual_review_required": True},
    }
    fake = _fake_extractor(draft, exit_code=0)
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    r = c.post(
        "/api/editor/kits/fresh/extract",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["fieldCount"] == 1
    assert body["schemaFile"] == "schema.json"
    # A clean draft is NOT stored-with-issues and carries zero lint counts.
    assert body["storedWithIssues"] is False
    assert body["errorCount"] == 0 and body["warningCount"] == 0
    # The temp --out path never leaks into the user-facing detail.
    assert ".tmp" not in body["detail"] and "extract_" not in body["detail"]
    # The draft landed in the store.
    assert _run(store.load_schema("fresh")) == draft


# --- store-with-issues (bd polyglot-pdf-v96b, P5.3a) -------------------------

# A lint-DIRTY draft with >= 1 field: a v1 field whose show_if names an unknown
# operator (unknown-operator ERROR) -- parseable, so it stores with issues.
_DIRTY_DRAFT = {
    "source": "pdf",
    "form_metadata": {"title": "T", "version": "unknown"},
    "sections": [],
    "fields": [
        {"id": "picker", "type": "select",
         "options": [{"value": "alpha", "label": "Alpha"}]},
        {"id": "dep", "type": "text",
         "show_if": {"field": "picker", "operator": "is_selected", "value": "alpha"}},
    ],
}


def test_extract_stores_lint_dirty_draft_with_issues_200(client, monkeypatch):
    # Exit criterion 1: a forced-imperfect extraction STORES the draft and
    # returns 200 carrying lint counts + storedWithIssues, not a 502.
    c, store, root = client
    _make_kit(root, "fresh")
    fake = _fake_extractor(_DIRTY_DRAFT, exit_code=3)  # tri-state ISSUES
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["storedWithIssues"] is True
    assert body["errorCount"] >= 1
    # The imperfect draft landed in the store (store-with-issues, not dropped).
    assert _run(store.load_schema("fresh")) == _DIRTY_DRAFT


def test_extract_junk_fields_list_is_no_usable_draft_502(client, monkeypatch):
    # fresh-eyes: a non-empty fields list of NON-DICT junk (a crash mid-write)
    # must NOT pass the floor -- lint_schema silently filters non-dicts out, so
    # storing it would report a false "clean success" with a junk field count.
    # The floor is re-derived from real (dict) field members, so this 502s.
    c, store, root = client
    _make_kit(root, "fresh")
    junk = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
            "sections": [], "fields": ["not", "a", "real", "field"]}
    fake = _fake_extractor(junk, exit_code=1)  # simulate a crash exit
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502, r.text
    assert "no usable draft" in r.json()["detail"]
    # Nothing was stored -- the junk never reached the kit's schema.
    with pytest.raises(FormKitNotFound):
        _run(store.load_schema("fresh"))


def test_extract_field_count_counts_only_real_fields(client, monkeypatch):
    # fresh-eyes: a mix of real + junk field entries reports only the real count.
    c, store, root = client
    _make_kit(root, "fresh")
    mixed = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
             "sections": [], "fields": [{"id": "a", "type": "text"}, "junk", 7]}
    fake = _fake_extractor(mixed, exit_code=0)
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["fieldCount"] == 1  # only the one dict-shaped field


def test_extract_persists_the_acroform_dump_artifact(client, monkeypatch):
    # The dump becomes the kit's acroform.json artifact (feeds the promotion-gate
    # widget-claim rule + the P5.3c picker).
    c, store, root = client
    _make_kit(root, "fresh")
    dump = {"fields": [{"name": "form1[0].a[0]"}], "field_count": 1}
    draft = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
             "sections": [], "fields": [{"id": "a", "type": "text"}]}
    fake = _fake_extractor(draft, exit_code=0, dump=dump)
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 200, r.text
    # The dump was stored as acroform.json and reads back.
    assert _run(store.load_json_artifact("fresh", "acroform.json")) == dump


# Pydantic-VALID but lint-ERROR draft (duplicate option values: v1 tolerance
# parses it, the lint duplicate-option-value rule rejects it). This reaches the
# LINT gate specifically (a Pydantic-invalid draft would 422 at the earlier
# gate), so it pins the two-gate seam at the lint layer.
_LINT_ERROR_VALID_DRAFT = {
    "source": "pdf",
    "form_metadata": {"title": "T", "version": "unknown"},
    "sections": [{"id": "s1", "label": "S1", "order": 1, "fields": ["picker"]}],
    "fields": [{"id": "picker", "name": "Picker", "spoken_name": "picker",
                "type": "select", "section_id": "s1",
                "pdf_field_name": "form1[0].p[0]",
                "options": [{"value": "dup", "label": "A"},
                            {"value": "dup", "label": "B"}]}],
    "extraction_info": {"extracted_at": "2026-07-05T00:00:00Z",
                        "extraction_confidence": 0.9, "extractor_version": "t",
                        "manual_review_required": True},
}


def test_extract_dump_store_failure_is_fatal_nothing_stored(client, monkeypatch):
    # Opus fallback (PR #323): the dump is the gating input for the
    # dump-widget-multiclaim ERROR at promotion. A schema stored WITHOUT its dump
    # would let a dump-only error the author saw at store time vanish at promotion
    # (re-opening the two-gate seam). So a dump-write failure is FATAL and stores
    # NOTHING (dump-first ordering: the schema write never runs).
    c, store, root = client
    _make_kit(root, "fresh")
    dump = {"fields": [{"name": "form1[0].a[0]"}]}
    draft = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
             "sections": [], "fields": [{"id": "a", "type": "text"}]}
    fake = _fake_extractor(draft, exit_code=0, dump=dump)
    monkeypatch.setattr(ekr.subprocess, "run", fake)

    async def _boom_artifact(kit_id, data, filename):
        raise FormKitStoreError("dump write failed")

    monkeypatch.setattr(store, "put_json_artifact", _boom_artifact)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502, r.text
    assert "PDF-widget map" in r.json()["detail"]
    # Nothing stored: the schema write never ran (dump-first).
    with pytest.raises(FormKitNotFound):
        _run(store.load_schema("fresh"))


def test_promotion_survives_a_transient_dump_read_error(client, monkeypatch):
    # Opus fallback (PR #323): _load_kit_dump must degrade to None on a store
    # error, never 500 the promotion gate. A clean schema stays promotable even
    # when the dump read transiently fails.
    c, store, root = client
    clean = dict(VALID_SCHEMA)
    _make_kit(root, "fresh", status="draft", schema=clean)

    async def _boom_load(kit_id, filename):
        raise FormKitStoreError("transient GCS read")

    monkeypatch.setattr(store, "load_json_artifact", _boom_load)
    r = c.post(
        "/api/editor/kits/fresh/status",
        headers={"X-Editor-Token": "auth-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 200, r.text  # dump-less lint, still promotable


def test_stored_with_issues_draft_is_unpromotable_two_gate_seam(client, monkeypatch):
    # The two-gate seam: a stored lint-ERROR draft (via the extract route) is
    # UN-PROMOTABLE -- mark-complete 409s on the LINT errors specifically (store
    # != promote). Uses a Pydantic-valid draft so the refusal is the lint gate,
    # not the earlier wire-contract gate.
    c, store, root = client
    _make_kit(root, "fresh")
    fake = _fake_extractor(_LINT_ERROR_VALID_DRAFT, exit_code=3)
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    stored = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert stored.status_code == 200 and stored.json()["storedWithIssues"] is True
    # Now try to promote it -- the lint gate must refuse (409).
    promote = c.post(
        "/api/editor/kits/fresh/status",
        headers={"X-Editor-Token": "auth-tok"},
        json={"status": "complete"},
    )
    assert promote.status_code == 409, promote.text
    assert "lint error" in promote.json()["detail"]


def test_extract_requires_author_role_and_a_pdf(client, monkeypatch):
    c, _store, root = client
    _make_kit(root, "fresh")
    monkeypatch.setattr(ekr.subprocess, "run", _fake_extractor({"fields": []}))
    assert c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "edit-tok"}
    ).status_code == 403
    # A kit with no PDF cannot extract.
    kit = root / "no-pdf"
    kit.mkdir()
    (kit / "metadata.json").write_text(json.dumps({"status": "draft"}), encoding="utf-8")
    assert c.post(
        "/api/editor/kits/no-pdf/extract", headers={"X-Editor-Token": "auth-tok"}
    ).status_code == 409


def test_extract_refuses_overwrite_without_force(client, monkeypatch):
    c, store, root = client
    _make_kit(root, "done", schema={"fields": [{"id": "old"}]})
    monkeypatch.setattr(
        ekr.subprocess, "run", _fake_extractor({"fields": [{"id": "new"}]})
    )
    r = c.post(
        "/api/editor/kits/done/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 409
    assert _run(store.load_schema("done")) == {"fields": [{"id": "old"}]}
    # force=true replaces it.
    r2 = c.post(
        "/api/editor/kits/done/extract",
        headers={"X-Editor-Token": "auth-tok"},
        data={"force": "true"},
    )
    assert r2.status_code == 200
    assert _run(store.load_schema("done")) == {"fields": [{"id": "new"}]}


def test_extract_failure_maps_to_502_and_stores_nothing(client, monkeypatch):
    c, store, root = client
    _make_kit(root, "fresh")
    monkeypatch.setattr(
        ekr.subprocess, "run",
        _fake_extractor({"fields": []}, exit_code=1, write_out=False),
    )
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502
    with pytest.raises(FormKitNotFound):
        _run(store.load_schema("fresh"))


def test_extract_zero_field_draft_is_no_usable_draft_502(client, monkeypatch):
    # A draft with ZERO fields is BELOW the store-with-issues floor (bd v96b):
    # nothing worth storing, so it is a hard-fail 502 -- and the message is a
    # clean generic one that leaks no internal temp path.
    c, _store, root = client
    _make_kit(root, "fresh")

    def _empty_run(cmd, **kwargs):
        out_path = cmd[cmd.index("--out") + 1]
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump({"fields": []}, fh)
        return SimpleNamespace(
            returncode=1,
            stdout=f"[INVALID] wrote {out_path} -- validation failed",
            stderr="",
        )

    monkeypatch.setattr(ekr.subprocess, "run", _empty_run)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "no usable draft" in detail
    # No internal path leaks in the generic message.
    assert "extract_" not in detail and ".tmp" not in detail
    assert "Temp" not in detail and "\\" not in detail.replace("\n", "")


def test_extract_missing_output_failure_detail_scrubs_temp_path(client, monkeypatch):
    # When the extractor writes NO --out file at all (a genuine crash), the 502
    # echoes its last stdout line -- which must scrub the internal temp path
    # exactly like the success path does (Opus fallback review, PR #282).
    c, _store, root = client
    _make_kit(root, "fresh")

    def _crash_run(cmd, **kwargs):
        out_path = cmd[cmd.index("--out") + 1]
        # Do NOT write out_path -- simulate a crash that produced no draft.
        return SimpleNamespace(
            returncode=1,
            stdout=f"Traceback: failed writing {out_path} -- boom",
            stderr="",
        )

    monkeypatch.setattr(ekr.subprocess, "run", _crash_run)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502
    detail = r.json()["detail"]
    assert "extract_" not in detail and ".tmp" not in detail
    assert "Temp" not in detail and "\\" not in detail.replace("\n", "")
    assert "schema.json" in detail  # the scrub substitutes the store name


def test_extract_unconfigured_is_503(client, monkeypatch):
    c, _store, root = client
    _make_kit(root, "fresh")
    # Non-gemini model (the container has no claude CLI) -> 503.
    monkeypatch.setattr(
        ekr, "get_settings",
        lambda: _settings(editor="edit-tok", author="auth-tok",
                          EXTRACTOR_MODEL="claude-opus-4-8"),
    )
    assert c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    ).status_code == 503
    # No API key AND no Vertex -> 503 (genuinely no way to authenticate).
    monkeypatch.setattr(
        ekr, "get_settings",
        lambda: _settings(editor="edit-tok", author="auth-tok",
                          GEMINI_API_KEY=None, VERTEXAI=False),
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    ).status_code == 503


def test_extract_vertex_without_key_passes_the_config_gate(client, monkeypatch):
    # The Cloud Run reality (bd fyq4): VERTEXAI=true, a service account, and NO
    # GEMINI_API_KEY. The config gate must NOT 503 -- extraction authenticates
    # via ADC. We stub the subprocess so this asserts the GATE opens, not a real
    # extraction (that path is covered by test_extract_runs_and_stores_the_draft).
    c, store, root = client
    _make_kit(root, "fresh")
    monkeypatch.setattr(
        ekr, "get_settings",
        lambda: _settings(editor="edit-tok", author="auth-tok",
                          GEMINI_API_KEY=None, VERTEXAI=True),
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(
        ekr.subprocess, "run", _fake_extractor(dict(VALID_SCHEMA)),
    )
    resp = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    # Not the 503 "not configured" -- the gate opened and the (stubbed) run ran.
    assert resp.status_code == 200, resp.text


def test_status_rejects_unknown_values(client):
    c, _store, root = client
    _make_kit(root, "i-90", schema=VALID_SCHEMA)
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "published"},
    )
    assert r.status_code == 422
