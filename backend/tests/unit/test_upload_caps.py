"""Upload-body size caps + resume-form parse timeout (bd polyglot-pdf-6088m,
sprint 23 C4; PF-10).

MAX_UPLOAD_MB was declared in Settings and reported by /health, but nothing
enforced it -- a knob nothing can turn on is a trap for the next caller
(CLAUDE.md scar #7). These tests pin the fix:

  1. A SET-DERIVED test enumerating every route in this backend that accepts
     a caller-controlled body carrying a real size (excluding tiny bounded-
     field routes like /api/disclaimer-acceptance, which are pinned
     separately). New unguarded routes joining that shape must fail this
     test, not slip through by omission (scar #8: pin the SET, not the
     instance).
  2. /api/fill-pdf and /api/resume-form refuse an over-cap body via
     Content-Length BEFORE FastAPI finishes parsing it.
  3. /api/resume-form refuses an over-length base64 string BEFORE decoding it.
  4. /api/resume-form's structural-comparison parse is wall-clock bounded --
     a parse that exceeds RESUME_FORM_PARSE_TIMEOUT_S fails closed (408)
     rather than hanging the request indefinitely.

All bodies here are fake/short; no test parses a real PDF (that requires a
form-kits/w7 checkout this worktree does not carry -- see
backend/tests/test_resume_form_route.py, which skips without it). These
tests exercise the CAP LOGIC itself, ahead of and independent of any real
PDF parse.
"""
from __future__ import annotations

import ast
import base64
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.routes.pdf_fill_routes as pfr
from backend.config import Settings
from backend.main import app
from backend.services.auth import require_auth

REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# 1. The enumerated set of upload/large-body routes in THIS backend's surface.
# ---------------------------------------------------------------------------
#
# Derived from the route source, not hand-maintained: every @router.post /
# @router.put decorator whose handler takes an UploadFile parameter, OR whose
# Pydantic body model has a field plausibly carrying a whole file (base64/
# schema payload), in backend/routes/*.py. A new such route that does not
# appear in _GUARDED_HERE or _ROUTED_ELSEWHERE below fails this test.
#
# The two editor upload routes are OUTSIDE this bead's declared surfaces
# (backend/routes/editor_kit_routes.py is not listed in bd polyglot-pdf-6088m's
# surfaces) -- they are ALREADY guarded, via a size-as-you-stream check against
# settings.EXTRACTOR_MAX_PDF_MB (backend/routes/editor_kit_routes.py's
# _read_upload_pdf), which is a distinct cap from MAX_UPLOAD_MB with its own
# authoring-time rationale (docs/components/config-deployment.md). They are
# listed here as ROUTED ELSEWHERE, not silently excluded.
_GUARDED_HERE = {
    ("POST", "/api/fill-pdf"),
    ("POST", "/api/resume-form"),
}
_ROUTED_ELSEWHERE = {
    # editor_kit_routes.py -- outside this bead's declared surfaces (not
    # listed among backend/routes/dev_console_routes.py,
    # backend/routes/pdf_fill_routes.py, backend/routes/disclaimer_routes.py
    # in bd polyglot-pdf-6088m). The two upload-file routes are already
    # capped via _read_upload_pdf(pdf, settings.EXTRACTOR_MAX_PDF_MB); the
    # three raw-schema-body routes (PUT .../schema, POST .../lint x2) accept
    # an unbounded `Annotated[dict, Body()]` with NO size cap today -- a real
    # gap, but this bead's surfaces do not include editor_kit_routes.py or
    # editor_readiness_routes.py, so it is reported here rather than fixed.
    ("POST", "/api/editor/kits"),
    ("POST", "/api/editor/kits/{kit_id}/extract"),
    ("PUT", "/api/editor/kits/{kit_id}/schema"),
    ("POST", "/api/editor/kits/{kit_id}/lint"),
    ("POST", "/api/editor/lint"),
    ("POST", "/api/editor/kits/{kit_id}/readiness"),
}


