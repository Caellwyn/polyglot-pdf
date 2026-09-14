"""Build the form-kits manifest (index.json) that the voice app reads (bd
polyglot-pdf-ywxoh, Epic 4 bead 4.2 of docs/sprint_22_admin-console_plan.md).

THIS IS THE PYTHON PORT of deploy-all.sh's inline bash manifest-generation
loop (the "FORM KITS DEPLOYMENT" section's second loop, plus its
write_validated_manifest/find_manifest_python helpers). It exists so
cloudbuild.yaml's `form-kits` target can build the SAME manifest a bash
`deploy-all.sh --form-kits` run would, from ONE implementation instead of
restating the bash in YAML (which the build cannot execute directly anyway --
Cloud Build steps are containers, and this logic is far too much to inline as
a heredoc without losing the ability to unit-test it).

WHAT IT DOES NOT DO: upload anything. This script only WALKS form-kits/,
applies the same complete-gate (bd polyglot-pdf-b0pe: only kits explicitly
marked status:complete in metadata.json ship) and the same label/schema/pdf
resolution deploy-all.sh has always used, and writes the resulting manifest
JSON to an output path. The caller -- deploy-all.sh (still, via a thin call
here) or cloudbuild.yaml's form-kits target -- does the actual
`gcloud storage cp`, because upload is a deploy-time decision (which bucket,
which credentials) this script has no business making.

KIT SELECTION AND FIELD RESOLUTION MIRROR THE BASH EXACTLY (deploy-all.sh's
kit_is_complete / kit_schema_file / the manifest loop):
  - an `_`-prefixed top-level directory is shared authoring data, not a kit,
    and is skipped silently (bd polyglot-pdf-qwex);
  - a kit's schema filename comes from metadata.json's "schema" key when
    present, defaulting to schema.json (bd polyglot-pdf-snpi);
  - a kit missing its schema file, or not status:complete in metadata.json,
    is excluded from the manifest as well as from the upload (bd
    polyglot-pdf-b0pe);
  - label precedence is metadata.json's "label" -> the schema's "title" ->
    the kit id itself (bd 15ic, mirroring backend/services/form_kits.py);
  - the PDF file is "form.pdf" if present, else the first *.pdf found.

VALIDATION: the manifest is built as a python dict and serialized with
json.dumps -- there is no "invalid JSON" failure mode possible the way the
bash version's string concatenation had (bd polyglot-pdf-4w0l, which this
script's dict-based construction makes structurally impossible rather than
merely validated after the fact).

ASCII only.
"""

from __future__ import annotations

import argparse
import sys
import datetime
import json
import re
from pathlib import Path


def _kit_is_complete(kit_dir: Path) -> bool:
    """Only kits explicitly marked status:complete in metadata.json ship
    (bd polyglot-pdf-b0pe). A draft/unmarked kit stays local + git-backed."""
    meta = kit_dir / "metadata.json"
    if not meta.is_file():
        return False
    try:
        data = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return data.get("status") == "complete"


def _kit_schema_file(kit_dir: Path) -> str:
    """metadata.json's "schema" key, when present and non-empty, else the
    default schema.json (bd polyglot-pdf-snpi)."""
    meta = kit_dir / "metadata.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        schema = data.get("schema")
        if isinstance(schema, str) and schema.strip():
            return schema.strip()
    return "schema.json"


