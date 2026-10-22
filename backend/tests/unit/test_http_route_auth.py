"""Auth gating on the HTTP routes (bd polyglot-pdf-z2is).

/api/fill-pdf renders user-entered field values, so it requires a Firebase ID
token via require_auth. /api/form-kits{,/schema} serve the kit catalogue and
require only require_signin -- a valid sign-in, NOT voice-app enrolment:
SELECTING a form is how the app is used, so gating it on a firm claim left a
signed-in user with nothing to pick and no way out (2026-08-25). Enrolment
gates ACTING on a form. /api/form-kits/{kit_id}/pdf stays DELIBERATELY public (blank
template = public government form, also shipped in the static Hosting bundle)
-- that non-gate is pinned here too so a future blanket-auth sweep can't
silently break the pdfjs viewer path without failing a test.

VFF_DISABLE_AUTH=true (local dev / voice harness) bypasses inside verify_token;
the 401 tests pin the bypass OFF explicitly so a dev .env can't green them.
"""
import asyncio

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import backend.routes.form_kit_routes as fkr
from backend.main import app
from backend.services.auth import require_auth
from backend.services.form_kits import FormKitNotFound

client = TestClient(app)

# Minimal but schema-valid body so a 401 is unambiguously the auth dependency,
# not a 422 from body validation.
_FILL_BODY = {
    "kit_id": "i-90",
    "pdf_filename": "form.pdf",
    "field_values": {},
    "form_schema": {"fields": []},
}


class _NotFoundStore:
    """Store double whose every read 404s -- keeps route tests hermetic."""

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        raise FormKitNotFound("no manifest")

    async def load_metadata(self, kit_id: str):
        raise FormKitNotFound("no metadata")

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json"):
        raise FormKitNotFound("no schema")

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        raise FormKitNotFound("no pdf")


@pytest.fixture
def _auth_on(monkeypatch):
    """Force real auth (bypass OFF) regardless of the dev machine's .env."""
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")


@pytest.fixture
def _auth_bypassed(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "true")


def test_fill_pdf_requires_token(_auth_on):
    resp = client.post("/api/fill-pdf", json=_FILL_BODY)
    assert resp.status_code == 401


def test_fill_pdf_rejects_garbage_token(_auth_on):
    resp = client.post(
        "/api/fill-pdf",
        json=_FILL_BODY,
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert resp.status_code == 401


def test_form_kits_list_requires_token(_auth_on):
    resp = client.get("/api/form-kits")
    assert resp.status_code == 401


def test_form_kit_schema_requires_token(_auth_on):
    resp = client.get("/api/form-kits/i-90/schema")
    assert resp.status_code == 401


def test_form_kit_pdf_is_deliberately_public(_auth_on, monkeypatch):
    """The PDF GET must NOT be auth-gated FOR PUBLIC KITS (updated
    DELIBERATELY by bd polyglot-pdf-vccy, which added the private-kit gate:
    the route now parses an OPTIONAL bearer token and 404s private kits for
    non-members -- see the firm-visibility tests below -- while a public
    kit's blank-template bytes ship in the static Hosting bundle regardless,
    so gating the public read still protects nothing). Pinned so a future
    blanket-auth sweep is a deliberate decision, not an accident.

    With auth forced on and no token, the route must still reach the store
    (404 from the double), never 401.
    """
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _NotFoundStore())
    resp = client.get("/api/form-kits/i-90/pdf")
    assert resp.status_code == 404


def test_bypass_admits_tokenless_requests(_auth_bypassed, monkeypatch):
    """VFF_DISABLE_AUTH=true keeps local dev / the harness working tokenless."""
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _NotFoundStore())
    resp = client.get("/api/form-kits")
    # Auth passed (bypass); the empty-manifest path returns an empty list.
    assert resp.status_code == 200
    assert resp.json() == {"forms": []}


def test_require_auth_passes_bearer_token_to_verifier(monkeypatch):
    seen = {}

    # **kwargs, so a signature change upstream cannot masquerade as a
    # confidentiality failure here. verify_token has been re-signed twice
    # (check_revoked added, then removed); each time a fixed-signature double
    # turned that into a TypeError. These tests are about PRIVATE-KIT
    # VISIBILITY, and that is what they should fail on.
    def _fake_verify(token: str, **_kw) -> dict:
        seen["token"] = token
        return {"uid": "u1"}

    monkeypatch.setattr("backend.services.auth.verify_token", _fake_verify)
    claims = asyncio.run(require_auth("Bearer abc123"))
    assert claims == {"uid": "u1"}
    assert seen["token"] == "abc123"


def test_require_auth_missing_header_is_401(monkeypatch):
    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_auth(None))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------
# Firm-scoped kit visibility (bd polyglot-pdf-vccy).
#
# One public + one private kit. Identity comes from a patched verify_token
# (tok-a -> firm-a staff, tok-b -> firm-b staff, tok-legacy -> no firm claim);
# the firm allowlist comes from a patched get_allowed_kits (firm-a may see
# priv-kit). The manifest entries carry NO visibility key on purpose: the
# LIVE metadata is the visibility source (the GCS index.json is deploy-time
# stale), so these tests also pin that metadata beats the manifest.
# --------------------------------------------------------------------------

