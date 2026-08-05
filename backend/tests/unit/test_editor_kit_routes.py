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
from datetime import datetime, timezone
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
    # asyncio.run (not get_event_loop): the legacy accessor breaks when an
    # earlier test file (e.g. the translate_option_labels CLI suite) has
    # closed the main loop via its own asyncio.run (bd polyglot-pdf-r8gq).
    return asyncio.run(coro)


# A minimal schema that validates against the canonical Pydantic FormSchema
# (source=pdf requires extraction_info) -- used by the mark-complete gate tests.
VALID_SCHEMA = {
    "source": "pdf",
    # Post the P6.2 flip (bd h76m.16) a complete kit MUST be v2 -- the
    # mark-complete gate requires schema_version=="2".
    "schema_version": "2",
    # edition_date present so this fixture stays CLEAN under the bd
    # polyglot-pdf-47r3 audit-identity lint (a kit with form_metadata but no
    # government edition now legitimately carries an advisory WARNING -- the
    # audit trail falls back to a content fingerprint). Same pattern as the
    # help.instructions note below: keep the "clean" fixture genuinely clean.
    "form_metadata": {
        "title": "Test Form", "version": "unknown", "edition_date": "12/2024",
    },
    "sections": [{"id": "s1", "label": "Section 1", "order": 1, "fields": ["f1"]}],
    "fields": [
        # help.instructions authored so this fixture is CLEAN under the
        # wsao.3 guidance-coverage lint too (a guidance-less field now
        # legitimately carries the aggregated coverage WARNING).
        # pdf_field_name present: under the sprint-17 ledger rules (bd xazf) a
        # source=pdf text field naming NO widget is a field-unbacked lint
        # ERROR, and this fixture must stay CLEAN for the gate tests.
        {"id": "f1", "name": "Field 1", "spoken_name": "field one",
         "type": "text", "section_id": "s1", "pdf_field_name": "f1[0]",
         "help": {"instructions": "Enter the value shown on your notice."}}
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
        OPTION_TRANSLATION_MODEL="gemini-2.5-pro",
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
    wiring (no override), so 401/503 behavior is the deployed behavior.

    The Mark-complete drift sweep (bd polyglot-pdf-783r) is stubbed to a clean
    no-op here so the OTHER gate tests (validate/lint/v2/PDF) exercise their own
    concern without a real model call or a translation block; the sweep has its
    own dedicated tests that un-patch it."""
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


# --- POST /kits/{id}/lint: kit-scoped lint with the persisted dump ----------
# (sprint-18 C1, bd polyglot-pdf-o7y9): the editor strip for an OPEN kit must
# lint with the SAME inputs as the /status promotion gate -- schema + the kit's
# acroform.json -- or the two dump-gated rules stay structurally invisible to
# the strip and a confident 100% can still 409 at the gate.

# Two fields claiming ONE dump widget: the dump-widget-multiclaim ERROR fires
# only when the dump is passed to lint_schema, which is exactly the difference
# between the dumpless /lint route and this kit-scoped one.
_MULTICLAIM_DRAFT = {
    "source": "pdf",
    "form_metadata": {"title": "T", "version": "unknown"},
    "sections": [],
    "fields": [
        {"id": "a", "type": "text", "pdf_field_name": "form1[0].shared[0]",
         "spoken_name": "a", "help": {"instructions": "Enter A."}},
        {"id": "b", "type": "text", "pdf_field_name": "form1[0].shared[0]",
         "spoken_name": "b", "help": {"instructions": "Enter B."}},
    ],
}

_MULTICLAIM_DUMP = {"fields": [{"name": "form1[0].shared[0]"}]}


def test_kit_lint_is_token_gated_and_404s_unknown_kits(client):
    c, _store, _root = client
    assert c.post(
        "/api/editor/kits/i-90/lint", json={"fields": []},
    ).status_code == 401
    assert c.post(
        "/api/editor/kits/no-such-kit/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json={"fields": []},
    ).status_code == 404


def test_kit_lint_surfaces_the_dump_gated_error_the_dumpless_route_cannot(client):
    # The C1 exit criterion's backend half: the same draft lints CLEAN of
    # widget-claim findings through the dumpless route but reports the
    # dump-widget-multiclaim ERROR through the kit-scoped route -- the same
    # lint_schema(schema, dump) inputs the /status promotion gate uses.
    c, store, root = client
    _make_kit(root, "i-90", schema=_MULTICLAIM_DRAFT)
    _run(store.put_json_artifact("i-90", _MULTICLAIM_DUMP, "acroform.json"))

    dumpless = c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    assert dumpless.status_code == 200
    assert not any(
        f["rule"] == "dump-widget-multiclaim"
        for f in dumpless.json()["findings"]
    )

    scoped = c.post(
        "/api/editor/kits/i-90/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    assert scoped.status_code == 200
    body = scoped.json()
    multi = [f for f in body["findings"] if f["rule"] == "dump-widget-multiclaim"]
    assert multi and multi[0]["severity"] == "ERROR"
    assert body["errorCount"] >= 1


def test_kit_lint_without_a_dump_degrades_to_the_dumpless_rules(client):
    # A pre-v96b kit has no acroform.json: the kit-scoped route must then agree
    # with the dumpless route (and with the gate, which degrades identically).
    c, _store, root = client
    _make_kit(root, "old-kit", schema=_MULTICLAIM_DRAFT)
    scoped = c.post(
        "/api/editor/kits/old-kit/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    dumpless = c.post(
        "/api/editor/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    assert scoped.status_code == dumpless.status_code == 200
    assert scoped.json() == dumpless.json()


def test_kit_lint_502s_on_a_transient_dump_read_failure(client, monkeypatch):
    # A FAILED dump read must not silently downgrade the lint to dump-blind
    # with a 200 the strip presents as authoritative (the confident-clean
    # state the route exists to end) -- it 502s like the metadata read, which
    # the strip renders as its "checks did not run" degraded state (Opus
    # outer review, pass 4). A MISSING dump (pre-v96b kit) still degrades to
    # the dumpless rules, pinned by the degradation test above.
    c, store, root = client
    _make_kit(root, "i-90", schema=_MULTICLAIM_DRAFT)

    async def _boom(_kit_id, _name):
        raise FormKitStoreError("gcs blip")

    monkeypatch.setattr(store, "load_json_artifact", _boom)
    r = c.post(
        "/api/editor/kits/i-90/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    assert r.status_code == 502


def test_kit_lint_lints_the_posted_schema_not_the_stored_one(client):
    # The strip lints what is ON SCREEN (possibly unsaved), never the stored
    # copy: post a draft that differs from the stored schema and confirm the
    # findings describe the posted one.
    c, store, root = client
    _make_kit(root, "i-90", schema=VALID_SCHEMA)
    _run(store.put_json_artifact("i-90", _MULTICLAIM_DUMP, "acroform.json"))
    r = c.post(
        "/api/editor/kits/i-90/lint",
        headers={"X-Editor-Token": "edit-tok"},
        json=_MULTICLAIM_DRAFT,
    )
    assert r.status_code == 200
    assert any(
        f["rule"] == "dump-widget-multiclaim" for f in r.json()["findings"]
    )


# --- POST /repair: one-click Repair-all (bd polyglot-pdf-zgln, P5.3b) ---------

# A draft with a repairable defect: duplicate/invalid option values that repair
# mints into slugs (a -> the label slug), so the repaired schema lints cleaner.
_REPAIRABLE_DRAFT = {
    "source": "pdf",
    "form_metadata": {"title": "T", "version": "unknown"},
    "sections": [{"id": "s1", "label": "S1", "order": 1, "fields": ["picker"]}],
    "fields": [{"id": "picker", "name": "Picker", "spoken_name": "picker",
                "type": "select", "section_id": "s1",
                "pdf_field_name": "form1[0].p[0]",
                "options": [{"value": "Dup Value!", "label": "Alpha"},
                            {"value": "Dup Value!", "label": "Beta"}]}],
    "extraction_info": {"extracted_at": "2026-07-05T00:00:00Z",
                        "extraction_confidence": 0.9, "extractor_version": "t",
                        "manual_review_required": True},
}


def test_repair_all_stores_and_reports_and_equals_cli(client):
    # Exit criterion 1: Repair-all repairs a stored draft; its output EQUALS a
    # direct schema_repair.repair() call on the same input (== CLI), and the
    # repaired schema is stored back.
    import backend.services.schema_repair as sr
    c, store, root = client
    _make_kit(root, "fresh", status="draft", schema=_REPAIRABLE_DRAFT)
    r = c.post(
        "/api/editor/kits/fresh/repair", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["applied"] >= 1
    # Equivalence: the STORED repaired schema equals repair() called directly
    # (no dump artifact present -> dump=None on both sides), proving == CLI.
    expected, _ = sr.repair(_REPAIRABLE_DRAFT, None)
    assert _run(store.load_schema("fresh")) == expected
    # The repaired option values are minted slugs (no longer duplicates).
    stored = _run(store.load_schema("fresh"))
    vals = [o["value"] for o in stored["fields"][0]["options"]]
    assert vals == ["alpha", "beta"] and len(set(vals)) == 2


def test_repair_all_passes_the_persisted_dump(client):
    # Repair uses the kit's persisted acroform dump for its widget-existence
    # check -- a draft claiming a REAL widget repairs fine.
    c, store, root = client
    schema = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
              "sections": [], "fields": [{"id": "f", "name": "F",
              "spoken_name": "f", "type": "text",
              "pdf_field_name": "form1[0].real[0]"}]}
    _make_kit(root, "fresh", status="draft", schema=schema)
    _run(store.put_json_artifact(
        "fresh", {"fields": [{"name": "form1[0].real[0]"}]}, "acroform.json"))
    r = c.post(
        "/api/editor/kits/fresh/repair", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 200, r.text


def test_repair_hallucinated_widget_is_422_not_500(client):
    # Exit criterion 2: a draft referencing a widget the PDF lacks (checkable
    # only with a dump) is a clear CLIENT error (422), never a 500.
    c, store, root = client
    schema = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
              "sections": [], "fields": [{"id": "f", "name": "F",
              "spoken_name": "f", "type": "text",
              "pdf_field_name": "form1[0].GHOST[0]"}]}
    _make_kit(root, "fresh", status="draft", schema=schema)
    _run(store.put_json_artifact(
        "fresh", {"fields": [{"name": "form1[0].real[0]"}]}, "acroform.json"))
    r = c.post(
        "/api/editor/kits/fresh/repair", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 422, r.text
    assert "widget" in r.json()["detail"].lower()
    # Nothing was overwritten: the un-repaired schema is unchanged.
    assert _run(store.load_schema("fresh")) == schema


def test_repair_requires_author_role(client):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft", schema=_REPAIRABLE_DRAFT)
    # editor token -> 403 (repair mutates the stored schema, author-only).
    r = c.post(
        "/api/editor/kits/fresh/repair", headers={"X-Editor-Token": "edit-tok"}
    )
    assert r.status_code == 403


def test_repair_unknown_kit_404_and_published_409(client):
    c, _store, root = client
    # Unknown kit -> 404.
    assert c.post(
        "/api/editor/kits/ghost/repair", headers={"X-Editor-Token": "auth-tok"}
    ).status_code == 404
    # A COMPLETE kit -> 409 (revert to draft first; repair rewrites the schema).
    _make_kit(root, "done", status="complete", schema=VALID_SCHEMA)
    r = c.post(
        "/api/editor/kits/done/repair", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 409


def test_repair_schemaless_kit_is_404(client):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft")  # PDF, no schema
    r = c.post(
        "/api/editor/kits/fresh/repair", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 404


# --- GET /unclaimed-widgets: the widget picker (bd polyglot-pdf-nivy) ---------

_WIDGET_DUMP = {
    "fields": [
        {"name": "form1[0].reason[0]", "logical_type": "checkbox",
         "widgets": [{"type": "checkbox", "on_value": "1", "tu": "Employment",
                      "rect": {"page": 0}}]},
        {"name": "form1[0].reason[1]", "logical_type": "checkbox",
         "widgets": [{"type": "checkbox", "on_value": "2", "tu": "Family",
                      "rect": {"page": 0}}]},
    ]
}


def test_unclaimed_widgets_lists_unclaimed_buttons(client):
    c, store, root = client
    schema = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
              "sections": [], "fields": [{"id": "reasons",
              "type": "checkbox_group", "options": [
                  {"value": "employment", "label": "Employment",
                   "pdf_field_name": "form1[0].reason[0]"}]}]}
    _make_kit(root, "fresh", status="draft", schema=schema)
    _run(store.put_json_artifact("fresh", _WIDGET_DUMP, "acroform.json"))
    r = c.get(
        "/api/editor/kits/fresh/unclaimed-widgets",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    widgets = r.json()["widgets"]
    # reason[0] is claimed; only reason[1] is offered.
    assert [w["name"] for w in widgets] == ["form1[0].reason[1]"]
    assert widgets[0]["on_value"] == "2" and widgets[0]["tooltip"] == "Family"


def test_unclaimed_widgets_empty_without_a_dump(client):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft", schema=VALID_SCHEMA)  # no dump artifact
    r = c.get(
        "/api/editor/kits/fresh/unclaimed-widgets",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200
    assert r.json() == {"widgets": []}


def test_unclaimed_widgets_requires_author(client):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft", schema=VALID_SCHEMA)
    assert c.get(
        "/api/editor/kits/fresh/unclaimed-widgets",
        headers={"X-Editor-Token": "edit-tok"},
    ).status_code == 403


def test_unclaimed_widgets_unknown_kit_404(client):
    c, _store, _root = client
    assert c.get(
        "/api/editor/kits/ghost/unclaimed-widgets",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 404


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


# --- publish date (bd polyglot-pdf-47r3) --------------------------------------
#
# The marked-complete date is the revision marker for a kit with no government
# edition: a firm's own intake form has no "12/2024", but it does have "the
# version published on <date>" (maintainer, 2026-08-04). Stamped here so the
# data accumulates; surfacing it into the audit record is epic
# polyglot-pdf-7jmy, which needs a manifest/wire change to carry it.


def test_a_kit_with_no_edition_date_can_still_be_published(client):
    """A custom form MUST stay publishable (bd polyglot-pdf-47r3, maintainer call).

    The audit-identity lint rule is a WARNING precisely so a firm's own intake
    sheet -- which has no government edition date -- is not blocked; the record
    falls back to a content fingerprint instead.

    This asserts the BEHAVIOR at the gate that can actually block, not the
    severity label. The lint-level test (test_missing_edition_date_warns_but_
    never_blocks) pins the label, but set_editor_kit_status 409s on ANY lint
    ERROR and never sees that assertion -- an Opus review proved a severity flip
    to ERROR left all 132 tests in this file green while making every
    edition-less kit un-publishable.
    """
    c, _store, root = client
    schema = {
        **VALID_SCHEMA,
        "form_metadata": {"title": "Acme Intake", "version": "unknown"},
    }
    assert "edition_date" not in schema["form_metadata"]
    _make_kit(root, "acme-intake", status="draft", schema=schema)

    r = c.post(
        "/api/editor/kits/acme-intake/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )

    assert r.status_code == 200, r.text
    meta = json.loads((root / "acme-intake" / "metadata.json").read_text())
    assert meta["status"] == "complete"


def test_promotion_stamps_the_publish_date(client):
    c, _store, root = client
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA)

    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )

    assert r.status_code == 200
    meta = json.loads((root / "i-90" / "metadata.json").read_text())
    # ISO-8601 UTC, parseable -- not a free-text date.
    stamped = datetime.fromisoformat(meta["published_at"])
    assert stamped.tzinfo is not None
    assert abs((datetime.now(timezone.utc) - stamped).total_seconds()) < 60


def test_revert_to_draft_keeps_the_last_publish_date(client):
    """A revert must not erase it: the kit WAS published then.

    Erasing on revert would lose the marker for every confirmation recorded
    while it was live -- the exact evidence the date exists to preserve.
    """
    c, _store, root = client
    _make_kit(root, "i-90", status="complete", schema=VALID_SCHEMA,
              extra_meta={"published_at": "2026-01-15T00:00:00+00:00"})

    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "draft"},
    )

    assert r.status_code == 200
    meta = json.loads((root / "i-90" / "metadata.json").read_text())
    assert meta["status"] == "draft"
    assert meta["published_at"] == "2026-01-15T00:00:00+00:00"


def test_republishing_moves_the_publish_date(client):
    """Re-publishing after an edit updates it -- that IS the revision signal."""
    c, _store, root = client
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA,
              extra_meta={"published_at": "2026-01-15T00:00:00+00:00"})

    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )

    assert r.status_code == 200
    meta = json.loads((root / "i-90" / "metadata.json").read_text())
    assert meta["published_at"] != "2026-01-15T00:00:00+00:00"


# --- POST status: the drift re-translation sweep (bd polyglot-pdf-783r) ------
#
# The client fixture stubs _sweep_drifted_translations to a no-op so the gate
# tests above are unaffected; these un-patch it and instead mock the sweep's
# INNER pieces (the TextAIGemini construction + bake_label_translations) so the
# real coverage gate runs against the swept schema, with NO live model call.

# The supported-language count the coverage gate spans (drives the "N of M"
# message). Imported from the same source the gate uses so this never drifts.
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47  # noqa: E402

_SUPPORTED = [n for n in SPOKEN_LANGUAGE_BCP47 if n != "english"]

# Captured at import BEFORE any fixture can patch it, so _unstub_sweep can
# restore the genuine implementation (the client fixture replaces the module
# attribute with a no-op for the OTHER gate tests).
_REAL_SWEEP = ekr._sweep_drifted_translations


def _unstub_sweep(monkeypatch):
    """Restore the real _sweep_drifted_translations (the client fixture stubbed
    it) and neutralize the model-client constructor so no live call happens."""
    monkeypatch.setattr(ekr, "_sweep_drifted_translations", _REAL_SWEEP)
    monkeypatch.setattr(ekr, "TextAIGemini", lambda **kw: SimpleNamespace())


def _cover_all(schema, languages):
    """Fake-bake fan-out: write a translation for EVERY translatable item
    (spoken names + section labels + option labels) in each of `languages`, so
    the real coverage gate sees the kit fully covered -- matching what the real
    bake does across all three classes (a fake that filled only spoken names
    would leave section labels uncovered and wrongly trip the gate)."""
    for field in schema.get("fields", []):
        if field.get("spoken_name") or field.get("name"):
            field["spoken_name_translations"] = {n: "traducido" for n in languages}
        for opt in field.get("options") or []:
            if opt.get("label"):
                opt["label_translations"] = {n: "traducido" for n in languages}
    for section in schema.get("sections", []):
        if section.get("label"):
            section["label_translations"] = {n: "traducido" for n in languages}


def test_mark_complete_runs_the_drift_sweep_then_completes(client, monkeypatch):
    """A drifted spoken name (source present, translations dropped) is filled by
    the sweep, and the response reports the count; status flips to complete."""
    c, _store, root = client
    _unstub_sweep(monkeypatch)
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA, label="I-90")

    async def _fake_bake(schema, _text_ai, languages, **_kw):
        # Simulate a full, successful bake: fan the spoken name AND the section
        # label out to every supported language so the coverage gate passes
        # (coverage spans every translatable item, section labels included).
        _cover_all(schema, languages)
        return {
            "changed": True, "failed_languages": [],
            "languages": {n: {"fields_updated": 1, "options_updated": 0,
                              "sections_updated": 1} for n in languages},
        }

    monkeypatch.setattr(ekr, "bake_label_translations", _fake_bake)
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 200, r.json()
    body = r.json()
    assert body["status"] == "complete"
    # One spoken name + one section label, each x every language.
    assert body["retranslated"] == 2 * len(_SUPPORTED)
    assert body["translationModel"] == "gemini-2.5-pro"
    # The swept translations were persisted.
    saved = json.loads((root / "i-90" / "schema.json").read_text())
    assert saved["fields"][0]["spoken_name_translations"]
    assert json.loads((root / "i-90" / "metadata.json").read_text())["status"] \
        == "complete"


def test_mark_complete_blocked_when_coverage_incomplete(client, monkeypatch):
    """A sweep that leaves some language uncovered REFUSES completion with the
    'N of M' message, and the kit stays draft. (The idempotent retry-only-gaps
    property is proven at the service-unit level by
    test_bake_only_missing_is_idempotent.)"""
    c, _store, root = client
    _unstub_sweep(monkeypatch)
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA, label="I-90")

    async def _partial_bake(schema, _text_ai, languages, **_kw):
        # Cover all but ONE language (simulate a language whose batch failed).
        covered = {n: c for n, c in languages.items() if n != _SUPPORTED[0]}
        _cover_all(schema, covered)
        return {
            "changed": True, "failed_languages": [_SUPPORTED[0]],
            "languages": {n: {"fields_updated": 1, "options_updated": 0,
                              "sections_updated": 1} for n in covered},
        }

    monkeypatch.setattr(ekr, "bake_label_translations", _partial_bake)
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "language translations complete" in detail
    assert "%d of %d" % (len(_SUPPORTED) - 1, len(_SUPPORTED)) in detail
    # Stayed a draft -- the completion was refused.
    assert json.loads((root / "i-90" / "metadata.json").read_text())["status"] \
        == "draft"


def test_mark_complete_blocked_when_translation_unconfigured(client, monkeypatch):
    """No Gemini auth -> the sweep cannot run; completion is refused with the
    maintainer-contact message (a config issue, not an editor one)."""
    c, _store, root = client
    _unstub_sweep(monkeypatch)
    # No key AND not Vertex -> the sweep's auth gate fails.
    monkeypatch.setattr(
        ekr, "get_settings",
        lambda: _settings(editor="edit-tok", author="auth-tok",
                          GEMINI_API_KEY=None, VERTEXAI=False),
    )
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _make_kit(root, "i-90", status="draft", schema=VALID_SCHEMA, label="I-90")
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 503
    assert "josh@caellwynai.com" in r.json()["detail"]
    assert json.loads((root / "i-90" / "metadata.json").read_text())["status"] \
        == "draft"


def test_mark_complete_sweep_is_noop_when_fully_translated(client, monkeypatch):
    """A kit already fully translated triggers ZERO model work: bake reports no
    change, retranslated is 0, and completion proceeds."""
    c, _store, root = client
    _unstub_sweep(monkeypatch)
    pre_translated = json.loads(json.dumps(VALID_SCHEMA))
    # Fully covered ALREADY (spoken name + section label) across every language.
    _cover_all(pre_translated, {n: n for n in _SUPPORTED})
    _make_kit(root, "i-90", status="draft", schema=pre_translated, label="I-90")

    called = {"n": 0}

    async def _noop_bake(schema, _text_ai, languages, **_kw):
        called["n"] += 1
        # only_missing over a fully-covered kit changes nothing.
        return {"changed": False, "failed_languages": [], "languages": {}}

    monkeypatch.setattr(ekr, "bake_label_translations", _noop_bake)
    r = c.post(
        "/api/editor/kits/i-90/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 200, r.json()
    assert r.json()["retranslated"] == 0
    assert called["n"] == 1  # the bake is invoked, but reports no change


# --- POST /kits/{kit_id}/label (rename the display label, bd 15ic) ---------- #

def test_label_rename_preserves_other_metadata(client):
    c, _store, root = client
    _make_kit(root, "form-2", status="draft", schema=VALID_SCHEMA,
              label="Form 2", extra_meta={"description": "the mystery form"})
    r = c.post(
        "/api/editor/kits/form-2/label",
        headers={"X-Editor-Token": "edit-tok"},
        json={"label": "  IRS W-9 (2024)  "},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True, "label": "IRS W-9 (2024)"}  # stripped
    meta = json.loads((root / "form-2" / "metadata.json").read_text())
    assert meta["label"] == "IRS W-9 (2024)"
    assert meta["status"] == "draft"                      # preserved
    assert meta["description"] == "the mystery form"      # preserved


def test_label_rename_rejects_a_blank_label(client):
    c, _store, root = client
    _make_kit(root, "form-2", status="draft", schema=VALID_SCHEMA, label="Form 2")
    r = c.post(
        "/api/editor/kits/form-2/label",
        headers={"X-Editor-Token": "edit-tok"},
        json={"label": "   "},
    )
    assert r.status_code == 422
    meta = json.loads((root / "form-2" / "metadata.json").read_text())
    assert meta["label"] == "Form 2"  # unchanged


def test_label_rename_rejects_an_absurdly_long_label(client):
    c, _store, root = client
    _make_kit(root, "form-2", status="draft", schema=VALID_SCHEMA, label="Form 2")
    r = c.post(
        "/api/editor/kits/form-2/label",
        headers={"X-Editor-Token": "edit-tok"},
        json={"label": "x" * 201},
    )
    assert r.status_code == 422
    meta = json.loads((root / "form-2" / "metadata.json").read_text())
    assert meta["label"] == "Form 2"  # unchanged


def test_label_rename_rejects_manifest_poison_characters(client):
    # A double quote or backslash in a label would truncate the deploy scripts'
    # grep/sed extraction and splice INVALID JSON into the deployed index.json
    # (the voice app then fails to parse the manifest -- no forms load). The
    # route is the single choke point, so it must refuse them (Opus review).
    c, _store, root = client
    _make_kit(root, "form-2", status="draft", schema=VALID_SCHEMA, label="Form 2")
    for bad in ['My "Special" Form', 'Path\Back', "Tab	here"]:
        r = c.post(
            "/api/editor/kits/form-2/label",
            headers={"X-Editor-Token": "edit-tok"},
            json={"label": bad},
        )
        assert r.status_code == 422, bad
    meta = json.loads((root / "form-2" / "metadata.json").read_text())
    assert meta["label"] == "Form 2"  # unchanged by every attempt


def test_label_rename_404s_on_an_unknown_kit(client):
    c, _store, _root = client
    r = c.post(
        "/api/editor/kits/no-such-kit/label",
        headers={"X-Editor-Token": "edit-tok"},
        json={"label": "Anything"},
    )
    assert r.status_code == 404


def test_label_rename_requires_the_access_token(client):
    c, _store, root = client
    _make_kit(root, "form-2", status="draft", schema=VALID_SCHEMA, label="Form 2")
    r = c.post("/api/editor/kits/form-2/label", json={"label": "New Name"})
    assert r.status_code == 401


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


def test_mark_complete_publish_gate_refuses_a_duplicate_option_schema(client):
    """bd h76m.5 (P2.1) + the P6.2 flip (bd h76m.16): a schema with duplicate
    option values must be refused at the publish gate, named so the editor can
    fix it. Post the flip, v2 strictness is always-on, so this defect is caught
    at the PARSE gate (422) rather than the lint gate -- the publish gate still
    stands between a bad schema and the voice app, just one layer earlier."""
    from backend.models.form_models import FormSchema

    c, _store, root = client
    linty = json.loads(json.dumps(VALID_SCHEMA))  # deep copy
    linty["sections"][0]["fields"].append("picker")
    linty["fields"].append({
        "id": "picker", "name": "Picker", "spoken_name": "picker",
        "type": "select", "section_id": "s1",
        "pdf_field_name": "form1[0].pick[0]",
        "options": [
            {"value": "same", "label": "A"},
            {"value": "same", "label": "B"},
        ],
    })
    # The parse gate now catches this (v2 strictness is always-on).
    with pytest.raises(Exception):
        FormSchema.model_validate(linty)

    _make_kit(root, "linty", schema=linty)
    r = c.post(
        "/api/editor/kits/linty/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "duplicate option values" in detail  # names the defect
    assert "picker" in detail                    # names the field
    # The kit stays draft.
    meta = json.loads((root / "linty" / "metadata.json").read_text())
    assert meta["status"] == "draft"


def test_mark_complete_requires_v2_schema_version(client):
    # P6.2 flip (bd h76m.16 / t96a): a complete kit must be v2. A v2-shaped schema
    # WITHOUT the schema_version stamp (or carrying a removed key the model would
    # silently ignore) is refused at the publish gate, closing the extra="ignore"
    # hole. VALID_SCHEMA minus the stamp is otherwise promotable.
    c, _store, root = client
    unstamped = json.loads(json.dumps(VALID_SCHEMA))
    del unstamped["schema_version"]
    _make_kit(root, "unstamped", schema=unstamped)
    r = c.post(
        "/api/editor/kits/unstamped/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 422
    assert "not v2" in r.json()["detail"] or "schema_version" in r.json()["detail"]
    assert json.loads((root / "unstamped" / "metadata.json").read_text())["status"] == "draft"


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
        # edition_date keeps this lint-clean under the bd polyglot-pdf-47r3
        # audit-identity WARNING (see the VALID_SCHEMA note at the top).
        "form_metadata": {
            "title": "T", "version": "unknown", "edition_date": "12/2024",
        },
        "sections": [{"id": "s1", "label": "S1", "order": 1, "fields": ["a"]}],
        "fields": [{"id": "a", "name": "A", "spoken_name": "a", "type": "text",
                    "section_id": "s1", "pdf_field_name": "form1[0].a[0]",
                    # authored guidance so the clean-draft path stays
                    # zero-findings under the wsao.3 coverage lint
                    "help": {"instructions": "Enter the code from your card."}}],
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
    # The two-gate seam: a defective draft (via the extract route) STORES
    # (200, storedWithIssues) but is UN-PROMOTABLE (store != promote). Post the
    # P6.2 flip (bd h76m.16), v2 strictness is always-on, so a duplicate-option
    # draft is refused at the PARSE gate (422) at promotion time -- the seam
    # (store accepts, promote refuses) still holds, one layer earlier.
    c, store, root = client
    _make_kit(root, "fresh")
    fake = _fake_extractor(_LINT_ERROR_VALID_DRAFT, exit_code=3)
    monkeypatch.setattr(ekr.subprocess, "run", fake)
    stored = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert stored.status_code == 200 and stored.json()["storedWithIssues"] is True
    # Now try to promote it -- the publish gate must refuse.
    promote = c.post(
        "/api/editor/kits/fresh/status",
        headers={"X-Editor-Token": "auth-tok"},
        json={"status": "complete"},
    )
    assert promote.status_code == 422, promote.text
    assert "duplicate option values" in promote.json()["detail"]


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


def test_extract_non_json_output_is_502(client, monkeypatch):
    # Exit criterion 2 (the no-JSON sub-case, Opus fallback coverage nit): the
    # extractor wrote --out but it is not valid JSON -> 502, nothing stored.
    c, store, root = client
    _make_kit(root, "fresh")

    def _garbage_run(cmd, **kwargs):
        out_path = cmd[cmd.index("--out") + 1]
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write("this is not json {{{")
        return SimpleNamespace(returncode=0, stdout="[OK] wrote schema.json", stderr="")

    monkeypatch.setattr(ekr.subprocess, "run", _garbage_run)
    r = c.post(
        "/api/editor/kits/fresh/extract", headers={"X-Editor-Token": "auth-tok"}
    )
    assert r.status_code == 502, r.text
    assert "unreadable schema" in r.json()["detail"]
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
                          EXTRACTOR_MODEL="claude-opus-5"),
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


# ---------------------------------------------------------------------------
# POST /kits/{id}/derive-divisions -- regenerate divisions (bd 6cfu.3)
# ---------------------------------------------------------------------------

# A draft whose divisions the derivation will overwrite: two placed fields on
# page 1 (no widget names, blank page -> page-fallback strategy) plus one
# positionless field that must land in 'To review (unplaced)'.
_DERIVABLE_DRAFT = {
    "source": "pdf",
    "schema_version": "2",
    "form_metadata": {"title": "T", "version": "u"},
    "parts": [{"id": "part_old", "label": "Old part", "order": 1,
               "section_ids": ["sec_llm"]}],
    "sections": [{"id": "sec_llm", "label": "LLM section", "order": 1,
                  "fields": ["f1", "f2", "f3"]}],
    "fields": [
        {"id": "f1", "name": "F1", "spoken_name": "f one", "type": "text",
         "section_id": "sec_llm",
         "pdf_position": {"page": 1, "x": 50.0, "y": 100.0,
                          "width": 80.0, "height": 12.0}},
        {"id": "f2", "name": "F2", "spoken_name": "f two", "type": "text",
         "section_id": "sec_llm",
         "pdf_position": {"page": 1, "x": 50.0, "y": 140.0,
                          "width": 80.0, "height": 12.0}},
        {"id": "f3", "name": "F3", "spoken_name": "f three", "type": "text",
         "section_id": "sec_llm"},
    ],
    "_bakeoff": {"authoring": {"division": {"strategy": "stale"}}},
}


def _real_pdf_bytes() -> bytes:
    import fitz
    doc = fitz.open()
    doc.new_page(width=612, height=792)
    data = doc.tobytes()
    doc.close()
    return data


def _make_derivable_kit(root, kit_id, **kwargs):
    kit_dir = _make_kit(root, kit_id, schema=json.loads(json.dumps(_DERIVABLE_DRAFT)),
                        **kwargs)
    (kit_dir / "form.pdf").write_bytes(_real_pdf_bytes())
    return kit_dir


def test_derive_divisions_rewrites_stores_and_reports(client):
    c, store, root = client
    _make_derivable_kit(root, "fresh")
    r = c.post("/api/editor/kits/fresh/derive-divisions",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["strategy"] == "page-fallback"
    assert body["toReviewFieldIds"] == ["f3"]
    assert body["errorCount"] >= 1  # the to-review-pending lint gate fires
    stored = _run(store.load_schema("fresh"))
    sec_ids = [s["id"] for s in stored["sections"]]
    assert "sec_llm" not in sec_ids  # LLM divisions overwritten
    assert any(sid.startswith("sec_to_review") for sid in sec_ids)
    by_id = {f["id"]: f for f in stored["fields"]}
    assert by_id["f1"]["section_id"] == by_id["f2"]["section_id"]
    assert by_id["f3"]["section_id"].startswith("sec_to_review")
    # Old parts replaced; extraction metadata record superseded.
    assert all(p["id"] != "part_old" for p in stored["parts"])
    assert stored["_bakeoff"]["authoring"]["division"]["strategy"] == "page-fallback"


def test_derive_divisions_equals_direct_derivation(client):
    # The route's stored output EQUALS derive_and_apply called directly on the
    # same schema + PDF (the route adds nothing of its own).
    c, store, root = client
    _make_derivable_kit(root, "fresh")
    r = c.post("/api/editor/kits/fresh/derive-divisions",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200, r.text
    ds = ekr._load_derive_sections()
    expected = json.loads(json.dumps(_DERIVABLE_DRAFT))
    summary = ds.derive_and_apply(expected, str(root / "fresh" / "form.pdf"))
    expected["_bakeoff"]["authoring"]["division"] = summary
    assert _run(store.load_schema("fresh")) == expected


def test_derive_divisions_requires_author_role(client):
    c, _store, root = client
    _make_derivable_kit(root, "fresh")
    r = c.post("/api/editor/kits/fresh/derive-divisions",
               headers={"X-Editor-Token": "edit-tok"})
    assert r.status_code == 403


def test_derive_divisions_published_kit_is_409(client):
    c, _store, root = client
    _make_derivable_kit(root, "done", status="complete")
    r = c.post("/api/editor/kits/done/derive-divisions",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 409
    assert "draft" in r.json()["detail"].lower()


def test_derive_divisions_corrupt_pdf_is_422(client):
    # _make_kit writes junk PDF bytes; the derivation's friendly ValueError
    # must surface as a 422 data defect, never a 500 -- and the schema must
    # not have been overwritten.
    c, store, root = client
    schema = json.loads(json.dumps(_DERIVABLE_DRAFT))
    _make_kit(root, "fresh", schema=schema)
    r = c.post("/api/editor/kits/fresh/derive-divisions",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 422, r.text
    assert _run(store.load_schema("fresh")) == schema


def test_derive_divisions_missing_pdf_is_409(client):
    c, _store, root = client
    kit_dir = _make_kit(root, "fresh",
                        schema=json.loads(json.dumps(_DERIVABLE_DRAFT)))
    (kit_dir / "form.pdf").unlink()
    r = c.post("/api/editor/kits/fresh/derive-divisions",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 409
    assert "pdf" in r.json()["detail"].lower()


def test_mark_complete_publish_gate_refuses_to_review_fields(client):
    """bd 6cfu.3: a form with fields still in a 'To review' section (the
    deterministic division pass's sec_to_review* buckets) cannot be marked
    complete -- the to-review-pending lint ERROR blocks the publish gate.
    Re-filing the field (and emptying the section) unblocks it."""
    c, _store, root = client
    pending = json.loads(json.dumps(VALID_SCHEMA))  # deep copy
    pending["sections"].append(
        {"id": "sec_to_review_p1", "label": "To review", "order": 2,
         "fields": ["stray"]})
    pending["fields"].append(
        {"id": "stray", "name": "Stray", "spoken_name": "stray",
         "type": "text", "section_id": "sec_to_review_p1",
         # Named so the ledger rule (field-unbacked, bd xazf) stays quiet --
         # this test pins ONLY the to-review-pending gate.
         "pdf_field_name": "stray[0]"})
    _make_kit(root, "pending", schema=pending)
    r = c.post(
        "/api/editor/kits/pending/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "to-review-pending" in detail
    assert "lint error" in detail

    # Re-file the stray into the real section -> the same flip succeeds.
    fixed = json.loads(json.dumps(pending))
    fixed["sections"][1]["fields"] = []
    fixed["sections"][0]["fields"].append("stray")
    fixed["fields"][1]["section_id"] = "s1"
    put = c.put(
        "/api/editor/kits/pending/schema",
        headers={"X-Editor-Token": "edit-tok"},
        json=fixed,
    )
    assert put.status_code == 200, put.text
    r2 = c.post(
        "/api/editor/kits/pending/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r2.status_code == 200, r2.text


def test_mark_complete_publish_gate_refuses_unbacked_field(client):
    """bd polyglot-pdf-xazf (sprint 17): a hand-edited draft carrying a field
    that names NO PDF widget at all (field-unbacked lint ERROR) cannot be
    marked complete -- the ledger backstop for what a human reintroduces
    after extraction-time repair (bd l1a9) already passed."""
    c, _store, root = client
    unbacked = json.loads(json.dumps(VALID_SCHEMA))  # deep copy
    unbacked["sections"][0]["fields"].append("ghost")
    unbacked["fields"].append(
        {"id": "ghost", "name": "Ghost", "spoken_name": "ghost",
         "type": "text", "section_id": "s1",
         "help": {"instructions": "A field with no widget behind it."}})
    _make_kit(root, "unbacked", schema=unbacked)
    r = c.post(
        "/api/editor/kits/unbacked/status",
        headers={"X-Editor-Token": "edit-tok"},
        json={"status": "complete"},
    )
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert "field-unbacked" in detail
    assert "ghost" in detail


# --- POST /kits/{id}/translate-options (bd polyglot-pdf-2h9j) ------------------

_TRANSLATABLE_DRAFT = {
    "source": "pdf", "form_metadata": {"title": "T", "version": "unknown"},
    "sections": [],
    "fields": [
        {"id": "sex", "name": "Sex", "spoken_name": "sex", "type": "radio",
         "options": [{"value": "M", "label": "Male"},
                     {"value": "F", "label": "Female"}]},
        {"id": "confirm", "name": "C", "spoken_name": "c", "type": "radio",
         "options": [{"value": "y", "label": "Yes"}]},
    ],
}


class _FakeTranslateAI:
    """Stands in for TextAIGemini in the translate-options route: records the
    constructor kwargs (tier-discipline pins) and answers every language via
    the context-carrying translate_items call (bd alry)."""

    instances: list = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        type(self).instances.append(self)

    async def translate_items(self, items, language_name, language_code, *,
                              form_name=None, glossary_context=None):
        sent = []
        result = {}
        for item in items:
            if item["kind"] == "option-set":
                sent.extend(item["options"])
                result[item["id"]] = {"options": {
                    s: f"{s} ({language_name})" for s in item["options"]}}
            else:
                sent.append(item["text"])
                result[item["id"]] = {
                    "translation": f"{item['text']} ({language_name})"}
        self.calls.append((tuple(sent), language_name))
        return {"items": result, "ambiguous": []}


class _OfflineLiteAI:
    """The verify loop's lite leg, forced offline: back_translate returns
    None (the fail-open signal), so the default-ON verify gate (bd 9ikj)
    exercises its unavailable path with ZERO live calls. Without this
    patch, option_translation._build_verify_lite_ai constructs a REAL
    adapter behind the route's TextAIGemini patch -- on a machine with live
    credentials that would make unit tests hit the real endpoint."""

    async def back_translate(self, items, language_name, language_code):
        return None


@pytest.fixture()
def translate_ai(monkeypatch):
    # Patch the adapter where the RESOLVER builds it (bd polyglot-pdf-cpiw):
    # provider selection moved out of the route and into
    # backend.services.editor_text_ai, so patching ekr.TextAIGemini no longer
    # intercepts anything -- the route would silently make real Gemini calls
    # and every assertion on recorded calls would read zero.
    import backend.services.editor_text_ai as _eta
    import backend.services.option_translation as _ot
    _FakeTranslateAI.instances = []
    monkeypatch.setattr(_eta, "TextAIGemini", _FakeTranslateAI)
    monkeypatch.setattr(
        _ot, "_build_verify_lite_ai", lambda: _OfflineLiteAI())
    return _FakeTranslateAI


def test_translate_options_bakes_stores_and_is_idempotent(client, translate_ai):
    c, store, root = client
    _make_kit(root, "fresh", status="draft", schema=_TRANSLATABLE_DRAFT)
    r = c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["changed"] is True
    assert body["failedLanguages"] == []
    # Every supported spoken language minus english, keyed lowercase.
    from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47
    expected_langs = sorted(n for n in SPOKEN_LANGUAGE_BCP47 if n != "english")
    assert sorted(body["languages"]) == expected_langs
    assert body["languages"]["spanish"]["translated"] == 3

    # Tier discipline pinned: no lite fallback chain, bounded thinking budget.
    ai = translate_ai.instances[0]
    assert ai.kwargs["fallback_models"] == ()
    assert ai.kwargs["thinking_budget"] == 512
    assert ai.kwargs["model"] == "gemini-2.5-pro"

    # Stored: canonical lowercase-name keys, values/labels untouched.
    stored = _run(store.load_schema("fresh"))
    male = stored["fields"][0]["options"][0]
    assert male["label_translations"]["spanish"] == "Male (Spanish)"
    assert (male["value"], male["label"]) == ("M", "Male")
    # Field spoken names bake through the SAME route call (bd tupu.3 "editor
    # bake round-trips"): the stored field carries spoken_name_translations
    # under the canonical key, with the spoken_name itself untouched.
    sex_field = stored["fields"][0]
    assert sex_field["spoken_name_translations"]["spanish"] == "sex (Spanish)"
    assert sex_field["spoken_name"] == "sex"

    # Idempotent: a second run translates nothing and stores nothing.
    r2 = c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["changed"] is False
    assert translate_ai.instances[1].calls == []


def test_translate_options_force_retranslates(client, translate_ai):
    c, store, root = client
    _make_kit(root, "fresh", status="draft", schema=_TRANSLATABLE_DRAFT)
    assert c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 200
    r = c.post(
        "/api/editor/kits/fresh/translate-options?force=true",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    # force retranslates everything: the second instance made real calls.
    assert len(translate_ai.instances[1].calls) > 0


def test_translate_options_partial_failure_stores_and_reports(
        client, translate_ai, monkeypatch):
    c, store, root = client
    _make_kit(root, "fresh", status="draft", schema=_TRANSLATABLE_DRAFT)

    async def _flaky(self, items, language_name, language_code, *,
                     form_name=None, glossary_context=None):
        if language_name.lower() == "french":
            self.calls.append(((), language_name))
            return None
        result = {}
        sent = []
        for item in items:
            if item["kind"] == "option-set":
                sent.extend(item["options"])
                result[item["id"]] = {"options": {
                    s: f"{s} ({language_name})" for s in item["options"]}}
            else:
                sent.append(item["text"])
                result[item["id"]] = {
                    "translation": f"{item['text']} ({language_name})"}
        self.calls.append((tuple(sent), language_name))
        return {"items": result, "ambiguous": []}

    monkeypatch.setattr(_FakeTranslateAI, "translate_items", _flaky)
    r = c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["failedLanguages"] == ["french"]
    assert body["changed"] is True
    stored = _run(store.load_schema("fresh"))
    male = stored["fields"][0]["options"][0]
    assert "spanish" in male["label_translations"]
    assert "french" not in male["label_translations"]


def test_translate_options_gates(client, translate_ai, monkeypatch):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft", schema=_TRANSLATABLE_DRAFT)
    # Author-only (it mutates the stored schema).
    assert c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "edit-tok"},
    ).status_code == 403
    # Unknown kit -> 404; published kit -> 409 (same gating as repair).
    assert c.post(
        "/api/editor/kits/ghost/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 404
    _make_kit(root, "done", status="complete", schema=VALID_SCHEMA)
    assert c.post(
        "/api/editor/kits/done/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 409
    # No Gemini auth configured -> 503 (same gate as hosted extraction).
    monkeypatch.setattr(ekr, "get_settings", lambda: _settings(
        editor="edit-tok", author="auth-tok", GEMINI_API_KEY=None, VERTEXAI=False))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 503


def test_translate_options_schemaless_kit_is_404(client, translate_ai):
    c, _store, root = client
    _make_kit(root, "fresh", status="draft")  # PDF, no schema
    assert c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    ).status_code == 404


def test_translate_options_surfaces_and_persists_flags(
        client, translate_ai, monkeypatch):
    """bd polyglot-pdf-9djc: the route must READ the bake report's flags, not
    drop them (the V3 review note) -- returning them on the response AND
    persisting them into the stored schema's _bakeoff provenance slot, where
    lint_schema re-emits them so the ValidationPanel lists the worklist on
    every later lint pass. Planted via the translator's `ambiguous` self-flag
    (a real report-channel flag that needs no judge stub -- zero live calls)."""
    c, store, root = client
    _make_kit(root, "fresh", status="draft", schema=_TRANSLATABLE_DRAFT)

    async def _ambiguous(self, items, language_name, language_code, *,
                         form_name=None, glossary_context=None):
        result = {}
        for item in items:
            if item["kind"] == "option-set":
                result[item["id"]] = {"options": {
                    s: f"{s} ({language_name})" for s in item["options"]}}
            else:
                result[item["id"]] = {
                    "translation": f"{item['text']} ({language_name})"}
        # Self-flag every option-set as under-determined source text.
        ambiguous = [i["id"] for i in items if i["kind"] == "option-set"]
        return {"items": result, "ambiguous": ambiguous}

    monkeypatch.setattr(_FakeTranslateAI, "translate_items", _ambiguous)
    r = c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    flags = body["flags"]
    assert flags, "the planted ambiguity flags must reach the response"
    # Two planted flag classes flow with zero live calls: the translator's
    # ambiguity self-flag, plus the deterministic mechanical lint tripping on
    # the fake "X (Language)" Latin strings for non-Latin-script languages
    # (wrong expected script) -- the offline verify leg keeps those lint
    # flags (fail-open keeps deterministic evidence).
    rules = {f["rule"] for f in flags}
    assert "translation-ambiguous-source" in rules
    assert rules <= {"translation-ambiguous-source", "translation-mechanical"}
    assert all(f["severity"] == "WARNING" for f in flags)
    # Field-focus works: option flags anchor to their field ids.
    assert {"sex", "confirm"} <= {
        f["field_id"] for f in flags
        if f["rule"] == "translation-ambiguous-source"}
    # The lint counts on the SAME response already include the persisted
    # flags (lint_schema re-emits them from provenance).
    assert body["warningCount"] >= len(flags)

    # Persisted verbatim in the extraction-parity provenance slot.
    stored = _run(store.load_schema("fresh"))
    slot = stored["_bakeoff"]["authoring"]["option_translation"]
    assert slot["flags"] == flags
    assert slot["model"] == "gemini-2.5-pro"

    # An idempotent re-run (nothing fresh -> no new flags) must NOT erase the
    # persisted worklist.
    r2 = c.post(
        "/api/editor/kits/fresh/translate-options",
        headers={"X-Editor-Token": "auth-tok"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["changed"] is False
    assert r2.json()["flags"] == []
    stored2 = _run(store.load_schema("fresh"))
    assert stored2["_bakeoff"]["authoring"]["option_translation"]["flags"] \
        == flags
    # And the re-run's lint counts still carry the persisted flags.
    assert r2.json()["warningCount"] >= len(flags)


def test_extract_threads_the_translate_options_flag(client, monkeypatch):
    # The extract route passes --translation-model (settings-resolved) when the
    # checkbox is on (the default) and --no-translate-options when it is off.
    c, _store, root = client
    seen_cmds = []

    draft = {"source": "pdf", "form_metadata": {"title": "T", "version": "u"},
             "sections": [], "fields": [{"id": "a", "type": "text"}]}

    def _capture(cmd, **kwargs):
        seen_cmds.append(cmd)
        return _fake_extractor(draft, exit_code=0)(cmd, **kwargs)

    monkeypatch.setattr(ekr.subprocess, "run", _capture)

    _make_kit(root, "fresh1")
    r = c.post("/api/editor/kits/fresh1/extract",
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200, r.text
    assert "--translation-model" in seen_cmds[0]
    model = seen_cmds[0][seen_cmds[0].index("--translation-model") + 1]
    assert model == "gemini-2.5-pro"
    assert "--no-translate-options" not in seen_cmds[0]
    # The guidance stage's model must ALSO be settings-resolved (bd wsao.6):
    # without --guidance-model the child falls through raw env vars to the
    # local claude CLI, absent in the hosted container.
    assert "--guidance-model" in seen_cmds[0]
    gmodel = seen_cmds[0][seen_cmds[0].index("--guidance-model") + 1]
    assert gmodel == "gemini-2.5-pro"

    _make_kit(root, "fresh2")
    r = c.post("/api/editor/kits/fresh2/extract",
               headers={"X-Editor-Token": "auth-tok"},
               data={"translate_options": "false"})
    assert r.status_code == 200, r.text
    assert "--no-translate-options" in seen_cmds[1]
    assert "--translation-model" not in seen_cmds[1]
    # the two opt-outs are independent: guidance stays ON here
    assert "--guidance-model" in seen_cmds[1]

    # The guidance kill switch's SERVER-SIDE half (bd wsao.6): unchecking
    # must actually suppress the LLM stage in the subprocess cmd.
    _make_kit(root, "fresh3")
    r = c.post("/api/editor/kits/fresh3/extract",
               headers={"X-Editor-Token": "auth-tok"},
               data={"enrich_guidance": "false"})
    assert r.status_code == 200, r.text
    assert "--no-enrich-guidance" in seen_cmds[2]
    assert "--guidance-model" not in seen_cmds[2]


# --- guidance regeneration (bd polyglot-pdf-cpiw) --------------------------- #
#
# The staleness gate (bd anim) offers a reviewer two ways out of a drifted
# field: acknowledge (free) or RE-AUTHOR (costly). Only the free half existed,
# so re-authoring meant hand-copying prose out of the instructions booklet.
# These pin the route that closes that gap. The model call itself is stubbed --
# what matters here is the gating, the scoping, and that a successful rewrite
# re-stamps provenance (which is what CLEARS the staleness flag).

_GUIDANCE_SCHEMA = {
    "schema_version": "2",
    "form_metadata": {"title": "T", "version": "1", "form_number": "X"},
    "sections": [],
    "fields": [
        {"id": "a", "name": "A", "type": "text", "spoken_name": "a",
         "pdf_field_name": "f1"},
        {"id": "b", "name": "B", "type": "text", "spoken_name": "b",
         "pdf_field_name": "f2"},
    ],
}


class _FakeEnrich:
    """Stand-in for scripts/authoring/enrich_instructions."""

    last_fields = None

    @staticmethod
    def booklet_text(path):
        return "BOOKLET TEXT"

    @staticmethod
    def askable_fields(schema):
        # The real one drops read_only/signature fields -- the route uses it so
        # an UNSCOPED run does not report never-candidates as "skipped".
        return [f for f in schema.get("fields", [])
                if isinstance(f, dict) and not f.get("read_only")
                and f.get("type") != "signature"]

    @staticmethod
    def verify_and_rectify(schema, proposals, booklet, form_name,
                           author_model, judge_model=None):
        # The real one judges every proposal and MUTATES per the KEEP rule.
        # The route must call it before writing (it is what earns the
        # "llm-verified" provenance stamp); the fake just records the flags.
        return [{"severity": "WARNING", "rule": "instructions-rectified",
                 "path": "x", "message": "judged"}]

    @classmethod
    def enrich_schema(cls, schema, booklet, form_name, model, chunk_size):
        # Record which fields were handed to the model -- that is how the
        # fieldIds scoping is asserted.
        cls.last_fields = [f["id"] for f in schema.get("fields", [])]
        return {"proposals": {
            "fields": {fid: {"instructions": f"new guidance for {fid}"}
                       for fid in cls.last_fields},
            "form_details": "",
        }}

    @staticmethod
    def apply_proposals(schema, proposals, booklet, flags, model, judge_model,
                        tu_map=None):
        written = 0
        for f in schema.get("fields", []):
            entry = (proposals.get("fields") or {}).get(f.get("id"))
            if isinstance(entry, dict) and entry.get("instructions"):
                f["help"] = {"instructions": entry["instructions"]}
                written += 1
        return {"written": written, "skipped_human": 0, "flags": 0,
                "unmatched_proposal_ids": []}


@pytest.fixture()
def guidance_enrich(monkeypatch):
    _FakeEnrich.last_fields = None
    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _FakeEnrich)
    return _FakeEnrich


def _kit_with_booklet(root, kit_id, *, status="draft", schema=None):
    kit_dir = _make_kit(root, kit_id, status=status,
                        schema=schema or _GUIDANCE_SCHEMA)
    (kit_dir / "w7-instructions.pdf").write_bytes(b"%PDF-1.7 booklet")
    return kit_dir


def test_regenerate_guidance_rewrites_and_stores(client, guidance_enrich):
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 200, r.text
    body = r.json()
    assert sorted(body["regenerated"]) == ["a", "b"]
    assert body["booklet"] == "w7-instructions.pdf"
    stored = json.loads((root / "fresh" / "schema.json").read_text(encoding="utf-8"))
    assert stored["fields"][0]["help"]["instructions"] == "new guidance for a"


def test_regenerate_guidance_scopes_to_requested_fields(client, guidance_enrich):
    # The staleness banner knows exactly which fields drifted, so the costly
    # rewrite must be limited to them rather than re-billing the whole form.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"},
               json={"fieldIds": ["b"]})
    assert r.status_code == 200, r.text
    assert guidance_enrich.last_fields == ["b"]
    assert r.json()["regenerated"] == ["b"]
    stored = json.loads((root / "fresh" / "schema.json").read_text(encoding="utf-8"))
    assert "help" not in stored["fields"][0]        # 'a' untouched
    assert stored["fields"][1]["help"]["instructions"] == "new guidance for b"


def test_regenerate_guidance_refuses_without_a_booklet(client, guidance_enrich):
    # The booklet is the GROUNDING for every proposal; without one the model
    # would be inventing legal-form prose. Refuse rather than fabricate.
    c, store, root = client
    _make_kit(root, "nobook", schema=_GUIDANCE_SCHEMA)  # form.pdf only
    r = c.post("/api/editor/kits/nobook/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 409
    assert "instructions booklet" in r.json()["detail"]


def test_regenerate_guidance_refuses_on_a_published_kit(client, guidance_enrich):
    c, store, root = client
    _kit_with_booklet(root, "done", status="complete")
    r = c.post("/api/editor/kits/done/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 409
    assert "draft" in r.json()["detail"]


def test_regenerate_guidance_needs_the_author_tier(client, guidance_enrich):
    # It spends model tokens and rewrites the stored schema, like extract.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "edit-tok"}, json={})
    assert r.status_code == 403


def test_regenerate_guidance_rejects_unknown_field_ids(client, guidance_enrich):
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"},
               json={"fieldIds": ["ghost"]})
    assert r.status_code == 422


def test_regenerate_guidance_reports_a_model_failure_without_writing(
        client, monkeypatch):
    # A transport/model failure must leave the stored schema BYTE-UNTOUCHED --
    # a half-written guidance rewrite is worse than none.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    before = (root / "fresh" / "schema.json").read_text(encoding="utf-8")

    class _Boom(_FakeEnrich):
        @staticmethod
        def enrich_schema(*a, **kw):
            raise RuntimeError("model exploded")

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _Boom)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 502
    assert "Nothing was changed" in r.json()["detail"]
    assert (root / "fresh" / "schema.json").read_text(encoding="utf-8") == before


def test_regenerate_guidance_preserves_flags_and_judge_model(
        client, guidance_enrich):
    # apply_proposals REPLACES the whole instructions_enrich block. Passing
    # flags=[] wiped the reviewer's guidance worklist (schema_lint re-emits
    # those flags as findings) and blanked which judge verified the kit.
    c, store, root = client
    schema = json.loads(json.dumps(_GUIDANCE_SCHEMA))
    schema["_bakeoff"] = {"authoring": {"instructions_enrich": {
        "model": "old", "judge_model": "gemini-2.5-flash",
        "flags": [{"severity": "WARNING", "rule": "instructions-rectified",
                   "path": "p", "message": "m"}],
        "provenance": {},
    }}}
    _kit_with_booklet(root, "fresh", schema=schema)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={"fieldIds": ["a"]})
    assert r.status_code == 200, r.text
    stored = json.loads((root / "fresh" / "schema.json").read_text(encoding="utf-8"))
    block = stored["_bakeoff"]["authoring"]["instructions_enrich"]
    assert block["judge_model"] == "gemini-2.5-flash"
    assert any(f["rule"] == "instructions-rectified" for f in block["flags"])


def test_regenerate_guidance_scoped_does_not_clobber_form_details(
        client, monkeypatch):
    # enrich_schema asks for form_details in EVERY chunk, so a one-field
    # rewrite would otherwise replace the kit's whole eligibility/where-to-file
    # block with whatever that chunk emitted.
    c, store, root = client
    schema = json.loads(json.dumps(_GUIDANCE_SCHEMA))
    schema["form_metadata"]["details"] = "THE REAL FORM-LEVEL PROSE"
    _kit_with_booklet(root, "fresh", schema=schema)

    class _Chatty(_FakeEnrich):
        @classmethod
        def enrich_schema(cls, s, booklet, form_name, model, chunk_size):
            out = _FakeEnrich.enrich_schema(s, booklet, form_name, model,
                                            chunk_size)
            out["proposals"]["form_details"] = "a one-chunk fragment"
            return out

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _Chatty)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={"fieldIds": ["a"]})
    assert r.status_code == 200, r.text
    stored = json.loads((root / "fresh" / "schema.json").read_text(encoding="utf-8"))
    assert stored["form_metadata"]["details"] == "THE REAL FORM-LEVEL PROSE"


def test_regenerate_guidance_writes_nothing_when_no_proposals(
        client, monkeypatch):
    # enrich_schema filters to ASKABLE fields, so a fieldIds list of only
    # read_only/signature fields yields zero proposals. Falling through would
    # re-stamp the bake block for no benefit -- a destructive no-op.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    before = (root / "fresh" / "schema.json").read_text(encoding="utf-8")

    class _Empty(_FakeEnrich):
        @classmethod
        def enrich_schema(cls, s, booklet, form_name, model, chunk_size):
            return {"proposals": {"fields": {}, "form_details": ""}}

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _Empty)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={"fieldIds": ["a"]})
    assert r.status_code == 200, r.text
    assert r.json()["regenerated"] == []
    assert (root / "fresh" / "schema.json").read_text(encoding="utf-8") == before


def test_regenerate_guidance_runs_the_verify_loop_before_writing(
        client, monkeypatch):
    # apply_proposals stamps source="llm-verified". Every other caller earns
    # that label by judging first; this route must too, or unreviewed model
    # prose lands in a stored kit labelled verified.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    called = {"verify": False}

    class _Tracked(_FakeEnrich):
        @staticmethod
        def verify_and_rectify(schema, proposals, booklet, form_name,
                               author_model, judge_model=None):
            called["verify"] = True
            return []

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _Tracked)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 200, r.text
    assert called["verify"], "the judge did not run before the write"


def test_regenerate_guidance_reports_nothing_when_the_judge_is_out(
        client, monkeypatch):
    # verify_and_rectify fails SAFE by blanking each entry to {} but KEEPING
    # its key, so `fields` stays truthy. An empty-dict guard misses that, and
    # the route would return 200 with a non-empty `regenerated` having written
    # nothing -- the reviewer believes the guidance was re-authored.
    c, store, root = client
    _kit_with_booklet(root, "fresh")
    before = (root / "fresh" / "schema.json").read_text(encoding="utf-8")

    class _JudgeDown(_FakeEnrich):
        @staticmethod
        def verify_and_rectify(schema, proposals, booklet, form_name,
                               author_model, judge_model=None):
            for fid in list((proposals.get("fields") or {})):
                proposals["fields"][fid] = {}   # the real fail-safe shape
            return [{"severity": "WARNING",
                     "rule": "instructions-enrich-unavailable",
                     "path": "x", "message": "judge down"}]

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _JudgeDown)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={})
    assert r.status_code == 200, r.text
    assert r.json()["regenerated"] == []
    assert (root / "fresh" / "schema.json").read_text(encoding="utf-8") == before


def test_regenerate_guidance_does_not_claim_it_overwrote_human_edits(
        client, monkeypatch):
    # apply_proposals SKIPS a field whose guidance a human edited. Reporting
    # the proposal ids would tell the reviewer their hand-written text was
    # overwritten -- the opposite of the route's contract.
    c, store, root = client
    _kit_with_booklet(root, "fresh")

    class _HumanOwned(_FakeEnrich):
        @staticmethod
        def apply_proposals(schema, proposals, booklet, flags, model,
                            judge_model, tu_map=None):
            # writes nothing: every field reads as hand-edited
            return {"written": 0, "skipped_human": 1, "flags": 0,
                    "unmatched_proposal_ids": []}

    monkeypatch.setattr(ekr, "_load_enrich_instructions", lambda: _HumanOwned)
    r = c.post("/api/editor/kits/fresh/regenerate-guidance",
               headers={"X-Editor-Token": "auth-tok"}, json={"fieldIds": ["a"]})
    assert r.status_code == 200, r.text
    assert r.json()["regenerated"] == []
    assert r.json()["skipped"] == ["a"]


# --- same-folder handshake (bd polyglot-pdf-s2bf) --------------------------- #
#
# In LOCAL mode the editor reads/writes the folder the human PICKED while the
# backend resolves kit ids against its OWN root. When those differ, the
# server-side actions rewrite the OTHER copy while the editor re-reads the
# picked one -- destructive and invisible. The browser cannot read a path out
# of a directory handle, so agreement is proved by shared observation: the
# editor writes a nonce, the backend reads it back from its own root.

def test_handshake_confirms_the_same_folder(client):
    c, store, root = client
    (root / ".editor-store-check.json").write_text(
        json.dumps({"nonce": "n1"}), encoding="utf-8")
    r = c.post("/api/editor/store-handshake", json={"nonce": "n1"},
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sameFolder"] is True
    assert body["backendRoot"] == str(root)


def test_handshake_reports_a_mismatch_when_the_marker_is_absent(client):
    # The editor wrote its marker somewhere ELSE -- i.e. a different folder.
    c, store, root = client
    r = c.post("/api/editor/store-handshake", json={"nonce": "n1"},
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200
    assert r.json()["sameFolder"] is False
    assert r.json()["reason"] == "mismatch"


def test_handshake_rejects_a_stale_marker(client):
    # A leftover from an earlier session in a DIFFERENT folder must not pass.
    # This is why the nonce is minted per check rather than being a constant.
    c, store, root = client
    (root / ".editor-store-check.json").write_text(
        json.dumps({"nonce": "old"}), encoding="utf-8")
    r = c.post("/api/editor/store-handshake", json={"nonce": "fresh"},
               headers={"X-Editor-Token": "auth-tok"})
    assert r.json()["sameFolder"] is False
    assert r.json()["reason"] == "stale"


def test_handshake_survives_a_corrupt_marker(client):
    # Unparseable = not observed. Never a 500.
    c, store, root = client
    (root / ".editor-store-check.json").write_text("{not json", encoding="utf-8")
    r = c.post("/api/editor/store-handshake", json={"nonce": "n1"},
               headers={"X-Editor-Token": "auth-tok"})
    assert r.status_code == 200
    assert r.json()["sameFolder"] is False


def test_handshake_never_writes_or_deletes(client):
    # The backend only ever READS the marker: a read-only store must degrade to
    # sameFolder=false, not fail. The editor owns the file's lifecycle.
    c, store, root = client
    marker = root / ".editor-store-check.json"
    marker.write_text(json.dumps({"nonce": "n1"}), encoding="utf-8")
    c.post("/api/editor/store-handshake", json={"nonce": "n1"},
           headers={"X-Editor-Token": "auth-tok"})
    assert marker.exists(), "the backend must not delete the editor's marker"