def _kit_label(kit_dir: Path, kit_id: str, schema_file: str) -> str:
    """metadata.json's "label" -> the schema's "title" -> the kit id (bd
    15ic, mirroring backend/services/form_kits.py's own precedence)."""
    meta = kit_dir / "metadata.json"
    if meta.is_file():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        label = data.get("label")
        if isinstance(label, str) and label.strip():
            return label.strip()

    schema_path = kit_dir / schema_file
    if schema_path.is_file():
        try:
            schema_data = json.loads(schema_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            schema_data = {}
        title = schema_data.get("title") if isinstance(schema_data, dict) else None
        if isinstance(title, str) and title.strip():
            return title.strip()

    return kit_id


def _kit_pdf_file(kit_dir: Path) -> str:
    """"form.pdf" if present, else the first *.pdf found, else the literal
    fallback "form.pdf" (matching the bash behavior when no PDF exists at
    all -- the manifest entry is still emitted; the upload step is what
    actually cares whether the file is there)."""
    if (kit_dir / "form.pdf").is_file():
        return "form.pdf"
    pdfs = sorted(kit_dir.glob("*.pdf"))
    if pdfs:
        return pdfs[0].name
    return "form.pdf"


def build_manifest(form_kits_dir: Path, prefix: str) -> dict:
    """The manifest dict for every complete, schema-bearing kit under
    `form_kits_dir`, in the same shape deploy-all.sh has always produced."""
    forms = []
    if form_kits_dir.is_dir():
        for kit_dir in sorted(form_kits_dir.iterdir()):
            if not kit_dir.is_dir():
                continue
            kit_id = kit_dir.name
            # An `_`-prefixed dir is shared authoring data, not a kit (e.g.
            # form-kits/_translation/) -- skip silently (bd polyglot-pdf-qwex).
            if kit_id.startswith("_"):
                continue

            schema_file = _kit_schema_file(kit_dir)
            if not (kit_dir / schema_file).is_file():
                continue
            if not _kit_is_complete(kit_dir):
                continue

            label = _kit_label(kit_dir, kit_id, schema_file)
            pdf_file = _kit_pdf_file(kit_dir)

            forms.append(
                {
                    "id": kit_id,
                    "label": label,
                    "schemaFile": schema_file,
                    "schemaPath": "/{}/{}/{}".format(prefix, kit_id, schema_file),
                    "pdfFile": pdf_file,
                    "pdfPath": "/{}/{}/{}".format(prefix, kit_id, pdf_file),
                }
            )

    return {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        ),
        "forms": forms,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--form-kits-dir",
        required=True,
        help="the form-kits/ directory to scan",
    )
    parser.add_argument(
        "--prefix",
        default="form-kits",
        help="the GCS prefix baked into each entry's schemaPath/pdfPath "
        "(default: form-kits, matching FORM_KITS_PREFIX's default)",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="where to write the manifest JSON (pretty-printed)",
    )
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help="permit a manifest with zero kits. Refused by default because "
        "uploading one BLANKS the bucket catalogue; pass this only for a "
        "genuinely empty bucket (initial setup) or a local dry run.",
    )
    args = parser.parse_args(argv)

    form_kits_dir = Path(args.form_kits_dir)
    # Refuse a MISSING directory outright rather than silently emitting a
    # valid, empty manifest (bd polyglot-pdf-ywxoh review round): a caller
    # that cannot see form-kits/ at all -- e.g. a Cloud Build tarball
    # source, which .gcloudignore excludes form-kits/ from -- is almost
    # always a wrong invocation, not "zero kits exist". An EXISTING but
    # empty/all-draft directory still produces forms: [] on purpose (a
    # legitimate state during initial setup, pinned by
    # tests/test_write_kits_manifest.py); only a directory that is not
    # there at all is refused. cloudbuild.yaml's form-kits target also
    # guards this earlier (require-connected-source-for-site-targets) --
    # this is the second, independent layer for any OTHER caller (a bare
    # python scripts/write_kits_manifest.py run from the wrong cwd, say).
    if not form_kits_dir.is_dir():
        print(
            "[write_kits_manifest] ERROR: --form-kits-dir "
            + str(form_kits_dir)
            + " does not exist -- refusing to write an empty manifest "
            "that could overwrite a real one. Check the working "
            "directory / --form-kits-dir value.",
            file=sys.stderr,
        )
        return 1

    manifest = build_manifest(form_kits_dir, args.prefix)

    # A PRESENT-but-empty directory is the dangerous case, and it became the
    # DEFAULT on 2026-09-11 when the last form kit left git (bd
    # polyglot-pdf-q3u5r): every clean checkout now has an empty form-kits/.
    # The missing-directory guard above does not cover it -- the directory
    # exists, it is simply empty -- so the manifest would be written, uploaded,
    # and would BLANK the bucket catalogue while every kit blob survived
    # untouched. index.json is authoritative (backend/services/form_kits.py
    # refuses a convention fallback), so the forms just vanish from the app.
    #
    # Zero kits stays REACHABLE for the genuinely-empty-bucket case the
    # original comment describes, but it is now opt-in rather than the silent
    # default (bd polyglot-pdf-y0dzd / 387h0).
    if not manifest["forms"] and not args.allow_empty:
        print(
            "[write_kits_manifest] ERROR: no kit under "
            + str(form_kits_dir)
            + " passed the complete-gate, so the manifest would be EMPTY -- "
            "refusing to write it. Uploading an empty manifest blanks the "
            "bucket's form list while leaving the kit blobs in place. Kits "
            "are bucket-canonical and NOT in git: pull them with "
            "scripts/pull-form-kits.sh, then re-run. Pass --allow-empty only "
            "if an empty catalogue is genuinely what you want.",
            file=sys.stderr,
        )
        return 1

    out_path = Path(args.out)
    out_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        "[write_kits_manifest] wrote {} kit(s) to {}".format(
            len(manifest["forms"]), out_path
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
