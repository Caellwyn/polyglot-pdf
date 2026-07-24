"""Deterministic mechanical lint for baked kit translations (bd
polyglot-pdf-ch7j, epic polyglot-pdf-sekc).

The cheapest layer of the translation quality gate: pure regex/rule checks,
NO model calls. A mechanical failure is PROOF of wrongness (a translated
"USCIS", a broken format mask, non-ASCII digits, the wrong script), so the
verify loop (V3, bd polyglot-pdf-9ikj) feeds these straight to rectify
without a judge call on the way in -- the rectified string then re-enters
the FULL loop (re-lint + back-translate + re-judge).

All language-specific data lives in form-kits/_translation/glossary.json
(UTF-8 data file); this module is ASCII-only (CLAUDE.md scar #6) and keeps
Unicode script ranges as escaped code points.

Check tolerances (plan review round 3 -- these are load-bearing):
- The script check asserts the expected script is PRESENT among letters
  remaining AFTER stripping do-not-translate terms, form numbers, format
  masks, and digits. It is NEVER "no Latin present": correct translations
  legitimately keep "I-90", "USCIS", "mm/dd/yyyy" verbatim inside
  Cyrillic/Devanagari/Han strings. (Presence-only, not dominance -- see
  _check_script's docstring for the measured rationale.)
- Glossary-pin checks are exact-substring (case-insensitive). Sound for the
  current pins (zh does not inflect; es only mildly, and the pinned phrases
  are stable in IRS usage). When pins expand to inflecting languages
  (ru/ur/pl-class), this check needs lemma normalization or demotion to
  advisory -- do not copy it as-is.

Findings are schema_lint.LintFinding-shaped, ALL severity=WARNING with
rule="translation-mechanical" (the flag-taxonomy kind); the specific check id
leads the message. WARNING never blocks kit publish -- shipping decisions on
flags stay human (fail-open doctrine).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

import structlog

from backend.services.schema_lint import SEVERITY_WARNING, LintFinding
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47

_log = structlog.get_logger(__name__)

# The one taxonomy rule id every mechanical finding carries (the plan's flag
# taxonomy); the per-check id leads the message text instead.
RULE_MECHANICAL = "translation-mechanical"

# Per-check ids (message prefixes + spike/report grouping).
CHECK_EMPTY = "empty"
CHECK_NON_ASCII_DIGITS = "non-ascii-digits"
CHECK_DIGIT_RUN = "digit-run-missing"
CHECK_MASK = "mask-broken"
CHECK_DNT = "dnt-violated"
CHECK_SCRIPT = "wrong-script"
CHECK_PIN = "pin-missed"

DEFAULT_GLOSSARY_PATH = (
    Path(__file__).resolve().parents[2] / "form-kits" / "_translation"
    / "glossary.json"
)

# Unicode letter ranges per expected-script id (glossary `script` values).
# Deliberately coarse: classification only has to separate the app's scripts
# (latin/cyrillic/han/hangul/devanagari/arabic), not implement UAX #24.
_SCRIPT_RANGES: Dict[str, List[Tuple[int, int]]] = {
    "latin": [
        (0x0041, 0x005A), (0x0061, 0x007A),  # A-Z a-z
        (0x00C0, 0x024F),                    # Latin-1 supp + Extended-A/B
    ],
    "cyrillic": [(0x0400, 0x04FF), (0x0500, 0x052F)],
    "han": [(0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF)],
    "hangul": [(0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7AF)],
    "devanagari": [(0x0900, 0x097F)],
    "arabic": [
        (0x0600, 0x06FF), (0x0750, 0x077F), (0x08A0, 0x08FF),
        (0xFB50, 0xFDFF), (0xFE70, 0xFEFF),
    ],
}


@dataclass(frozen=True)
class MechanicalFailure:
    """One deterministic-lint failure for one (source, translation) pair."""

    check: str
    message: str


# ---------------------------------------------------------------------------
# Glossary loading
# ---------------------------------------------------------------------------

def load_glossary(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Load + shape-validate the glossary file. Fail-open: returns None on a
    missing/unreadable/malformed file (callers skip glossary-dependent
    behavior); never raises."""
    glossary_path = Path(path) if path is not None else DEFAULT_GLOSSARY_PATH
    try:
        with open(glossary_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        _log.warning(
            "translation_glossary_load_failed",
            path=str(glossary_path), exc_type=type(exc).__name__,
        )
        return None
    if not isinstance(data, dict) or not isinstance(
            data.get("languages"), dict):
        _log.warning(
            "translation_glossary_bad_shape", path=str(glossary_path))
        return None
    return data


def glossary_language(
    glossary: Optional[Dict[str, Any]], language_name: str
) -> Optional[Dict[str, Any]]:
    """The per-language glossary entry for a spoken-language name (or a code
    alias like "es" / "es-US" -- same tolerant read side as the kits). None
    when the glossary or the language is absent."""
    if not isinstance(glossary, dict):
        return None
    languages = glossary.get("languages")
    if not isinstance(languages, dict):
        return None
    name = _resolve_language_key(language_name)
    entry = languages.get(name) if name else None
    return entry if isinstance(entry, dict) else None


def glossary_prompt_context(
    glossary: Optional[Dict[str, Any]], language_name: str
) -> Optional[Dict[str, Any]]:
    """The prompt-injection slice for one language: {register, pins,
    do_not_translate, digits_policy}. This is what translate/judge/rectify
    prompts carry (TextAIGemini.translate_items takes it verbatim). None when
    the glossary is unavailable (callers translate without it -- fail-open)."""
    if not isinstance(glossary, dict):
        return None
    entry = glossary_language(glossary, language_name) or {}
    pins = entry.get("pins")
    context: Dict[str, Any] = {
        "register": entry.get("register") or "",
        "pins": pins if isinstance(pins, dict) else {},
        "do_not_translate": [
            t for t in (glossary.get("do_not_translate") or [])
            if isinstance(t, str) and t
        ],
        "digits_policy": glossary.get("digits_policy") or "",
    }
    return context


_LANGUAGE_ALIASES: Dict[str, str] = {}


def _resolve_language_key(raw: Any) -> Optional[str]:
    """Normalize a translation-map key to the canonical lowercase language
    name. Accepts the name ("spanish"), the full BCP-47 code ("es-US") and
    the code stem ("es") -- parity with option_translation's tolerant read
    side. None for unknown keys."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    if not _LANGUAGE_ALIASES:
        for name, code in SPOKEN_LANGUAGE_BCP47.items():
            _LANGUAGE_ALIASES[name] = name
            full = code.lower()
            _LANGUAGE_ALIASES[full] = name
            _LANGUAGE_ALIASES[full.split("-")[0]] = name
    return _LANGUAGE_ALIASES.get(raw.strip().lower())


# ---------------------------------------------------------------------------
# Per-string checks
# ---------------------------------------------------------------------------

def lint_translation(
    source: str,
    translation: str,
    language_name: str,
    glossary: Optional[Dict[str, Any]],
) -> List[MechanicalFailure]:
    """Run every deterministic check on one (source, translation) pair.

    Pure function, no I/O. Order: empty short-circuits (everything else is
    meaningless on an empty string); the rest accumulate independently.
    """
    failures: List[MechanicalFailure] = []
    if not isinstance(translation, str) or not translation.strip():
        return [MechanicalFailure(CHECK_EMPTY, "empty: translation is empty")]
    source = source if isinstance(source, str) else str(source)

    glossary = glossary if isinstance(glossary, dict) else {}
    dnt_terms = [
        t for t in (glossary.get("do_not_translate") or [])
        if isinstance(t, str) and t
    ]
    form_number_re = _compile(glossary.get("form_number_pattern"))
    mask_re = _compile(glossary.get("format_mask_pattern"))
    lang_entry = glossary_language(glossary, language_name) or {}

    failures.extend(_check_digits(source, translation))
    failures.extend(_check_masks(source, translation, mask_re))
    failures.extend(
        _check_dnt(source, translation, dnt_terms, form_number_re))
    failures.extend(
        _check_script(source, translation, lang_entry, dnt_terms,
                      form_number_re, mask_re))
    failures.extend(_check_pins(source, translation, lang_entry))
    return failures


def _compile(pattern: Any) -> Optional[re.Pattern]:
    if not isinstance(pattern, str) or not pattern:
        return None
    try:
        return re.compile(pattern)
    except re.error:
        _log.warning("translation_lint_bad_pattern", pattern=pattern[:80])
        return None


def _check_digits(source: str, translation: str) -> List[MechanicalFailure]:
    """ASCII-digit policy: no native decimal digits anywhere in the
    translation; every digit run in the source survives byte-exact."""
    failures: List[MechanicalFailure] = []
    native = sorted({
        ch for ch in translation
        if ch.isdecimal() and not ("0" <= ch <= "9")
    })
    if native:
        escaped = ", ".join("U+%04X" % ord(ch) for ch in native)
        failures.append(MechanicalFailure(
            CHECK_NON_ASCII_DIGITS,
            "non-ascii-digits: translation uses native digit(s) %s -- the "
            "glossary digits policy pins ASCII 0-9" % escaped,
        ))
    for run in sorted(set(re.findall(r"[0-9]+", source))):
        if run not in translation:
            failures.append(MechanicalFailure(
                CHECK_DIGIT_RUN,
                "digit-run-missing: source digit run '%s' does not appear "
                "in the translation" % run,
            ))
    return failures


def _check_masks(
    source: str, translation: str, mask_re: Optional[re.Pattern]
) -> List[MechanicalFailure]:
    """Format masks ("mm/dd/yyyy") found in the source must survive
    byte-exact in the translation."""
    if mask_re is None:
        return []
    failures = []
    for mask in sorted({m.group(0) for m in mask_re.finditer(source)}):
        if mask not in translation:
            failures.append(MechanicalFailure(
                CHECK_MASK,
                "mask-broken: format mask '%s' from the source is not "
                "byte-identical in the translation" % mask,
            ))
    return failures


def _dnt_tokens_in(
    text: str, dnt_terms: List[str], form_number_re: Optional[re.Pattern]
) -> List[str]:
    """Every do-not-translate token present in `text`: explicit glossary
    terms (word-boundary match) + form-number pattern hits."""
    tokens: List[str] = []
    for term in dnt_terms:
        if re.search(r"(?<!\w)%s(?!\w)" % re.escape(term), text):
            tokens.append(term)
    if form_number_re is not None:
        tokens.extend(m.group(0) for m in form_number_re.finditer(text))
    return sorted(set(tokens))


def _check_dnt(
    source: str,
    translation: str,
    dnt_terms: List[str],
    form_number_re: Optional[re.Pattern],
) -> List[MechanicalFailure]:
    """DNT tokens in the source must appear byte-identical in the
    translation. Presence is plain substring (word-boundary assertions
    misfire next to CJK/Arabic letters, which count as \\w)."""
    failures = []
    for token in _dnt_tokens_in(source, dnt_terms, form_number_re):
        if token not in translation:
            failures.append(MechanicalFailure(
                CHECK_DNT,
                "dnt-violated: '%s' must stay untranslated and byte-"
                "identical, but is missing/altered in the translation"
                % token,
            ))
    return failures


def _script_of(ch: str) -> Optional[str]:
    code = ord(ch)
    for script, ranges in _SCRIPT_RANGES.items():
        for lo, hi in ranges:
            if lo <= code <= hi:
                return script
    return "other"


def _check_script(
    source: str,
    translation: str,
    lang_entry: Dict[str, Any],
    dnt_terms: List[str],
    form_number_re: Optional[re.Pattern],
    mask_re: Optional[re.Pattern],
) -> List[MechanicalFailure]:
    """Expected script PRESENT after stripping DNT terms, form numbers,
    format masks and digits. NEVER 'no Latin present' -- Latin runs like
    'I-90' are legitimate in any script (plan review round 3).

    Presence-only by measurement, not laziness: a dominance variant was
    piloted against the 4 shipped kits and flagged correct translations
    that keep short un-DNT'd Latin acronyms ('ZIP code' -> arabic=6,
    latin=7), the exact flag-everything failure mode review round 3 warns
    about. Absent-expected-script still catches the real class (fully
    untranslated English shipped as a 'translation'). Semantic quality of
    mixed-script strings is the JUDGE's job, not the lint's.

    Identity-kept strings (translation == source) are SKIPPED entirely,
    also by measurement: the shipped i-90 carries ~600 US state names
    deliberately kept Latin-identical in ar/hi/ur ('Alabama' -> 'Alabama'),
    which the translate prompt itself sanctions ('return proper nouns
    unchanged'). Identity is a translator CHOICE the lint cannot prove
    wrong without a proper-noun oracle -- whether 'Given name' -> 'Given
    name' is lazy or 'Alabama' -> 'Alabama' is right is exactly the
    bilingual judge's call (V3), not a mechanical one."""
    expected = lang_entry.get("script")
    if not isinstance(expected, str) or expected not in _SCRIPT_RANGES:
        return []
    if translation.strip() == source.strip():
        return []
    stripped = translation
    for token in _dnt_tokens_in(stripped, dnt_terms, form_number_re):
        stripped = stripped.replace(token, " ")
    if mask_re is not None:
        stripped = mask_re.sub(" ", stripped)
    counts: Dict[str, int] = {}
    for ch in stripped:
        if ch.isalpha():
            script = _script_of(ch)
            counts[script] = counts.get(script, 0) + 1
    if not counts:
        return []  # nothing left to check (string was all DNT/masks/digits)
    if counts.get(expected, 0) == 0:
        summary = ", ".join(
            "%s=%d" % (script, counts[script]) for script in sorted(counts))
        return [MechanicalFailure(
            CHECK_SCRIPT,
            "wrong-script: expected %s script is entirely absent after "
            "stripping DNT/masks/digits; letter counts {%s}"
            % (expected, summary),
        )]
    return []


def _check_pins(
    source: str, translation: str, lang_entry: Dict[str, Any]
) -> List[MechanicalFailure]:
    """Where an official pinned rendering exists for a term in the source,
    the translation must contain it (case-insensitive substring; see the
    module docstring's inflection caveat)."""
    pins = lang_entry.get("pins")
    if not isinstance(pins, dict) or not pins:
        return []
    failures = []
    source_lower = source.lower()
    translation_lower = translation.lower()
    for en_term, target in pins.items():
        if not isinstance(en_term, str) or not isinstance(target, str):
            continue
        if en_term.lower() in source_lower \
                and target.lower() not in translation_lower:
            failures.append(MechanicalFailure(
                CHECK_PIN,
                "pin-missed: source contains '%s', whose official rendering "
                "'%s' is absent from the translation" % (en_term, target),
            ))
    return failures


# ---------------------------------------------------------------------------
# Kit-schema traversal + sweep
# ---------------------------------------------------------------------------

def iter_translation_entries(
    schema: Optional[Dict[str, Any]],
) -> Iterator[Tuple[str, str, str, str]]:
    """Yield (path, language_key, source, translation) for every baked
    translation in a kit schema: field spoken_name_translations, option
    label_translations, section label_translations.

    Field-level paths carry `(id=<field_id>)` in the exact shape
    `schema_lint.field_id_of()` parses (`fields[3] (id=x).show_if`), so
    `LintFinding.as_dict()` derives a clickable field_id for the editor
    UI (fresh-eyes finding on this bead: the first cut used a prettier
    `fields[<id>].` format the parser could not read, which would have
    shipped field_id=None into V4's surfacing). Section paths carry no
    `(id=...)` on purpose -- there is no field to focus for a section
    label, so field_id=None is correct there."""
    for index, field in enumerate((schema or {}).get("fields") or []):
        if not isinstance(field, dict):
            continue
        field_ref = "fields[%d] (id=%s)" % (index, field.get("id"))
        spoken = field.get("spoken_name") or field.get("name")
        translations = field.get("spoken_name_translations")
        if isinstance(spoken, str) and spoken.strip() \
                and isinstance(translations, dict):
            for lang, value in translations.items():
                yield (
                    "%s.spoken_name_translations.%s" % (field_ref, lang),
                    str(lang), spoken, value if isinstance(value, str) else "",
                )
        options = field.get("options") or field.get("allowed_values")
        for opt in options or []:
            if not isinstance(opt, dict):
                continue
            label = opt.get("label")
            opt_translations = opt.get("label_translations")
            if not isinstance(label, str) or not label.strip() \
                    or not isinstance(opt_translations, dict):
                continue
            for lang, value in opt_translations.items():
                yield (
                    "%s.options[%s].label_translations.%s"
                    % (field_ref, opt.get("value"), lang),
                    str(lang), label, value if isinstance(value, str) else "",
                )
    for section in (schema or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = section.get("label")
        translations = section.get("label_translations")
        if not isinstance(label, str) or not label.strip() \
                or not isinstance(translations, dict):
            continue
        for lang, value in translations.items():
            yield (
                "sections[%s].label_translations.%s"
                % (section.get("id"), lang),
                str(lang), label, value if isinstance(value, str) else "",
            )


def lint_kit_schema(
    schema: Optional[Dict[str, Any]],
    glossary: Optional[Dict[str, Any]],
) -> List[LintFinding]:
    """Lint every baked translation in one kit schema. Translation-map keys
    that resolve to no known language (hand-authored oddities) are SKIPPED,
    not flagged -- the lint checks strings, not key hygiene."""
    findings: List[LintFinding] = []
    for path, lang_key, source, translation in \
            iter_translation_entries(schema):
        language = _resolve_language_key(lang_key)
        if language is None or language == "english":
            continue
        for failure in lint_translation(
                source, translation, language, glossary):
            findings.append(LintFinding(
                severity=SEVERITY_WARNING,
                rule=RULE_MECHANICAL,
                path=path,
                message=failure.message,
            ))
    return findings


def lint_kits(
    kits_root: Path,
    glossary: Optional[Dict[str, Any]],
    kit_ids: Optional[List[str]] = None,
) -> Dict[str, List[LintFinding]]:
    """Sweep every kit dir under `kits_root` (skipping _-prefixed dirs like
    _translation) and lint its schema.json. Returns {kit_id: findings};
    kits with an unreadable schema get one WARNING finding instead of an
    exception (the sweep must always complete -- fail-open)."""
    results: Dict[str, List[LintFinding]] = {}
    root = Path(kits_root)
    for kit_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        kit_id = kit_dir.name
        if kit_id.startswith(("_", ".")):
            continue
        if kit_ids and kit_id not in kit_ids:
            continue
        schema_path = kit_dir / "schema.json"
        if not schema_path.is_file():
            continue
        try:
            with open(schema_path, encoding="utf-8") as fh:
                schema = json.load(fh)
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            results[kit_id] = [LintFinding(
                severity=SEVERITY_WARNING,
                rule=RULE_MECHANICAL,
                path="schema.json",
                message="unreadable schema (%s) -- kit skipped"
                        % type(exc).__name__,
            )]
            continue
        results[kit_id] = lint_kit_schema(schema, glossary)
    return results


# ---------------------------------------------------------------------------
# CLI (the script-checkable sweep behind epic criterion 2)
# ---------------------------------------------------------------------------

def _ascii(text: str) -> str:
    """Console-safe rendering: Windows' default cp1252 console chokes on
    non-ASCII (CLAUDE.md scar #6), so escape everything outside ASCII."""
    return text.encode("ascii", "backslashreplace").decode("ascii")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Deterministic mechanical lint over baked kit "
                    "translations (no model calls).")
    parser.add_argument(
        "--kits-root", type=Path,
        default=DEFAULT_GLOSSARY_PATH.parents[1],
        help="form-kits directory (default: the repo's form-kits/)")
    parser.add_argument(
        "--glossary", type=Path, default=None,
        help="glossary path (default: form-kits/_translation/glossary.json)")
    parser.add_argument(
        "kits", nargs="*",
        help="kit ids to lint (default: every kit under --kits-root)")
    parser.add_argument(
        "--verbose", action="store_true",
        help="print every finding, not just per-kit counts")
    args = parser.parse_args(argv)

    glossary = load_glossary(args.glossary)
    if glossary is None:
        print("ERROR: glossary unavailable -- cannot lint")
        return 2
    results = lint_kits(args.kits_root, glossary, args.kits or None)
    total = 0
    for kit_id, findings in results.items():
        total += len(findings)
        print("%s: %d finding(s)" % (kit_id, len(findings)))
        if args.verbose:
            for finding in findings:
                print("  [%s] %s" % (
                    _ascii(finding.path), _ascii(finding.message)))
    print("TOTAL: %d finding(s) across %d kit(s)" % (total, len(results)))
    return 0 if total == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
