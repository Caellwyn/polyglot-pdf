"""Every code site that touches a select option's identity channel, PINNED.

WHY THIS FILE EXISTS. bd polyglot-pdf-g2fpr moves a dropdown's PDF export code
out of option.value (where it printed verbatim) into option.pdf_on_value, so
option.value can be a slug like every other choice type. That is a schema-SHAPE
change, and the maintainer's mandate was: be certain nothing down the chain
breaks. Three read-only explorations enumerated every consumer; this test keeps
that enumeration honest.

THE RULE (same shape as test_deployed_iam_envelope.py): DERIVE the set from the
tree -- every shipped source file that mentions pdf_on_value -- and assert it
equals the reviewed list below, each entry carrying its verdict. A new file that
starts reading pdf_on_value without a verdict fails CI instead of a review
round. An entry that disappears (the file stopped touching the channel) also
fails, so the list cannot rot into fiction.

Static on purpose: no runtime, runs in CI on every change.
"""

from __future__ import annotations

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[3]

# Shipped source only. Tests, docs, journal, kits and vendored trees are out.
_SCAN_ROOTS = ("backend", "frontend/src", "schema-editor/src", "scripts")
_SUFFIXES = {".py", ".ts", ".tsx"}
_EXCLUDE_PARTS = {"node_modules", ".venv", "__pycache__", "tests", "test",
                  "dist", "build", ".claude"}


def _is_test_file(p: pathlib.Path) -> bool:
    n = p.name
    return (n.startswith("test_") or ".test." in n or n.endswith("_test.py")
            or n == "conftest.py")


def derived_readers() -> set[str]:
    out: set[str] = set()
    for root in _SCAN_ROOTS:
        base = _ROOT / root
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in _SUFFIXES:
                continue
            # RELATIVE parts: a worktree lives under .claude/worktrees/, so
            # matching the ABSOLUTE path's parts excluded every file and the
            # scan came back empty -- the floor below caught it (g2fpr.1).
            rel_parts = set(p.relative_to(_ROOT).parts)
            if _EXCLUDE_PARTS & rel_parts or _is_test_file(p):
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "pdf_on_value" in text:
                out.add(p.relative_to(_ROOT).as_posix())
    return out


