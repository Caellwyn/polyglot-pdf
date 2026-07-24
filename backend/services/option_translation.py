"""Runtime option-label translation (bd polyglot-pdf-ow1e).

Multiple-choice option labels reach the voice model in English only, and the
model translates them aloud on the fly -- which misfired live (English "Male or
Female" spoken in a Spanish session). This module pre-translates the labels so
the guidance the model reads is already in the session language; the option
VALUES are untouched, so tool-call matching (update_form_fields) is unaffected.

Precedence per label (maintainer 2026-07-16):
  1. kit-provided FieldOption.label_translations for the session language
     (bake_label_translations below -- bd polyglot-pdf-2h9j -- populates them
     at authoring time, making the secretary call a natural no-op on baked
     kits);
  2. else ONE batched secretary call (TextAIGemini.translate_labels, lite tier)
     over the remaining unique labels;
  3. else (failure/timeout) English fallback -- the DTI SI's translate-on-the-fly
     rule still covers that window.

Process-level cache keyed (form_id, language): concurrent sessions in the same
language await ONE in-flight task; later sessions hit the result instantly.
Failures (including the ~20s timeout) are NOT cached, so the next session
retries. ASCII only (CLAUDE.md scar #6) -- translated strings are runtime data.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import structlog

from backend.services.schema_lint import SEVERITY_WARNING, LintFinding
from backend.services.translation_lint import (
    glossary_prompt_context,
    load_glossary,
)
from backend.services.translation_verify import (
    VerifyFlag,
    verify_fresh_translations,
)

# The translator's own under-determined-source self-flag (bd polyglot-pdf-alry;
# the flag taxonomy's fourth kind -- usually fixed by enriching context or the
# glossary, not by editing the string).
FLAG_AMBIGUOUS = "translation-ambiguous-source"
from backend.utils.language_codes import bcp47_codes_for_spoken_language

_log = structlog.get_logger(__name__)

# Hard bound on one build (collection is instant; this bounds the secretary
# call). A build that blows it fails -- uncached -- and the session runs on
# English labels; the next session retries.
OPTION_TRANSLATION_TIMEOUT_S = 20.0

# (form_id, language-lowercase) -> the in-flight/completed build task. Module
# level on purpose: the translation of a form's labels into a language is
# process-global, not per-session (schema data only, no PII, stateless-backend
# invariant holds -- nothing about a USER is stored).
_build_tasks: Dict[Tuple[str, str], asyncio.Task] = {}


class OptionTranslationError(Exception):
    """The secretary translate call failed -- build fails, result is not cached."""


def _reset_cache_for_tests() -> None:
    _build_tasks.clear()


def _kit_translation_keys(language_name: str) -> List[str]:
    """The label_translations keys accepted for a session language, lowercase.

    CANONICAL key (settled by bd polyglot-pdf-2h9j): the lowercase spoken-
    language NAME ("spanish") -- what bake_label_translations writes. The read
    side stays tolerant for hand-authored kits: the plain name, the short code
    ("es") and the full BCP-47 code ("es-US") all resolve, case-insensitively.
    (Bare ISO-639-1 codes that differ from the BCP-47 stem -- "zh", "tl" -- do
    NOT resolve; the accepted short forms are the stems "cmn", "fil".)
    """
    keys = [language_name.strip().lower()]
    codes = bcp47_codes_for_spoken_language(language_name)
    if codes:
        full = codes[0].lower()
        keys.append(full)
        short = full.split("-")[0]
        if short != full:
            keys.append(short)
    return keys


def _kit_translation(label_translations: Any, keys: List[str]) -> Optional[str]:
    """Resolve a kit-provided translation from an option's label_translations
    dict against the accepted key candidates (case-insensitive). Returns None
    when the dict is absent/empty or carries no usable entry."""
    if not isinstance(label_translations, dict) or not label_translations:
        return None
    lowered = {
        str(k).strip().lower(): v
        for k, v in label_translations.items()
        if isinstance(v, str) and v.strip()
    }
    for key in keys:
        if key in lowered:
            return lowered[key]
    return None


def _collect_labels(
    full_schema: Optional[Dict[str, Any]], language_name: str
) -> Tuple[List[str], Dict[str, str]]:
    """Walk every option dict in the schema's flat fields[] array and return
    (unique_labels_in_order, kit_translations). Dedupes -- "Yes"/"No" repeat
    across the I-90's 294 options, so the unique set is far smaller."""
    keys = _kit_translation_keys(language_name)
    labels: List[str] = []
    seen: set = set()
    kit: Dict[str, str] = {}
    for field in (full_schema or {}).get("fields") or []:
        if not isinstance(field, dict):
            continue
        options = field.get("options") or field.get("allowed_values")
        for opt in options or []:
            if not isinstance(opt, dict):
                continue
            label = opt.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            if label not in seen:
                seen.add(label)
                labels.append(label)
            if label not in kit:
                translated = _kit_translation(opt.get("label_translations"), keys)
                if translated:
                    kit[label] = translated
    return labels, kit


