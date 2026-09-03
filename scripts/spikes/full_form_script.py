"""Full-form I-90 question-plan generator (bd polyglot-pdf-n86b, epic 00pt).

Builds the --schema i90-full plan for measure_form_session_costs.py: a spoken
question step for EVERY field the production frontend would show, derived from
the hand-validated zero-contradiction persona in backend/scripts/g1b_answer_key.py
(Linh Thi Nguyen, LPR replacing a lost card). The 34-question --schema i90 plan
(Maria Vasquez, Parts 1.1-1.4) is untouched; this module only ADDS the full-form
plan the stress-test series (E0-E6) runs on.

What the generator does, per schema field in document order:
  - evaluates the field's show_if gate against the persona's answers using the
    SAME operator semantics as the frontend evaluator
    (frontend/src/schema-forms/utils/validation.ts::evaluateAtomicCondition;
    this kit's conditions are all legacy single atoms -- no composites);
    hidden fields are never asked, exactly as production hides them;
  - auto-applies copy_from page-header repeats and signature-type fields (the
    frontend copies/collects those without the voice loop; the harness seeds
    them confirmed at handshake) -- they are not spoken;
  - renders a spoken "say" phrasing per field type (digits spelled out, dates
    natural, option LABELS for radios/selects, decline phrasings for visible
    fields the persona leaves empty), plus a mechanically-mutated "wrong"
    phrasing for the unhappy path;
  - emits the expected post-fill canon per field (option SLUG for option
    fields, MM/DD/YYYY for dates, "" for declined optionals) for the driver's
    fill-accuracy scorer and startup drift guard.

Build-time guards (all abort before any live spend):
  - g1b_answer_key.validate_answer_key() must return [];
  - every override in ANSWER_OVERRIDES must be a valid schema option value
    (option fields) and every spoken field's show_if gate must be satisfied by
    answers given EARLIER in the plan (the ordering invariant the 34-q plan
    maintains by hand);
  - the driver's _assert_expected_canon_matches_schema runs over the generated
    expected dict as it does for the hand-written plans.

Language: phrase() takes lang ("en" or "es"; "es" is the E6 Spanish arm, bd
polyglot-pdf-0cyu). The Spanish persona SPEAKS in Spanish (values spoken
Spanish-style: digits, dates, option labels), but expected_canon() never
takes a lang parameter -- the form fills in English regardless of the
spoken language, so build_full_form_plan(schema, lang="es") produces the
SAME field ids and expected canon as lang="en"; only the "say"/"wrong"
phrasings differ.

Stdlib-only (json/os/re/datetime) so --synth-only and the guards run without
google-genai installed. ASCII only.
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BACKEND_SCRIPTS = os.path.join(_REPO_ROOT, "backend", "scripts")
if _BACKEND_SCRIPTS not in sys.path:
    sys.path.insert(0, _BACKEND_SCRIPTS)

import g1b_answer_key  # noqa: E402  (backend/scripts, no package __init__)

I90_SCHEMA_PATH = os.path.join(_REPO_ROOT, "form-kits", "i-90", "schema.json")

# Data-driven phrasing for languages beyond en/es (bd polyglot-pdf-6mzi).
# Native-script strings live in the UTF-8 JSON fixture, never in this file
# (ASCII-only source rule, CLAUDE.md scar #6).
MULTILANG_PHRASES_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures",
    "multilang_phrases.json")
_multilang_cache: dict | None = None


def multilang_phrases() -> dict:
    """Lazy-load the per-language phrase data ({lang: {...}}); {} if absent."""
    global _multilang_cache
    if _multilang_cache is None:
        try:
            with open(MULTILANG_PHRASES_PATH, encoding="utf-8") as f:
                _multilang_cache = json.load(f)
        except FileNotFoundError:
            _multilang_cache = {}
        _multilang_cache.pop("_note", None)
    return _multilang_cache

MULTI_SEP = g1b_answer_key.MULTI_SEP


# --------------------------------------------------------------------------
# Persona overrides -- corrections of the g1b answer key where the CURRENT kit
# schema contradicts it (the key predates two schema changes). Tracked in the
# answer-key staleness bead; the overrides keep the harness plan valid against
# today's kit without editing the g1b corpus module underneath its consumers.
# --------------------------------------------------------------------------
# The A-number: the key stores "A123456789"; the kit pattern is ^\d{7,9}$ and
# the a_number normalizer strips the A prefix on write (validation.format_preset,
# bd 0zr/jnjj.40). The model therefore WRITES bare digits; expect those.
_ANUMBER_EXPECTED = "123456789"

ANSWER_OVERRIDES: dict = {
    # The kit's pattern is ^[0-9]{12}$ (min/max_length 12); the key's value is
    # 13 digits and could never validate. 12-digit stand-in, same persona.
    "uscis_account": "123456789012",
    # The key marks the reason-for-new-card radio NA citing a commuter-only
    # show_if; the CURRENT kit gates it `in [lawful_permanent_resident,
    # permanent_resident_in_commuter_status]` -- VISIBLE for the persona, and
    # her documented reason is the lost card (the key's own docstring).
    "reason_section_a": "my_previous_card_has_been_lost_stolen_or_destroyed",
    # The Part-8 page-header copy of the A-number must hold what the CLIENT
    # copies from the FILLED source field -- the A-stripped digits the model
    # writes -- not the key's raw "A123456789". Seeding the raw form would put
    # two renderings of one number in the validator payload and could
    # manufacture a spurious conflict in the precision measurement
    # (fresh-eyes round 2 on this bead).
    "a_number": _ANUMBER_EXPECTED,
}

# Fields the frontend fills without the voice loop; the harness seeds them
# confirmed at handshake and the plan never speaks them.
AUTO_APPLY_TYPES = ("signature",)


# --------------------------------------------------------------------------
# show_if evaluation -- mirrors evaluateAtomicCondition/shouldShowField for the
# operator set this kit uses (equals / not_equals / is_checked / is_not_empty /
# in / includes; all legacy single atoms). Fail-open on unknown operators,
# matching the frontend (falls back to the static hidden flag).
# --------------------------------------------------------------------------
_KNOWN_OPS = {"equals", "not_equals", "is_checked", "is_not_empty", "is_empty",
              "in", "not_in", "includes", "not_includes", "contains"}


def _trigger_value(field_by_id: dict, values: dict, fid: str):
    """The evaluator-facing value of a trigger field: checkbox_group values are
    the selected-slug LIST (the client stores an array), a single checkbox is a
    boolean, everything else the stored scalar."""
    v = values.get(fid)
    f = field_by_id.get(fid) or {}
    if f.get("type") == "checkbox_group" and v is not None:
        if isinstance(v, list):
            return [str(x) for x in v]
        return [p.strip() for p in str(v).split(MULTI_SEP) if p.strip()]
    if f.get("type") == "checkbox":
        return True if v not in (None, "", False) else (v if v is None else False)
    return v


def evaluate_show_if(cond, field_by_id: dict, values: dict) -> bool:
    """True when the (legacy atomic) condition holds over `values`."""
    if not isinstance(cond, dict):
        return True
    op = cond.get("operator")
    if op not in _KNOWN_OPS:
        return True  # fail-open, like the frontend's unknown-operator fallback
    tv = _trigger_value(field_by_id, values, cond.get("field"))
    val = cond.get("value")
    if op == "equals":
        return tv == val
    if op == "not_equals":
        return tv != val
    if op == "is_checked":
        return len(tv) > 0 if isinstance(tv, list) else tv is True
    if op == "is_not_empty":
        return len(tv) > 0 if isinstance(tv, list) else tv not in (None, "")
    if op == "is_empty":
        return len(tv) == 0 if isinstance(tv, list) else tv in (None, "")
    if op == "in":
        return isinstance(val, list) and str(tv) in [str(x) for x in val]
    if op == "not_in":
        return not (isinstance(val, list) and str(tv) in [str(x) for x in val])
    if op in ("includes", "not_includes"):
        if isinstance(tv, list):
            hit = str(val) in tv
        elif tv in (None, ""):
            hit = False
        else:
            hit = str(tv) == str(val)
        return hit if op == "includes" else not hit
    if op == "contains":
        if isinstance(tv, list):
            return str(val) in [str(x) for x in tv]
        return str(val) in str(tv)
    return True


def field_visible(field: dict, field_by_id: dict, values: dict) -> bool:
    if field.get("hidden"):
        return False
    cond = field.get("show_if")
    if not cond:
        return True
    return evaluate_show_if(cond, field_by_id, values)


# --------------------------------------------------------------------------
# Spoken phrasing
# --------------------------------------------------------------------------
_DIGIT_WORDS = {
    "en": ["zero", "one", "two", "three", "four", "five", "six", "seven",
           "eight", "nine"],
    "es": ["cero", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
           "ocho", "nueve"],
}
_MONTHS_EN = ["January", "February", "March", "April", "May", "June", "July",
              "August", "September", "October", "November", "December"]
# Plain-ASCII Spanish month names (no accents -- gTTS 'es' pronounces
# unaccented Spanish acceptably; CLAUDE.md scar #6).
_MONTHS_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
              "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
_ORDINALS_EN = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh",
    12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
    16: "sixteenth", 17: "seventeenth", 18: "eighteenth", 19: "nineteenth",
    20: "twentieth", 21: "twenty first", 22: "twenty second", 23: "twenty third",
    24: "twenty fourth", 25: "twenty fifth", 26: "twenty sixth",
    27: "twenty seventh", 28: "twenty eighth", 29: "twenty ninth",
    30: "thirtieth", 31: "thirty first",
}


def _spell_digits(s: str, lang: str = "en") -> str:
    words = _DIGIT_WORDS.get(lang)
    if words is None:
        # JSON-fixture languages (bd polyglot-pdf-6mzi): digit_words[0..9].
        words = multilang_phrases()[lang]["digit_words"]
    return " ".join(words[int(c)] for c in s if c.isdigit())


def _year_spoken_en(year: int) -> str:
    """Natural spoken year: 1985 -> 'nineteen eighty five', 2015 -> 'twenty
    fifteen', 2025 -> 'twenty twenty five'. Good enough for gTTS."""
    if 2000 <= year <= 2009:
        return "two thousand " + (_DIGIT_WORDS["en"][year - 2000] if year > 2000 else "")
    hi, lo = divmod(year, 100)
    tens = {19: "nineteen", 20: "twenty"}.get(hi, str(hi))
    if lo == 0:
        return f"{tens} hundred"
    if lo < 10:
        return f"{tens} oh {_DIGIT_WORDS['en'][lo]}"
    lo_words = {
        10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen", 14: "fourteen",
        15: "fifteen", 16: "sixteen", 17: "seventeen", 18: "eighteen",
        19: "nineteen", 20: "twenty", 25: "twenty five", 27: "twenty seven",
    }.get(lo)
    if lo_words is None:
        t, o = divmod(lo, 10)
        tens_w = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty",
                  7: "seventy", 8: "eighty", 9: "ninety"}[t]
        lo_words = tens_w + ("" if o == 0 else " " + _DIGIT_WORDS["en"][o])
    return f"{tens} {lo_words}"