def _router_prefix(tree: ast.Module) -> str:
    """Read the `prefix=` kwarg off this module's `router = APIRouter(...)`
    assignment, defaulting to "" (tts_routes.py and dev_console_routes.py
    declare no prefix)."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not (len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "router"):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        for kw in node.value.keywords:
            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                return kw.value.value
    return ""


def _discover_large_body_routes() -> set[tuple[str, str]]:
    """Statically find every POST/PUT route under backend/routes/ whose body
    can carry a caller-controlled payload with NO other size bound: either an
    UploadFile parameter, a field named like a whole-file payload (base64-
    shaped), or a field typed Dict[...] / dict (an arbitrary-shape JSON blob
    with no Field max_length to cap it, unlike an ordinary str field). AST-
    based so it needs no app import side effects and cannot miss a route
    behind an import-time guard."""
    routes_dir = REPO_ROOT / "backend" / "routes"
    found: set[tuple[str, str]] = set()

    # Field names, anywhere in a Pydantic model, that mark "this body carries
    # a whole file/document" rather than ordinary scalar form data.
    file_shaped_field_names = {"pdf_base64", "file_base64", "content_base64"}

    def _is_unbounded_dict_annotation(ann: ast.AST | None) -> bool:
        """True for `Dict[...]` / `dict` — an arbitrary-shape JSON object with
        no length bound available (Field max_length applies to str/bytes/
        list, not dict)."""
        if ann is None:
            return False
        if isinstance(ann, ast.Name) and ann.id == "dict":
            return True
        if isinstance(ann, ast.Subscript):
            base = ann.value
            if isinstance(base, ast.Name) and base.id in ("Dict", "dict"):
                return True
            if isinstance(base, ast.Attribute) and base.attr in ("Dict", "dict"):
                return True
        return False

    for path in sorted(routes_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        prefix = _router_prefix(tree)
        # Field names declared on each class in this module, and which of
        # those fields are unbounded-dict-shaped.
        class_fields: dict[str, set[str]] = {}
        class_dict_fields: dict[str, set[str]] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                fields = set()
                dict_fields = set()
                for stmt in node.body:
                    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                        fields.add(stmt.target.id)
                        if _is_unbounded_dict_annotation(stmt.annotation):
                            dict_fields.add(stmt.target.id)
                class_fields[node.name] = fields
                class_dict_fields[node.name] = dict_fields

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                call = deco if isinstance(deco, ast.Call) else None
                if call is None:
                    continue
                func = call.func
                if not (isinstance(func, ast.Attribute) and func.attr in ("post", "put")):
                    continue
                if not (isinstance(func.value, ast.Name) and func.value.id == "router"):
                    continue
                if not call.args or not isinstance(call.args[0], ast.Constant):
                    continue
                sub_path = call.args[0].value

                # Map each positional arg to its default (Depends(...), Query(...),
                # etc.), so a dependency-injected `user: dict = Depends(...)`
                # is never mistaken for a body field just because it is
                # annotated `dict` -- that annotation describes the VERIFIED
                # CLAIMS dict a dependency returns, not a request body.
                defaults = node.args.defaults
                num_no_default = len(node.args.args) - len(defaults)
                arg_defaults: dict[str, ast.AST | None] = {}
                for i, arg in enumerate(node.args.args):
                    di = i - num_no_default
                    arg_defaults[arg.arg] = defaults[di] if di >= 0 else None

                def _is_dependency_default(default: ast.AST | None) -> bool:
                    if not isinstance(default, ast.Call):
                        return False
                    fn = default.func
                    name = fn.id if isinstance(fn, ast.Name) else getattr(fn, "attr", None)
                    return name in ("Depends", "Query", "Header", "Path", "Cookie")

                has_upload = False
                for arg in node.args.args:
                    if _is_dependency_default(arg_defaults.get(arg.arg)):
                        continue  # not a body field
                    ann = arg.annotation
                    ann_src = ast.dump(ann) if ann is not None else ""
                    if "UploadFile" in ann_src:
                        has_upload = True
                    if isinstance(ann, ast.Name) and ann.id in class_fields:
                        if class_fields[ann.id] & file_shaped_field_names:
                            has_upload = True
                        if class_dict_fields.get(ann.id):
                            has_upload = True
                    # An inline Annotated[dict, Body()] (or bare `dict`)
                    # parameter -- a raw JSON-object body with no Pydantic
                    # model, and so no Field max_length to bound it (e.g.
                    # editor_kit_routes.save_editor_kit_schema's
                    # `schema: Annotated[dict, Body()]`).
                    if isinstance(ann, ast.Subscript) and isinstance(ann.value, ast.Name) \
                            and ann.value.id == "Annotated":
                        inner = ann.slice
                        inner_elts = inner.elts if isinstance(inner, ast.Tuple) else [inner]
                        if inner_elts and _is_unbounded_dict_annotation(inner_elts[0]):
                            has_upload = True
                    elif _is_unbounded_dict_annotation(ann):
                        has_upload = True
                if has_upload:
                    found.add((func.attr.upper(), prefix + sub_path))

    return found


def test_the_enumerated_upload_route_set_is_fully_dispositioned():
    """Every discovered upload/large-body route is either guarded in THIS
    bead's surfaces or explicitly routed elsewhere -- never silently absent
    from both. A new route joining this shape must be added to one list or
    this test fails (scar #8: pin the set, not the instance)."""
    discovered = _discover_large_body_routes()
    assert discovered, "no upload routes were discovered -- the AST scan itself is broken"

    accounted_for = _GUARDED_HERE | _ROUTED_ELSEWHERE
    unaccounted = discovered - accounted_for
    assert not unaccounted, (
        f"new upload-shaped route(s) with no size-cap disposition: {unaccounted} "
        "-- add to _GUARDED_HERE (and cap it) or _ROUTED_ELSEWHERE (and say why)"
    )

    # And the reverse: nothing hand-listed here should have vanished from the
    # source (a route rename/removal should also touch this test).
    stale = _GUARDED_HERE - discovered
    assert not stale, f"routes listed as guarded here no longer exist: {stale}"


# ---------------------------------------------------------------------------
# 2. Content-Length rejection on /api/fill-pdf and /api/resume-form.
# ---------------------------------------------------------------------------


@pytest.fixture()
def client(monkeypatch):
    settings = Settings()
    monkeypatch.setattr(pfr, "get_settings", lambda: settings)
    app.dependency_overrides[require_auth] = lambda: {"uid": "test", "jti": None}
    try:
        yield TestClient(app), settings
    finally:
        app.dependency_overrides.pop(require_auth, None)


def test_fill_pdf_refuses_an_over_cap_content_length(client):
    tc, settings = client
    cap_bytes = int(settings.MAX_UPLOAD_MB * 1024 * 1024)
    # A tiny real body, but a LIED-ABOUT Content-Length header well over the
    # cap -- the dependency checks the header, not (only) the actual bytes
    # read, so this alone must be refused without FastAPI ever finishing
    # body validation.
    resp = tc.post(
        "/api/fill-pdf",
        content=b"{}",
        headers={"content-length": str(cap_bytes + 1), "content-type": "application/json"},
    )
    assert resp.status_code == 413


def test_fill_pdf_accepts_a_small_body(client, monkeypatch):
    """The cap must not reject a normal request. A missing kit is expected
    (no real store wired) -- the point is that the SIZE gate itself passes
    and the handler is reached."""
    tc, _settings = client
    body = {
        "kit_id": "nonexistent-kit-xyz",
        "pdf_filename": "form.pdf",
        "field_values": {},
        "form_schema": {"fields": []},
    }
    resp = tc.post("/api/fill-pdf", json=body)
    # Reached the handler (proven by a 404 on the missing kit, not a 413).
    assert resp.status_code != 413


def test_resume_form_refuses_an_over_cap_content_length(client):
    """/api/resume-form has its OWN, larger cap than /api/fill-pdf
    (_MAX_RESUME_BODY_BYTES, derived from _MAX_RESUME_UPLOAD_BYTES's 25MB --
    NOT settings.MAX_UPLOAD_MB's 5MB): a base64-encoded PDF inflates the JSON
    envelope well past 5MB for a perfectly legitimate few-MB saved form, so
    reusing the smaller generic cap here would reject real resumes. This
    pins that the ROUTE-SPECIFIC cap is what is actually enforced.
    """
    tc, _settings = client
    resp = tc.post(
        "/api/resume-form",
        content=b"{}",
        headers={
            "content-length": str(pfr._MAX_RESUME_BODY_BYTES + 1),
            "content-type": "application/json",
        },
    )
    assert resp.status_code == 413


def test_resume_form_content_length_cap_is_looser_than_fill_pdfs(client):
    """The two routes must NOT share settings.MAX_UPLOAD_MB directly -- a
    Content-Length between MAX_UPLOAD_MB and _MAX_RESUME_BODY_BYTES must pass
    the resume-form gate (a legitimate few-MB resume) while the SAME
    Content-Length would be refused on /api/fill-pdf.
    """
    tc, settings = client
    mid_size = int(settings.MAX_UPLOAD_MB * 1024 * 1024) + (1024 * 1024)  # 5MB + 1MB
    assert mid_size < pfr._MAX_RESUME_BODY_BYTES, "test constant assumption broke"

    resume_resp = tc.post(
        "/api/resume-form",
        content=b"{}",
        headers={"content-length": str(mid_size), "content-type": "application/json"},
    )
    assert resume_resp.status_code != 413, (
        "a body between the two caps was refused by /api/resume-form -- it "
        "must accept up to its OWN larger cap"
    )

    fill_resp = tc.post(
        "/api/fill-pdf",
        content=b"{}",
        headers={"content-length": str(mid_size), "content-type": "application/json"},
    )
    assert fill_resp.status_code == 413, (
        "the same body size was accepted by /api/fill-pdf -- it must enforce "
        "the SMALLER MAX_UPLOAD_MB cap, not resume-form's looser one"
    )


# ---------------------------------------------------------------------------
# 3. base64 length checked BEFORE decoding, on /api/resume-form.
# ---------------------------------------------------------------------------


def test_resume_form_refuses_an_oversized_base64_string_before_decoding(client, monkeypatch):
    """THE FIX. Before this bead, the base64 string was decoded FIRST and only
    the decoded byte length was checked -- so an attacker paid nothing extra
    to force the decode of a large buffer up to the point b64decode itself
    raised or completed. This pins that an over-length base64 STRING is
    refused without ever reaching base64.b64decode.
    """
    tc, _settings = client

    decode_called = {"value": False}
    real_b64decode = base64.b64decode

    def _spy_b64decode(*args, **kwargs):
        decode_called["value"] = True
        return real_b64decode(*args, **kwargs)

    monkeypatch.setattr(base64, "b64decode", _spy_b64decode)

    # One character over the base64-length cap (_MAX_RESUME_UPLOAD_BYTES * 4/3).
    oversized_b64_len = (pfr._MAX_RESUME_UPLOAD_BYTES * 4 // 3) + 4
    body = {
        "kit_id": "w7",
        "pdf_filename": "form.pdf",
        "pdf_base64": "A" * oversized_b64_len,
    }
    resp = tc.post("/api/resume-form", json=body)
    assert resp.status_code == 413
    assert not decode_called["value"], (
        "base64.b64decode was called despite an over-length input -- the "
        "length check must run BEFORE decoding, not after"
    )


def test_resume_form_still_decodes_a_normal_sized_base64_string(client, monkeypatch):
    """The length gate must not block legitimate (small) uploads before they
    even reach the kit lookup -- proven by observing the decode actually ran
    and the request proceeded past the base64 gate (a 404 on the missing kit
    is the expected next failure, not a 413)."""
    tc, _settings = client
    decode_called = {"value": False}
    real_b64decode = base64.b64decode

    def _spy_b64decode(*args, **kwargs):
        decode_called["value"] = True
        return real_b64decode(*args, **kwargs)

    monkeypatch.setattr(base64, "b64decode", _spy_b64decode)

    body = {
        "kit_id": "nonexistent-kit-xyz",
        "pdf_filename": "form.pdf",
        "pdf_base64": base64.b64encode(b"%PDF-1.4 not a real pdf").decode("ascii"),
    }
    resp = tc.post("/api/resume-form", json=body)
    assert decode_called["value"], "a normal-sized upload never reached b64decode"
    assert resp.status_code != 413


# ---------------------------------------------------------------------------
# 4. Wall-clock timeout around the structural-comparison parse.
# ---------------------------------------------------------------------------


def _minimal_pdf_bytes() -> bytes:
    """A real, minimal, one-page PDF -- valid enough for fitz.open to parse
    past the structural-check mock into the (real) read-back step later in
    the route."""
    import fitz as _fitz

    doc = _fitz.open()
    try:
        doc.new_page()
        return doc.tobytes()
    finally:
        doc.close()


def test_resume_form_parse_is_wall_clock_bounded(client, monkeypatch):
    """A structural-comparison call that never returns must not hang the
    request forever -- it must fail closed with a 408 once
    RESUME_FORM_PARSE_TIMEOUT_S elapses.

    assert_matches_reference is monkeypatched to block past the (very short,
    test-only) timeout, standing in for a pathological PDF that is slow to
    parse. The real function is exercised by backend/tests/test_resume_form_route.py
    (skipped in this worktree without the w7 kit); this test is only about
    the TIMEOUT MECHANISM around it.
    """
    import time as _time

    tc, settings = client
    settings.RESUME_FORM_PARSE_TIMEOUT_S = 0.2

    def _hang(*args, **kwargs):
        _time.sleep(2.0)

    monkeypatch.setattr(pfr, "assert_matches_reference", _hang)

    # Stub the store so the request reaches the parse step without a real kit.
    # load_schema is also stubbed so that, IF the timeout mechanism fails to
    # bound the hang (the mutation this test guards against), the test fails
    # on the actual status-code assertion below rather than on an unrelated
    # AttributeError from an incomplete fake -- the point of this test is the
    # timeout, not the shape of the rest of the route.
    pdf_bytes = _minimal_pdf_bytes()

    class _FakeStore:
        async def load_metadata(self, kit_id):
            return {"status": "complete"}

        async def load_pdf_bytes(self, kit_id, filename):
            return pdf_bytes

        async def load_schema(self, kit_id):
            return {"fields": []}

    monkeypatch.setattr(pfr, "get_form_kit_store", lambda: _FakeStore())

    body = {
        "kit_id": "fake-kit",
        "pdf_filename": "form.pdf",
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    resp = tc.post("/api/resume-form", json=body)
    assert resp.status_code == 408


def test_resume_form_parse_returns_promptly_when_under_the_timeout(client, monkeypatch):
    """The timeout mechanism itself must not add meaningful latency to a
    normal (fast) parse -- proven by a fast, non-hanging fake completing well
    inside a short timeout."""
    tc, settings = client
    settings.RESUME_FORM_PARSE_TIMEOUT_S = 5.0

    def _fast(*args, **kwargs):
        return None  # assert_matches_reference returns None on success

    monkeypatch.setattr(pfr, "assert_matches_reference", _fast)

    pdf_bytes = _minimal_pdf_bytes()

    class _FakeStore:
        async def load_metadata(self, kit_id):
            return {"status": "complete"}

        async def load_pdf_bytes(self, kit_id, filename):
            return pdf_bytes

        async def load_schema(self, kit_id):
            return {"fields": []}

    monkeypatch.setattr(pfr, "get_form_kit_store", lambda: _FakeStore())

    body = {
        "kit_id": "fake-kit",
        "pdf_filename": "form.pdf",
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    resp = tc.post("/api/resume-form", json=body)
    assert resp.status_code != 408