# path -> verdict. Keep the verdict to one line: what the site does with the
# channel and which g2fpr bead (if any) changes it. This IS the review record.
REVIEWED: dict[str, str] = {
    "backend/models/conditional_vocabulary.py":
        "the v2 contract statement: value is a slug, identity in pdf_on_value",
    "backend/models/form_models.py":
        "FieldOption declares pdf_on_value (type-agnostic); _collect_v2_problems applies the slug rule to selects too since g2fpr.4 (the 4we6j exemption is gone; the remedy names the migration tool)",
    "backend/routes/editor_kit_routes.py":
        "widget-picker plumbing for shared-name radio kids; not a select reader",
    "backend/scripts/g1b_answer_key.py":
        "READER: option_label resolves a state picker through the option's pdf_on_value (the abbreviation), the hand-built table as fallback (bd bxjck, g2fpr.4)",
    "backend/routes/pdf_fill_routes.py":
        "READS it: radio shared-field kids; (g2fpr.1) resolve_select_fill_value on fill and resolve_select_resume_value on /resume-form, the inverse",
    "backend/services/manifest_service.py":
        "STRIPS it before the voice model sees options; the model speaks value only",
    "backend/services/schema_lint.py":
        "rules select-on-value-not-in-pdf / select-on-value-missing (g2fpr.1, collapsed in g2fpr.4: every dropdown choice carries a pdf_on_value the PDF declares; the 4we6j /Opt exemption in option-value-slug and the select-value-not-slug rule are retired)",
    "backend/services/schema_repair.py":
        "_mint_slugs CONVERTS a PDF-sanctioned code in a select value (code -> pdf_on_value, value minted with mint_select_slugs) since g2fpr.4; the alias tail registers pdf_on_value -> slug",
    "backend/services/widget_picker.py":
        "_claimed_widgets reads EVERY option's pdf_on_value type-agnostically, so since g2fpr.2 a select option enters the claimed set keyed (name, code) instead of (name, None); harmless because unclaimed_button_widgets filters candidates to _BUTTON_TYPES (comboboxes excluded) -- cross-surface, g2fpr.2",
    "frontend/src/pdf-view/valuePainting.ts":
        "paints pdf_on_value ?? raw for a select (g2fpr.1) -- mirrors the filler",
    "frontend/src/schema-forms/state/schemaFormState.ts":
        "READER (session restore): reconcileSelectValues maps a stored select value that matches no fresh option through the option whose pdf_on_value it equals (claimant = non-empty string value, the /resume-form predicate) or clears it; the stale-session guard, bd polyglot-pdf-f2a8k (g2fpr PR 3c)",
    "frontend/src/schema-forms/types/schema.ts":
        "FieldOption type declares pdf_on_value",
    "schema-editor/src/components/FieldEditor.tsx":
        "displays it on radio kids; the select export-code input WRITES it and the select mint reads it (g2fpr.2)",
    "schema-editor/src/types/schema.ts":
        "FieldOption type declares pdf_on_value",
    "schema-editor/src/utils/lintFindings.ts":
        "RULE_REMEDIES prose names pdf_on_value in the select-value-not-slug remedy; labels only, not a reader "
        "(this file joined the set when the remedy was reworded in g2fpr.1 round 2 -- the pin caught it)",
    "schema-editor/src/utils/fieldGrouping.ts":
        "grouping rules (pdf_on_value alone is not a checkbox_group) and mintSelectSlugs, which reserves codes already slug-shaped (g2fpr.2)",
    "schema-editor/src/utils/remoteKitStore.ts":
        "WidgetPicker on_value plumbing; not a select reader",
    "scripts/authoring/backfill_option_positions.py":
        "disambiguates multi-widget groups by pdf_on_value; not a select reader",
    "scripts/authoring/eval_extraction.py":
        "counts options lacking both pdf_field_name and pdf_on_value as unmapped",
    "scripts/authoring/extract_form.py":
        "reads it for radio positions; _backfill_dropdown_options WRITES {value: slug, pdf_on_value: code} for selects (g2fpr.2)",
    "scripts/bakeoff/group_candidates.py":
        "grouping heuristic over widget on-states; not a select reader",
    "scripts/bakeoff/roundtrip_fill.py":
        "the BAKEOFF filler: reads it for shared-field radios; a select is still filled with option[0].value, not pdf_on_value -- bd polyglot-pdf-zmxuw (sonnet), deliberately not folded into g2fpr.4",
    "scripts/bakeoff/schema_contract.py":
        "the extraction prompt: a select condition references the SLUG; the code lives in pdf_on_value (g2fpr.2)",
    "scripts/migrate_schema_v2.py":
        "already writes {value: slug, pdf_on_value: code} for selects built from the dump (c5r8) -- the channel the filler never read",
    "scripts/migrate_select_on_values.py":
        "the g2fpr.3 MIGRATION: writes pdf_on_value = old value and mints the slug via mint_select_slugs for every legacy select option; retargets conditions (bd polyglot-pdf-ub7om)",
}


def test_every_pdf_on_value_reader_has_a_verdict():
    derived = derived_readers()
    assert derived, "scan found nothing -- the roots or the exclusion set are wrong"
    missing = sorted(derived - set(REVIEWED))
    assert not missing, (
        "these shipped files now touch pdf_on_value but carry no verdict in "
        "REVIEWED -- read them against the g2fpr consumer matrix and add one: "
        f"{missing}"
    )


def test_no_verdict_describes_a_file_that_stopped_reading_the_channel():
    derived = derived_readers()
    stale = sorted(set(REVIEWED) - derived)
    assert not stale, (
        "these REVIEWED entries no longer touch pdf_on_value (moved, renamed, "
        f"or the read was removed) -- update the list: {stale}"
    )


def test_the_three_sites_this_bead_changed_carry_their_new_symbols():
    """The set test proves the FILES are accounted for; this proves the three
    g2fpr.1 changes are actually present in them, so a revert of one file
    cannot hide behind an unchanged file list."""
    fill = (_ROOT / "backend/routes/pdf_fill_routes.py").read_text(encoding="utf-8")
    lint = (_ROOT / "backend/services/schema_lint.py").read_text(encoding="utf-8")
    paint = (_ROOT / "frontend/src/pdf-view/valuePainting.ts").read_text(encoding="utf-8")
    assert "def resolve_select_fill_value(" in fill
    assert 'field_type == "select"' in fill
    for rule in ("select-value-not-slug", "select-on-value-not-in-pdf",
                 "select-on-value-missing"):
        assert rule in lint, rule
    assert "pdf_on_value" in paint and "case 'select'" in paint