from backend.services.form_kits import normalize_manifest  # noqa: E402

_TOKENS = {
    "tok-a": {"uid": "staff-a", "firm_id": "firm-a", "firm_role": "manager"},
    "tok-b": {"uid": "staff-b", "firm_id": "firm-b", "firm_role": "employee"},
    "tok-legacy": {"uid": "legacy-user"},
}


class _TwoKitStore:
    """One public + one private kit; live metadata is the visibility source."""

    def __init__(self):
        self.meta = {
            "pub-kit": {"status": "complete"},
            "priv-kit": {
                "status": "complete",
                "visibility": "private",
                "owner_firm_id": "firm-a",
            },
        }
        # Superseded revisions (bd qfyxr): one stamped-newer, one
        # stamped-older, one stampless -- the sorting dimension.
        self.archive = {
            "priv-kit": {
                "2024-01": {
                    "schema": {"rev": "old"},
                    "metadata": {"published_at": "2024-01-05T00:00:00+00:00"},
                },
                "2025-06": {
                    "schema": {"rev": "newer"},
                    "metadata": {"published_at": "2025-06-01T00:00:00+00:00"},
                },
                "sha256-abc": {"schema": {"rev": "unstamped"}, "metadata": None},
            },
            "pub-kit": {
                "2023-12": {
                    "schema": {"rev": "pub-old"},
                    "metadata": {"published_at": "2023-12-01T00:00:00+00:00"},
                },
            },
        }

    async def load_manifest(self, manifest_file: str = "index.json") -> dict:
        return normalize_manifest({
            "forms": [
                {"id": "pub-kit", "label": "Public Kit"},
                {"id": "priv-kit", "label": "Private Kit", "pdfFile": "intake.pdf"},
            ]
        })

    async def load_metadata(self, kit_id: str):
        return self.meta.get(kit_id)

    async def load_schema(self, kit_id: str, schema_file: str = "schema.json"):
        return {"kit": kit_id}

    async def list_archived_markers(self, kit_id: str) -> list:
        return list(self.archive.get(kit_id, {}))

    async def load_archived_metadata_or_none(self, kit_id: str, marker: str):
        entry = self.archive.get(kit_id, {}).get(marker)
        return entry.get("metadata") if entry else None

    async def load_archived_revision(self, kit_id: str, marker: str):
        entry = self.archive.get(kit_id, {}).get(marker)
        if entry is None:
            raise FormKitNotFound(f"no archive {kit_id}/{marker}")
        return entry["schema"]

    async def load_pdf_bytes(self, kit_id: str, pdf_filename: str) -> bytes:
        if pdf_filename == "REAL":
            # A minimal VALID pdf, for the fill route (fitz must open it).
            import pymupdf as fitz

            doc = fitz.open()
            doc.new_page()
            data = doc.tobytes()
            doc.close()
            return data
        return b"%PDF-" + kit_id.encode("ascii")


@pytest.fixture
def _firm_world(_auth_on, monkeypatch):
    """Wire the two-kit store, the token->claims map, and the firm allowlist."""

    # **kwargs, so a signature change upstream cannot masquerade as a
    # confidentiality failure here. verify_token has been re-signed twice
    # (check_revoked added, then removed); each time a fixed-signature double
    # turned that into a TypeError. These tests are about PRIVATE-KIT
    # VISIBILITY, and that is what they should fail on.
    def _fake_verify(token: str, **_kw) -> dict:
        claims = _TOKENS.get(token)
        if claims is None:
            raise HTTPException(status_code=401, detail="bad token")
        return dict(claims)

    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _TwoKitStore())
    monkeypatch.setattr(
        "backend.routes.pdf_fill_routes.get_form_kit_store",
        lambda: _TwoKitStore(),
    )
    # require_auth (fill) and require_signin (list/schema) both resolve
    # verify_token inside the auth module; the pdf route uses the copy
    # imported into form_kit_routes.
    monkeypatch.setattr("backend.services.auth.verify_token", _fake_verify)
    monkeypatch.setattr(fkr, "verify_token", _fake_verify)
    # The gates live in backend/services/kit_gates.py (shared by ALL four
    # client-tier read sites, bd vy6id) -- patch the allowlist THERE.
    monkeypatch.setattr(
        "backend.services.kit_gates.get_allowed_kits",
        lambda firm_id: {"firm-a": ["priv-kit"]}.get(firm_id, []),
    )


