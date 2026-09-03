"""Fill invariants for the SHIPPED i-90 kit.

ORIGINALLY (bd polyglot-pdf-c5r8, P6.1b) this pinned that P6.1a's
migrate_schema_v2.py had not regressed the P0 baseline when it migrated the
132-field i-90 from v1 to v2. THAT MIGRATION IS HISTORY: the `i-90` kit id now
serves the applicant-only v2 schema (94 fields, a FRESH extraction -- not that
migration's output), and schema_archived.json is gone with the old kit. The
migration-specific assertions (the v1 archive, the 132-field count, the 28/110
baseline inventories) had no subject left and were retired 2026-09-02.

What SURVIVES is the part that was never really about the migration: the shipped
kit validates as v2 with no warnings, lints clean against its own acroform dump,
and round-trips 100% of both its choice and text fields. Those are properties of
whatever kit ships under this id, so they are asserted against the live
inventory rather than a frozen baseline number -- 100% is the invariant, the
counts are recorded for drift.

Imports roundtrip_fill by adding scripts/bakeoff to sys.path (repo precedent:
test_extract_form_lint.py). ASCII only.
"""
from __future__ import annotations

import json
import pathlib
import sys
import warnings

import pytest

_REPO = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "scripts" / "bakeoff"))

from backend.models.form_models import FormSchema  # noqa: E402
from backend.models import conditional_vocabulary as vocab  # noqa: E402
from backend.services.schema_lint import lint_schema, has_errors  # noqa: E402

_KIT = _REPO / "form-kits" / "i-90"
_SCHEMA = _KIT / "schema.json"
_PDF = _KIT / "form.pdf"

pytestmark = pytest.mark.skipif(not _SCHEMA.exists(), reason="i-90 kit not present")


def _schema():
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def _dump():
    import acroform_dump  # scripts/bakeoff on sys.path
    return acroform_dump.dump_pdf(str(_PDF))


def test_committed_i90_is_v2():
    assert str(_schema().get("schema_version")) == vocab.SCHEMA_VERSION_V2


def test_shipped_i90_validates_v2_and_lints_clean():
    schema = _schema()
    with warnings.catch_warnings():
        # Post the P6.2 flip (bd h76m.16) controls_fields is DELETED from the
        # model (not demoted), so the migrated i-90 validates with NO warning at
        # all -- promote any warning to an error to prove it.
        warnings.simplefilter("error")
        FormSchema.model_validate(schema)
    assert not has_errors(lint_schema(schema, _dump()))
    # Sanity floor only -- the applicant-only kit is 94 fields; the old
    # migrated one was 132. A kit that shrank to nearly nothing is a red flag,
    # an exact count here would just be churn.
    assert len(schema["fields"]) >= 90


def test_shipped_i90_roundtrip_fills_every_field():
    import roundtrip_fill  # scripts/bakeoff on sys.path
    result = roundtrip_fill.run(str(_SCHEMA), str(_PDF))
    # 100% fill on both is the load-bearing invariant and is kit-independent.
    assert result["choice_fill_success"]["pct"] == 100.0, result["choice_fill_success"]
    assert result["text_fill_success"]["pct"] == 100.0, result["text_fill_success"]
    # Inventories are pinned too (fresh-eyes on the original): a pct-only
    # assertion stays green if a future edit DROPS fields, as long as the
    # survivors fill. Measured on the applicant-only v2 kit 2026-09-02; the
    # pre-v2 kit was 28 choice / 110 text.
    assert result["choice_fill_success"]["attempted"] == 23
    assert result["text_fill_success"]["attempted"] == 75