def _date_spoken_en(iso: str) -> str:
    """ISO 'YYYY-MM-DD' -> 'April twelfth, nineteen eighty five'."""
    d = datetime.strptime(iso, "%Y-%m-%d")
    return f"{_MONTHS_EN[d.month - 1]} {_ORDINALS_EN[d.day]}, {_year_spoken_en(d.year)}"


_UNITS_ES = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
             "ocho", "nueve", "diez", "once", "doce", "trece", "catorce",
             "quince", "dieciseis", "diecisiete", "dieciocho", "diecinueve",
             "veinte"]
_TENS_ES = {2: "veinte", 3: "treinta", 4: "cuarenta", 5: "cincuenta",
            6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}


def _two_digit_es(n: int) -> str:
    """0-99 -> Spanish words, plain ASCII (e.g. 'veintidos', no accent)."""
    if n <= 20:
        return _UNITS_ES[n]
    if n < 30:
        # 21-29: "veintiuno".."veintinueve" (contracted, no "y")
        ones = ["", "uno", "dos", "tres", "cuatro", "cinco", "seis", "siete",
                "ocho", "nueve"]
        return "veinti" + ones[n - 20]
    tens, ones = divmod(n, 10)
    if ones == 0:
        return _TENS_ES[tens]
    return f"{_TENS_ES[tens]} y {_UNITS_ES[ones]}"