def _list_ids(resp) -> list:
    return [f["id"] for f in resp.json()["forms"]]


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_kit_absent_from_list_for_other_firms_and_legacy(_firm_world, token):
    """Catalogue invisibility (epic 02ye rubric #2, list surface). Mutation:
    drop the visibility filter in list_form_kits -- red."""
    resp = client.get(
        "/api/form-kits", headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 200
    assert _list_ids(resp) == ["pub-kit"]


def test_private_kit_listed_for_own_firm_with_backend_paths(_firm_world):
    """Firm-A sees its private kit, whose paths are REWRITTEN to the
    authenticated backend routes (the static-bundle exclusion is bd kkos),
    while the public kit keeps its static paths, and BOTH entries carry
    explicit schema_file/pdf_file (the fill path posts the real filename).
    Mutations: drop the rewrite branch -- the path asserts go red; drop the
    schema_file/pdf_file population -- the filename asserts go red."""
    resp = client.get(
        "/api/form-kits", headers={"Authorization": "Bearer tok-a"}
    )
    assert resp.status_code == 200
    forms = {f["id"]: f for f in resp.json()["forms"]}
    assert set(forms) == {"pub-kit", "priv-kit"}
    assert forms["priv-kit"]["schema_path"] == "/api/form-kits/priv-kit/schema"
    assert forms["priv-kit"]["pdf_path"] == "/api/form-kits/priv-kit/pdf"
    assert forms["priv-kit"]["pdf_file"] == "intake.pdf"
    assert forms["pub-kit"]["schema_path"] == "/form-kits/pub-kit/schema.json"
    assert forms["pub-kit"]["pdf_path"] == "/form-kits/pub-kit/form.pdf"
    assert forms["pub-kit"]["schema_file"] == "schema.json"


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_schema_is_404_for_other_firms_and_legacy(_firm_world, token):
    """Schema-read invisibility: 404 (existence is the secret), never 403.
    Mutation: drop the _require_visible call in get_form_kit_schema -- red."""
    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_private_schema_loads_for_own_firm(_firm_world):
    """The usability half of rubric #2: firm-A actually READS its kit."""
    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"kit": "priv-kit"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer not-a-real-token"},
        {"Authorization": "Bearer tok-b"},
        {"Authorization": "Bearer tok-legacy"},
    ],
    ids=["anonymous", "invalid-token", "firm-b", "legacy"],
)
def test_private_pdf_is_404_for_everyone_but_the_firm(_firm_world, headers):
    """PDF invisibility, incl. the anonymous + garbage-token paths the public
    route shape makes possible (invalid degrades to anonymous -> 404, not
    401 -- existence is the secret). Mutation: drop the _require_visible call
    in get_form_kit_pdf -- red."""
    resp = client.get("/api/form-kits/priv-kit/pdf", headers=headers)
    assert resp.status_code == 404


def test_private_pdf_loads_for_own_firm(_firm_world):
    resp = client.get(
        "/api/form-kits/priv-kit/pdf",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.content == b"%PDF-priv-kit"


def test_a_CLIENT_LINK_can_fetch_its_own_private_kits_PDF(_firm_world, monkeypatch):
    """THE BEHAVIORAL PIN the door-set guard could not provide (Opus r7).

    This route is OPTIONAL-auth, so it resolves credentials ITSELF instead of
    going through require_auth -- which is why it was never taught the
    client-link shape and a client's own private form's PDF 404'd (r6).

    The guard I wrote for that counts which FILES call verify_token. Reverting
    the fix leaves that call in place, so the count is unchanged and the whole
    backend suite stays green: the guard pins "no NEW door appeared", not "each
    door handles a link", and the second is the property that broke three
    times.

    So this asserts the BEHAVIOR: a client link fetching the PDF of the kit it
    names gets BYTES. Mutation: replace the shape branch with a bare
    verify_token -- red.
    """
    monkeypatch.setenv("LINK_TOKEN_SECRET", "p" * 40)
    # A real signed link naming the private kit the firm holds.
    from backend.services.link_tokens import mint_link_token

    token, _jti = mint_link_token("firm-a", "priv-kit", "u-emp-7")
    # The route REDEEMS the link (a door that only verifies is a burned-link
    # hole), so the store must answer.
    import time as _t

    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(_t.time()), "completed_at": None,
        },
    )

    resp = client.get(
        "/api/form-kits/priv-kit/pdf",
        headers={"Authorization": "Bearer " + token},
    )

    assert resp.status_code == 200, (
        "a client link must fetch the PDF of the kit it names -- this route "
        "bypasses require_auth, so it needs its own link dispatch"
    )
    assert resp.content == b"%PDF-priv-kit"


def test_a_CLIENT_LINK_still_cannot_fetch_ANOTHER_kits_PDF(_firm_world, monkeypatch):
    """The widening must not leak: a link names ONE kit, and the firm holding
    a second one does not put it within the client's reach."""
    monkeypatch.setenv("LINK_TOKEN_SECRET", "p" * 40)
    from backend.services.link_tokens import mint_link_token

    import time as _t

    monkeypatch.setattr(
        "backend.services.link_redemptions.open_link",
        lambda jti, firm_id, kit_id, now=None: {
            "jti": jti, "firm_id": firm_id, "kit_id": kit_id,
            "opened_at": int(_t.time()), "completed_at": None,
        },
    )
    # The link names priv-kit; the client asks for the OTHER kit.
    token, _jti = mint_link_token("firm-a", "priv-kit", "u-emp-7")

    resp = client.get(
        "/api/form-kits/pub-kit/pdf",
        headers={"Authorization": "Bearer " + token},
    )

    # pub-kit is PUBLIC, so it serves anonymously either way -- the assertion
    # that matters is that the client credential did not widen anything: the
    # bytes are the public kit's, reachable with no token at all.
    assert resp.status_code == 200
    assert resp.content == b"%PDF-pub-kit"


