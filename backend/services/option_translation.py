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
    """
    semaphore = asyncio.Semaphore(max(1, concurrency))
    report: Dict[str, Any] = {"changed": False, "failed_languages": [], "languages": {}}

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
        if not labels and not spoken_names:
            return
        missing = labels if not only_missing else [
            label for label in labels if label not in existing
        ]
        entry["missing"] = len(missing)
        names_missing = spoken_names if not only_missing else [
            n for n in spoken_names if n not in existing_names
        ]
        entry["names_missing"] = len(names_missing)
        overrides = dict(existing)
        name_overrides = dict(existing_names)
        # Union of both string sets, deduped, labels first (a string that is
        # BOTH a label and a spoken name translates once and serves both).
        union_missing = list(dict.fromkeys([*missing, *names_missing]))
        if union_missing:
            try:
                async with semaphore:
                    translated = await text_ai.translate_labels(
                        union_missing, name.capitalize(), code
                    )
            except Exception as exc:  # noqa: BLE001 -- skip-and-report by design
                _log.warning(
                    "option_translation_bake_language_failed",
                    language=name, exc_type=type(exc).__name__,
                )
                translated = None
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
    return report


def _collect_section_labels(
    full_schema: Optional[Dict[str, Any]]
) -> List[str]:
    """Unique section labels in order. Sections carry no kit translation
    structure (unlike options/fields), so every label rides the batched call
    (bd polyglot-pdf-tupu.2 -- closes the zmlo residual where a greeting read
    a section title in English)."""
    labels: List[str] = []
    seen: set = set()
    for section in (full_schema or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = section.get("label")
        if isinstance(label, str) and label.strip() and label not in seen:
            seen.add(label)
            labels.append(label)
    return labels


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
    section_labels = _collect_section_labels(full_schema)
    if not labels and not spoken_names and not section_labels:
        return EMPTY_OVERRIDES

    remaining_labels = [s for s in labels if s not in label_overrides]
    remaining_names = [s for s in spoken_names if s not in name_overrides]
    section_overrides: Dict[str, str] = {}
    union = list(dict.fromkeys(
        [*remaining_labels, *remaining_names, *section_labels]))
    if union:
        codes = bcp47_codes_for_spoken_language(language_name)
        language_code = codes[0] if codes else ""
        translated = await text_ai.translate_labels(
            union, language_name, language_code
        )
        if translated is None:
            raise OptionTranslationError("translate_labels failed")
        # Kit precedence is absolute: only strings actually sent to the
        # secretary may land, so a stray response entry can never overwrite a
        # kit-provided translation. Membership splits the union back into its
        # three maps (a shared string legitimately lands in several).
        clean = {k: v for k, v in translated.items()
                 if isinstance(v, str) and v.strip()}
        label_set = set(remaining_labels)
        name_set = set(remaining_names)
        section_set = set(section_labels)
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