def _year_spoken_es(year: int) -> str:
    """1900-2099 -> Spanish words. 1985 -> 'mil novecientos ochenta y cinco';
    2015 -> 'dos mil quince'; 2025 -> 'dos mil veinticinco'."""
    if 1900 <= year <= 1999:
        rem = year - 1900
        if rem == 0:
            return "mil novecientos"
        return f"mil novecientos {_two_digit_es(rem)}"
    if 2000 <= year <= 2099:
        rem = year - 2000
        if rem == 0:
            return "dos mil"
        return f"dos mil {_two_digit_es(rem)}"
    # Fallback outside the covered range: digit-by-digit.
    return _spell_digits(str(year), "es")


def _date_spoken_es(iso: str) -> str:
    """ISO 'YYYY-MM-DD' -> '12 de abril de 1985' style, spoken:
    'doce de abril de mil novecientos ochenta y cinco'."""
    d = datetime.strptime(iso, "%Y-%m-%d")
    day_words = _two_digit_es(d.day)
    return f"{day_words} de {_MONTHS_ES[d.month - 1]} de {_year_spoken_es(d.year)}"


def _iso_to_mdy(iso: str) -> str:
    d = datetime.strptime(iso, "%Y-%m-%d")
    return d.strftime("%m/%d/%Y")


def _option_label(field: dict, slug) -> str:
    for o in field.get("options") or []:
        if isinstance(o, dict) and str(o.get("value")) == str(slug):
            return str(o.get("label") or slug)
    return str(slug)


def _is_digit_field(field: dict) -> bool:
    v = field.get("validation") or {}
    pat = v.get("pattern") or ""
    preset = v.get("format_preset") or ""
    return bool(
        preset in ("a_number", "ssn", "uscis_account", "phone", "zip")
        or re.match(r"^\^\\d\{", pat)
        or re.match(r"^\^\[0-9\]\{", pat)
    )


def _is_date_field(field: dict) -> bool:
    if field.get("type") == "date":
        return True
    v = field.get("validation") or {}
    return (v.get("hint") == "MM/DD/YYYY") or (v.get("pattern") == "^\\d{2}/\\d{2}/\\d{4}$")