def _collect_spoken_names(
    full_schema: Optional[Dict[str, Any]], language_name: str
) -> Tuple[List[str], Dict[str, str]]:
    """Field-level counterpart of _collect_labels (bd polyglot-pdf-tupu.1):
    walk the flat fields[] array and return (unique_spoken_names_in_order,
    kit_translations) from each field's spoken_name / spoken_name_translations.
    Falls back to field name when spoken_name is absent -- the SAME fallback
    get_field_guidance renders (manifest_service.py), so the bake covers
    exactly the strings the model would otherwise hear in English."""
    keys = _kit_translation_keys(language_name)
    names: List[str] = []
    seen: set = set()
    kit: Dict[str, str] = {}
    for field in (full_schema or {}).get("fields") or []:
        if not isinstance(field, dict):
            continue
        spoken = field.get("spoken_name") or field.get("name")
        if not isinstance(spoken, str) or not spoken.strip():
            continue
        if spoken not in seen:
            seen.add(spoken)
            names.append(spoken)
        if spoken not in kit:
            translated = _kit_translation(
                field.get("spoken_name_translations"), keys)
            if translated:
                kit[spoken] = translated
    return names, kit


def _iter_field_dicts(schema: Optional[Dict[str, Any]]):
    """Yield every field dict the spoken-name bake covers (flat fields[]),
    parity with _collect_spoken_names."""
    for field in (schema or {}).get("fields") or []:
        if isinstance(field, dict):
            yield field


def _iter_option_dicts(schema: Optional[Dict[str, Any]]):
    """Yield every option dict bake/collect traversal covers: the flat
    fields[] array's options / dict-shaped allowed_values. TableColumn.options
    are deliberately skipped -- parity with _collect_labels, whose output is
    what the runtime consumer renders."""
    for field in (schema or {}).get("fields") or []:
        if not isinstance(field, dict):
            continue
        options = field.get("options") or field.get("allowed_values")
        for opt in options or []:
            if isinstance(opt, dict):
                yield opt


