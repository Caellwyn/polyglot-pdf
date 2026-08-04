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
- Glossary-pin checks match the ENGLISH source term at word boundaries
  (bd polyglot-pdf-m6w5: a bare substring match tripped on English
  derivational morphology -- 'Refundable credit' contains 'refund', which
  then demanded the pinned 'reembolso' inside the correct 'reembolsable')
  and the TARGET rendering as exact-substring (case-insensitive). The
  target side is sound for the current pins (zh does not inflect; es only
  mildly, and the pinned phrases are stable in IRS usage). When pins expand
  to inflecting languages (ru/ur/pl-class), the target check needs lemma
  normalization or demotion to advisory -- do not copy it as-is.
- The wrong-language check (bd polyglot-pdf-za4p) is MARKER-based and
  precision-first: it flags only characters that are standard orthography
  in a same-script NEIGHBOR language but foreign to the expected one
  (Portuguese a-tilde/o-tilde in a Spanish slot; Russian yery/hard-sign in
  a Ukrainian slot; Persian pe/che/zhe/gaf in an Arabic slot). It cannot
  catch a wrong-language string that avoids every marker -- that residual
  is the bilingual judge's job. Under the language-lock purpose (memory:
  translations-are-drift-anchors-not-display) a wrong-LANGUAGE string is
  the worst shippable defect: it anchors the voice model to the wrong
  language, the exact live failure (a Spanish session slipping into
  Portuguese) that started the epic.

Findings are schema_lint.LintFinding-shaped, ALL severity=WARNING. String
checks carry rule="translation-mechanical" (the flag-taxonomy kind) with the
specific check id leading the message; the kit-level coverage check (bd
polyglot-pdf-x41u) carries rule="translation-coverage" -- one finding per
language whose coverage is incomplete in an otherwise-translated kit,
because a MISSING translation falls back to the English label mid-session
(an English injection at the exact point the language lock is held), making
gaps worse than imperfect strings. WARNING never blocks kit publish --
shipping decisions on flags stay human (fail-open doctrine).
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

# The taxonomy rule id every mechanical STRING finding carries (the plan's
# flag taxonomy). The per-check id exists on MechanicalFailure
# internally but is NOT carried onto findings today -- bd xfdb removed
# the old message prefixes that used to leak it as prose, and a proper
# structural home on the finding is tracked as bd polyglot-pdf-21sw.
RULE_MECHANICAL = "translation-mechanical"
# Kit-level coverage findings (bd polyglot-pdf-x41u) carry their own rule so
# the editor can label the class distinctly (a gap is not a bad string).
RULE_COVERAGE = "translation-coverage"

# Per-check ids (the structural `check` field + spike/report grouping).
CHECK_EMPTY = "empty"
CHECK_NON_ASCII_DIGITS = "non-ascii-digits"
CHECK_DIGIT_RUN = "digit-run-missing"
CHECK_MASK = "mask-broken"
CHECK_DNT = "dnt-violated"
CHECK_SCRIPT = "wrong-script"
CHECK_PIN = "pin-missed"
CHECK_WRONG_LANGUAGE = "wrong-language-marker"

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


# Same-script neighbor markers (bd polyglot-pdf-za4p). For each EXPECTED
# language, characters that are standard orthography in a neighbor language
# sharing its script but foreign to the expected one -- their presence is a
# high-confidence wrong-language signal the script check cannot see (both
# languages pass the script-range test). Precision-first: only unambiguous
# markers are listed; e.g. the enye is NOT a marker for tagalog (Tagalog
# legitimately uses it in Spanish loans), and urdu gets no marker set at all
# (its alphabet embeds both the Perso-Arabic and retroflex letters). ASCII
# escapes per the module rule; the claimed-language string feeds the message.
_MARKS_PT = {c: "portuguese" for c in
             "\u00e3\u00c3\u00f5\u00d5"}  # a/o with tilde