# Per-field SAY overrides -- phrasings a generic template renders badly
# (long statement options, per-digit comb boxes, street numbers, the A-number).
# Values are (say, wrong) pairs; None wrong means "reuse the generic mutation".
_SAY_OVERRIDES_EN: dict = {
    "a_number": (
        "My alien registration number is A one two three four five six seven eight nine.",
        "My alien registration number is A nine eight seven six five four three two one.",
    ),
    # Personal names are SPELLED OUT (E0 pilot finding, bd polyglot-pdf-0cyu):
    # English gTTS mangles the Vietnamese names badly enough that the live model
    # transcribed "Nguyen" as "Smith", "Linh" as "Lynn", "Thi" as "T". Spelling
    # an uncommon name is exactly what a real user does; the raw
    # no-spelling fragility is recorded as a product finding in the E-series
    # findings doc, not hidden by this phrasing.
    "family_name": (
        "My current family name is Nguyen, spelled N G U Y E N.",
        "My current family name is Tran, spelled T R A N.",
    ),
    "given_name": (
        "My current given name is Linh, spelled L I N H.",
        "My current given name is Lan, spelled L A N.",
    ),
    "middle_name": (
        "My current middle name is Thi, spelled T H I.",
        "My current middle name is Van, spelled V A N.",
    ),
    "mother_given_name": (
        "My mother's given name is Lan, spelled L A N.",
        "My mother's given name is Mai, spelled M A I.",
    ),
    "father_given_name": (
        "My father's given name is Minh, spelled M I N H.",
        "My father's given name is Duc, spelled D U C.",
    ),
    "mail_street": (
        "My street address is four two zero zero Westheimer Road.",
        "My street address is nine nine zero zero Richmond Avenue.",
    ),
    "phys_street": (
        "My physical street address is four two zero zero Westheimer Road.",
        "My physical street address is one one zero zero Main Street.",
    ),
    "mail_unit_number": ("Apartment number twelve.", "Apartment number fourteen."),
    "phys_unit_number": ("Apartment number twelve.", "Apartment number fifteen."),
    "class_of_admission": (
        "My class of admission is I R one.", "My class of admission is C R one."),
    "applicant_reads_english": (
        "An interpreter read the form to me in my language.",
        "I can read and understand English myself.",
    ),
    "reason_section_a": (
        "I need a new card because my previous card was lost.",
        "I need a new card because my existing card has been mutilated.",
    ),
    "status": ("I am a lawful permanent resident.",
                     "I am a conditional permanent resident."),
    "name_changed": ("No, my name has not changed.",
                     "Yes, my name has legally changed."),
    "p3_removal_proceedings": ("No, I have never been in removal proceedings.", None),
    "p3_abandoned_status": ("No, I have never filed Form I-407 or abandoned my status.", None),
    "accommodation_requested": ("No, I am not requesting any accommodation.", None),
    "ethnicity": ("I am not Hispanic or Latino.", "I am Hispanic or Latino."),
    "race": ("Asian.", "White."),
    "height_feet": ("Five feet.", "Six feet."),
    "height_inches": ("Four inches.", "Seven inches."),
    "weight_digit_1": ("The first digit of my weight is one.", None),
    "weight_digit_2": ("The second digit is three.", None),
    "weight_digit_3": ("The last digit is zero.", None),
    "applicant_email": (
        "My email address is linh dot nguyen at example dot com.",
        "My email address is linh dot n at example dot org.",
    ),
    "p3_destination": ("My destination in the United States is Houston Texas.", None),
    "p3_poe_city_state": ("The city and state is Houston Texas.", None),
    # These seven fall through the generic mutation branches in _wrong_for:
    # the three "_country" fields answer "United States" (13 chars, hits the
    # len>=12 text fallback with no digits to swap); the two visa-location
    # fields and the interpreter business-name field are long free-text with
    # no digits either; the interpreter zip code is a plain "text" field with
    # no validation block, so it renders via the generic "{name} is {answer}"
    # template with RAW digits (not spelled-out words), and the digit-replace
    # branch in _wrong_for silently no-ops because it looks for spelled-out
    # digit words that were never in the say string. Explicit wrong phrasings,
    # same style as the other overrides above.
    "mail_country": ("My mailing country is United States.",
                          "My mailing country is Canada."),
    "phys_country": ("My physical country is United States.",
                          "My physical country is Mexico."),
    "p3_location_applied": (
        "My location where you applied for immigrant visa is Ho Chi Minh City, Vietnam.",
        "My location where you applied for immigrant visa is Hanoi, Vietnam."),
    "p3_location_issued": (
        "My location where immigrant visa was issued is Ho Chi Minh City, Vietnam.",
        "My location where immigrant visa was issued is Bangkok, Thailand."),
}

# Decline phrasings for visible fields the persona leaves EMPTY. Keyed by
# field id where a generic decline reads badly; the generic fallback is
# "I do not have a {spoken_name}." / "That does not apply to me."
_DECLINE_OVERRIDES_EN: dict = {
    "mail_in_care_of": "There is no in care of name, my mail comes directly to me.",
    "accommodation_deaf": "No accommodation, I am not deaf or hard of hearing.",
    "accommodation_blind": "No accommodation, I am not blind or low vision.",
    "accommodation_other": "No, I do not need any other accommodation.",
}
_GENERIC_DECLINE_EN = "I do not have a {name}."
_GENERIC_DECLINE_NA_EN = "That does not apply to me."

# Visible-NA fields where "I do not have X" is wrong and "does not apply" is
# right (statement-ish or block-level fields).
_NA_STYLE_FIELDS = re.compile(r"^(p7_|p8_)")