async def bake_label_translations(
    schema: Optional[Dict[str, Any]],
    text_ai: Any,
    languages: Dict[str, str],
    *,
    only_missing: bool = True,
    concurrency: int = 4,
    verify: Optional[bool] = None,
    verify_lite_ai: Any = None,
    glossary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bake label_translations into a kit schema, in place (bd polyglot-pdf-2h9j).

    The authoring-time counterpart of build_option_label_overrides: for each
    language in `languages` ({lowercase-name: bcp47-code}, normally
    SPOKEN_LANGUAGE_BCP47 minus english), collect the unique option labels,
    batch-translate the ones the kit lacks (ONE translate_labels call per
    language), and fan the results out to every option carrying that label --
    written under the CANONICAL key, the lowercase language name. Option
    value / label / spoken_label are never touched.

    Idempotent when only_missing=True (the default): an option already covered
    under ANY accepted key form counts as covered and is not rewritten, so
    re-runs are no-ops and future language additions are cheap. A pre-existing
    translation of a duplicate label fans out to uncovered twins WITHOUT a
    model call. only_missing=False retranslates everything and overwrites the
    canonical key (the stale-after-rename remedy).

    Per-language failures (translate_labels -> None, or an adapter exception)
    skip that language and continue -- one flaky language must not cost the
    rest; the report's failed_languages drives the caller's exit code and an
    idempotent re-run fills the gap. Returns a JSON-ready report:
    {"changed": bool, "failed_languages": [...],
     "languages": {name: {labels, missing, translated, options_updated, failed}}}.

    VERIFY GATE (bd polyglot-pdf-9ikj, default-ON via
    TRANSLATION_VERIFY_ENABLED; `verify` overrides): freshly translated
    strings run through the verify/rectify loop
    (backend/services/translation_verify.py) BEFORE fan-out -- corrected
    values replace flagged ones only on a verified-clean re-judge; the keep
    rules and flip-flop detector are the V1-probe-decided ones. When the
    gate runs, the report additionally carries `flags` (a list of
    LintFinding dicts, ALL severity=WARNING -- flags never block publish)
    and per-language `verify` counts; a verify outage leaves every baked
    value byte-identical to the no-verify bake (fail-open) with
    verify.available=false. With verify disabled the report is
    byte-identical to the pre-gate shape.
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))
    report: Dict[str, Any] = {"changed": False, "failed_languages": [], "languages": {}}
    verify_enabled = verify
    if verify_enabled is None:
        from backend.config import get_settings
        verify_enabled = get_settings().TRANSLATION_VERIFY_ENABLED
    if glossary is None:
        # Loaded UNCONDITIONALLY (bd alry): the glossary injects into the
        # FORWARD translate_items prompt too, not just the verify loop.
        glossary = load_glossary()
    if verify_enabled and verify_lite_ai is None:
        verify_lite_ai = _build_verify_lite_ai()
    verify_flags: List[Tuple[str, VerifyFlag]] = []
    form_name = _form_name(schema)

    async def _bake_one(name: str, code: str) -> None:
        name = name.strip().lower()
        entry: Dict[str, Any] = {
            "labels": 0, "missing": 0, "translated": 0,
            "options_updated": 0, "failed": False,
            # Field spoken-name bake (bd polyglot-pdf-tupu.1) -- additive report
            # keys so existing CLI/route consumers of the label keys are
            # untouched.
            "spoken_names": 0, "names_missing": 0, "names_translated": 0,
            "fields_updated": 0,
            # Section-label bake (bd polyglot-pdf-tupu.2): kit coverage keeps
            # session start call-free (the greeting's bounded await depends
            # on it).
            "section_labels": 0, "sections_missing": 0,
            "sections_translated": 0, "sections_updated": 0,
        }
        report["languages"][name] = entry
        if name == "english":  # labels are already English; nothing to bake
            return
        keys = _kit_translation_keys(name)
        labels, existing = _collect_labels(schema, name)
        entry["labels"] = len(labels)
        # Field spoken names ride the SAME batched call as the option labels
        # (bd tupu.1): both are plain strings; the union preserves the
        # one-translate-call-per-language invariant the bake tests pin.
        spoken_names, existing_names = _collect_spoken_names(schema, name)
        entry["spoken_names"] = len(spoken_names)
        section_labels, existing_sections = _collect_section_labels(schema, name)
        entry["section_labels"] = len(section_labels)
        if not labels and not spoken_names and not section_labels:
            return
        missing = labels if not only_missing else [
            label for label in labels if label not in existing
        ]
        entry["missing"] = len(missing)
        names_missing = spoken_names if not only_missing else [
            n for n in spoken_names if n not in existing_names
        ]
        entry["names_missing"] = len(names_missing)
        sections_missing = section_labels if not only_missing else [
            s for s in section_labels if s not in existing_sections
        ]
        entry["sections_missing"] = len(sections_missing)
        overrides = dict(existing)
        name_overrides = dict(existing_names)
        section_overrides = dict(existing_sections)
        # Union of the string sets, deduped, labels first (a string appearing
        # in several classes translates once and serves all of them).
        union_missing = list(dict.fromkeys(
            [*missing, *names_missing, *sections_missing]))
        if union_missing:
            # Context-carrying forward path (bd alry, plan Part A.1): ONE
            # translate_items call per language -- kinds, form name, parent
            # questions, and option sets as units, glossary injected.
            payload_items = _build_context_items(
                schema, missing, names_missing, sections_missing)
            try:
                async with semaphore:
                    raw = await text_ai.translate_items(
                        payload_items, name.capitalize(), code,
                        form_name=form_name,
                        glossary_context=glossary_prompt_context(
                            glossary, name),
                    )
            except Exception as exc:  # noqa: BLE001 -- skip-and-report by design
                _log.warning(
                    "option_translation_bake_language_failed",
                    language=name, exc_type=type(exc).__name__,
                )
                raw = None
            translated, ambiguous_sources = _flatten_items_result(
                payload_items, raw)
            # Ambiguous self-flags ride the same report channel as verify
            # flags (kind resolved by membership; a source in several kinds
            # flags each).
            for source in set(ambiguous_sources):
                if source in set(missing):
                    verify_flags.append((name, VerifyFlag(
                        taxonomy=FLAG_AMBIGUOUS, kind="option-label",
                        source=source,
                        message="translator self-flagged the source as "
                                "under-determined; enrich context/glossary "
                                "rather than editing the string")))
                if source in set(names_missing):
                    verify_flags.append((name, VerifyFlag(
                        taxonomy=FLAG_AMBIGUOUS, kind="field-name",
                        source=source,
                        message="translator self-flagged the source as "
                                "under-determined; enrich context/glossary "
                                "rather than editing the string")))
                if source in set(sections_missing):
                    verify_flags.append((name, VerifyFlag(
                        taxonomy=FLAG_AMBIGUOUS, kind="section-title",
                        source=source,
                        message="translator self-flagged the source as "
                                "under-determined; enrich context/glossary "
                                "rather than editing the string")))
            if translated is None:
                entry["failed"] = True
                report["failed_languages"].append(name)
                # Existing kit entries can still fan out to uncovered twins.
                translated = {}
            missing_set = set(missing)
            names_missing_set = set(names_missing)
            fresh = {
                k: v for k, v in translated.items()
                if k in missing_set and isinstance(v, str) and v.strip()
            }
            entry["translated"] = len(fresh)
            overrides.update(fresh)
            fresh_names = {
                k: v for k, v in translated.items()
                if k in names_missing_set and isinstance(v, str) and v.strip()
            }
            entry["names_translated"] = len(fresh_names)
            name_overrides.update(fresh_names)
            sections_missing_set = set(sections_missing)
            fresh_sections = {
                k: v for k, v in translated.items()
                if k in sections_missing_set and isinstance(v, str) and v.strip()
            }
            entry["sections_translated"] = len(fresh_sections)
            section_overrides.update(fresh_sections)
            # VERIFY GATE (bd 9ikj): freshly translated strings only --
            # already-covered kit strings are not re-verified, so idempotent
            # re-runs stay call-free. Corrections land in the override maps
            # BEFORE fan-out; a verify outage changes nothing (fail-open).
            if verify_enabled and (fresh or fresh_names or fresh_sections):
                # Deliberately OUTSIDE the semaphore (fresh-eyes finding on
                # this bead): the verify loop makes several SEQUENTIAL model
                # calls per language, and holding a translate-concurrency
                # slot across all of them starves other languages' translate
                # calls. Verify concurrency is naturally bounded by the
                # language count, and each language's loop is serial inside.
                try:
                    result = await verify_fresh_translations(
                        language_name=name,
                        language_code=code,
                        fresh={
                            "option-label": fresh,
                            "field-name": fresh_names,
                            "section-title": fresh_sections,
                        },
                        pro_ai=text_ai,
                        lite_ai=verify_lite_ai,
                        glossary=glossary,
                    )
                except Exception as exc:  # noqa: BLE001 -- fail-open
                    _log.warning(
                        "option_translation_verify_failed",
                        language=name, exc_type=type(exc).__name__,
                    )
                    entry["verify"] = {"available": False}
                else:
                    entry["verify"] = {
                        "available": result.available, **result.counts}
                    overrides.update(result.final.get("option-label", {}))
                    name_overrides.update(
                        result.final.get("field-name", {}))
                    section_overrides.update(
                        result.final.get("section-title", {}))
                    verify_flags.extend(
                        (name, flag) for flag in result.flags)
        # Fan spoken-name translations out to the fields (canonical lowercase-
        # name key; only_missing semantics identical to the option path).
        for field in _iter_field_dicts(schema):
            spoken = field.get("spoken_name") or field.get("name")
            if not isinstance(spoken, str) or not spoken.strip():
                continue
            value = name_overrides.get(spoken)
            if not value:
                continue
            if only_missing and _kit_translation(
                    field.get("spoken_name_translations"), keys):
                continue  # covered under an accepted key -- no rewrite
            translations = field.get("spoken_name_translations")
            if not isinstance(translations, dict):
                translations = {}
                field["spoken_name_translations"] = translations
            if translations.get(name) == value:
                continue
            translations[name] = value
            entry["fields_updated"] += 1
            report["changed"] = True
        # Fan section-label translations out to the sections (same semantics).
        for section in _iter_section_dicts(schema):
            label = section.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            value = section_overrides.get(label)
            if not value:
                continue
            if only_missing and _kit_translation(
                    section.get("label_translations"), keys):
                continue
            translations = section.get("label_translations")
            if not isinstance(translations, dict):
                translations = {}
                section["label_translations"] = translations
            if translations.get(name) == value:
                continue
            translations[name] = value
            entry["sections_updated"] += 1
            report["changed"] = True
        for opt in _iter_option_dicts(schema):
            label = opt.get("label")
            if not isinstance(label, str) or not label.strip():
                continue
            value = overrides.get(label)
            if not value:
                continue
            if only_missing and _kit_translation(opt.get("label_translations"), keys):
                continue  # covered under an accepted key -- no rewrite, minimal diff
            translations = opt.get("label_translations")
            if not isinstance(translations, dict):
                translations = {}
                opt["label_translations"] = translations
            if translations.get(name) == value:
                continue
            translations[name] = value
            entry["options_updated"] += 1
            report["changed"] = True

    await asyncio.gather(*(
        _bake_one(name, code) for name, code in languages.items()
    ))
    report["failed_languages"].sort()
    if verify_enabled or verify_flags:
        # (verify_flags may carry translator ambiguous-source flags even
        # with the verify loop off -- they come from the forward call.)
        # Resolve each flag's SOURCE string to its kit path(s) post-fan-out
        # (one WARNING finding per location, parent-carrying so
        # schema_lint.field_id_of derives a clickable field id). The flags
        # key exists whenever the gate ran -- presence == verify ran.
        findings: List[Dict[str, Any]] = []
        for language, flag in verify_flags:
            paths = _resolve_flag_paths(
                schema, flag.kind, flag.source, language)
            for path in paths or ["(unresolved path) %s" % flag.source]:
                findings.append(LintFinding(
                    severity=SEVERITY_WARNING,
                    rule=flag.taxonomy,
                    path=path,
                    message=flag.message,
                ).as_dict())
        report["flags"] = findings
    return report


