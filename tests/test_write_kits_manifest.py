"""scripts/write_kits_manifest.py -- the python port of deploy-all.sh's inline
manifest-generation loop (bd polyglot-pdf-ywxoh, Epic 4 bead 4.2).

Builds synthetic form-kits/ trees to pin the same selection rules the bash
loop has always applied: the complete-gate (bd b0pe), the `_`-prefix skip (bd
qwex), the custom-schema-filename resolution (bd snpi), and the label/PDF
precedence (bd 15ic) -- plus this script's own structural guarantee that the
manifest can never be invalid JSON (bd polyglot-pdf-4w0l is unreachable by
construction here, since the manifest is built as a dict and serialized with
json.dumps rather than assembled by string concatenation).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from write_kits_manifest import build_manifest, main  # noqa: E402


def _write_kit(root: Path, kit_id: str, metadata: dict | None = None,
                schema: dict | None = None, schema_filename: str = "schema.json",
                pdf_name: str | None = "form.pdf"):
    kit_dir = root / kit_id
    kit_dir.mkdir(parents=True, exist_ok=True)
    if metadata is not None:
        (kit_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    if schema is not None:
        (kit_dir / schema_filename).write_text(json.dumps(schema), encoding="utf-8")
    if pdf_name:
        (kit_dir / pdf_name).write_bytes(b"%PDF-1.4 fake")
    return kit_dir


def test_a_complete_kit_with_default_schema_is_included(tmp_path):
    _write_kit(tmp_path, "w7", metadata={"status": "complete", "label": "W-7"},
               schema={"title": "IRS W-7"})
    manifest = build_manifest(tmp_path, "form-kits")
    ids = [f["id"] for f in manifest["forms"]]
    assert ids == ["w7"]
    entry = manifest["forms"][0]
    assert entry["label"] == "W-7"
    assert entry["schemaFile"] == "schema.json"
    assert entry["schemaPath"] == "/form-kits/w7/schema.json"
    assert entry["pdfFile"] == "form.pdf"
    assert entry["pdfPath"] == "/form-kits/w7/form.pdf"


def test_a_draft_kit_is_excluded():
    """bd polyglot-pdf-b0pe: only status:complete kits ship."""
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _write_kit(root, "draft-kit", metadata={"status": "draft"},
                   schema={"title": "Draft"})
        manifest = build_manifest(root, "form-kits")
        assert manifest["forms"] == []


def test_a_kit_with_no_metadata_json_is_excluded(tmp_path):
    """Absent metadata.json means absent status -- not complete by default."""
    _write_kit(tmp_path, "no-meta", metadata=None, schema={"title": "X"})
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"] == []


def test_underscore_prefixed_directory_is_skipped_silently(tmp_path):
    """bd polyglot-pdf-qwex: shared authoring data (e.g. _translation/), not a kit."""
    _write_kit(tmp_path, "_translation", metadata={"status": "complete"},
               schema={"title": "not a kit"})
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"] == []


def test_missing_schema_file_excludes_the_kit(tmp_path):
    kit_dir = tmp_path / "no-schema"
    kit_dir.mkdir()
    (kit_dir / "metadata.json").write_text(
        json.dumps({"status": "complete"}), encoding="utf-8"
    )
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"] == []


def test_custom_schema_filename_from_metadata_is_honored(tmp_path):
    """bd polyglot-pdf-snpi: metadata.json's "schema" key overrides the default."""
    _write_kit(
        tmp_path, "custom", metadata={"status": "complete", "schema": "custom.json"},
        schema={"title": "Custom Kit"}, schema_filename="custom.json",
    )
    manifest = build_manifest(tmp_path, "form-kits")
    assert len(manifest["forms"]) == 1
    entry = manifest["forms"][0]
    assert entry["schemaFile"] == "custom.json"
    assert entry["schemaPath"] == "/form-kits/custom/custom.json"


def test_label_precedence_metadata_over_schema_title(tmp_path):
    """bd 15ic: metadata.json's label wins over the schema's title."""
    _write_kit(tmp_path, "k1", metadata={"status": "complete", "label": "Meta Label"},
               schema={"title": "Schema Title"})
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"][0]["label"] == "Meta Label"


def test_label_falls_back_to_schema_title_when_metadata_has_none(tmp_path):
    _write_kit(tmp_path, "k1", metadata={"status": "complete"},
               schema={"title": "Schema Title"})
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"][0]["label"] == "Schema Title"


def test_label_falls_back_to_kit_id_when_nothing_else_present(tmp_path):
    _write_kit(tmp_path, "k1", metadata={"status": "complete"}, schema={})
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"][0]["label"] == "k1"


def test_pdf_file_defaults_to_form_pdf_when_present(tmp_path):
    _write_kit(tmp_path, "k1", metadata={"status": "complete"}, schema={"title": "T"},
               pdf_name="form.pdf")
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"][0]["pdfFile"] == "form.pdf"


def test_pdf_file_falls_back_to_first_pdf_found(tmp_path):
    kit_dir = _write_kit(tmp_path, "k1", metadata={"status": "complete"},
                          schema={"title": "T"}, pdf_name=None)
    (kit_dir / "actual-form.pdf").write_bytes(b"%PDF fake")
    manifest = build_manifest(tmp_path, "form-kits")
    assert manifest["forms"][0]["pdfFile"] == "actual-form.pdf"
    assert manifest["forms"][0]["pdfPath"] == "/form-kits/k1/actual-form.pdf"