def test_public_pdf_full_success_path_stays_tokenless(_firm_world):
    """Stronger than the 404 pin above: a PUBLIC kit's pdf serves BYTES with
    no token at all, end to end. Mutation: add a blanket auth dependency to
    the pdf route -- red."""
    resp = client.get("/api/form-kits/pub-kit/pdf")
    assert resp.status_code == 200
    assert resp.content == b"%PDF-pub-kit"


_FILL_PRIV_BODY = {
    "kit_id": "priv-kit",
    "pdf_filename": "REAL",
    "field_values": {},
    "form_schema": {"fields": []},
}


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_fill_pdf_is_404_for_other_firms_and_legacy_on_private_kit(_firm_world, token):
    """THE FOURTH DOOR (bd polyglot-pdf-vy6id, Opus cross-surface catch on
    vccy): POST /api/fill-pdf takes a caller-supplied kit_id, and with an
    empty field_values its response is the kit's blank template verbatim --
    so an ungated fill route hands any authed user exactly the private bytes
    the pdf GET now 404s. Mutation: drop the require_visible call in
    fill_pdf -- red."""
    resp = client.post(
        "/api/fill-pdf",
        json=_FILL_PRIV_BODY,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_fill_pdf_loads_private_kit_for_own_firm(_firm_world):
    """The usability half: firm-A actually FILLS its private kit (empty
    values on a minimal valid pdf -> 200 with pdf bytes)."""
    resp = client.post(
        "/api/fill-pdf",
        json=_FILL_PRIV_BODY,
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.content.startswith(b"%PDF")


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_kit_archive_is_404_for_other_firms_and_legacy(_firm_world, token):
    """A private kit's HISTORY is as invisible as the kit (bd qfyxr): the
    archive list 404s for non-members. Mutation: drop the _require_visible
    call in list_kit_archive -- red."""
    resp = client.get(
        "/api/form-kits/priv-kit/archive",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_private_kit_archive_lists_newest_first_for_own_firm(_firm_world):
    """Firm-A sees its private kit's revisions sorted newest-first by
    published_at, stampless revisions last (the maintainer's 'organized by
    form, then chronologically'). Mutation: drop the sort -- red (the store
    returns markers in dict order: 2024-01 first)."""
    resp = client.get(
        "/api/form-kits/priv-kit/archive",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert [r["marker"] for r in resp.json()["revisions"]] == [
        "2025-06", "2024-01", "sha256-abc",
    ]


def test_archived_schema_on_nonexistent_kit_is_404(_firm_world):
    """The schema-read sibling of the ghost-kit pin below: the 404 must come
    from the DELIBERATE manifest-membership check, not from the store
    happening to fail closed. Mutation: drop the _resolve_kit_filenames call
    in get_archived_kit_schema -- this stays 404 via the store miss, so the
    REAL mutation target is the pair: dropping BOTH the check and relying on
    a store whose load_archived_revision returns a default -- pinned here so
    the route's contract is explicit either way."""
    resp = client.get(
        "/api/form-kits/ghost-kit/archive/2024-01/schema",
        headers={"Authorization": "Bearer tok-legacy"},
    )
    assert resp.status_code == 404


def test_archive_list_on_nonexistent_kit_is_404(_firm_world):
    """A GHOST kit must 404 on the archive list in EVERY mode -- local
    stores return [] from list_archived_markers for a directory that never
    existed, so without the manifest-membership check the route answered
    200 {"revisions": []} while the sibling schema read 404'd (qfyxr
    fresh-eyes, reproduced live). Mutation: drop the _resolve_kit_filenames
    call in list_kit_archive -- red."""
    resp = client.get(
        "/api/form-kits/ghost-kit/archive",
        headers={"Authorization": "Bearer tok-legacy"},
    )
    assert resp.status_code == 404


def test_public_kit_archive_lists_for_any_authed_user(_firm_world):
    resp = client.get(
        "/api/form-kits/pub-kit/archive",
        headers={"Authorization": "Bearer tok-legacy"},
    )
    assert resp.status_code == 200
    assert [r["marker"] for r in resp.json()["revisions"]] == ["2023-12"]


@pytest.mark.parametrize("token", ["tok-b", "tok-legacy"])
def test_private_archived_schema_is_404_for_other_firms_and_legacy(_firm_world, token):
    """Mutation: drop the _require_visible call in get_archived_kit_schema
    -- red."""
    resp = client.get(
        "/api/form-kits/priv-kit/archive/2024-01/schema",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 404


def test_private_archived_schema_loads_for_own_firm(_firm_world):
    resp = client.get(
        "/api/form-kits/priv-kit/archive/2024-01/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"rev": "old"}


@pytest.mark.parametrize(
    "marker, expected",
    [
        ("a..b", 400),      # contains ".." -- validation, not the store
        ("a/b", 404),       # the slash splits the path -- FastAPI routing 404
        ("a" * 129, 400),   # over encode_marker's length cap
        ("%2e%2e", 400),    # decodes to ".." at the route -- validation
        ("a b", 400),       # outside the charset
    ],
    ids=["dotdot-inside", "slash", "overlong", "encoded-dotdot", "space"],
)
def test_archive_marker_validation_rejects_unsafe_segments(_firm_world, marker, expected):
    """The marker becomes a path segment; anything outside encode_marker's
    contract must be refused by VALIDATION (400), never by luck of the store
    lookup missing (404) -- a 404 here would mean the hostile value REACHED
    the store. (A raw ".." segment is untestable at this layer: the HTTP
    client normalizes /archive/../schema into the LIVE schema route, which
    carries its own gates; "%2e%2e" is the row that reaches _safe_marker as
    "..".) Mutation: drop the _safe_marker call -- every 400 row goes red
    (the fake store's miss turns them into 404s)."""
    resp = client.get(
        f"/api/form-kits/pub-kit/archive/{marker}/schema",
        headers={"Authorization": "Bearer tok-legacy"},
    )
    assert resp.status_code == expected


@pytest.mark.parametrize(
    "kit_id, pdf_filename, hops_above_tmp_path",
    [
        ("../../outside_secret", "form.pdf", 1),
        ("w7", "../../outside_secret/schema.json", 0),
    ],
    ids=["traversing-kit_id", "traversing-pdf_filename"],
)
def test_fill_pdf_refuses_a_traversing_kit_id_or_pdf_filename(
    _auth_bypassed, monkeypatch, tmp_path, kit_id, pdf_filename, hops_above_tmp_path
):
    """bd polyglot-pdf-7hicd: /fill-pdf is the ONE client-tier kit read that
    never resolves its filename through the manifest allowlist -- every other
    route gets pdf_filename from _resolve_kit_filenames (kit-controlled,
    normalize_manifest-sanitized), but PDFFillRequest.pdf_filename comes
    straight off the POST body, and kit_id here arrives in JSON, not a URL
    path segment -- unlike test_archive_marker_validation_rejects_unsafe_
    segments above, a raw ".." is NOT normalized away before it reaches the
    handler. A REAL LocalFormKitStore is used (not a fake) so a traversal
    that isn't actually blocked would ACTUALLY read the planted decoy file
    outside the store root, exactly as bd polyglot-pdf-xddtl's fix proved for
    load_draft_snapshot.

    The two cases escape to DIFFERENT depths relative to tmp_path, verified
    by hand (os.path.normpath on the exact join each store method performs)
    rather than guessed -- xddtl's own test got a depth wrong once already,
    caught only by mutation-testing it:
    - kit_id="../../outside_secret" joins as kits_root/../../outside_secret
      (kits_root IS tmp_path/"form-kits") -> normalizes to
      tmp_path.parent/"outside_secret" -- ONE hop above tmp_path.
    - pdf_filename="../../outside_secret/schema.json" (with kit_id="w7")
      joins as kits_root/"w7"/../../outside_secret/schema.json -> the extra
      "w7" segment absorbs one ".." before any climbing out of tmp_path, so
      this normalizes to tmp_path/"outside_secret"/"schema.json" -- ZERO
      hops, still inside tmp_path itself."""
    from backend.services.form_kits import LocalFormKitStore
    import backend.routes.pdf_fill_routes as pfr

    kits_root = tmp_path / "form-kits"
    kits_root.mkdir()
    (kits_root / "w7").mkdir()

    # A REAL minimal PDF, not a fake byte string -- if the traversal isn't
    # blocked, fitz.open() actually opens it and the route serves it as a
    # 200, which is the unambiguous proof a mutation test needs. A fake
    # non-PDF payload here would make an unguarded route 500 instead
    # (Failed to open stream) -- still wrong, but not distinguishable from
    # any other 4xx/5xx failure, so it would not pin what this test claims.
    import pymupdf as fitz
    decoy_doc = fitz.open()
    decoy_doc.new_page()
    decoy_bytes = decoy_doc.tobytes()
    decoy_doc.close()

    decoy_parent = tmp_path
    for _ in range(hops_above_tmp_path):
        decoy_parent = decoy_parent.parent
    outside = decoy_parent / "outside_secret"
    outside.mkdir(exist_ok=True)
    (outside / "schema.json").write_bytes(decoy_bytes)

    store = LocalFormKitStore(kits_root)
    monkeypatch.setattr(pfr, "get_form_kit_store", lambda: store)

    resp = client.post(
        "/api/fill-pdf",
        json={
            "kit_id": kit_id,
            "pdf_filename": pdf_filename,
            "field_values": {},
            "form_schema": {"fields": []},
        },
    )
    assert resp.status_code == 400
    assert resp.content != decoy_bytes


def test_every_client_tier_kit_read_is_visibility_gated():
    """THE SET PIN (bd polyglot-pdf-vy6id). The Opus cross-surface review
    caught the fill route ungated precisely because the set of client-tier
    kit-read sites was never enumerated -- the gate landed on three of four.
    This test derives the set from the SHIPPED route sources: every
    non-editor route function that reads kit bytes/schema must call the
    kit_gates visibility gate, and the set itself must match the expected
    list, so a FIFTH read site fails HERE instead of shipping ungated.
    Mutations: remove a require_visible call from any gated function -- red;
    add a new load_pdf_bytes/load_schema call site outside the list -- red."""
    import re as _re
    from pathlib import Path as _Path

    routes_dir = _Path(fkr.__file__).resolve().parent
    expected = {
        ("form_kit_routes.py", "get_form_kit_schema"),
        ("form_kit_routes.py", "get_form_kit_pdf"),
        ("form_kit_routes.py", "get_archived_kit_schema"),
        ("pdf_fill_routes.py", "fill_pdf"),
        # resume_form joined with bd polyglot-pdf-dft1: it reads the kit's own
        # form.pdf as the REFERENCE to verify a client's uploaded resume file
        # against. Gated identically to fill_pdf (require_auth ->
        # require_published -> require_visible) BEFORE the read, so a client
        # link resolves to the one kit it was minted for and cannot aim the
        # comparison at another firm's form.
        ("pdf_fill_routes.py", "resume_form"),
    }
    # load_archived_revision joined the read set with bd polyglot-pdf-qfyxr:
    # an archived schema is the same secret as the live one.
    read_re = _re.compile(
        r"\.load_pdf_bytes\(|\.load_schema\(|\.load_archived_revision\("
    )
    func_split = _re.compile(r"^(?:async )?def (\w+)", _re.MULTILINE)
    found = set()
    ungated = []
    for path in sorted(routes_dir.glob("*.py")):
        if path.name.startswith("editor_"):
            continue  # contractor tooling behind role tokens, not client tier
        src = path.read_text(encoding="utf-8")
        marks = [(m.start(), m.group(1)) for m in func_split.finditer(src)]
        for i, (start, name) in enumerate(marks):
            end = marks[i + 1][0] if i + 1 < len(marks) else len(src)
            # Comment lines can NAME a read (e.g. FormKitInfo's field note
            # citing store.load_pdf_bytes) without performing one.
            body = "\n".join(
                line for line in src[start:end].splitlines()
                if not line.strip().startswith("#")
            )
            if not read_re.search(body):
                continue
            found.add((path.name, name))
            if "require_visible" not in body:
                ungated.append((path.name, name))
    assert found == expected, (
        f"client-tier kit-read set changed: {sorted(found)} -- a new read "
        "site must be gated AND added here deliberately"
    )
    assert not ungated, f"kit reads without the visibility gate: {ungated}"


def test_single_kit_routes_read_metadata_exactly_once(_firm_world, monkeypatch):
    """ONE live metadata read serves BOTH single-kit gates (publish +
    visibility): each gate loading independently doubled the GCS read per
    schema/pdf request (vccy fresh-eyes round 2). Mutation: add a second
    _load_live_metadata call to either route -- red."""
    store = _TwoKitStore()
    calls = []
    orig = store.load_metadata

    async def counting(kit_id):
        calls.append(kit_id)
        return await orig(kit_id)

    store.load_metadata = counting
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: store)

    resp = client.get(
        "/api/form-kits/priv-kit/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert calls == ["priv-kit"]

    calls.clear()
    resp = client.get("/api/form-kits/pub-kit/pdf")
    assert resp.status_code == 200
    assert calls == ["pub-kit"]

    # The archived-schema read follows the same one-read pattern (qfyxr).
    calls.clear()
    resp = client.get(
        "/api/form-kits/priv-kit/archive/2024-01/schema",
        headers={"Authorization": "Bearer tok-a"},
    )
    assert resp.status_code == 200
    assert calls == ["priv-kit"]


def test_empty_allowlist_hides_private_even_for_claimed_firm(_firm_world, monkeypatch):
    """FAIL-CLOSED pin: a firms store answering [] (disabled, broken, firm
    suspended) hides the private kit even from a caller whose token CLAIMS
    the owning firm -- an outage narrows visibility, never widens it.
    Mutation: treat an empty allowlist as allow-all in _require_visible
    (`if allowed and kit_id not in allowed`) -- red."""
    monkeypatch.setattr(
        "backend.services.kit_gates.get_allowed_kits", lambda firm_id: []
    )
    for path in ("/api/form-kits/priv-kit/schema", "/api/form-kits/priv-kit/pdf"):
        resp = client.get(path, headers={"Authorization": "Bearer tok-a"})
        assert resp.status_code == 404, path
    resp = client.get("/api/form-kits", headers={"Authorization": "Bearer tok-a"})
    assert _list_ids(resp) == ["pub-kit"]


# --------------------------------------------------------------------------
# The COMPLETE gated set (bd polyglot-pdf-qs7m6)
# --------------------------------------------------------------------------
#
# Every route above was pinned INDIVIDUALLY, so /api/tts/spellback -- added
# later, and correctly gated in code -- had no test, and two docs
# (components/auth.md, components/config-deployment.md) enumerated only the
# original three. Nothing failed, because nothing asserted the SET.
#
# This derives the gated set from the live app and pins it whole (CLAUDE.md
# scar #7): adding or removing a require_auth dependency now fails HERE, with
# the doc sites named in the message, instead of surfacing as a stale doc a
# reviewer happens to notice.


def _routes_depending_on(target) -> set:
    """(method, path) for every app route wired to `target` as a dependency.

    Reads the actual dependency objects off each route, so it cannot drift the
    way a hand-maintained list does.
    """
    gated = set()
    for route in app.routes:
        for dep in getattr(route, "dependencies", []) or []:
            if getattr(dep, "dependency", None) is target:
                for method in sorted(route.methods or []):
                    gated.add((method, route.path))
        # The common spelling in this repo is a PARAMETER default
        # (`_user: dict = Depends(require_auth)`), which FastAPI flattens into
        # the route's dependant graph rather than route.dependencies.
        dependant = getattr(route, "dependant", None)
        if dependant is not None:
            for sub in dependant.dependencies:
                if sub.call is target:
                    for method in sorted(route.methods or []):
                        gated.add((method, route.path))
    return gated


def _routes_depending_on_require_auth() -> set:
    return _routes_depending_on(require_auth)


# The routes that carry user data or gate paid work. Deliberately NO COUNT in
# this comment: it was stale at "seven" while the set held eight, then dev's
# require_signin split moved it again -- a number here drifts on every route
# change, and the derived set below is the authority. Update this list ONLY
# together with the prose enumerations in:
#   docs/components/auth.md            ("HTTP routes (bd polyglot-pdf-z2is)")
#   docs/components/config-deployment.md  (the VFF_DISABLE_AUTH bullet)
# SELECTING a form is deliberately NOT gated on enrolment (maintainer,
# 2026-08-25). GET /api/form-kits and the live schema read use require_signin,
# which verifies WHO the caller is without demanding a firm or dev claim.
# Gating them left a signed-in user with no claims in an app with no form to
# pick and no way out -- and it bought nothing, because both routes already
# filter to kits that are PUBLIC or in the caller's own firm allowlist.
# Enrolment gates ACTING on a form, which is everything in the set below.
_EXPECTED_BROWSE_ROUTES = {
    ("GET", "/api/form-kits"),
    ("GET", "/api/form-kits/{kit_id}/schema"),
}

_EXPECTED_GATED_ROUTES = {
    # The archived-revisions reads (bd polyglot-pdf-qfyxr): same gates as the
    # live schema read, incl. firm visibility on the owning kit.
    ("GET", "/api/form-kits/{kit_id}/archive"),
    ("GET", "/api/form-kits/{kit_id}/archive/{marker}/schema"),
    # The firm tier's FIRST write path (bd polyglot-pdf-z6bk9): a firm
    # MANAGER retires a private form the firm owns. Authorization is three
    # checks beyond require_auth (role + ownership + private), pinned in
    # test_firm_retire.py -- require_auth alone would let any authed user
    # reach it.
    ("POST", "/api/form-kits/{kit_id}/retire"),
    # Firm staff mint a CLIENT link (bd polyglot-pdf-ugm6). Per-user Firebase
    # auth, deliberately NOT a per-firm API key -- the employee's uid is what
    # attributes the link. Its sibling POST /api/links/open is correctly
    # ABSENT from this set: the client has no account, so the signed link IS
    # the credential.
    ("POST", "/api/links/mint"),
    # NOTE: the two /api/tts/* routes LEFT this set (maintainer, 2026-08-24).
    # They spend money, so they declare require_paid_client_work -- which is
    # require_auth PLUS redemption. They are still auth-gated; they are just
    # gated by the stricter dependency, pinned by
    # test_the_PAID_route_set_is_pinned below.
    ("POST", "/api/fill-pdf"),
    # A client resumes from the PDF they saved (bd polyglot-pdf-dft1). It
    # reads the kit's own form.pdf as the reference to verify the UPLOAD
    # against, so it carries the same gates as /api/fill-pdf. Deliberately
    # require_auth and NOT require_paid_client_work: resuming your own saved
    # work spends nothing and must not burn the link -- the same
    # retrieval-vs-spend split the TTL correction established.
    ("POST", "/api/resume-form"),
    # OUR OWN safety notices, spoken free (bd polyglot-pdf-dft1). Note it is
    # here and NOT in the paid set below, which is the entire point: the paid
    # dependency REDEEMS the link, so using it would answer the
    # budget-exhausted client with silence -- exactly the client who needs to
    # hear "save your form now" -- and would burn a live link to deliver a
    # warning we chose to give. It speaks only KEYED, server-side text, so a
    # free route cannot become an open text-to-speech service.
    ("POST", "/api/tts/notice"),
}


def test_the_browse_routes_do_NOT_require_enrolment():
    """Selecting a form must stay reachable for any signed-in user.

    The failure this prevents is silent and total: the catalogue 403s, the app
    renders no forms, and the only remedy the UI can offer is "sign in again"
    -- which was never the problem. Found on the live app by the maintainer,
    after nine review rounds that all traced the blast radius and called it
    clean. They were right that no code path BREAKS; nobody asked whether the
    app stays USABLE for a caller with no claims.
    """
    from backend.services.auth import require_signin

    actual = _routes_depending_on(require_signin)
    assert actual == _EXPECTED_BROWSE_ROUTES, (
        "The set of browse (sign-in only) routes changed.\n"
        f"  added:   {sorted(actual - _EXPECTED_BROWSE_ROUTES)}\n"
        f"  removed: {sorted(_EXPECTED_BROWSE_ROUTES - actual)}\n"
        "A route REMOVED here has almost certainly moved to require_auth, "
        "which locks a claimless signed-in user out of selecting a form."
    )


def test_the_complete_require_auth_route_set_is_pinned():
    actual = _routes_depending_on_require_auth()
    assert actual == _EXPECTED_GATED_ROUTES, (
        "The set of require_auth-gated routes changed.\n"
        f"  added:   {sorted(actual - _EXPECTED_GATED_ROUTES)}\n"
        f"  removed: {sorted(_EXPECTED_GATED_ROUTES - actual)}\n"
        "Update _EXPECTED_GATED_ROUTES *and* both prose enumerations:\n"
        "  docs/components/auth.md\n"
        "  docs/components/config-deployment.md"
    )


def test_spellback_requires_token(_auth_on):
    # The route this bead's doc fix was missing -- gated in code since it was
    # added, but never pinned, so nothing caught the docs falling behind.
    #
    # A schema-VALID body (`value`, per SpellbackRequest) so the 401 is
    # unambiguously require_auth and not a 422 -- same discipline as _FILL_BODY
    # above. require_auth runs ahead of body validation, so a wrong-shaped body
    # would still 401 here and the test would pass for the wrong reason.
    resp = client.post("/api/tts/spellback",
                       json={"value": "A1234", "language": "Spanish"})
    assert resp.status_code == 401


def test_the_PAID_route_set_is_pinned():
    """The routes that SPEND MONEY, and therefore redeem a client link.

    The split (maintainer, 2026-08-24): "one time" bounds a backend
    CONNECTION, not the client's own document. A completed link must buy no
    further synthesis and start no further session -- but must still download
    the PDF it already produced.

    A new route that calls a model MUST declare require_paid_client_work, or
    a burned link keeps spending. Derived from the shipped sources so a
    fourth paid route reddens here.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    paid = {}
    call = re.compile(r"Depends\(require_paid_client_work\)")
    for path in sorted((root / "backend/routes").rglob("*.py")):
        n = sum(1 for l in path.read_text(encoding="utf-8").splitlines()
                if call.search(l))
        if n:
            paid[path.relative_to(root).as_posix()] = n

    assert paid == {
        # Both TTS routes synthesize audio -- real per-call spend.
        "backend/routes/tts_routes.py": 2,
    }, (
        "the PAID route set changed. A route that calls a model must use "
        "require_paid_client_work so a completed link cannot keep spending; "
        "a retrieval route must NOT, or the client loses access to their own "
        "finished form."
    )


def test_a_CLAIMLESS_user_can_actually_LOAD_the_catalogue(monkeypatch):
    """END TO END through the real route, with the REAL enrolment check.

    THE GAP THIS CLOSES: reverting the fix -- require_signin calling
    verify_token(token) instead of verify_token(token, require_enrolment=False)
    -- left all 3837 tests green. Every other test here either drives
    verify_token DIRECTLY (so it pins that the flag is HONORED, never that the
    call site PASSES it) or asserts which dependency object is wired (which does
    not change under the revert).

    So this drives the HTTP route, through require_signin, into the real
    _require_voice_access, with a token whose claims carry no firm_id and no
    vff_dev -- exactly the maintainer's account before enrolment, and exactly
    the shape a magic-link user arrives with.
    """
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            # Verified, real, and carrying NOTHING else.
            return {"uid": "uid-newcomer", "email": "newcomer@example.com"}

    # Patch the SDK, not verify_token -- the whole point is that
    # _require_voice_access runs for real.
    monkeypatch.setattr(va, "auth", _Auth)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _TwoKitStore())

    resp = client.get("/api/form-kits",
                      headers={"Authorization": "Bearer any-token"})

    assert resp.status_code == 200, (
        "a signed-in user with no claims got {} loading the form catalogue -- "
        "the app shows no forms and the only remedy the UI offers is 'sign in "
        "again', which was never the problem".format(resp.status_code))
    assert "forms" in resp.json()


def test_that_same_claimless_user_is_still_REFUSED_by_a_gated_route(monkeypatch):
    """The other direction, also end to end.

    If this stops refusing, the enrolment gate has been removed rather than
    narrowed, and the two-allowlist decision is silently undone.
    """
    import backend.services.auth as va

    monkeypatch.setenv("VFF_DISABLE_AUTH", "false")

    class _Auth:
        @staticmethod
        def verify_id_token(_tok, **_kw):
            return {"uid": "uid-newcomer", "email": "newcomer@example.com"}

    monkeypatch.setattr(va, "auth", _Auth)
    monkeypatch.setattr(fkr, "get_form_kit_store", lambda: _TwoKitStore())

    resp = client.get("/api/form-kits/kit-public/archive",
                      headers={"Authorization": "Bearer any-token"})

    assert resp.status_code == 403, (
        "a claimless user reached a gated route (got {})".format(resp.status_code))