def _build_verify_lite_ai() -> Any:
    """The verify loop's independent LITE back-translation adapter.
    Lazy import: the adapter module must not become an option_translation
    import-time dependency (test stubs replace this via the
    verify_lite_ai param)."""
    from backend.adapters.text_ai_gemini import TextAIGemini
    from backend.config import get_settings

    settings = get_settings()
    # The DEFAULT fallback chain is kept ON PURPOSE (unlike the pro-tier
    # authoring constructions, which pass fallback_models=() to fail loud):
    # this leg is deliberately LITE, and a within-lite-tier fallback on a
    # transient outage is harmless -- failing it instead would cost the
    # whole verify pass (fail-open) for nothing.
    return TextAIGemini(
        api_key=settings.GEMINI_API_KEY,
        model=settings.TRANSLATION_VERIFY_BT_MODEL,
        vertexai=settings.VERTEXAI,
    )


def _resolve_flag_paths(
    schema: Optional[Dict[str, Any]],
    kind: str,
    source: str,
    language: str,
) -> List[str]:
    """Every kit location a verified source string fans out to, in the
    exact shape schema_lint.field_id_of parses for field-level paths
    (sections carry no (id=...) -- nothing to focus)."""
    paths: List[str] = []
    if kind == "section-title":
        for section in (schema or {}).get("sections") or []:
            if isinstance(section, dict) and section.get("label") == source:
                paths.append("sections[%s].label_translations.%s"
                             % (section.get("id"), language))
        return paths
    for index, field in enumerate((schema or {}).get("fields") or []):
        if not isinstance(field, dict):
            continue
        field_ref = "fields[%d] (id=%s)" % (index, field.get("id"))
        if kind == "field-name":
            spoken = field.get("spoken_name") or field.get("name")
            if spoken == source:
                paths.append("%s.spoken_name_translations.%s"
                             % (field_ref, language))
        elif kind == "option-label":
            options = field.get("options") or field.get("allowed_values")
            for opt in options or []:
                if isinstance(opt, dict) and opt.get("label") == source:
                    paths.append(
                        "%s.options[%s].label_translations.%s"
                        % (field_ref, opt.get("value"), language))
    return paths