# --------------------------------------------------------------------------
# Spanish (lang='es') phrasing -- E6 arm, bd polyglot-pdf-0cyu.
#
# The persona ANSWERS SPOKEN IN SPANISH (a Spanish-speaking user filling the
# same I-90), while the EXPECTED canon is UNCHANGED from English (the form is
# filled in English regardless of spoken language -- same slugs, same
# MM/DD/YYYY dates, same digits; see expected_canon(), which takes no lang
# parameter and is shared by both arms unmodified).
#
# Template scheme (value-forward, not a literal translation of the English
# generic template): a Spanish speaker answering an English-voiced assistant
# naturally leads with the VALUE, not the English field name -- so the
# generic templates below never embed field.spoken_name (English) into the
# Spanish sentence. Per field-shape:
#   - digit fields:   "Es {digits spelled in Spanish}."
#   - date fields:     "Es el {Spanish spoken date}."
#   - option fields:   "Selecciono {ENGLISH option label}." -- the label is
#                       kept VERBATIM in English (a realistic bilingual
#                       answer pattern: the option text on an English form
#                       has no natural Spanish slug for the model to map to,
#                       so a real bilingual speaker reads the printed English
#                       label back rather than translating it).
#   - generic/text:    "Es {value}."
#   - declines:        "No tengo eso." (generic) / "Eso no aplica en mi caso."
#                       (NA-style block fields, mirrors _NA_STYLE_FIELDS).
# All plain ASCII (no enye/accents in code strings) -- wordings were chosen to
# avoid enye words where possible (e.g. "fecha de admision" not the accented
# "admision" -- the word itself has no enye; "numero"/"direccion" drop the
# accent only, gTTS 'es' pronounces the unaccented forms acceptably).
# --------------------------------------------------------------------------
_SAY_OVERRIDES_ES: dict = {
    "a_number": (
        "Mi numero de registro de extranjero es A uno dos tres cuatro cinco "
        "seis siete ocho nueve.",
        "Mi numero de registro de extranjero es A nueve ocho siete seis "
        "cinco cuatro tres dos uno.",
    ),
    # Personal names are SPELLED OUT, same rationale as English: an uncommon
    # name spoken to an English-tuned recognizer needs spelling to land.
    "family_name": (
        "Mi apellido actual es Nguyen, se deletrea N G U Y E N.",
        "Mi apellido actual es Tran, se deletrea T R A N.",
    ),
    "given_name": (
        "Mi nombre actual es Linh, se deletrea L I N H.",
        "Mi nombre actual es Lan, se deletrea L A N.",
    ),
    "middle_name": (
        "Mi segundo nombre es Thi, se deletrea T H I.",
        "Mi segundo nombre es Van, se deletrea V A N.",
    ),
    "mother_given_name": (
        "El nombre de mi madre es Lan, se deletrea L A N.",
        "El nombre de mi madre es Mai, se deletrea M A I.",
    ),
    "father_given_name": (
        "El nombre de mi padre es Minh, se deletrea M I N H.",
        "El nombre de mi padre es Duc, se deletrea D U C.",
    ),
    "mail_street": (
        "Mi direccion es cuatro dos cero cero Westheimer Road.",
        "Mi direccion es nueve nueve cero cero Richmond Avenue.",
    ),
    "phys_street": (
        "Mi direccion fisica es cuatro dos cero cero Westheimer Road.",
        "Mi direccion fisica es uno uno cero cero Main Street.",
    ),
    "mail_unit_number": ("Es el apartamento numero doce.",
                                 "Es el apartamento numero catorce."),
    "phys_unit_number": ("Es el apartamento numero doce.",
                                 "Es el apartamento numero quince."),
    "class_of_admission": (
        "Mi clase de admision es I R uno.", "Mi clase de admision es C R uno."),
    "applicant_reads_english": (
        "Selecciono: Un interprete me leyo el formulario en mi idioma.",
        "Selecciono: Yo puedo leer y entender ingles por mi mismo.",
    ),
    "reason_section_a": (
        "Selecciono: Necesito una tarjeta nueva porque mi tarjeta anterior "
        "se perdio.",
        "Selecciono: Necesito una tarjeta nueva porque mi tarjeta actual "
        "esta mutilada.",
    ),
    "status": ("Selecciono: Soy residente permanente legal.",
                     "Selecciono: Soy residente permanente condicional."),
    "name_changed": ("No, mi nombre no ha cambiado.",
                     "Si, mi nombre ha cambiado legalmente."),
    "p3_removal_proceedings": ("No, nunca he estado en un proceso de deportacion.", None),
    "p3_abandoned_status": (
        "No, nunca he presentado el Formulario I-407 ni he abandonado mi estatus.",
        None),
    "accommodation_requested": ("No, no estoy solicitando ninguna adaptacion.", None),
    "ethnicity": ("No soy hispano ni latino.", "Soy hispano o latino."),
    "race": ("Asiatico.", "Blanco."),
    "height_feet": ("Mido cinco pies.", "Mido seis pies."),
    "height_inches": ("Y cuatro pulgadas.", "Y siete pulgadas."),
    "weight_digit_1": ("El primer digito de mi peso es uno.", None),
    "weight_digit_2": ("El segundo digito es tres.", None),
    "weight_digit_3": ("El ultimo digito es cero.", None),
    "applicant_email": (
        "Mi correo electronico es linh punto nguyen arroba example punto com.",
        "Mi correo electronico es linh punto n arroba example punto org.",
    ),
    "p3_destination": ("Mi destino en los Estados Unidos es Houston Texas.", None),
    "p3_poe_city_state": ("La ciudad y el estado es Houston Texas.", None),
    "mail_country": ("Mi pais de correo es Estados Unidos.",
                          "Mi pais de correo es Canada."),
    "phys_country": ("Mi pais fisico es Estados Unidos.",
                          "Mi pais fisico es Mexico."),
    "p3_location_applied": (
        "El lugar donde solicite la visa de inmigrante es Ciudad Ho Chi "
        "Minh, Vietnam.",
        "El lugar donde solicite la visa de inmigrante es Hanoi, Vietnam."),
    "p3_location_issued": (
        "El lugar donde se emitio mi visa de inmigrante es Ciudad Ho Chi "
        "Minh, Vietnam.",
        "El lugar donde se emitio mi visa de inmigrante es Bangkok, Tailandia."),
}