def test_nonexistent_form_kits_dir_produces_an_empty_manifest(tmp_path):
    manifest = build_manifest(tmp_path / "does-not-exist", "form-kits")
    assert manifest["forms"] == []
    assert "generatedAt" in manifest


def test_multiple_kits_all_included_and_sorted(tmp_path):
    _write_kit(tmp_path, "b-kit", metadata={"status": "complete"}, schema={"title": "B"})
    _write_kit(tmp_path, "a-kit", metadata={"status": "complete"}, schema={"title": "A"})
    manifest = build_manifest(tmp_path, "form-kits")
    ids = [f["id"] for f in manifest["forms"]]
    assert ids == ["a-kit", "b-kit"]


def test_manifest_is_always_valid_json_by_construction(tmp_path):
    """bd polyglot-pdf-4w0l: the bash version's failure mode (string-
    concatenated invalid JSON) cannot occur here -- json.dumps on a dict
    always produces valid JSON. This is a structural guarantee, not a
    behavior to mutate: there is no "make it invalid" code path to break."""
    _write_kit(tmp_path, "weird-kit", metadata={"status": "complete", "label": 'a "quoted" label'},
               schema={"title": "T"})
    manifest = build_manifest(tmp_path, "form-kits")
    # Round-trips cleanly even with quote characters in the label/id.
    dumped = json.dumps(manifest)
    reloaded = json.loads(dumped)
    assert reloaded == manifest


# ---------------------------------------------------------------------------
# The CLI entry point.
# ---------------------------------------------------------------------------


def test_cli_writes_a_manifest_file(tmp_path):
    _write_kit(tmp_path, "k1", metadata={"status": "complete"}, schema={"title": "T"})
    out = tmp_path / "index.json"
    rc = main(["--form-kits-dir", str(tmp_path), "--out", str(out), "--prefix", "form-kits"])
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert len(written["forms"]) == 1
    assert written["forms"][0]["id"] == "k1"


def test_cli_prefix_flows_into_the_paths(tmp_path):
    _write_kit(tmp_path, "k1", metadata={"status": "complete"}, schema={"title": "T"})
    out = tmp_path / "index.json"
    main(["--form-kits-dir", str(tmp_path), "--out", str(out), "--prefix", "custom-prefix"])
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["forms"][0]["schemaPath"] == "/custom-prefix/k1/schema.json"


def test_cli_refuses_a_missing_form_kits_dir(tmp_path, capsys):
    """(Not in the original handoff, caught by cross-surface review of bd
    polyglot-pdf-ywxoh.) build_manifest() itself is intentionally lenient on
    a missing directory (test_nonexistent_form_kits_dir_produces_an_empty_manifest
    above pins that as a library-level contract), but the CLI entry point --
    the thing cloudbuild.yaml's form-kits target and deploy-all.sh actually
    invoke -- must refuse outright rather than silently write an empty
    manifest that could overwrite the demo's real one (e.g. a Cloud Build
    tarball build, which .gcloudignore excludes form-kits/ from).
    """
    missing = tmp_path / "does-not-exist"
    out = tmp_path / "index.json"
    rc = main(["--form-kits-dir", str(missing), "--out", str(out), "--prefix", "form-kits"])
    assert rc != 0, "main() returned success for a nonexistent --form-kits-dir"
    assert not out.exists(), (
        "main() wrote an output file even though it refused the missing directory"
    )
    captured = capsys.readouterr()
    assert "ERROR" in captured.err, (
        f"no ERROR message on stderr for a missing --form-kits-dir; "
        f"stderr was: {captured.err!r}"
    )


def test_cli_refuses_an_existing_but_empty_directory_by_default(tmp_path, capsys):
    """An EXISTING but empty directory is now REFUSED unless --allow-empty.

    This reverses the earlier contract deliberately (bd polyglot-pdf-y0dzd).
    That contract read "an empty directory is a legitimate state (initial
    bring-up, or every kit still in draft), so emit a valid empty manifest" --
    true when written, and DANGEROUS since 2026-09-11, when the last form kit
    left git (bd polyglot-pdf-q3u5r). Every clean checkout now has an empty
    form-kits/, so the legitimate-but-rare case became the DEFAULT one, and
    uploading its empty manifest BLANKS the bucket catalogue while every kit
    blob survives untouched (index.json is authoritative -- form_kits.py
    refuses a convention fallback).

    The missing-dir guard does not cover this: the directory exists, it is
    simply empty.
    """
    empty_dir = tmp_path / "form-kits"
    empty_dir.mkdir()
    out = tmp_path / "index.json"
    rc = main(["--form-kits-dir", str(empty_dir), "--out", str(out), "--prefix", "form-kits"])
    assert rc != 0, "an empty manifest was written without --allow-empty"
    assert not out.exists(), (
        "main() wrote an output file even though it refused the empty manifest "
        "-- a leftover temp file is exactly what a deploy would then upload"
    )
    assert "ERROR" in capsys.readouterr().err


def test_cli_allows_an_empty_directory_when_explicitly_asked(tmp_path):
    """...and the legitimate case stays REACHABLE, just opt-in.

    A genuinely empty bucket (initial bring-up) is still serviceable; it now
    requires saying so, which is the difference between an intended empty
    catalogue and one produced by running the deploy from the wrong checkout.
    """
    empty_dir = tmp_path / "form-kits"
    empty_dir.mkdir()
    out = tmp_path / "index.json"
    rc = main([
        "--form-kits-dir", str(empty_dir), "--out", str(out),
        "--prefix", "form-kits", "--allow-empty",
    ])
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["forms"] == []