def _collect_section_labels(
    full_schema: Optional[Dict[str, Any]], language_name: str
) -> Tuple[List[str], Dict[str, str]]:
    """Unique section labels in order + kit translations from each section's
    label_translations (bd polyglot-pdf-tupu.2 -- closes the zmlo residual
    where a greeting read a section title in English). Kit coverage matters
    here for LATENCY, not just cost: an uncovered section label forces a live
    translate call at session start, which outruns the greeting's bounded
    await and leaves the first turn English."""
    keys = _kit_translation_keys(language_name)
    labels: List[str] = []
    seen: set = set()
    kit: Dict[str, str] = {}
    for section in (full_schema or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = section.get("label")
        if not isinstance(label, str) or not label.strip():
            continue
        if label not in seen:
            seen.add(label)
            labels.append(label)
        if label not in kit:
            translated = _kit_translation(section.get("label_translations"), keys)
            if translated:
                kit[label] = translated
    return labels, kit


def _iter_section_dicts(schema: Optional[Dict[str, Any]]):
    """Yield every section dict the section-label bake covers."""
    for section in (schema or {}).get("sections") or []:
        if isinstance(section, dict):
            yield section


def _form_name(schema: Optional[Dict[str, Any]]) -> Optional[str]:
    """Human form reference for the translate_items context payload, from
    form_metadata the kit already carries."""
    meta = (schema or {}).get("form_metadata")
    if not isinstance(meta, dict):
        return None
    title = meta.get("title")
    number = meta.get("form_number")
    if isinstance(title, str) and title.strip():
        if isinstance(number, str) and number.strip():
            return "%s (Form %s)" % (title.strip(), number.strip())
        return title.strip()
    if isinstance(number, str) and number.strip():
        return "Form %s" % number.strip()
    return None


def _build_context_items(
    schema: Optional[Dict[str, Any]],
    missing_labels: List[str],
    missing_names: List[str],
    missing_sections: List[str],
) -> List[Dict[str, Any]]:
    """The structured translate_items payload, built from data the schema
    already holds (bd polyglot-pdf-alry, plan Part A.1): field names and
    section titles as single items; option labels grouped into their SETS
    (with the field's spoken name as parent_question) so the choices
    translate as a coherent, mutually distinguishable group. Sets dedupe by
    their ordered label tuple (identical Yes/No sets translate once); a set
    is included whenever ANY of its labels is missing -- the whole set goes
    into the payload for context, and the caller's membership filtering
    keeps kit precedence intact for the covered labels."""
    items: List[Dict[str, Any]] = []
    for index, text in enumerate(missing_names):
        items.append({"id": "fn:%d" % index, "kind": "field-name",
                      "text": text})
    for index, text in enumerate(missing_sections):
        items.append({"id": "st:%d" % index, "kind": "section-title",
                      "text": text})
    missing_set = set(missing_labels)
    seen_sets: set = set()
    set_index = 0
    for field in (schema or {}).get("fields") or []:
        if not isinstance(field, dict):
            continue
        options = field.get("options") or field.get("allowed_values")
        labels = [
            opt.get("label") for opt in options or []
            if isinstance(opt, dict) and isinstance(opt.get("label"), str)
            and opt.get("label").strip()
        ]
        if not labels or not (set(labels) & missing_set):
            continue
        key = tuple(labels)
        if key in seen_sets:
            continue
        seen_sets.add(key)
        entry: Dict[str, Any] = {
            "id": "os:%d" % set_index, "kind": "option-set",
            "options": labels,
        }
        parent = field.get("spoken_name") or field.get("name")
        if isinstance(parent, str) and parent.strip():
            entry["parent_question"] = parent
        items.append(entry)
        set_index += 1
    return items


def _flatten_items_result(
    payload_items: List[Dict[str, Any]],
    raw: Optional[Dict[str, Any]],
) -> Tuple[Optional[Dict[str, str]], List[str]]:
    """(flat {source: translation}, ambiguous source strings) from a
    translate_items result. None raw (the adapter's fail-open signal)
    passes through as (None, []). A string that is both an option label
    and a field name translates once per kind; the field-name rendering
    wins in the flat map (applied last) -- both kinds' consumers filter by
    their own membership sets, so kit precedence is unaffected."""
    if raw is None:
        return None, []
    by_id = {item["id"]: item for item in payload_items}
    flat: Dict[str, str] = {}
    results = raw.get("items") if isinstance(raw, dict) else None
    results = results if isinstance(results, dict) else {}
    for item_id, value in results.items():
        request = by_id.get(item_id)
        if request is None or not isinstance(value, dict):
            continue
        if request["kind"] == "option-set":
            for source, translated in (value.get("options") or {}).items():
                if isinstance(source, str) and isinstance(translated, str) \
                        and translated.strip():
                    flat[source] = translated.strip()
    for item_id, value in results.items():
        request = by_id.get(item_id)
        if request is None or not isinstance(value, dict):
            continue
        if request["kind"] != "option-set":
            translated = value.get("translation")
            if isinstance(translated, str) and translated.strip():
                flat[request["text"]] = translated.strip()
    ambiguous_sources: List[str] = []
    raw_ambiguous = raw.get("ambiguous") if isinstance(raw, dict) else None
    for item_id in raw_ambiguous or []:
        request = by_id.get(item_id) if isinstance(item_id, str) else None
        if request is None:
            continue
        if request["kind"] == "option-set":
            ambiguous_sources.extend(request["options"])
        else:
            ambiguous_sources.append(request["text"])
    return flat, ambiguous_sources


@dataclass(frozen=True)
class TranslationOverrides:
    """The session-language translation maps, all keyed by ENGLISH source
    string (bd polyglot-pdf-tupu.2). One shared cached build produces all
    three; consumers fail open to the English string on any missing key."""
    option_labels: Dict[str, str]
    spoken_names: Dict[str, str]
    section_labels: Dict[str, str]

    def __bool__(self) -> bool:
        return bool(self.option_labels or self.spoken_names
                    or self.section_labels)


EMPTY_OVERRIDES = TranslationOverrides({}, {}, {})


async def build_translation_overrides(
    full_schema: Optional[Dict[str, Any]],
    language_name: str,
    text_ai: Any,
) -> TranslationOverrides:
    """Build the session-language TranslationOverrides (bd tupu.2; supersedes
    the label-only build_option_label_overrides, the named ow1e contract
    change).

    Kit translations win (option label_translations + field
    spoken_name_translations); the remainder -- including section labels,
    which have no kit structure -- goes through ONE batched translate_labels
    call over the deduped union. Raises OptionTranslationError when that call
    fails, so the cache layer does not keep a failed build.
    """
    labels, label_overrides = _collect_labels(full_schema, language_name)
    spoken_names, name_overrides = _collect_spoken_names(
        full_schema, language_name)
    section_labels, section_overrides = _collect_section_labels(
        full_schema, language_name)
    if not labels and not spoken_names and not section_labels:
        return EMPTY_OVERRIDES

    remaining_labels = [s for s in labels if s not in label_overrides]
    remaining_names = [s for s in spoken_names if s not in name_overrides]
    remaining_sections = [s for s in section_labels
                          if s not in section_overrides]
    union = list(dict.fromkeys(
        [*remaining_labels, *remaining_names, *remaining_sections]))
    if union:
        codes = bcp47_codes_for_spoken_language(language_name)
        language_code = codes[0] if codes else ""
        # The SAME context-carrying call the bake makes (bd alry, plan A.5:
        # the runtime path is unified, not silently diverged) -- the full
        # schema is in hand, so the context payload is free. HONEST
        # RESIDUAL, stated not hidden: runtime translations remain
        # UNVERIFIED (no judge loop at session start -- the bounded
        # greeting await cannot absorb a judge round-trip); after the V5
        # re-bake this path fires only for new/edited kits pre-bake.
        payload_items = _build_context_items(
            full_schema, remaining_labels, remaining_names,
            remaining_sections)
        raw = await text_ai.translate_items(
            payload_items, language_name, language_code,
            form_name=_form_name(full_schema),
            glossary_context=glossary_prompt_context(
                load_glossary(), language_name),
        )
        if raw is None:
            raise OptionTranslationError("translate_items failed")
        translated, _ambiguous = _flatten_items_result(payload_items, raw)
        # Kit precedence is absolute: only strings actually sent to the
        # secretary may land, so a stray response entry can never overwrite a
        # kit-provided translation. Membership splits the union back into its
        # three maps (a shared string legitimately lands in several).
        clean = {k: v for k, v in translated.items()
                 if isinstance(v, str) and v.strip()}
        label_set = set(remaining_labels)
        name_set = set(remaining_names)
        section_set = set(remaining_sections)
        label_overrides.update(
            {k: v for k, v in clean.items() if k in label_set})
        name_overrides.update(
            {k: v for k, v in clean.items() if k in name_set})
        section_overrides.update(
            {k: v for k, v in clean.items() if k in section_set})
    return TranslationOverrides(
        option_labels=label_overrides,
        spoken_names=name_overrides,
        section_labels=section_overrides,
    )


async def _build_bounded(
    full_schema: Optional[Dict[str, Any]], language_name: str, text_ai: Any
) -> TranslationOverrides:
    return await asyncio.wait_for(
        build_translation_overrides(full_schema, language_name, text_ai),
        timeout=OPTION_TRANSLATION_TIMEOUT_S,
    )


async def get_translation_overrides(
    form_id: str,
    full_schema: Optional[Dict[str, Any]],
    language_name: str,
    text_ai: Any,
) -> TranslationOverrides:
    """Cached entry point: one build per (form, language) per process.

    Concurrent callers share the in-flight task (shielded, so one session's
    teardown never cancels the shared build). On build failure -- secretary
    error or the 20s timeout -- returns EMPTY_OVERRIDES and DROPS the cache
    entry so the next session retries. Never raises (except CancelledError
    propagation for the awaiting session's own teardown).
    """
    key = (str(form_id), (language_name or "").strip().lower())
    task = _build_tasks.get(key)
    if task is None:
        task = asyncio.create_task(
            _build_bounded(full_schema, language_name, text_ai)
        )
        _build_tasks[key] = task
    try:
        result = await asyncio.shield(task)
    except asyncio.CancelledError:
        if not task.cancelled():
            # WE were cancelled (session teardown); the shared build keeps
            # running for other sessions -- leave it cached and propagate.
            raise
        _build_tasks.pop(key, None)
        return EMPTY_OVERRIDES
    except Exception as exc:  # noqa: BLE001 -- fail-open by design
        if _build_tasks.get(key) is task:
            _build_tasks.pop(key, None)
        _log.warning(
            "option_translation_build_failed",
            form_id=str(form_id),
            language=key[1],
            exc_type=type(exc).__name__,
        )
        return EMPTY_OVERRIDES
    _log.info(
        "option_translation_ready",
        form_id=str(form_id),
        language=key[1],
        override_count=len(result.option_labels),
        spoken_name_count=len(result.spoken_names),
        section_label_count=len(result.section_labels),
    )
    return result