# Decline phrasings for visible fields the persona leaves EMPTY, Spanish arm.
# Mirrors _DECLINE_OVERRIDES_EN field-for-field.
_DECLINE_OVERRIDES_ES: dict = {
    "mail_in_care_of": (
        "No hay nombre de a cargo de, mi correo llega directamente a mi."),
    "accommodation_deaf": "Ninguna adaptacion, no soy sordo ni tengo problemas de audicion.",
    "accommodation_blind": "Ninguna adaptacion, no soy ciego ni tengo baja vision.",
    "accommodation_other": "No, no necesito ninguna otra adaptacion.",
}
_GENERIC_DECLINE_ES = "No tengo eso."
_GENERIC_DECLINE_NA_ES = "Eso no aplica en mi caso."


def _wrong_for(field: dict, say: str, answer, lang: str) -> str:
    """Mechanical unhappy-path mutation. Option fields pick a DIFFERENT option
    label; digit fields reverse the digits; dates shift a month; text swaps to a
    generic alternate. Deterministic (no randomness -- resume-safe)."""
    opts = field.get("options") or []
    if opts and answer is not None:
        others = [o for o in opts
                  if isinstance(o, dict) and str(o.get("value")) != str(answer)]
        if others:
            alt_label = _option_label(field, others[0].get("value"))
            if lang == "es":
                return f"En realidad, {alt_label}."
            return f"Actually, {alt_label}."
    if answer and _is_date_field(field):
        d = datetime.strptime(str(answer), "%Y-%m-%d")
        # Shift one month LATER (December wraps to January of the NEXT year --
        # never earlier, so a date-ordering plant stays a genuine wrongness)
        # and clamp the day to 28 so Feb 31-class ValueErrors cannot occur
        # (fresh-eyes round 1 on this bead).
        month = (d.month % 12) + 1
        year = d.year + (1 if d.month == 12 else 0)
        alt = d.replace(year=year, month=month, day=min(d.day, 28))
        alt_iso = alt.strftime("%Y-%m-%d")
        if lang == "es":
            return f"Fue el {_date_spoken_es(alt_iso)}."
        return f"It was {_date_spoken_en(alt_iso)}."
    digits = re.sub(r"\D", "", str(answer or ""))
    if digits and len(digits) >= 5:
        spelled = _spell_digits(digits, lang)
        reversed_spelled = _spell_digits(digits[::-1], lang)
        if spelled in say:
            return say.replace(spelled, reversed_spelled)
        if digits in say:
            # say rendered via the generic template with RAW digits (the
            # field wasn't recognized as a digit field by _is_digit_field,
            # e.g. a plain "text" field with no validation block) -- swap
            # the raw digit substring instead of the (absent) spelled words.
            return say.replace(digits, digits[::-1])
    if isinstance(answer, str) and answer:
        if lang == "es":
            return f"Es {answer[::-1].title()}." if len(answer) < 12 else say
        return f"It is {answer[::-1].title()}." if len(answer) < 12 else say
    return say


def _phrase_en(field: dict, answer) -> tuple:
    fid = field.get("id", "")
    name = field.get("spoken_name") or field.get("name") or fid

    if answer is None:
        say = _DECLINE_OVERRIDES_EN.get(fid)
        if say is None:
            if _NA_STYLE_FIELDS.match(fid):
                say = _GENERIC_DECLINE_NA_EN
            else:
                say = _GENERIC_DECLINE_EN.format(name=name)
        return say, say  # a decline has no distinct unhappy variant

    if fid in _SAY_OVERRIDES_EN:
        say, wrong = _SAY_OVERRIDES_EN[fid]
        return say, (wrong if wrong is not None
                     else _wrong_for(field, say, answer, "en"))

    if field.get("options"):
        say = f"{_option_label(field, answer)}."
        return say, _wrong_for(field, say, answer, "en")

    if _is_date_field(field):
        say = f"My {name} is {_date_spoken_en(str(answer))}."
        return say, _wrong_for(field, say, answer, "en")

    digits = re.sub(r"\D", "", str(answer))
    if _is_digit_field(field) and digits:
        say = f"My {name} is {_spell_digits(digits, 'en')}."
        return say, _wrong_for(field, say, answer, "en")

    say = f"My {name} is {answer}."
    return say, _wrong_for(field, say, answer, "en")


def _phrase_es(field: dict, answer) -> tuple:
    """Spanish-spoken phrasing. Value-forward templates (see the scheme note
    above _SAY_OVERRIDES_ES) -- never embeds the English spoken_name into the
    generic Spanish sentence."""
    fid = field.get("id", "")

    if answer is None:
        say = _DECLINE_OVERRIDES_ES.get(fid)
        if say is None:
            say = (_GENERIC_DECLINE_NA_ES if _NA_STYLE_FIELDS.match(fid)
                   else _GENERIC_DECLINE_ES)
        return say, say  # a decline has no distinct unhappy variant

    if fid in _SAY_OVERRIDES_ES:
        say, wrong = _SAY_OVERRIDES_ES[fid]
        return say, (wrong if wrong is not None
                     else _wrong_for(field, say, answer, "es"))

    if field.get("options"):
        # Keep the ENGLISH option label verbatim -- a real bilingual answer
        # pattern; the label is what's printed on the (English) form, and the
        # model must map the spoken label back to its slug either way.
        say = f"Selecciono {_option_label(field, answer)}."
        return say, _wrong_for(field, say, answer, "es")

    if _is_date_field(field):
        say = f"Es el {_date_spoken_es(str(answer))}."
        return say, _wrong_for(field, say, answer, "es")

    digits = re.sub(r"\D", "", str(answer))
    if _is_digit_field(field) and digits:
        say = f"Es {_spell_digits(digits, 'es')}."
        return say, _wrong_for(field, say, answer, "es")

    say = f"Es {answer}."
    return say, _wrong_for(field, say, answer, "es")