_MARKS_ES = {c: "spanish" for c in "\u00f1\u00d1"}  # enye
_MARKS_DE = {c: "german" for c in "\u00df\u1e9e"}  # sharp s
_MARKS_UK = {c: "ukrainian" for c in
             "\u0456\u0406\u0457\u0407\u0454\u0404\u0491\u0490"}  # i / yi / ye / ghe
_MARKS_RU = {c: "russian" for c in
             "\u044b\u042b\u044d\u042d\u044a\u042a\u0451\u0401"}  # yery / e / hard sign / yo
_MARKS_FA_UR = {c: "persian/urdu" for c in
                "\u067e\u0686\u0698\u06af"}  # pe / che / zhe / gaf
_MARKS_UR = {c: "urdu" for c in
             "\u0679\u0688\u0691\u06ba\u06d2\u06be"}  # retroflex set + barree ye / do-chashmi he

_FOREIGN_MARKERS: Dict[str, Dict[str, str]] = {
    "spanish": {**_MARKS_PT, **_MARKS_DE},
    "portuguese": {**_MARKS_ES, **_MARKS_DE},
    "italian": {**_MARKS_PT, **_MARKS_ES, **_MARKS_DE},
    "french": {**_MARKS_PT, **_MARKS_ES, **_MARKS_DE},
    "german": {**_MARKS_PT, **_MARKS_ES},
    "dutch": {**_MARKS_PT, **_MARKS_ES, **_MARKS_DE},
    "afrikaans": {**_MARKS_PT, **_MARKS_ES, **_MARKS_DE},
    "swedish": {**_MARKS_PT, **_MARKS_ES, **_MARKS_DE},
    "tagalog": {**_MARKS_PT, **_MARKS_DE},
    "russian": _MARKS_UK,
    "ukrainian": _MARKS_RU,
    "arabic": {**_MARKS_FA_UR, **_MARKS_UR},
    "persian": _MARKS_UR,
}


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
        return [MechanicalFailure(
            CHECK_EMPTY,
            "this translation is empty -- the English text will be shown "
            "or spoken instead until it is filled in",
        )]
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
                      form_number_re, mask_re, language_name))
    failures.extend(_check_wrong_language(source, translation, language_name))
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
        # Show the glyph itself beside the codepoint: a reviewer cannot
        # find a character named only "U+0660" (Opus outer review). The
        # SOURCE stays ASCII (the glyph is runtime data), which means the
        # message is NO LONGER ascii-by-construction: any consumer that
        # prints it must go through _ascii() or equivalent (cp1252 scar,
        # CLAUDE.md #6) -- both current console sinks already do.
        rendered = ", ".join(
            "'%s' (U+%04X)" % (ch, ord(ch)) for ch in native)
        failures.append(MechanicalFailure(
            CHECK_NON_ASCII_DIGITS,
            "this translation uses non-standard digit characters (%s) -- "
            "numbers must always use plain 0-9, replace them" % rendered,
        ))
    for run in sorted(set(re.findall(r"[0-9]+", source))):
        if run not in translation:
            failures.append(MechanicalFailure(
                CHECK_DIGIT_RUN,
                "the number '%s' from the source text is missing from the "
                "translation -- add it back exactly as written" % run,
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
                "the format pattern '%s' from the source text (for example "
                "a date format) is missing or altered in the translation -- "
                "copy it exactly, unchanged" % mask,
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
                "'%s' is supposed to stay in English (it is a form number, "
                "agency name, or other fixed term) but is missing or "
                "altered in the translation -- put it back exactly as "
                "written" % token,
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
    language_name: str = "",
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
        # Lead with the LANGUAGE, not the internal script-registry id
        # ("han-alphabet" is jargon AND wrong -- Han is not an alphabet;
        # Opus outer review). The dominant found script is named plainly.
        found_script = max(counts, key=counts.get)
        lang = language_name or expected
        return [MechanicalFailure(
            CHECK_SCRIPT,
            "this translation has no %s characters at all -- it looks "
            "like it was never actually translated (the letters it does "
            "use are mostly %s); replace it with a real %s translation"
            % (lang, found_script, lang),
        )]
    return []


def _check_wrong_language(
    source: str, translation: str, language_name: str
) -> List[MechanicalFailure]:
    """Same-script wrong-language detection (bd polyglot-pdf-za4p): flag
    characters that are standard orthography in a neighbor language but
    foreign to the expected one -- the class the script check is blind to
    (a Portuguese string in a spanish slot passes the latin-script test).
    Marker-based and precision-first (see _FOREIGN_MARKERS); identity-kept
    strings are skipped for parity with _check_script (a deliberately
    untranslated proper noun is the translator's sanctioned choice)."""
    markers = _FOREIGN_MARKERS.get(language_name)
    if not markers or translation.strip() == source.strip():
        return []
    hits: Dict[str, List[str]] = {}
    for ch in set(translation):
        claimed = markers.get(ch)
        if claimed:
            # Glyph beside codepoint; message no longer ascii-by-
            # construction -- print sites must _ascii() (see _check_digits).
            hits.setdefault(claimed, []).append(
                "'%s' (U+%04X)" % (ch, ord(ch)))
    if not hits:
        return []
    detail = "; ".join(
        "%s marker(s) %s" % (claimed, ", ".join(sorted(chars)))
        for claimed, chars in sorted(hits.items()))
    return [MechanicalFailure(
        CHECK_WRONG_LANGUAGE,
        "this %s translation contains characters that only appear in a "
        "different language (%s) -- it may have been translated into the "
        "wrong language; a session in %s could end up hearing the wrong "
        "language spoken back, so check and fix it"
        % (language_name, detail, language_name),
    )]


def _check_pins(
    source: str, translation: str, lang_entry: Dict[str, Any]
) -> List[MechanicalFailure]:
    """Where an official pinned rendering exists for a term in the source,
    the translation must contain it (case-insensitive substring on the
    target side; see the module docstring's inflection caveat).

    The ENGLISH term is matched at ASCII-letter word boundaries (bd
    polyglot-pdf-m6w5): a bare substring match trips on English
    derivational morphology -- 'Refundable credit' contains 'refund',
    which then demands the pinned noun rendering inside the correct
    adjectival translation. ASCII-letter lookarounds are safe here because
    the SOURCE side is English (the translation-side caveat about \\w next
    to CJK/Arabic letters does not apply)."""
    pins = lang_entry.get("pins")
    if not isinstance(pins, dict) or not pins:
        return []
    failures = []
    source_lower = source.lower()
    translation_lower = translation.lower()
    for en_term, target in pins.items():
        if not isinstance(en_term, str) or not isinstance(target, str):
            continue
        term_re = r"(?<![a-z])%s(?![a-z])" % re.escape(en_term.lower())
        if re.search(term_re, source_lower) \
                and target.lower() not in translation_lower:
            failures.append(MechanicalFailure(
                CHECK_PIN,
                "the source text says '%s', which has an official required "
                "translation ('%s') that is missing from this translation "
                "-- use the official wording" % (en_term, target),
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


def _iter_translation_items(
    schema: Optional[Dict[str, Any]],
) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Yield (path_base, translations_map_or_empty) for every translation-
    BEARING item in a kit schema -- unlike iter_translation_entries, an item
    with NO translations dict still yields (with {}), so coverage can see
    absences."""
    for index, field in enumerate((schema or {}).get("fields") or []):
        if not isinstance(field, dict):
            continue
        field_ref = "fields[%d] (id=%s)" % (index, field.get("id"))
        spoken = field.get("spoken_name") or field.get("name")
        if isinstance(spoken, str) and spoken.strip():
            tmap = field.get("spoken_name_translations")
            yield (field_ref + ".spoken_name_translations",
                   tmap if isinstance(tmap, dict) else {})
        for opt in field.get("options") or field.get("allowed_values") or []:
            if not isinstance(opt, dict):
                continue
            label = opt.get("label")
            if isinstance(label, str) and label.strip():
                tmap = opt.get("label_translations")
                yield ("%s.options[%s].label_translations"
                       % (field_ref, opt.get("value")),
                       tmap if isinstance(tmap, dict) else {})
    for section in (schema or {}).get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = section.get("label")
        if isinstance(label, str) and label.strip():
            tmap = section.get("label_translations")
            yield ("sections[%s].label_translations" % section.get("id"),
                   tmap if isinstance(tmap, dict) else {})


def coverage_findings(
    schema: Optional[Dict[str, Any]],
    languages: Optional[List[str]] = None,
    *,
    attempted: bool = False,
) -> List[LintFinding]:
    """Per-language coverage gaps (bd polyglot-pdf-x41u): one WARNING per
    language whose coverage is INCOMPLETE in an otherwise-translated kit
    (a fully-failed language counts -- coverage 0 is the failed-batch
    case). A kit with NO baked translations at all yields nothing (an
    untranslated draft is not a gap). Rationale: a missing translation
    falls back to the English label mid-session -- an English injection at
    the exact point the language lock is held -- so gaps are worse than
    imperfect strings (memory: translations-are-drift-anchors-not-display).

    `languages` scopes the judgment: the kit-level sweep passes None (every
    supported language -- kit health), while the bake report passes the
    languages THAT BAKE addressed, so a deliberate `--languages spanish`
    subset run is not flagged for the 16 languages it never attempted.

    `attempted=True` (the bake's attestation) disables the untranslated-kit
    silence: a bake that REQUESTED languages and ended with zero coverage
    is the every-batch-failed outage, which must flag loudly -- without the
    attestation it is indistinguishable from a never-translated draft
    (fresh-eyes gap on bd x41u: a scoped bake whose only language failed
    produced no finding at all)."""
    if languages is None:
        languages = sorted(
            n for n in SPOKEN_LANGUAGE_BCP47 if n != "english")
    else:
        languages = sorted(
            lang for lang in ((_resolve_language_key(l) for l in languages))
            if lang and lang != "english")
    total = 0
    covered: Dict[str, int] = {lang: 0 for lang in languages}
    missing_examples: Dict[str, List[str]] = {lang: [] for lang in languages}
    for path_base, tmap in _iter_translation_items(schema):
        total += 1
        # Count a language covered only when its value is a NON-EMPTY string
        # (parity with option_translation._kit_translation, bd polyglot-pdf-z3rs):
        # keying on mere PRESENCE let a hand-authored empty ({"spanish": ""}) --
        # which the bake's fresh-value filter never fills -- pass the hard
        # completion gate (bd 783r) as "covered", shipping a form that speaks the
        # ENGLISH label in that session. An empty/whitespace/non-string value is
        # not a translation, so it does not count.
        resolved = {
            _resolve_language_key(k)
            for k, v in tmap.items()
            if isinstance(v, str) and v.strip()
        }
        for lang in languages:
            if lang in resolved:
                covered[lang] += 1
            elif len(missing_examples[lang]) < 3:
                missing_examples[lang].append(path_base)
    if total == 0 or (not attempted and not any(covered.values())):
        return []
    findings: List[LintFinding] = []
    for lang in languages:
        n = covered[lang]
        if n >= total:
            continue
        examples = "; ".join(missing_examples[lang])
        findings.append(LintFinding(
            severity=SEVERITY_WARNING,
            rule=RULE_COVERAGE,
            path="coverage.%s" % lang,
            message="%s covers %d/%d strings -- the other %d have no "
                    "translation, so a %s session will hear the ENGLISH "
                    "text instead in those spots; re-run the translation "
                    "pass to fill the gap. First missing: %s"
                    % (lang, n, total, total - n, lang, examples),
        ))
    return findings


def lint_kit_schema(
    schema: Optional[Dict[str, Any]],
    glossary: Optional[Dict[str, Any]],
) -> List[LintFinding]:
    """Lint every baked translation in one kit schema, plus the per-language
    coverage check. Translation-map keys that resolve to no known language
    (hand-authored oddities) are SKIPPED, not flagged -- the string lint
    checks strings, not key hygiene."""
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
    findings.extend(coverage_findings(schema))
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
                message="this kit's schema.json could not be read (%s) -- "
                        "it was skipped and needs to be fixed or "
                        "re-extracted"
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