def _date_spoken_generic(iso: str, lang: str) -> str:
    """Spoken date for a JSON-fixture language: numerals for day/year (gTTS
    reads numerals in the target language), month from the months table."""
    data = multilang_phrases()[lang]
    d = datetime.strptime(iso, "%Y-%m-%d")
    return data["templates"]["date"].format(
        day=d.day, month=data["months"][d.month - 1], year=d.year)


def _wrong_generic(field: dict, say: str, answer, lang: str) -> str:
    """Mechanical unhappy-path mutation for JSON-fixture languages; mirrors
    _wrong_for shape-for-shape (option swap / month shift / digit reverse)."""
    t = multilang_phrases()[lang]["templates"]
    opts = field.get("options") or []
    if opts and answer is not None:
        others = [o for o in opts
                  if isinstance(o, dict) and str(o.get("value")) != str(answer)]
        if others:
            return t["wrong_option"].format(
                label=_option_label(field, others[0].get("value")))
    if answer and _is_date_field(field):
        d = datetime.strptime(str(answer), "%Y-%m-%d")
        month = (d.month % 12) + 1
        year = d.year + (1 if d.month == 12 else 0)
        alt = d.replace(year=year, month=month, day=min(d.day, 28))
        return _date_spoken_generic(alt.strftime("%Y-%m-%d"), lang)
    digits = re.sub(r"\D", "", str(answer or ""))
    if digits and len(digits) >= 5:
        spelled = _spell_digits(digits, lang)
        reversed_spelled = _spell_digits(digits[::-1], lang)
        if spelled in say:
            return say.replace(spelled, reversed_spelled)
        if digits in say:
            return say.replace(digits, digits[::-1])
    if answer is not None and str(answer):
        # Always a REAL mutation (reversed value) -- the plan builder aborts on
        # a degenerate wrong == say, and unlike the en/es arms there are no
        # per-field override tables to fall back on here.
        return t["wrong_value"].format(value=str(answer)[::-1].title())
    return say


def _phrase_generic(field: dict, answer, lang: str) -> tuple:
    """Value-forward phrasing for a JSON-fixture language (bd polyglot-pdf-6mzi).
    Mirrors _phrase_es: never embeds the English spoken_name in the generic
    sentence; option labels are read back in ENGLISH verbatim (the printed-form
    bilingual answer pattern) unless a say_override supplies a native answer."""
    data = multilang_phrases()[lang]
    t = data["templates"]
    fid = field.get("id", "")

    if answer is None:
        say = (data.get("decline_overrides") or {}).get(fid)
        if say is None:
            say = (t["decline_na"] if _NA_STYLE_FIELDS.match(fid)
                   else t["decline"])
        return say, say  # a decline has no distinct unhappy variant

    ov = (data.get("say_overrides") or {}).get(fid)
    if ov:
        say, wrong = ov[0], (ov[1] if len(ov) > 1 else None)
        return say, (wrong if wrong is not None
                     else _wrong_generic(field, say, answer, lang))

    if field.get("options"):
        say = t["option"].format(label=_option_label(field, answer))
        return say, _wrong_generic(field, say, answer, lang)

    if _is_date_field(field):
        say = _date_spoken_generic(str(answer), lang)
        return say, _wrong_generic(field, say, answer, lang)

    digits = re.sub(r"\D", "", str(answer))
    if _is_digit_field(field) and digits:
        say = t["digits"].format(digits=_spell_digits(digits, lang))
        return say, _wrong_generic(field, say, answer, lang)

    say = t["value"].format(value=answer)
    return say, _wrong_generic(field, say, answer, lang)


def phrase(field: dict, answer, lang: str = "en") -> tuple:
    """(say, wrong) spoken phrasings for a field + its persona answer.
    answer=None means a visible field the persona declines (expect-empty).
    Dispatches by lang: 'en'/'es' are code-native; any other lang must have an
    entry in fixtures/multilang_phrases.json (bd polyglot-pdf-6mzi). The
    expected-canon path (expected_canon) is unchanged by lang -- the form fills
    in English regardless of the spoken input language."""
    if lang == "es":
        return _phrase_es(field, answer)
    if lang == "en":
        return _phrase_en(field, answer)
    if lang in multilang_phrases():
        return _phrase_generic(field, answer, lang)
    raise NotImplementedError(
        f"lang={lang!r} is not implemented; use 'en', 'es', or add an entry "
        "to fixtures/multilang_phrases.json.")


# --------------------------------------------------------------------------
# Expected canon
# --------------------------------------------------------------------------
def expected_canon(field: dict, answer):
    """The post-fill value the driver's scorer should expect. Option fields
    expect the SLUG (what the client stores); dates expect MM/DD/YYYY (the
    kit's validation.hint format the model writes); declines expect ''."""
    fid = field.get("id", "")
    if answer is None:
        return ""
    if fid == "a_number":
        return _ANUMBER_EXPECTED
    if field.get("options"):
        return str(answer)
    if _is_date_field(field):
        return _iso_to_mdy(str(answer))
    if fid.endswith("_country") and str(answer) == "United States":
        return ["United States", "USA"]
    if fid.endswith("_streetnumbername"):
        # The persona answer abbreviates ("Rd", "St"); the model writes what was
        # SPOKEN ("Road", "Street"). Accept both renderings.
        full = (str(answer).replace(" Rd", " Road").replace(" St", " Street")
                .replace(" Ave", " Avenue"))
        return [str(answer), full] if full != str(answer) else str(answer)
    digits = re.sub(r"\D", "", str(answer))
    if _is_digit_field(field) and digits:
        return digits
    return str(answer)


# --------------------------------------------------------------------------
# Plan builder
# --------------------------------------------------------------------------
def persona_answers() -> dict:
    """The answer key with the current-kit overrides applied."""
    merged = dict(g1b_answer_key.ANSWER_KEY)
    merged.update(ANSWER_OVERRIDES)
    return merged


def load_schema() -> dict:
    with open(I90_SCHEMA_PATH, encoding="utf-8") as f:
        return json.load(f)


def build_full_form_plan(schema: dict, lang: str = "en") -> dict:
    """Build the full-form plan. Returns:
        {"questions": [ {field_id, say, wrong}, ... ],   # spoken steps
         "expected":  {field_id: canon, ...},            # scorer table
         "auto_apply": [ {field_id, value}, ... ],       # seeded confirmed
         "hidden":    [field_id, ...]}                   # never asked
    Raises SystemExit on any guard violation (abort before live spend)."""
    problems = g1b_answer_key.validate_answer_key()
    if problems:
        raise SystemExit(
            "g1b answer key failed validate_answer_key(); fix before running:\n  "
            + "\n  ".join(str(p) for p in problems))

    answers = persona_answers()
    fields = schema["fields"]
    field_by_id = {f["id"]: f for f in fields}

    # Guard: every override on an option field must be a valid CURRENT option.
    for fid, val in ANSWER_OVERRIDES.items():
        f = field_by_id.get(fid)
        if f is None:
            raise SystemExit(f"ANSWER_OVERRIDES names unknown field {fid}")
        opts = [str(o.get("value")) for o in (f.get("options") or [])
                if isinstance(o, dict)]
        if opts and str(val) not in opts:
            raise SystemExit(
                f"ANSWER_OVERRIDES[{fid}]={val!r} is not a schema option; "
                f"options are {opts}")

    questions: list = []
    expected: dict = {}
    auto_apply: list = []
    hidden: list = []
    answered_so_far: dict = {}  # progressive gate check (ordering invariant)

    for f in fields:
        fid = f["id"]
        answer = answers.get(fid)
        visible = field_visible(f, field_by_id, answers)
        if not visible:
            hidden.append(fid)
            continue

        # Ordering invariant: a visible field's gate must already be satisfied
        # by answers scripted EARLIER (schema order == plan order), otherwise
        # the model could be asked a not-yet-unlocked field mid-run.
        cond = f.get("show_if")
        if cond and not evaluate_show_if(cond, field_by_id, answered_so_far):
            raise SystemExit(
                f"plan ordering violation: {fid} is gated on "
                f"{cond.get('field')} which is answered LATER in schema order")

        if f.get("copy_from") or f.get("type") in AUTO_APPLY_TYPES:
            auto_apply.append({"field_id": fid,
                               "value": "" if answer is None else str(answer)})
            answered_so_far[fid] = answers.get(fid)
            continue

        say, wrong = phrase(f, answer, lang)
        questions.append({"field_id": fid, "say": say, "wrong": wrong})
        expected[fid] = expected_canon(f, answer)
        answered_so_far[fid] = answer

    # Guard: every answered (non-empty-expected) question must have a wrong
    # utterance DISTINCT from say -- a degenerate unhappy-path turn (REJECT
    # then re-hear the identical value) corrupts the unhappy-path measurement
    # (bd polyglot-pdf-3gt9). Declines are exempt: phrase() intentionally
    # returns the same text for both (a decline has no distinct unhappy
    # variant -- see phrase()'s answer=None branch).
    degenerate = [q["field_id"] for q in questions
                  if expected[q["field_id"]] != "" and q["say"] == q["wrong"]]
    if degenerate:
        raise SystemExit(
            "degenerate unhappy-path utterance(s) -- 'wrong' equals 'say' for "
            "answered field(s): " + ", ".join(degenerate)
            + " (fix _wrong_for or add a _SAY_OVERRIDES_EN entry)")

    return {"questions": questions, "expected": expected,
            "auto_apply": auto_apply, "hidden": hidden}


if __name__ == "__main__":
    plan = build_full_form_plan(load_schema())
    print(f"spoken questions: {len(plan['questions'])}")
    print(f"auto-applied (copy_from/signature): {len(plan['auto_apply'])}")
    print(f"hidden (gate unsatisfied): {len(plan['hidden'])}")
    declines = sum(1 for q in plan["questions"] if plan["expected"][q["field_id"]] == "")
    print(f"  of spoken: {len(plan['questions']) - declines} answered, "
          f"{declines} declines (expect-empty)")
    for q in plan["questions"][:8]:
        print(" ", q["field_id"], "->", q["say"])
