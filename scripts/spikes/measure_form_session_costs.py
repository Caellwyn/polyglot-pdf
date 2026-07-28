"""Per-question token/cost measurement instrument (bd polyglot-pdf-4loz, epic hcsl).

Drives the REAL form-filling stack -- FormFillingService + CallbackHandler +
RequestCoordinator + LiveAIGemini, the production system instruction built by
build_form_context_message from the real demo schema, the production
TOOL_DECLARATIONS -- against live Gemini with scripted gTTS audio, simulating
the frontend client (the stateless contract's other half) over a fake
WebSocket. Deploy fidelity per docs/standards/testing.md ("Live-endpoint
probes and spikes"); the one labeled deviation is turn injection via explicit
activity brackets with server VAD neutralized (synthetic audio needs
deterministic turn boundaries; bd h04c ran 51 sessions this way).

Outputs, per run:
  - <out>/costs_<model>_<arm>_<path>_<stamp>.csv -- one row per question 1..N,
    EXACTLY these 11 columns (epic criterion 2): question number, audio in
    tokens, audio in token cost, audio out tokens, audio out token cost, text
    in tokens, text in token cost, text out tokens, text out token cost, total
    tokens, total cost
  - the same name + .meta.json -- run config, per-turn latency (activity_end ->
    first audio byte), per-question tool-call record (compliance), the raw
    prompt-token curve + detected eviction drops, captured errors, and -- for the
    i90 schema -- the G3 fill-correctness score (meta["fill_accuracy"]: per-field
    canon-compared right/wrong + accuracy). G3 (bd polyglot-pdf-jnjj.7) is the
    clean correctness instrument the noisy jnjj.25 confirm-counts could not be --
    it scores whether the reduced-SI (DTI+eviction) arm fills the form as
    CORRECTLY as the full-SI baseline. (The get_field_value recall-lookup arm was
    removed with that tool -- bd polyglot-pdf-p5h2/2wod.)

Arms (--arm):
  unbounded      one session, no compression, no resets (raw growth curve)
  section-reset  the CURRENT production flow: per-section sub-schema, session
                 restart at each section boundary via switch_to_section (the
                 restart + re-greeting tokens are attributed to the FIRST
                 question of the new section -- that IS the cost of advancing)
  sliding-window one session with ContextWindowCompressionConfig on
                 (--trigger/--window)

Question scripts (--path):
  happy    2 turns/question: value, positive confirmation
  unhappy  4 turns/question: wrong value, rejection, corrected value,
           positive confirmation

Audio is gTTS-synthesized once and cached as PCM16@16k under
scripts/spikes/fixtures/audio_cache/ (committed; reruns are network-free).
--synth-only builds the cache and exits without touching the live endpoint.

Run from repo root with GEMINI_API_KEY (a 20-question happy run is ~5-8 min):

    backend/.venv/Scripts/python.exe scripts/spikes/measure_form_session_costs.py \
        --model 2.5 --arm unbounded --path happy
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _rc = getattr(_stream, "reconfigure", None)
    if _rc is not None:
        try:
            _rc(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

import numpy as np  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend import config as _config  # noqa: E402
from backend.config import (  # noqa: E402
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    MODEL_NATIVE_STANDARD_VERTEX,
    get_pricing_for_model,
)
from backend.services.form_filling_service import FormFillingService  # noqa: E402

_SPIKES_DIR = str(Path(__file__).resolve().parent)
if _SPIKES_DIR not in sys.path:
    sys.path.insert(0, _SPIKES_DIR)
import full_form_script as _ffs  # noqa: E402  (stdlib-only sibling module)
import scenario_events as _se  # noqa: E402  (stdlib-only sibling module)

MODELS = {"2.5": MODEL_NATIVE_STANDARD, "3.1": MODEL_NATIVE_PREMIUM}

# Per-model text-sidecar rate table, USD per token (bd polyglot-pdf-0cyu: the
# W6 whole-form gemini-2.5-pro pass, bd polyglot-pdf-gbus/#434, added a SECOND
# text model to the sidecar -- flash-lite for the secretary + lite validator
# windows, pro for the end-of-form pass -- so a single flat TEXT_RATES row
# silently mispriced every pro call at the flash-lite rate. text_ai_usage
# already carries a `model` field (text_ai_gemini._log_usage); key pricing off
# it. Rates dated 2026-07:
#   gemini-2.5-flash-lite: $0.10 in / $0.01 cached-in / $0.40 out per 1M
#     (unchanged from the pre-existing TEXT_RATES row).
#   gemini-2.5-pro (<=200k prompt tier, the only tier this harness's payloads
#     hit): $1.25 in / $0.125 cached-in / $10.00 out per 1M -- the 2026-07
#     Gemini API list price for gemini-2.5-pro (docs/standards/ai-models.md and
#     backend/config.py record no text-model list price for pro; this table is
#     the harness's own sourced record, dated so a future rate change is
#     visible as a diff here rather than a silent drift).
TEXT_RATES_BY_MODEL = {
    "gemini-2.5-flash-lite": {
        "input": 0.10e-6, "cached_input": 0.01e-6, "output": 0.40e-6},
    "gemini-2.5-pro": {
        "input": 1.25e-6, "cached_input": 0.125e-6, "output": 10.00e-6},
}
# Back-compat alias: the flash-lite row, for any caller that still wants a
# single default rate (price_text_usage below; historical CLI/tests).
TEXT_RATES = TEXT_RATES_BY_MODEL["gemini-2.5-flash-lite"]


def _rates_for_model(model: str | None) -> tuple[dict, bool]:
    """Resolve the rate row for a text-sidecar model name. Returns
    (rates, unpriced) -- unpriced=True means the model name was not in the
    table and the run priced it at the HIGHEST known rate (never silently
    under-priced) so build_summary can surface an 'unpriced_model' warning
    instead of a quietly-wrong dollar figure."""
    row = TEXT_RATES_BY_MODEL.get(model or "")
    if row is not None:
        return row, False
    # Unknown model (a future model swap, a typo, or a test double): price at
    # the highest per-token rate across every known row, field by field, so
    # the estimate is never an under-count.
    worst = {
        k: max(r[k] for r in TEXT_RATES_BY_MODEL.values())
        for k in ("input", "cached_input", "output")
    }
    return worst, True


def price_text_usage(prompt_tokens: int, cached_tokens: int,
                     output_tokens: int, model: str | None = None) -> float:
    """USD for one text-sidecar call: cached prompt tokens bill at the cached
    rate, the uncached remainder at the input rate, output at the output rate.
    `model` selects the rate row (TEXT_RATES_BY_MODEL); omitted/unknown falls
    back to the flash-lite row for back-compat with pre-per-model callers."""
    prompt = max(0, int(prompt_tokens or 0))
    cached = max(0, min(int(cached_tokens or 0), prompt))
    out = max(0, int(output_tokens or 0))
    rates = TEXT_RATES if model is None else _rates_for_model(model)[0]
    return ((prompt - cached) * rates["input"]
            + cached * rates["cached_input"]
            + out * rates["output"])

# Schema sources (bd polyglot-pdf-jnjj.24). The harness was hardcoded to the DEMO
# schema, which is non-representative (flat 'description' on 2/174 fields, no nested
# 'help', no parts/sections arrays). The REAL I-90 (form-kits/i-90/schema.json:
# parts/sections arrays, help.instructions on 132/132 fields) is what forward
# cost/JIT/DTI/secretary measurement must use. --schema selects the source +
# its matching question plan.
DEMO_SCHEMA_PATH = _REPO_ROOT / "frontend" / "public" / "adult_intake_demo_schema.json"
I90_SCHEMA_PATH = _REPO_ROOT / "form-kits" / "i-90" / "schema.json"
AUDIO_CACHE = Path(__file__).resolve().parent / "fixtures" / "audio_cache"
_AUDIO_RATE = 16000
_CHUNK_MS = 40

CONFIRM_YES = "Yes, that's correct."
REJECT = "No, that's not right."

# W2 window geometry (bd polyglot-pdf-kxkw), mirrored from the LANDED client
# constants WebFormConnection.VALIDATOR_WINDOW_SIZE / _STRIDE
# (webFormConnection.ts:264-265): window k covers schema-field-order indices
# [k*stride, k*stride+size).
WEBFORM_VALIDATOR_WINDOW_SIZE = 20
WEBFORM_VALIDATOR_WINDOW_STRIDE = 10

# The DEMO 20-question plan: 12 client-info + 5 reasons + 3 living-situation fields
# from the demo schema, in schema order, with realistic FICTIONAL answers
# (no real PII). "wrong" is the unhappy path's first (rejected) value.
DEMO_QUESTIONS = [
    {"field_id": "firstName", "say": "My first name is Maria.",
     "wrong": "My first name is Mario."},
    {"field_id": "middleName", "say": "My middle name is Elena.",
     "wrong": "My middle name is Elaine."},
    {"field_id": "lastName", "say": "My last name is Vasquez.",
     "wrong": "My last name is Vargas."},
    {"field_id": "preferredName", "say": "Please call me Mari.",
     "wrong": "Please call me Ria."},
    {"field_id": "pronouns", "say": "My pronouns are she her.",
     "wrong": "My pronouns are they them."},
    {"field_id": "dob",
     "say": "I was born on March fourteenth, nineteen eighty eight.",
     "wrong": "I was born on May fourteenth, nineteen eighty eight."},
    {"field_id": "age", "say": "I am thirty eight years old.",
     "wrong": "I am thirty five years old."},
    {"field_id": "genderIdentity", "say": "Cisgender female.",
     "wrong": "Non binary."},
    {"field_id": "sexualOrientation", "say": "I am heterosexual.",
     "wrong": "I am bisexual."},
    {"field_id": "maritalStatus", "say": "I am married.",
     "wrong": "I am single."},
    {"field_id": "partnerSpouseName",
     "say": "My spouse's name is Daniel Vasquez.",
     "wrong": "My spouse's name is David Vasquez."},
    {"field_id": "legalCustodian", "say": "I do not have a legal custodian.",
     "wrong": "My legal custodian is my mother."},
    {"field_id": "mandatedBy", "say": "I was not mandated by anyone, I came voluntarily.",
     "wrong": "I was mandated by the court."},
    {"field_id": "otherReason", "say": "I have been feeling anxious about work.",
     "wrong": "I have been feeling sad about school."},
    {"field_id": "problemStart", "say": "The problems began about two years ago.",
     "wrong": "The problems began about two months ago."},
    {"field_id": "desiredChanges",
     "say": "I want to manage my anxiety better and sleep through the night.",
     "wrong": "I want to stop arguing with my coworkers."},
    {"field_id": "strengths",
     "say": "I am persistent and I have a supportive family.",
     "wrong": "I am creative and I have a good sense of humor."},
    {"field_id": "primaryHousehold",
     "say": "I live with my spouse and our daughter.",
     "wrong": "I live alone."},
    {"field_id": "householdMembers",
     "say": "There are three people in my household.",
     "wrong": "There are five people in my household."},
    {"field_id": "member1_name",
     "say": "The first household member is Daniel Vasquez.",
     "wrong": "The first household member is David Vasquez."},
]

# The REAL I-90 question plan (bd polyglot-pdf-jnjj.24): the first 3 sections of
# form-kits/i-90/schema.json -- Part 1 "Information About You" (sec 1), the mailing
# address (sec 2), and the physical address (sec 3). FICTIONAL answers (no real PII).
# spoken_name is the natural phrasing the model asks by. The plan scripts EVERY
# field that is visible in a section given the scripted conditional answers, in
# SCHEMA ORDER, so the section-reset SI's field list and the next-field hint never
# contradict -- otherwise the model could ask for an SI-listed field the plan never
# answers and stall the run (fresh-eyes for this bead):
#   - the name-change radio (p1_checkbox4) is answered "no", so the show_if
#     previous-name fields (p1_line5a/b/c) stay HIDDEN and are correctly NOT scripted;
#   - each unit-type radio (p1_unit_type6c/7b) IS answered, which makes its show_if
#     apt-number field (p1_line6c/7b_aptsteflrnumber) VISIBLE -- so that apt-number
#     field IS scripted (a real apartment filer fills it);
#   - the always-visible optional province/postalcode fields are scripted too, with
#     a US-filer "not applicable" answer, so no visible field is left unanswered.
I90_QUESTIONS = [
    # --- Section 1: Part 1 - Information About You ---
    # Answer the A-Number as BARE DIGITS (no "A" prefix): the a_number A-strip
    # normalizer is currently broken (bd polyglot-pdf-cn0e -- it reads top-level
    # format_preset but the schema nests it under validation.format_preset), so an
    # "A..."-prefixed answer fails the ^\d{7,9}$ pattern and adds validation noise to
    # the cost measurement. Bare digits validate cleanly today; revert to a natural
    # "A12345678" phrasing once cn0e lands.
    {"field_id": "p1_line1_aliennumber", "say": "My alien registration number is one two three four five six seven eight.",
     "wrong": "My alien registration number is eight seven six five four three two one."},
    # USCIS online account number is EXACTLY 12 digits (the field's min/max_length).
    # The old 10-digit fixture was itself invalid and would fail length even with
    # clean transcription (bd polyglot-pdf-jnjj.40 -- the harness answer, not just
    # the model, was wrong on this field).
    {"field_id": "p1_line2_acctidentifier", "say": "My USCIS online account number is 1 2 3 4 5 6 7 8 9 0 1 2.",
     "wrong": "My USCIS online account number is 9 8 7 6 5 4 3 2 1 0 9 8."},
    {"field_id": "p1_line3a_familyname", "say": "My current family name is Vasquez.",
     "wrong": "My current family name is Vargas."},
    {"field_id": "p1_line3b_givenname", "say": "My current given name is Maria.",
     "wrong": "My current given name is Mario."},
    {"field_id": "p1_line3c_middlename", "say": "My current middle name is Elena.",
     "wrong": "My current middle name is Elaine."},
    {"field_id": "p1_checkbox4", "say": "No, my name has not changed.",
     "wrong": "Yes, my name has changed."},
    # --- Section 2: mailing address ---
    {"field_id": "p1_line6a_incareofname", "say": "In care of Daniel Vasquez.",
     "wrong": "In care of David Vasquez."},
    {"field_id": "p1_line6b_streetnumbername", "say": "Twelve thirty four Maple Street.",
     "wrong": "Fifty six seventy eight Oak Street."},
    {"field_id": "p1_unit_type6c_unit", "say": "Apartment.",
     "wrong": "Suite."},
    # apt-number is show_if (unit_type is_not_empty) -- now visible, so scripted.
    {"field_id": "p1_line6c_aptsteflrnumber", "say": "Apartment number twelve B.",
     "wrong": "Apartment number fourteen C."},
    {"field_id": "p1_line6d_cityortown", "say": "My mailing city is Austin.",
     "wrong": "My mailing city is Houston."},
    {"field_id": "p1_line6e_state", "say": "Texas.",
     "wrong": "Florida."},
    {"field_id": "p1_line6f_zipcode", "say": "My mailing zip code is seven three seven zero one.",
     "wrong": "My mailing zip code is seven seven zero zero one."},
    {"field_id": "p1_line6g_province", "say": "I do not have a province, I am in the United States.",
     "wrong": "My province is Ontario."},
    {"field_id": "p1_line6h_postalcode", "say": "I do not have a postal code, I am in the United States.",
     "wrong": "My postal code is K1A 0B1."},
    {"field_id": "p1_line6i_country", "say": "United States.",
     "wrong": "Canada."},
    # --- Section 3: physical address (schema order: ...zipcode, province, postalcode, country) ---
    {"field_id": "p1_line7a_streetnumbername", "say": "Twelve thirty four Maple Street.",
     "wrong": "Ninety nine Pine Avenue."},
    {"field_id": "p1_unit_type7b_unit", "say": "Apartment.",
     "wrong": "Floor."},
    {"field_id": "p1_line7b_aptsteflrnumber", "say": "Apartment number twelve B.",
     "wrong": "Apartment number fifteen D."},
    {"field_id": "p1_line7c_cityortown", "say": "My physical city is Austin.",
     "wrong": "My physical city is Dallas."},
    {"field_id": "p1_line7d_state", "say": "Texas.",
     "wrong": "Arizona."},
    {"field_id": "p1_line7e_zipcode", "say": "My physical zip code is seven three seven zero one.",
     "wrong": "My physical zip code is eight five zero zero one."},
    {"field_id": "p1_line7f_province", "say": "I do not have a province, I am in the United States.",
     "wrong": "My province is Quebec."},
    {"field_id": "p1_line7g_postalcode", "say": "I do not have a postal code, I am in the United States.",
     "wrong": "My postal code is K1A 0B1."},
    {"field_id": "p1_line7h_country", "say": "United States.",
     "wrong": "Mexico."},
    # --- Section 4: Part 1.4 Additional Information (bd polyglot-pdf-ctu8) ---
    # Added to take the plan past 30 questions so a 30-question CONTINUOUS run
    # (the ctu8 candidate arm) fits inside it. The WHOLE 9-field section is
    # scripted (no field skipped) to keep the every-visible-field invariant for
    # the section-reset arms; none of these fields is show_if-conditional.
    # Same fictional Maria Vasquez persona (no real PII).
    {"field_id": "p1_line8_male", "say": "I am female.",
     "wrong": "I am male."},
    {"field_id": "p1_line9_dateofbirth", "say": "My date of birth is March fifth, nineteen ninety.",
     "wrong": "My date of birth is April sixth, nineteen ninety one."},
    {"field_id": "p1_line10_citytownofbirth", "say": "I was born in Guadalajara.",
     "wrong": "I was born in Monterrey."},
    {"field_id": "p1_line11_countryofbirth", "say": "My country of birth is Mexico.",
     "wrong": "My country of birth is Guatemala."},
    {"field_id": "p1_line12_mothergivenname", "say": "My mother's given name is Rosa.",
     "wrong": "My mother's given name is Rita."},
    {"field_id": "p1_line13_fathergivenname", "say": "My father's given name is Carlos.",
     "wrong": "My father's given name is Miguel."},
    # Class of admission is a 3-character code (help.instructions); IR6 is a real
    # LPR category, spoken letter-by-letter so gTTS renders it cleanly.
    {"field_id": "p1_line14_classofadmission", "say": "My class of admission is I R six.",
     "wrong": "My class of admission is C R one."},
    {"field_id": "p1_line15_dateofadmission", "say": "My date of admission was June tenth, twenty fifteen.",
     "wrong": "My date of admission was July ninth, twenty sixteen."},
    {"field_id": "p1_line16_ssn", "say": "My social security number is one two three four five six seven eight nine.",
     "wrong": "My social security number is nine eight seven six five four three two one."},
]

# G3 fill-accuracy scoring (bd polyglot-pdf-jnjj.7). The EXPECTED canonical value
# each field should hold after a correct fill -- the answer extracted from the
# question's "say" prompt (NOT the spoken sentence). Scoring normalizes both the
# model-written value and this expected value (see _canon_value) before comparing,
# so "Apartment" vs "apartment" or "737 01" vs "73701" match. Keyed by field_id;
# any I90 field absent here is scored leniently (non-empty == filled) and flagged.
I90_EXPECTED = {
    "p1_line1_aliennumber": "12345678",
    "p1_line2_acctidentifier": "123456789012",
    "p1_line3a_familyname": "Vasquez",
    "p1_line3b_givenname": "Maria",
    "p1_line3c_middlename": "Elena",
    # Radio/select fields store the CANONICAL option VALUE -- that is what the
    # frontend writes and what get_form_state returns. Scoring against the spoken
    # label would mark a CORRECT structured fill as wrong (the first-draft fixture
    # bug). NOTE the option-value VOCABULARY migrated once already: pre-v2 kits
    # stored widget ids / state codes ("P1_checkbox4[1]", "TX"); the v2 slug
    # migration (PR #333) re-minted them to semantic slugs ("apartment", "texas").
    # Runs recorded BEFORE that migration were correctly scored against the old
    # canon; this table now holds the CURRENT kit's slugs, and
    # _assert_expected_canon_matches_schema (called at startup) fails loudly if
    # the kit's option vocabulary drifts again (bd jnjj.7 -- the stale canon
    # silently under-scored the 2026-07-11 baseline arm by ~5 fields).
    "p1_checkbox4": "no_proceed_to_item_numbers_6_a_6_c",  # "No, name has not changed"
    "p1_line6a_incareofname": "Daniel Vasquez",
    "p1_line6b_streetnumbername": "1234 Maple Street",
    "p1_unit_type6c_unit": "apartment",
    "p1_line6c_aptsteflrnumber": "12B",
    "p1_line6d_cityortown": "Austin",
    "p1_line6e_state": "texas",                    # select stores the option slug
    "p1_line6f_zipcode": "73701",
    "p1_line6g_province": "",
    "p1_line6h_postalcode": "",
    "p1_line6i_country": ["United States", "USA"],
    "p1_line7a_streetnumbername": "1234 Maple Street",
    "p1_unit_type7b_unit": "apartment",
    "p1_line7b_aptsteflrnumber": "12B",
    "p1_line7c_cityortown": "Austin",
    "p1_line7d_state": "texas",                    # select stores the option slug
    "p1_line7e_zipcode": "73701",
    "p1_line7f_province": "",
    "p1_line7g_postalcode": "",
    "p1_line7h_country": ["United States", "USA"],
    # Section 4 (Part 1.4 Additional Information, bd polyglot-pdf-ctu8).
    "p1_line8_male": "female",                     # radio stores the option slug
    "p1_line9_dateofbirth": "03/05/1990",          # MM/DD/YYYY (validation.hint)
    "p1_line10_citytownofbirth": "Guadalajara",
    "p1_line11_countryofbirth": "Mexico",
    "p1_line12_mothergivenname": "Rosa",
    "p1_line13_fathergivenname": "Carlos",
    "p1_line14_classofadmission": "IR6",
    "p1_line15_dateofadmission": "06/10/2015",
    "p1_line16_ssn": "123456789",
}

_WORD_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
}


def _canon_value(v) -> str:
    """Canonicalize a field value for fill-accuracy comparison (bd jnjj.7).

    Lowercase, map SINGLE spelled-out digits (zero-nine) to numerals, strip ALL
    non-alphanumerics. So "73701"/"737 01", "Apartment"/"apartment", "12 B"/"12-B"
    all collapse to the same key. Deliberately lossy -- it scores whether the right
    DATA landed, not punctuation/format (format is the normalizer layer's job, not
    G3's). NOTE: only SINGLE-digit words map (not "twelve"/"thirty") -- the model
    transcribes spoken multi-digit numbers to numerals itself before writing the
    field, so I90_EXPECTED holds the numeral form the model actually writes
    ("1234 Maple Street", "12B"); a spelled-out write would correctly score as a
    miss (the model failed to transcribe)."""
    if v is None:
        return ""
    s = str(v).strip().lower()
    toks = [_WORD_DIGITS.get(t, t) for t in re.split(r"\s+", s) if t]
    joined = "".join(toks)
    return re.sub(r"[^a-z0-9]", "", joined)


def _jsonable(obj):
    """Best-effort JSON-safe copy for the debug artifact (bd jnjj.39). Tool args /
    responses are plain dicts/strings in practice, but a stray non-serializable
    value (e.g. a sentinel) must never crash the debug write -- coerce it to its
    repr rather than raising."""
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        if isinstance(obj, dict):
            return {str(k): _jsonable(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_jsonable(v) for v in obj]
        return repr(obj)


def attribute_tools_by_window(tool_io, q_windows):
    """Reliable per-question tool attribution (bd jnjj.39 criterion 2).

    The legacy per_question_tools stamps each async tool call with the loop's
    mutable current_q, which under-attributes when calls land after the loop moved
    on. Instead, bucket each captured tool call by which question's TIME WINDOW
    (t_start..t_end of that question's turns) its timestamp falls in. Calls before
    q1's window (e.g. greeting) bucket to q0. Returns {q: [tool_names...]}."""
    return {q: [r["tool"] for r in recs]
            for q, recs in _attribute_records_by_window(tool_io, q_windows).items()}


def _attribute_records_by_window(tool_io, q_windows):
    """Bucket each tool-I/O RECORD (not just its name) by question time window.

    Shared by the tool-name attribution above and the per-question tool_io in the
    debug artifact, so the two are ALWAYS consistent: a call attributed to qN by
    tools_reliable appears in qN's tool_io with its args/response (Codex PR #246 --
    a strict in-window filter previously pushed a late call's args/response to
    out_of_window even though tools_reliable claimed qN owned it). A call that lands
    after a window closes attributes to the last window it passed; one before q1's
    window buckets to q0. Returns {str(q): [record, ...]}."""
    out: dict[str, list[dict]] = {}
    for rec in tool_io:
        ts = rec["ts"]
        q = 0
        for w in q_windows:
            if w["t_start"] <= ts <= w["t_end"]:
                q = w["q"]
                break
            if ts > w["t_end"]:
                q = w["q"]  # after this window's end, before the next starts
        out.setdefault(str(q), []).append(rec)
    return out


def _assert_expected_canon_matches_schema(schema_fields: dict, expected: dict) -> None:
    """Fail LOUDLY at startup if the expected canon drifted from the kit.

    The i-90 option-value vocabulary migrated once already (widget ids ->
    semantic slugs, PR #333) and the stale I90_EXPECTED silently under-scored
    a whole arm (bd jnjj.7). For every expected value on an option-bearing
    field, require it to be one of the field's CURRENT option values, so the
    next vocabulary migration aborts the run instead of corrupting the data."""
    problems = []
    for fid, exp in expected.items():
        f = schema_fields.get(fid)
        if not f:
            # A canon entry keyed on a field the kit no longer HAS is drift
            # too (a deleted/renamed field), not just a re-mapped option
            # vocabulary (fresh-eyes on this bead).
            problems.append(f"{fid}: keyed in expected but absent from the schema")
            continue
        # Mirror _hint_for's vocabulary read (options OR allowed_values) so a
        # field expressing its choices via allowed_values is guarded too
        # (outer review on this bead).
        raw_opts = f.get("options") or f.get("allowed_values") or []
        opts = [o.get("value") if isinstance(o, dict) else o for o in raw_opts]
        opts = [o for o in opts if o is not None]
        if not opts:
            continue
        vals = exp if isinstance(exp, (list, tuple)) else [exp]
        for v in vals:
            if v != "" and v not in opts:
                problems.append(f"{fid}: expected {v!r} not in options {opts}")
    if problems:
        raise SystemExit(
            "I90_EXPECTED canon has drifted from the kit schema (option-value "
            "vocabulary changed?). Fix the table before running -- a stale "
            "canon silently mis-scores fill accuracy:\n  " + "\n  ".join(problems))


def score_fill_accuracy(client, plan, expected) -> dict:
    """Per-field fill correctness for one arm (bd jnjj.7 / G3).

    For each scripted field: did the model write a value that canon-matches the
    expected answer? Returns counts + a per-field detail list. Empty-expected
    fields (US-filer province/postal "not applicable") are correct when the model
    left them blank OR wrote an explicit empty -- the harness scripts a spoken
    "I do not have a province" answer, so a model that correctly declines to fill
    is RIGHT, and a model that invents a value is WRONG."""
    detail = []
    matched = 0
    for q in plan:
        fid = q["field_id"]
        written = client.state.get(fid, {}).get("value")
        exp = expected.get(fid)
        if exp is None:
            ok = written not in (None, "")  # lenient: unknown field, count as filled
            scored = "lenient"
        elif exp == "":
            canon = _canon_value(written)
            # Correct to leave blank. For a CHECKBOX decline, an explicit
            # false-ish write is the same correct end state (the box is
            # unchecked); only a truthy write is a wrong answer (E1 finding,
            # bd filed: the model sometimes CHECKS a declined checkbox).
            is_checkbox = (client.schema_fields.get(fid) or {}).get("type") == "checkbox"
            ok = canon == "" or (is_checkbox and canon in ("false", "unchecked", "no", "0"))
            scored = "expect-empty"
        elif isinstance(exp, (list, tuple)):
            # Any-of: fields with several equally-correct renderings (e.g. a text
            # country field the model may write as "United States" OR "USA").
            ok = _canon_value(written) in {_canon_value(e) for e in exp}
            scored = "any-of"
        else:
            ok = _canon_value(written) == _canon_value(exp)
            scored = "exact"
        matched += 1 if ok else 0
        detail.append({"field_id": fid, "expected": exp, "written": written,
                       "ok": ok, "scored": scored})
    return {"matched": matched, "total": len(plan),
            "accuracy": round(matched / len(plan), 4) if plan else 0.0,
            "detail": detail}


# --schema registry: source path + matching question plan. Default is "demo" for
# back-compat with the pre-jnjj.24 callers; "i90" is the production-faithful set.
SCHEMAS = {
    "demo": {"path": DEMO_SCHEMA_PATH, "questions": DEMO_QUESTIONS, "expected": {}},
    "i90": {"path": I90_SCHEMA_PATH, "questions": I90_QUESTIONS,
            "expected": I90_EXPECTED},
}

CSV_COLUMNS = [
    "question number",
    "audio in tokens", "audio in token cost",
    "audio out tokens", "audio out token cost",
    "text in tokens", "text in token cost",
    "text out tokens", "text out token cost",
    "total tokens", "total cost",
]


# ---------------------------------------------------------------- audio cache

def synth_cached(text: str, lang: str = "en") -> bytes:
    """gTTS -> mono PCM16 @ 16 kHz, disk-cached so committed runs are repeatable.

    lang parameterizes the SPOKEN language (the E6 Spanish arm synthesizes the
    persona's answers with lang='es'). English keeps the legacy text-only cache
    key so the whole committed fixture cache stays valid; other languages key
    on lang|text."""
    AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
    key_src = text if lang == "en" else f"{lang}|{text}"
    key = hashlib.sha1(key_src.encode("utf-8")).hexdigest()[:16]
    cached = AUDIO_CACHE / f"{key}.pcm"
    if cached.exists():
        return cached.read_bytes()
    from gtts import gTTS
    import soundfile as sf

    # Harness --lang values are full_form_script phrase keys; a few differ from
    # gTTS's code ("zh" -> "zh-CN"). Cache key stays on the harness lang.
    gtts_lang = {"zh": "zh-CN"}.get(lang, lang)
    buf = io.BytesIO()
    gTTS(text, lang=gtts_lang).write_to_fp(buf)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != _AUDIO_RATE:
        n_out = int(len(y) * _AUDIO_RATE / sr)
        y = np.interp(np.linspace(0, len(y), n_out, endpoint=False),
                      np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    cached.write_bytes(pcm)
    return pcm


def _pcm_chunks(pcm: bytes) -> list[bytes]:
    n = int(_AUDIO_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


# ------------------------------------------------------------- schema helpers

def load_schema(schema_key: str = "demo") -> dict:
    return json.loads(SCHEMAS[schema_key]["path"].read_text(encoding="utf-8"))


def sections_in_plan(schema: dict, plan: list[dict]) -> list[dict]:
    """Ordered distinct sections covered by the plan, with labels from the schema.

    Label resolution prefers, in order: a field's own `section_label` (the demo
    schema shape), then the schema-root `sections[]` entry's `label` (the I-90 shape
    -- its fields carry no section_label, so without this the SI would announce the
    raw snake_case section_id like "part_1_2_addresses" instead of the production
    "Part 1.2 Mailing Address"; bd polyglot-pdf-jnjj.24 fresh-eyes), then the id.
    """
    by_id = {f["id"]: f for f in schema["fields"]}
    section_labels = {s.get("id"): s.get("label")
                      for s in schema.get("sections", []) if s.get("id")}
    seen: list[dict] = []
    for q in plan:
        f = by_id[q["field_id"]]
        sid = f.get("section_id") or "section-1"
        if not any(s["id"] == sid for s in seen):
            label = f.get("section_label") or section_labels.get(sid) or sid
            seen.append({"id": sid, "label": label, "number": len(seen) + 1})
    return seen


def section_subschema(schema: dict, section_id: str) -> dict:
    """What the production frontend hands the backend per section: that
    section's fields only, same metadata."""
    return {
        "form_metadata": schema.get("form_metadata", {}),
        "fields": [f for f in schema["fields"]
                   if (f.get("section_id") or "section-1") == section_id],
    }


def jit_handshake_schema(sub: dict, section_id: str, section_label: str) -> dict:
    """The JIT-shaped schema the backend synthesizes from a handshake_jit, post-A2
    (bd polyglot-pdf-jnjj.9). Mirrors frontend getJITHandshakePayload +
    websocket_routes' JIT branch: a manifest carrying the full section
    field_id|spoken_name pairs, plus only the FIRST field's full schema in `fields`
    (the rest arrive on demand). This is what build_form_context consumes in JIT
    mode -- so the cost harness's section-reset-jit arm measures the REAL repaired
    JIT SI, not the full per-section dump."""
    section_fields = sub["fields"]
    manifest_fields = [
        {"field_id": f["id"], "spoken_name": f.get("spoken_name", f.get("name", f["id"]))}
        for f in section_fields
    ]
    first_field = section_fields[0] if section_fields else None
    return {
        "source": "web",
        "jit_mode": True,
        "form_metadata": sub.get("form_metadata", {}),
        # JIT mode carries only the first field's full schema; the rest are in the
        # manifest (id|spoken_name) and stream in via the confirm_field drip.
        "fields": [first_field] if first_field else [],
        "manifest": {
            "current_section": {
                "section_id": section_id,
                "section_label": section_label,
                "fields": manifest_fields,
            },
            "previous_sections": [],
            "parts": [{"id": section_id, "order": 1, "label": section_label}],
        },
        "loaded_field_ids": [],
        "parts": [{"id": section_id, "order": 1, "label": section_label}],
    }


def _hint_for(field: dict, order: int) -> str:
    """The frontend's hint format (frontend/src/navigation.ts)."""
    required = ", required" if field.get("required") else ""
    options = field.get("options") or field.get("allowed_values")
    opt = f", options: [{', '.join(map(str, options))}]" if options else ""
    return (f"Next field to fill is #{order}: '{field.get('name', field['id'])}' "
            f"(field_id: '{field['id']}', type: {field.get('type', 'text')}"
            f"{required}{opt})")


# ----------------------------------------------------------- client simulator

class FakeClientWebSocket:
    """Stands in for both the WebSocket and the frontend client: owns the field
    state (the stateless contract's client half) and answers the coordinator's
    synchronous round-trips (get_form_state / get_next_field_hint /
    confirm_field) the way webFormConnection does."""

    def __init__(self, schema: dict, plan: list[dict], dti_mode: bool = False):
        self.schema_fields = {f["id"]: f for f in schema["fields"]}
        self.schema_field_order = [f["id"] for f in schema["fields"]]
        self.plan = plan
        self.active_field_ids: list[str] = [q["field_id"] for q in plan]
        self.state: dict[str, dict] = {}
        self.service: FormFillingService | None = None
        self.first_audio_at: float | None = None
        # Stress-test seams (bd polyglot-pdf-eh1h). pinned_field_id mirrors the
        # frontend's pinField: switch_to_field pins the target so every
        # next-field consumer returns it first until confirmed (a pin on an
        # already-confirmed field is dormant until a value update resets
        # confirmed -- the correction flow). validation_results records every
        # validation_result envelope the harness pushed back to this client;
        # steered markers live per-field in self.state (client-owned marker,
        # mirroring markFieldsSteered). switch_events/skip_events record the
        # coordinator round-trips for seam-latency scoring.
        self.pinned_field_id: str | None = None
        self.validation_results: list[dict] = []
        self.switch_events: list[dict] = []
        self.skip_events: list[dict] = []
        self.sent_messages: list[str] = []
        # W2 (bd polyglot-pdf-kxkw, mirrored bd polyglot-pdf-0cyu): settledness-
        # window indices already sent as validate_windows (mirrors the client's
        # persisted state.validatedWindowIndices). A window index, once sent,
        # never re-fires.
        self.validated_window_indices: set[int] = set()
        # W3 (bd polyglot-pdf-pr3i, mirrored 0cyu): the report-only validator's
        # findings queue (mirrors state.validatorFindingsQueue), deduped by
        # field-id SET, plus the single-flight drain guard (mirrors
        # WebFormConnection.drainInFlight). drain_results records every
        # drain_findings_result this client received (t_enqueue/t_drain_submit/
        # t_drain_result timestamps live on the matching entries below).
        self.validator_findings_queue: list[dict] = []
        self.drain_in_flight: bool = False
        self.drain_results: list[dict] = []
        self.drain_tasks: list = []
        self._pending_drain_rec: dict | None = None
        # validate_windows call records (mirrors ValidationSeam.records) +
        # their async tasks (drained at run end / pre-reconnect, same as the
        # drain_tasks above).
        self.validation_records: list[dict] = []
        self.window_tasks: list = []
        # bd jnjj.39 debug mode: collect the model's OUTPUT transcript chunks (each
        # {"type":"transcript"} message) with a timestamp, joined per-question later
        # by time window. Populated only when start_session was called with
        # send_transcript=True (the --debug path). LOCAL-ONLY -- transcripts are user
        # speech (PHI); the harness is a never-deployed spike.
        self.transcript_chunks: list[dict] = []
        # DTI (bd polyglot-pdf-jnjj.25): in DTI mode the client owns the schema and
        # supplies the next field's FULL schema on next_field_hint_response, which
        # the backend renders into the confirm_field next_field_guidance. Mirrors the
        # production frontend (webFormConnection.handleGetNextFieldHintRequest +
        # getFieldSchema). Off for the section-reset/JIT arms.
        self.dti_mode = dti_mode
        # GoAway (bd polyglot-pdf-c5t / ctu8): the Vertex Live connection is capped
        # at ~9-10 min and announces the close with a go_away message the backend
        # forwards to the client. Production's frontend pre-emptively reconnects;
        # the continuous arm's driver loop does the same when this flag is set.
        self.go_away_pending = False

    # -- WebSocket surface the backend touches
    async def accept(self):
        return None

    async def close(self, *a, **k):
        return None

    async def send_text(self, _data):
        return None

    async def send_bytes(self, _data: bytes):
        if self.first_audio_at is None:
            self.first_audio_at = time.monotonic()

    @staticmethod
    def _same_field_value(a, b) -> bool:
        """Mirror SchemaFormStateManager._sameFieldValue (W4, bd polyglot-pdf-
        ny4s, schemaFormState.ts:277): value-equality for the steered re-arm
        decision. Empty-ish (None/''/all-blank-list) both sides -> same; a
        checkbox-group list compares as an order-INSENSITIVE set (the real
        CheckboxField.handleToggle APPENDS a re-checked value, so a re-checked
        box can land in a different order); everything else compares by ==."""
        def _is_empty(v) -> bool:
            return (v is None or v == ""
                    or (isinstance(v, list) and all(x in (None, "") for x in v)))
        a_empty, b_empty = _is_empty(a), _is_empty(b)
        if a_empty and b_empty:
            return True
        if a_empty != b_empty:
            return False
        if isinstance(a, list) or isinstance(b, list):
            def _clean(v):
                items = v if isinstance(v, list) else [v]
                return sorted(str(x) for x in items if x not in (None, ""))
            return _clean(a) == _clean(b)
        return a == b

    async def send_json(self, msg: dict):
        mtype = msg.get("type")
        self.sent_messages.append(mtype or "?")
        if mtype == "form_updated":
            data = msg.get("data") or {}
            form_state = data.get("form_state") or {}
            for fid, val in form_state.items():
                value = val.get("value") if isinstance(val, dict) else val
                # Apply EMPTY-STRING values too (mirror production, bd w3ic): an
                # optional field the user declines is filled with '' and then
                # confirmed -- the SI instructs exactly that flow. Dropping ''
                # here made that flow unsatisfiable (confirm -> no_value -> the
                # model re-fills '' -> infinite loop; wedged the first 30q
                # continuous run at the optional postal-code field).
                if fid in self.schema_fields and value is not None:
                    entry = self.state.setdefault(fid, {})
                    prior_value = entry.get("value")
                    value_changed = not self._same_field_value(prior_value, value)
                    # A VALUE CHANGE resets confirmed (mirror the frontend's
                    # updateField): the correction flow re-fills a confirmed
                    # field, which must un-confirm it so the pin re-activates
                    # and confirm_field can re-confirm the new value.
                    if value_changed:
                        entry["confirmed"] = False
                    # W4 (bd polyglot-pdf-ny4s): RE-ARM the steered marker on a
                    # genuine value change; carry it forward unchanged on a
                    # same-value re-write (confirm-without-change preserves it,
                    # matching updateField's carrySteered rule -- schemaFormState.
                    # ts:363-365). A same-value re-write is exactly the "both are
                    # intentional" confirm path: no value moved, so the field must
                    # NOT re-enter the validator net (no-nagging guarantee).
                    if value_changed:
                        entry["steered"] = False
                    entry["value"] = value
                    entry.setdefault("confirmed", False)
        elif mtype == "get_form_state":
            rid = msg.get("request_id")
            want = msg.get("field_ids")
            if want:
                snapshot = {fid: {"value": self.state[fid].get("value"),
                                  "confirmed": self.state[fid].get("confirmed", False),
                                  "shown": self.field_shown(fid)}
                            for fid in want if fid in self.state}
            else:
                # A whole-form ask (the secretary's values tail, bd jnjj.45d):
                # production sends EVERY schema field with its `shown` flag --
                # including untouched conditional fields -- so the backend
                # shown_map never defaults a hidden field to shown.
                snapshot = {
                    fid: {"value": self.state.get(fid, {}).get("value"),
                          "confirmed": self.state.get(fid, {}).get("confirmed", False),
                          "shown": self.field_shown(fid)}
                    for fid in self.schema_field_order}
            self._reply(lambda: self.service.handle_form_state_response(rid, snapshot))
        elif mtype == "skip_field":
            self._handle_skip_field(msg)
        elif mtype == "switch_field":
            self._handle_switch_field(msg)
        elif mtype == "validation_result":
            # W3 (bd polyglot-pdf-pr3i, mirrored 0cyu): REPORT-ONLY since W3 --
            # mirror handleValidationResult (webFormConnection.ts:2222-2257).
            # A clean result resolves nothing to enqueue. A result carrying
            # conflicts ENQUEUES them (dedup by field-id set, mirroring
            # enqueueValidatorFindings) and, if the queue GREW, triggers the
            # drain seam -- the steered marker is set ONLY at
            # drain_findings_result (handleDrainFindingsResult), never here.
            conflicts = msg.get("conflicts") or []
            self.validation_results.append(
                {"ts": time.monotonic(), "conflicts": conflicts})
            if conflicts:
                self._enqueue_validator_findings(conflicts)
        elif mtype == "drain_findings_result":
            # W3 mirror (handleDrainFindingsResult, webFormConnection.ts:2295-
            # 2324): the delivered conflicts get the steered marker + are
            # consumed from the queue; undelivered conflicts stay queued.
            self._handle_drain_findings_result(msg)
        elif mtype == "get_next_field_hint":
            rid = msg.get("request_id")
            hint = self.next_hint()
            # DTI: also hand the backend the next field's FULL schema (the client
            # owns it) so it renders into next_field_guidance -- otherwise the DTI
            # model gets no per-field guidance past field 1 and stalls.
            nfs = self.next_field_schema() if self.dti_mode else None
            self._reply(lambda: self.service.handle_next_field_hint_response(rid, hint, nfs))
        elif mtype == "confirm_field":
            rid = msg.get("request_id")
            fid = msg.get("field_id")
            entry = self.state.get(fid)
            value = entry.get("value") if entry else None
            # Mirror the production hasUsableValue gate (webFormConnection, bd
            # w3ic): '' is a legitimate confirmable end state for an OPTIONAL
            # field ("does not apply"); only required fields reject ''.
            f = self.schema_fields.get(fid) or {}
            required = bool((f.get("validation") or {}).get("required"))
            usable = value is not None and (value != "" or not required)
            if usable:
                entry["confirmed"] = True
                self._reply(lambda: self.service.handle_confirm_field_response(rid, True))
            else:
                self._reply(lambda: self.service.handle_confirm_field_response(
                    rid, False, "no_value"))
        elif mtype == "go_away":
            # The Live server announced the connection close (time_left rider).
            # Mirror the production frontend: flag it so the driver reconnects.
            self.go_away_pending = True
        elif mtype == "transcript":
            # bd jnjj.39 debug: the model's output speech, streamed in chunks. Stamp
            # each with a monotonic ts so it can be joined per-question by time window.
            text = msg.get("data")
            if text:
                self.transcript_chunks.append(
                    {"ts": time.monotonic(), "text": str(text)})
        # section_switched / status messages need no reply

    def _reply(self, fn):
        # Resolve on the next loop tick, like a (very fast) frontend round-trip.
        asyncio.get_event_loop().call_soon(fn)

    # -- frontend navigation logic
    def set_active_section(self, plan_slice: list[dict]):
        self.active_field_ids = [q["field_id"] for q in plan_slice]

    def _pin_active(self) -> str | None:
        """The pinned field, while it is pinned AND unconfirmed (mirror the
        frontend's computeNextField pin priority: a pin on a confirmed field is
        dormant until a value update resets confirmed)."""
        fid = self.pinned_field_id
        if fid and not self.state.get(fid, {}).get("confirmed"):
            return fid
        return None

    def next_hint(self) -> str | None:
        pin = self._pin_active()
        if pin:
            order = (self.active_field_ids.index(pin) + 1
                     if pin in self.active_field_ids else 1)
            return _hint_for(self.schema_fields[pin], order)
        for order, fid in enumerate(self.active_field_ids, 1):
            entry = self.state.get(fid)
            if not entry or not entry.get("confirmed"):
                return _hint_for(self.schema_fields[fid], order)
        return None

    def next_field_schema(self) -> dict | None:
        """The FULL schema dict of the next unconfirmed field (DTI mode). The client
        owns the full schema, so this is the harness analogue of the frontend's
        getFieldSchema(nextField.id) -- the backend renders it into the confirm_field
        next_field_guidance."""
        pin = self._pin_active()
        if pin:
            return self.schema_fields.get(pin)
        for fid in self.active_field_ids:
            entry = self.state.get(fid)
            if not entry or not entry.get("confirmed"):
                return self.schema_fields.get(fid)
        return None

    # -- stress-test seams (bd polyglot-pdf-eh1h)
    def field_shown(self, fid: str) -> bool:
        """shouldShowField over the CURRENT state values (the harness mirror of
        the frontend evaluator; full_form_script.evaluate_show_if implements the
        same operator semantics)."""
        f = self.schema_fields.get(fid)
        if f is None:
            return False
        values = {k: v.get("value") for k, v in self.state.items()}
        return _ffs.field_visible(f, self.schema_fields, values)

    def resolve_field(self, identifier: str) -> str | None:
        """Resolve a model-supplied identifier -- the FULL mirror of the
        frontend's resolveFieldForNavigation (schemaFormState.ts:1154): exact
        field_id, then case-insensitive spoken_name, then field NAME, then any
        spoken_aliases entry. (The first harness version checked only
        id/spoken_name -- stricter than production -- which under-resolved the
        E4 navigation scenarios; fixed to full parity.)"""
        ident = (identifier or "").strip()
        if not ident:
            return None
        if ident in self.schema_fields:
            return ident
        low = ident.lower()
        for fid, f in self.schema_fields.items():
            if str(f.get("spoken_name") or "").lower() == low:
                return fid
            if str(f.get("name") or "").lower() == low:
                return fid
            aliases = f.get("spoken_aliases") or []
            if any(str(a).lower() == low for a in aliases):
                return fid
        return None

    def _suggest_candidates(self, identifier: str, limit: int = 6) -> list[dict]:
        """Mirror SchemaFormStateManager.suggestNavigationCandidates: up to
        `limit` currently-visible fields ranked by whole-word overlap with the
        identifier, then document order. Suggestion only -- resolution stays
        exact (bd polyglot-pdf-3vby)."""
        import re as _re
        words = [w for w in _re.split(r"[^a-z0-9]+", (identifier or "").lower())
                 if len(w) > 2]
        scored = []
        for idx, (fid, f) in enumerate(self.schema_fields.items()):
            if f.get("hidden") or not self.field_shown(fid):
                continue
            hay = " ".join(str(x) for x in [
                f.get("spoken_name"), f.get("name"), *(f.get("spoken_aliases") or [])
            ] if x).lower()
            hay_words = set(w for w in _re.split(r"[^a-z0-9]+", hay) if w)
            overlap = sum(1 for w in words if w in hay_words)
            scored.append((overlap, idx, fid, f))
        scored.sort(key=lambda t: (-t[0], t[1]))
        return [
            {"field_id": fid,
             "spoken_name": str(f.get("spoken_name") or f.get("name") or fid)}
            for _, _, fid, f in scored[:limit]
        ]

    def _handle_skip_field(self, msg: dict):
        """Mirror handleSkipFieldRequest: refuse unknown/already-filled, else
        record the skip (empty value + skipped flag, counts as confirmed)."""
        rid = msg.get("request_id")
        fid = msg.get("field_id")
        rec = {"ts": time.monotonic(), "field_id": fid}
        field = self.schema_fields.get(fid)
        # NB: unlike switch (whole ack dict), the skip response is DISCRETE
        # args -- handle_skip_field_response(request_id, recorded: bool,
        # reason, section_complete). Passing a dict here reads as truthy and
        # reports every refusal as recorded (fresh-eyes round 1 on this bead).
        if field is None:
            rec["outcome"] = "unknown_field"
            self.skip_events.append(rec)
            self._reply(lambda: self.service.handle_skip_field_response(
                rid, False, "unknown_field", False))
            return
        existing = self.state.get(fid, {}).get("value")
        if existing not in (None, ""):
            rec["outcome"] = "already_filled"
            self.skip_events.append(rec)
            self._reply(lambda: self.service.handle_skip_field_response(
                rid, False, "already_filled", False))
            return
        entry = self.state.setdefault(fid, {})
        entry.update({"value": "", "confirmed": True, "skipped": True})
        if self.pinned_field_id == fid:
            self.pinned_field_id = None
        rec["outcome"] = "recorded"
        self.skip_events.append(rec)
        self._reply(lambda: self.service.handle_skip_field_response(
            rid, True, None, False))

    def _handle_switch_field(self, msg: dict):
        """Mirror handleSwitchFieldRequest (continuous mode): resolve, check
        visibility, PIN, ack with the target's hint + value + (DTI) schema."""
        rid = msg.get("request_id")
        ident = msg.get("field")
        rec = {"ts": time.monotonic(), "identifier": str(ident)}
        fid = self.resolve_field(ident)
        if fid is None:
            rec["outcome"] = "unknown_field"
            self.switch_events.append(rec)
            candidates = self._suggest_candidates(str(ident))
            self._reply(lambda: self.service.handle_switch_field_response(
                rid, {"found": False, "reason": "unknown_field",
                      "candidates": candidates}))
            return
        rec["field_id"] = fid
        if not self.field_shown(fid):
            rec["outcome"] = "hidden"
            self.switch_events.append(rec)
            self._reply(lambda: self.service.handle_switch_field_response(
                rid, {"found": False, "reason": "hidden", "field_id": fid}))
            return
        self.pinned_field_id = fid
        entry = self.state.get(fid) or {}
        value = entry.get("value")
        has_value = value not in (None, "")
        field = self.schema_fields[fid]
        order = (self.active_field_ids.index(fid) + 1
                 if fid in self.active_field_ids else 1)
        ack = {
            "found": True,
            "field_id": fid,
            "spoken_name": field.get("spoken_name") or field.get("name") or fid,
            "next_field_hint": _hint_for(field, order),
            "already_confirmed": bool(entry.get("confirmed")),
            "has_value": has_value,
        }
        if has_value:
            ack["value"] = value
        if self.dti_mode:
            ack["next_field_schema"] = field
        rec["outcome"] = "pinned"
        self.switch_events.append(rec)
        self._reply(lambda: self.service.handle_switch_field_response(rid, ack))

    def validation_fields(self, up_to_fid: str | None = None,
                         field_ids: list[str] | None = None) -> list[dict]:
        """The contract-2 validator payload (mirror buildValidatorFields):
        VISIBLE fields with a non-empty value, schema order, each
        {field_id, name, value, steered}. `field_ids`, when given, restricts
        the scan to exactly that id list (in schema order) -- the window-range
        cut used by maybe_emit_validate_windows. up_to_fid (legacy page-
        boundary cut, kept for the terminal/whole-form callers) bounds the
        list at that field (inclusive)."""
        scan_ids = (field_ids if field_ids is not None else self.schema_field_order)
        out: list[dict] = []
        for fid in scan_ids:
            entry = self.state.get(fid)
            if entry is None:
                continue
            value = entry.get("value")
            if value in (None, ""):
                pass
            elif self.field_shown(fid):
                f = self.schema_fields[fid]
                out.append({"field_id": fid,
                            "name": f.get("spoken_name") or f.get("name") or fid,
                            "value": value,
                            "steered": bool(entry.get("steered"))})
            if up_to_fid is not None and fid == up_to_fid:
                break
        return out

    # -- W2 settledness windows (bd polyglot-pdf-kxkw, mirrored 0cyu) ----

    def _field_settled(self, fid: str) -> bool:
        """A field is SETTLED when it is no longer awaiting an answer:
        confirmed, explicitly skipped, or hidden by conditional logic (not
        part of the active form). Mirrors SchemaFormStateManager.
        computeReadyWindows' isSettled (schemaFormState.ts:1362-1367)."""
        if not self.field_shown(fid):
            return True  # N/A
        entry = self.state.get(fid)
        return bool(entry and (entry.get("confirmed") or entry.get("skipped")))

    def compute_ready_windows(self, size: int, stride: int) -> list[dict]:
        """PURE mirror of SchemaFormStateManager.computeReadyWindows
        (schemaFormState.ts:1350-1388): tile self.schema_field_order into
        windows of `size` starting every `stride` fields; a window is ELIGIBLE
        once EVERY field it covers is settled AND its index is not already in
        self.validated_window_indices. Page-agnostic -- keys only on schema
        field order + settledness, never pdf_position.page (report-cadence
        revision 2026-07-13). Returns {index, start, end} dicts ascending by
        index; does NOT mutate validated_window_indices (the caller marks sent
        indices after rendering)."""
        total = len(self.schema_field_order)
        if total == 0 or size <= 0 or stride <= 0:
            return []
        step = min(stride, size)  # clamp: stride > size would leave gaps
        ready: list[dict] = []
        index = 0
        start = 0
        while start < total:
            if index not in self.validated_window_indices:
                end = min(start + size, total)
                window_ids = self.schema_field_order[start:end]
                if all(self._field_settled(fid) for fid in window_ids):
                    ready.append({"index": index, "start": start, "end": end})
            index += 1
            start = index * step
        return ready

    def maybe_emit_validate_windows(self) -> None:
        """Mirror WebFormConnection.maybeEmitValidateWindows
        (webFormConnection.ts:2477-2524): compute newly-eligible windows, mark
        their indices sent, and submit ONE validate_windows call (all new
        windows at once) to the service. Called by the driver after every
        question/event step (the confirm/skip/manual-edit seam) and on
        reconnect (the handleSessionReady analogue)."""
        ready = self.compute_ready_windows(
            WEBFORM_VALIDATOR_WINDOW_SIZE, WEBFORM_VALIDATOR_WINDOW_STRIDE)
        if not ready:
            return
        windows: list[list[dict]] = []
        sent_indices: list[int] = []
        for w in ready:
            window_ids = self.schema_field_order[w["start"]:w["end"]]
            payload = self.validation_fields(field_ids=window_ids)
            if payload:
                windows.append(payload)
            sent_indices.append(w["index"])
        self.validated_window_indices |= set(sent_indices)
        if windows and self.service is not None:
            self._submit_validate_windows(windows)

    def _submit_validate_windows(self, windows: list[list[dict]]) -> None:
        """Fire-and-forget the async validator call + push its verdict back
        as a validation_result (mirror websocket_routes._run_validation_and_
        push). Recorded on self.validation_records for the summary."""
        rec = {"t_submit": time.monotonic(), "t_verdict": None,
               "window_count": len(windows), "conflicts": []}
        self.validation_records.append(rec)

        async def _run():
            try:
                verdict = await self.service.handle_validation_windows(windows)
            except Exception as exc:  # fail-open, mirror the route's guard
                verdict = {"conflicts": [], "_error": type(exc).__name__}
            rec["t_verdict"] = time.monotonic()
            rec["conflicts"] = verdict.get("conflicts", [])
            await self.send_json(
                {"type": "validation_result",
                 "conflicts": verdict.get("conflicts", [])})

        self.window_tasks.append(asyncio.get_event_loop().create_task(_run()))

    async def drain_pending_windows(self, timeout: float = 12.0) -> int:
        """Await in-flight validate_windows tasks (run end / pre-reconnect).
        Returns the count that did NOT finish in time (dropped)."""
        pending = [t for t in self.window_tasks if not t.done()]
        if not pending:
            return 0
        _, still = await asyncio.wait(pending, timeout=timeout)
        return len(still)

    # -- W3 findings queue + finding-driven drain (bd polyglot-pdf-pr3i,
    # mirrored 0cyu) ------------------------------------------------------

    @staticmethod
    def _finding_key(field_ids) -> frozenset:
        """Mirror SchemaFormStateManager.findingKey: a finding's identity is
        its field-id SET (order-insensitive), matching the backend's frozenset
        dedupe (schemaFormState.ts:1235-1238)."""
        return frozenset(str(x) for x in (field_ids or []))

    def _enqueue_validator_findings(self, conflicts: list[dict]) -> None:
        """Mirror enqueueValidatorFindings + the enqueue-then-maybe-drain half
        of handleValidationResult (webFormConnection.ts:2222-2257): append
        only findings whose field-id SET is not already queued, stamping
        t_enqueue on each. If the queue GREW, trigger the drain seam."""
        existing = {self._finding_key(f.get("field_ids")) for f in self.validator_findings_queue}
        grew = False
        for c in conflicts:
            ids = [str(x) for x in (c.get("field_ids") or []) if x]
            if not ids:
                continue
            key = self._finding_key(ids)
            if key in existing:
                continue
            existing.add(key)
            self.validator_findings_queue.append({
                "field_ids": ids, "reason": c.get("reason", ""),
                "field_names": c.get("field_names") or {},
                "t_enqueue": time.monotonic(),
            })
            grew = True
        if grew:
            self._drain_findings()

    def _drain_findings(self) -> None:
        """Mirror WebFormConnection.drainFindings (webFormConnection.ts:2267-
        2286): single-flight (drain_in_flight), fire-and-forget the drain
        round-trip carrying the CURRENT queue snapshot. Called on enqueue-
        growth and on reconnect if a queue survived (driver's reconnect
        block)."""
        if self.drain_in_flight:
            return
        if not self.validator_findings_queue:
            return
        if self.service is None:
            return
        self.drain_in_flight = True
        snapshot = list(self.validator_findings_queue)
        t_submit = time.monotonic()
        rec = {"t_submit": t_submit, "t_result": None,
               "conflicts_sent": len(snapshot), "delivered": None}
        self.drain_results.append(rec)

        async def _run():
            try:
                verdict = await self.service.handle_drain_findings(
                    [{"field_ids": f["field_ids"], "reason": f["reason"],
                      "field_names": f["field_names"]} for f in snapshot])
                delivered = (verdict.get("conflicts", [])
                            if isinstance(verdict, dict) else [])
            except Exception as exc:  # fail-open, mirror the route's guard
                delivered = []
                rec["_error"] = type(exc).__name__
            await self.send_json(
                {"type": "drain_findings_result", "conflicts": delivered})

        task = asyncio.get_event_loop().create_task(_run())
        self.drain_tasks.append(task)
        self._pending_drain_rec = rec  # consumed by _handle_drain_findings_result

    def _handle_drain_findings_result(self, msg: dict) -> None:
        """Mirror WebFormConnection.handleDrainFindingsResult (webFormConn
        ection.ts:2295-2324): clear drain_in_flight, mark delivered fields
        steered, consume delivered findings from the queue (undelivered ones
        stay queued to retry), and re-drain if the queue grew mid-flight."""
        self.drain_in_flight = False
        rec = getattr(self, "_pending_drain_rec", None)
        delivered = msg.get("conflicts") or []
        if rec is not None:
            rec["t_result"] = time.monotonic()
            rec["delivered"] = len(delivered)
            # THIS drain's delivered field-id sets, kept on the record so a
            # caller (check_steers) can scope its correction-rail matching to
            # exactly what THIS drain steered -- not every field ever steered
            # this run (client.state can carry an older steered marker whose
            # correction was an "overridden_unplanted" ack, which never clears
            # it; scanning all of client.state would wrongly re-match a stale
            # plant on a later, unrelated drain).
            rec["field_ids"] = [str(x) for c in delivered
                                for x in (c.get("field_ids") or [])]
            self._pending_drain_rec = None
        if not delivered:
            # Undelivered (dead live session): do NOT immediately re-drain
            # (mirrors the client -- a re-drain would spin against the dead
            # session). Findings stay queued to retry on the next enqueue-
            # growth or reconnect.
            return
        delivered_keys = set()
        for c in delivered:
            for fid in (c.get("field_ids") or []):
                if fid in self.schema_fields:
                    self.state.setdefault(fid, {})["steered"] = True
            delivered_keys.add(self._finding_key(c.get("field_ids")))
        self.validator_findings_queue = [
            f for f in self.validator_findings_queue
            if self._finding_key(f["field_ids"]) not in delivered_keys]
        if self.validator_findings_queue:
            self._drain_findings()

    async def drain_pending_drains(self, timeout: float = 12.0) -> int:
        """Await in-flight drain_findings round-trips (run end / pre-
        reconnect). Returns the count that did NOT finish in time (dropped --
        the errors.dropped_drains summary key)."""
        pending = [t for t in self.drain_tasks if not t.done()]
        if not pending:
            return 0
        _, still = await asyncio.wait(pending, timeout=timeout)
        return len(still)


# ------------------------------------------------------------------ log tap

_ERROR_EVENTS = {
    "gemini_session_connection_closed",
    "gemini_session_no_events_received",
    "receive_loop_unexpected_error",
}


class _LogTap:
    """Record warning+ structlog events from the adapter without touching it
    (same pattern as diag_compression_matrix_sdk28.py).

    info_events (bd polyglot-pdf-eh1h): a WHITELIST of info-level event names
    to additionally capture -- the pre-existing tap was warning+ ONLY, and the
    stress-test signals (text_ai_usage, ask_secretary_*, validator_steer_*,
    dti_confirm_coerced_*) are all logged at info. Whitelisted info events are
    stamped with a monotonic ts and the current _TEXT_CALLER tag so concurrent
    validator windows / secretary calls attribute correctly."""

    _CAPTURE = ("warning", "error", "exception", "critical")

    def __init__(self, inner, sink: list, info_events: frozenset = frozenset()):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_sink", sink)
        object.__setattr__(self, "_info_events", info_events)

    def bind(self, **kw):
        return _LogTap(self._inner.bind(**kw), self._sink, self._info_events)

    def __getattr__(self, name):
        orig = getattr(self._inner, name)
        if name in self._CAPTURE and callable(orig):
            sink = self._sink

            def _wrapped(event, *a, **kw):
                try:
                    sink.append({"level": name, "event": str(event),
                                 "fields": {k: str(v) for k, v in kw.items()}})
                except Exception:
                    pass
                return orig(event, *a, **kw)

            return _wrapped
        if name == "info" and self._info_events and callable(orig):
            sink = self._sink
            wanted = self._info_events

            def _wrapped_info(event, *a, **kw):
                try:
                    if str(event) in wanted:
                        sink.append({"level": "info", "event": str(event),
                                     "ts": time.monotonic(),
                                     "caller": _TEXT_CALLER.get(),
                                     "fields": {k: str(v) for k, v in kw.items()}})
                except Exception:
                    pass
                return orig(event, *a, **kw)

            return _wrapped_info
        return orig


# The stress-test info-event whitelist. Names verified against the emitters:
# text_ai_gemini._log_usage / ask()/validate(); form_filling_service's
# ask_secretary_* + validator_* events; callback_handler's DTI coercion event.
_INFO_EVENTS = frozenset({
    "text_ai_usage", "text_ai_ask_complete", "text_ai_validate_complete",
    "ask_secretary_complete", "ask_secretary_pending_async_deliver",
    "ask_secretary_async_delivered", "ask_secretary_async_dropped_session_inactive",
    "validator_steer_delivered", "validator_steer_not_delivered_fail_open",
    "validator_steer_dropped_session_inactive", "validator_windows_complete",
    "dti_confirm_coerced_to_current_field",
    "dti_update_coerced_to_current_field",
    "dti_skip_coerced_to_current_field",
})
# (ask_secretary_pending / ask_secretary_timeout / the *_fail_open family are
# WARNING-level and already captured by the warning+ tap.)

# Attribution tag for concurrent text-sidecar calls: the ask()/validate()
# wrappers set it, the info tap stamps it onto every captured event emitted
# inside that call's task context.
import contextvars  # noqa: E402

_TEXT_CALLER = contextvars.ContextVar("stress_text_caller", default="")


def _tag_text_ai(text_ai, ledger_calls: list, validate_caller: str = "validator"):
    """Wrap text_ai.ask/.validate so (a) every whitelisted log event emitted
    inside carries the caller tag, and (b) per-call wall latency is recorded.
    `validate_caller` labels .validate() calls made through THIS instance --
    "validator" for the lite sidecar (the default, back-compat), "pro" for the
    W6 whole-form gemini-2.5-pro instance (bd polyglot-pdf-gbus, mirrored
    0cyu) -- so build_summary can separate the two in the pro_pass section
    without guessing from the model name alone."""
    orig_ask, orig_validate = text_ai.ask, text_ai.validate

    async def ask_tagged(*a, **kw):
        tok = _TEXT_CALLER.set("secretary")
        t0 = time.monotonic()
        try:
            return await orig_ask(*a, **kw)
        finally:
            ledger_calls.append({"caller": "secretary", "t_start": t0,
                                 "dur_s": round(time.monotonic() - t0, 3)})
            _TEXT_CALLER.reset(tok)

    async def validate_tagged(*a, **kw):
        tok = _TEXT_CALLER.set(validate_caller)
        t0 = time.monotonic()
        try:
            return await orig_validate(*a, **kw)
        finally:
            ledger_calls.append({"caller": validate_caller, "t_start": t0,
                                 "dur_s": round(time.monotonic() - t0, 3)})
            _TEXT_CALLER.reset(tok)

    text_ai.ask = ask_tagged
    text_ai.validate = validate_tagged


# NOTE (bd polyglot-pdf-0cyu): the earlier ValidationSeam class (page-boundary
# window builder authored against the pre-W2/W3 spec) was REMOVED once W2
# (stride windows, bd kxkw) and W3 (findings queue/drain, bd pr3i) landed on
# dev -- its job is now FakeClientWebSocket.compute_ready_windows /
# maybe_emit_validate_windows / _enqueue_validator_findings / _drain_findings,
# which mirror the LANDED webFormConnection.ts behavior directly on the
# client stand-in (the real client owns this state, not a separate object).


# ------------------------------------------------------------------- summary

def build_summary(meta: dict, rows: list, log_sink: list, client,
                  planted_groups: list, plan_fids: set) -> dict:
    """Assemble the per-run headline summary (bd polyglot-pdf-eh1h). Pure
    function over the run's collected records so it is unit-testable without a
    live session. All dollar figures include the text sidecar."""
    voice_usd = round(sum(r.get("total cost", 0) for r in rows), 6)
    voice_tokens = sum(r.get("total tokens", 0) for r in rows)

    usage_events = [e for e in log_sink if e.get("event") == "text_ai_usage"]
    text_rows = []
    unpriced_models: set = set()
    for e in usage_events:
        f = e.get("fields") or {}

        def _i(name):
            try:
                return int(float(f.get(name) or 0))
            except (TypeError, ValueError):
                return 0
        # Per-model pricing (bd polyglot-pdf-0cyu): text_ai_usage carries the
        # model name (text_ai_gemini._log_usage); the lite sidecar and the W6
        # pro pass bill at DIFFERENT rates, so a flat rate silently mispriced
        # every pro call. A missing model field (older log shape / a test
        # double) falls back to the flash-lite row for back-compat rather than
        # raising unpriced -- only a NAMED-but-unknown model counts as
        # unpriced (never silently under-priced: it bills at the highest
        # known rate and is surfaced in errors.unpriced_model_calls).
        model = f.get("model") or None
        rates, unpriced = _rates_for_model(model) if model else (TEXT_RATES, False)
        if unpriced:
            unpriced_models.add(model)
        prompt = _i("prompt_tokens")
        cached = _i("cached_tokens")
        output = _i("output_tokens")
        cached_c = max(0, min(cached, prompt))
        usd = ((prompt - cached_c) * rates["input"] + cached_c * rates["cached_input"]
               + output * rates["output"])
        text_rows.append({
            "caller": e.get("caller") or "", "model": model,
            "prompt": prompt, "cached": cached, "output": output,
            "cache_hit": str(f.get("cache_hit")).lower() == "true",
            "usd": round(usd, 6)})
    text_usd = round(sum(r["usd"] for r in text_rows), 6)
    ledger_calls = meta.get("text_ledger_calls") or []

    def _caller(rows_, name):
        return [r for r in rows_ if r["caller"] == name]

    sec_calls = _caller(ledger_calls, "secretary")
    val_calls = _caller(ledger_calls, "validator")
    pro_calls = _caller(ledger_calls, "pro")
    sec_usage = _caller(text_rows, "secretary")
    pro_usage = _caller(text_rows, "pro")

    ev = meta.get("event_records") or []
    recalls = [e for e in ev if e.get("type") == "recall"]
    navs = [e for e in ev if e.get("type") == "navigate_back"]
    skips = [e for e in ev if e.get("type") == "skip"]
    steers = meta.get("steer_records") or []
    vrecords = meta.get("validation_records") or []

    # Distinct flagged conflict groups across all verdicts (+ duplicate count:
    # the SAME group surfacing in more than one verdict is a duplicate steer
    # the suppression layer should have prevented).
    seen: dict = {}
    for r in vrecords:
        for c in r.get("conflicts") or []:
            key = frozenset(str(x) for x in (c.get("field_ids") or []))
            if key:
                seen[key] = seen.get(key, 0) + 1
    flagged_groups = [set(k) for k in seen]
    duplicate_steers = sum(n - 1 for n in seen.values() if n > 1)

    fa = meta.get("fill_accuracy") or {}
    turns = meta.get("turns") or []
    turn_lat = [t.get("latency_s") for t in turns if t.get("latency_s")]
    reconnects = meta.get("continuous_reconnects") or []

    coercions = [e for e in log_sink
                 if str(e.get("event", "")).startswith("dti_")
                 and "coerced" in str(e.get("event", ""))]
    close_1011 = [e for e in log_sink
                  if e.get("event") == "gemini_session_connection_closed"
                  and "1011" in json.dumps(e.get("fields") or {})]
    fail_open_val = [e for e in log_sink
                     if e.get("event") == "validator_window_fail_open"]
    fail_open_sec = [e for e in log_sink
                     if str(e.get("event", "")).startswith("ask_secretary")
                     and e.get("level") in ("warning", "error")]
    scripted = plan_fids | {aa for aa in (meta.get("auto_apply_fids") or [])}
    spurious = [fid for fid in client.state
                if fid not in scripted
                and client.state[fid].get("value") not in (None, "")]

    pr = (_se.score_validator_pr(planted_groups, flagged_groups)
          if (planted_groups or flagged_groups) else None)

    # W3 drain stats (bd polyglot-pdf-pr3i, mirrored 0cyu): every drain_
    # findings round-trip this client ran, keyed off drain_records
    # (client.drain_results), NOT validation_records -- a drain is a DISTINCT
    # event from the report that enqueued it (a drain can carry several
    # enqueued reports, or fire again on the same report if the first
    # delivery failed).
    drecords = meta.get("drain_records") or []
    delivered_drains = [d for d in drecords if d.get("delivered")]
    undelivered_drains = [d for d in drecords
                          if d.get("delivered") is not None and not d.get("delivered")]
    drain_latencies = [round(d["t_result"] - d["t_submit"], 3) for d in drecords
                       if d.get("t_result") is not None]

    pro_pass_meta = meta.get("pro_pass") or {"ran": False, "model": None,
                                             "conflicts": 0}
    pro_usd = round(sum(r["usd"] for r in pro_usage), 6)

    return {
        "run": {k: meta.get(k) for k in
                ("model", "tier", "schema", "arm", "path", "questions",
                 "compression", "trigger", "window", "continuous", "started",
                 "events_mode", "reactivity", "lang", "text_ai_wired")},
        "headline": {
            "all_in_usd": round(voice_usd + text_usd, 6),
            "voice_usd": voice_usd,
            "text_usd": text_usd,
            "voice_tokens": voice_tokens,
            "wall_clock_s": meta.get("wall_clock_s"),
            "steps": len(rows),
            "fill_accuracy": {k: fa.get(k) for k in
                              ("matched", "total", "accuracy")},
            "fill_failure_modes": {
                k: len(v) for k, v in (meta.get("fill_failure_modes") or {}).items()},
            "usd_per_correct_field": (
                round((voice_usd + text_usd) / fa["matched"], 4)
                if fa.get("matched") else None),
        },
        "validator": {
            "windows_submitted": sum(r.get("window_count", 0) for r in vrecords),
            "boundaries": len(vrecords),
            "calls": len(val_calls),
            "window_latency_s": _se.latency_summary(
                [r["dur_s"] for r in val_calls]),
            "verdict_latency_s": _se.latency_summary(
                [round(r["t_verdict"] - r["t_submit"], 3) for r in vrecords
                 if r.get("t_verdict")]),
            "pr": pr,
            "duplicate_steers": duplicate_steers,
            "steers": len(steers),
            "steer_outcomes": {o: sum(1 for s in steers if s.get("outcome") == o)
                               for o in {s.get("outcome") for s in steers}},
            "steer_to_switch_s": _se.latency_summary(
                [s.get("steer_to_switch_s") for s in steers]),
            "fail_opens": len(fail_open_val),
            "drains": {
                "count": len(drecords),
                "delivered": len(delivered_drains),
                "undelivered_retries": len(undelivered_drains),
            },
            "drain_latency_s": _se.latency_summary(drain_latencies),
        },
        "pro_pass": {
            "ran": bool(pro_pass_meta.get("ran")),
            "model": pro_pass_meta.get("model"),
            "usd": pro_usd,
            "latency_s": pro_pass_meta.get("latency_s"),
            "conflicts": pro_pass_meta.get("conflicts", 0),
            "calls": len(pro_calls),
        },
        "secretary": {
            "calls": len(sec_calls),
            "blocked_s": _se.latency_summary([r["dur_s"] for r in sec_calls]),
            "pending_detached": sum(1 for e in recalls if e.get("pending_detached")),
            "recall_events": len(recalls),
            "tool_fired": sum(1 for e in recalls if e.get("tool_fired")),
            "answers_correct": sum(1 for e in recalls
                                   if e.get("answer_correct") is True),
            "answers_wrong": sum(1 for e in recalls
                                 if e.get("answer_correct") is False),
            "cache_hit_rate": (round(sum(1 for r in sec_usage if r["cache_hit"])
                                     / len(sec_usage), 3) if sec_usage else None),
            "warnings": len(fail_open_sec),
        },
        "navigation": {
            "attempts": len(navs),
            "switched": sum(1 for e in navs if e.get("switched_to")),
            "hit_target": sum(1 for e in navs if e.get("hit_target")),
            "seam_latency_s": _se.latency_summary(
                [e.get("seam_latency_s") for e in navs]),
        },
        "skips": {"requested": len(skips),
                  "recorded": sum(1 for e in skips if e.get("recorded"))},
        "latency": {"turn_s": _se.latency_summary(turn_lat)},
        "errors": {
            "close_1011": len(close_1011),
            "go_away_announced": sum(1 for r in reconnects if r.get("announced")),
            "reconnects": len(reconnects),
            "reconnect_downtime_s": _se.latency_summary(
                [r.get("downtime_s") for r in reconnects]),
            "stalled_turns": sum(1 for t in turns if t.get("stalled")),
            "tool_callback_exceptions": len(meta.get("tool_callback_exceptions") or []),
            "dti_coercions": len(coercions),
            "unknown_field_rejections": (
                sum(1 for e in (client.switch_events or [])
                    if e.get("outcome") == "unknown_field")
                + sum(1 for e in (client.skip_events or [])
                      if e.get("outcome") == "unknown_field")),
            "spurious_fills": sorted(spurious),
            "validation_dropped": (meta.get("validation_dropped_reconnect", 0)
                                   + meta.get("validation_dropped_at_end", 0)),
            "secretary_delivers_dropped": meta.get(
                "secretary_delivers_dropped_reconnect", 0),
            "dropped_drains": meta.get("dropped_drains", 0),
            "unpriced_model_calls": sorted(unpriced_models),
            "captured_errors": len(meta.get("errors") or []),
        },
    }


# ------------------------------------------------------------------- driver

def _make_settings(arm: str, trigger: int, window: int, compression: bool = False,
                   continuous: bool = False):
    # The production code defaults are continuous-DTI (bd polyglot-pdf-7872:
    # USE_DTI / CONTINUOUS_SESSION / CONTEXT_COMPRESSION_ENABLED all default ON),
    # so every arm PINS its full mode explicitly -- a future default flip must
    # never silently relabel an arm's measured configuration (the el92 /
    # section-reset-jit failure class). The driver still emulates the session
    # LIFECYCLE itself for --continuous runs, but the SETTINGS flag must be True
    # there (E0 pilot finding, bd polyglot-pdf-0cyu): the two production
    # consumers must fire -- _build_tool_declarations drops switch_section (the
    # E0 model actually CALLED the deprecated tool from the 7-tool catalog;
    # production continuous runs 6 tools) and the SI suppresses the
    # "Section N of M" counters. Neither consumer touches the driver's
    # switch_to_section reconnect vehicle (verified: only those two reads).
    # Non-continuous arms keep False, exactly as every historical run measured.
    overrides = {
        "USE_DTI": False,
        "CONTINUOUS_SESSION": bool(continuous),
        "CONTEXT_COMPRESSION_ENABLED": False,
    }
    if arm == "sliding-window":
        overrides.update({
            "CONTEXT_COMPRESSION_ENABLED": True,
            "CONTEXT_COMPRESSION_TRIGGER_TOKENS": trigger,
            "CONTEXT_COMPRESSION_WINDOW_TOKENS": window,
            # This arm applies the EXACT --trigger/--window the operator asked for;
            # disable per-form derivation (default-on under DTI, bd jnjj.35) so the
            # adapter honors the fixed values instead of silently auto-sizing while
            # the run metadata still records the requested fixed numbers.
            "CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR": False,
        })
    elif arm == "section-reset-jit":
        # The JIT SI mode was REMOVED (bd polyglot-pdf-en2j): USE_JIT_SCHEMA no
        # longer exists, so this arm can no longer render a distinct JIT manifest
        # SI -- it would silently measure the legacy full-SI while labeling the
        # output "section-reset-jit" (mislabeled cost data). Fail loudly instead of
        # producing misleading numbers (bd polyglot-pdf-el92). Use --arm dti for the
        # shipped reduced-SI cost path, or --arm section-reset for the full-SI
        # baseline.
        raise SystemExit(
            "--arm section-reset-jit is removed: the JIT SI mode was deleted in bd "
            "polyglot-pdf-en2j. Use --arm dti (shipped reduced-SI) or --arm "
            "section-reset (full-SI baseline)."
        )
    elif arm == "dti":
        # The Dynamic Turn Injection cost arm (bd polyglot-pdf-jnjj.25): same
        # per-section-reset flow + JIT-shaped handshake, but USE_DTI makes
        # build_form_context render the TINY DTI SI (static backbone + only the
        # current field's guidance) and each next field's guidance rides the
        # confirm_field tool response (client-supplied; the FakeClient sends the
        # next field's schema on next_field_hint_response). This is the production
        # DTI principal path -- jnjj.22.
        overrides["USE_DTI"] = True

    # --compression layers calibrated context-window eviction onto the arm (the
    # jnjj.25-folded eviction experiment, formerly jnjj.34). jnjj.25 found DTI's
    # per-field guidance ACCUMULATES within a section, cancelling the SI saving;
    # eviction should purge that stale guidance turn-over-turn. Calibration: the
    # window must EXCEED the unevictable SI+tools floor (~1978 tok for the DTI SI on
    # the I-90) -- else compression fires on turn 1 and the data is incomparable --
    # but be tight enough to evict accumulated guidance; the trigger sits above the
    # window so a couple of fields' guidance must pile up before eviction. Defaults:
    # window 2500 (floor + the current field's guidance headroom), trigger 3500.
    if compression and arm != "sliding-window":
        overrides["CONTEXT_COMPRESSION_ENABLED"] = True
        overrides["CONTEXT_COMPRESSION_TRIGGER_TOKENS"] = trigger
        overrides["CONTEXT_COMPRESSION_WINDOW_TOKENS"] = window
        # Honor the EXACT --trigger/--window for this calibration sweep: turn OFF
        # the production per-form derivation (default-on under DTI, bd jnjj.35),
        # which would otherwise auto-size the window and ignore the CLI values --
        # silently, while the run metadata still records the requested fixed pair.
        overrides["CONTEXT_COMPRESSION_DERIVE_FROM_SI_FLOOR"] = False

    s = _config.Settings(**overrides)
    # Labeled deviation from deploy config: DISABLE automatic VAD so the explicit
    # activity brackets are actually honored (deterministic synthetic-turn
    # boundaries). The old "neutralized sensitivities" (UNSPECIFIED) did NOT
    # disable automatic VAD -- the adapter no-ops manual brackets in native mode,
    # so turn ends were detected by the server's VAD on the gTTS audio. AI Studio
    # tolerated that; Vertex intermittently misses a gTTS utterance end and the
    # model hangs ~41s until the NEXT utterance's audio flushes it (past the 40s
    # _wait_turn timeout -> the harness barges in -> escalating desync -> wedge;
    # observed 2026-07-05 on two 30q continuous runs, both dying ~q8). With
    # DISABLE_GEMINI_VAD=True the adapter sends real ActivityStart/End and
    # _build_vad_settings sends {'disabled': True} -- the h04c "explicit activity
    # brackets" design, now actually wired.
    s.DISABLE_GEMINI_VAD = True
    s.VAD_START_SENSITIVITY = "UNSPECIFIED"
    s.VAD_END_SENSITIVITY = "UNSPECIFIED"
    s.VAD_PREFIX_PADDING_MS = None
    s.VAD_SILENCE_DURATION_MS = None
    return s


class CounterTracker:
    """Per-question deltas over the adapter's cumulative per-modality counters,
    robust to the counter reset a section-restart causes."""

    FIELDS = ("_session_text_input_tokens", "_session_audio_input_tokens",
              "_session_text_output_tokens", "_session_audio_output_tokens",
              "_session_total_tokens")

    def __init__(self, adapter):
        self.adapter = adapter
        self.base = {f: 0 for f in self.FIELDS}

    def snapshot(self) -> dict:
        return {f: getattr(self.adapter, f, 0) or 0 for f in self.FIELDS}

    def delta_and_advance(self) -> dict:
        cur = self.snapshot()
        if cur["_session_total_tokens"] < self.base["_session_total_tokens"]:
            # Session restarted (section switch): counters reset to 0; the new
            # session's whole accumulation since restart belongs to this delta.
            self.base = {f: 0 for f in self.FIELDS}
        delta = {f: cur[f] - self.base[f] for f in self.FIELDS}
        self.base = cur
        return delta


async def _wait_turn(adapter, tracker_field="_session_total_tokens",
                     last=0, timeout=40.0) -> int:
    waited = 0.0
    while waited < timeout:
        await asyncio.sleep(0.5)
        waited += 0.5
        cur = getattr(adapter, tracker_field, 0) or 0
        if cur > last:
            await asyncio.sleep(1.2)  # settle: trailing usage events
            return getattr(adapter, tracker_field, 0) or 0
    return last  # timed out; caller records a stall


async def run(args) -> int:
    # --vertex: run against Vertex AI via ADC instead of the AI Studio API key
    # (the AI Studio prepaid credits are depleted -- 1011 on connect; the deployed
    # demo runs Vertex anyway, so this is the deploy-faithful path). google-genai's
    # Client(vertexai=True, project=..., location=...) reads the ADC file directly;
    # no GOOGLE_GENAI_USE_VERTEXAI env needed on this constructor-arg path.
    if args.vertex and args.model == "3.1":
        # 3.1 is AI-Studio-only (backend/config.py: "There is no Vertex 3.1
        # (premium) id yet"); connecting it to Vertex 1008s. Vertex is now the
        # DEFAULT (bd kbi1), so a bare `--model 3.1` must fall BACK to AI
        # Studio rather than fail on a default the user never chose -- an
        # EXPLICIT --vertex with 3.1 is still a contradiction we refuse.
        # Distinguish an EXPLICIT --vertex from the new default=True. A literal
        # `"--vertex" in sys.argv` misses argparse's legal abbreviations
        # (--vert, --verte), silently overriding an explicit ask instead of
        # refusing it (bd kbi1 round 2). Match any unambiguous prefix of the
        # real flag, which is exactly what argparse itself accepts.
        # argparse accepts ANY unambiguous prefix, down to "--v" -- an earlier
        # fix stopped at "--vert" and still missed --v/--ve/--ver (bd kbi1
        # outer review). Treat every prefix of "--vertex" longer than "--" as
        # explicit; "--no-vertex" is a different string and never matches.
        explicit_vertex = any(
            len(a) > 2 and "--vertex".startswith(a) for a in sys.argv)
        if explicit_vertex:
            print("--vertex is not available for --model 3.1: the 3.1 Live "
                  "model has no Vertex id (AI-Studio-only as of 2026-06). "
                  "Use --model 2.5, or --no-vertex with GEMINI_API_KEY.")
            return 1
        print("--model 3.1 has no Vertex id; falling back to the AI Studio "
              "path (needs GEMINI_API_KEY).", flush=True)
        args.vertex = False
    if not args.vertex and not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; cannot run "
              "(the AI Studio path needs a key; Vertex is the default -- "
              "drop --no-vertex, or use --model 2.5).")
        return 1
    # --events unhappy is the E3 scenario and is meant to run on --path
    # unhappy globally (see the mix=0 comment below: "E3 runs --path unhappy
    # globally; no per-step mix"). Without this guard, a run invoked with
    # --events unhappy but the --path default (happy) silently measures a
    # mostly-happy session mislabeled as the unhappy arm (bd polyglot-pdf-3gt9).
    if (getattr(args, "events", "none") == "unhappy" and args.path == "happy"
            and not getattr(args, "allow_path_mismatch", False)):
        raise SystemExit(
            "--events unhappy combined with --path happy silently measures a "
            "mostly-happy session mislabeled as the unhappy (E3) arm. Pass "
            "--path unhappy to match, or --allow-path-mismatch to override.")
    # --schema i90-full (bd polyglot-pdf-n86b): the full-form stress-test plan,
    # generated from the g1b answer key at run time (build-time guards inside
    # abort before any live spend). Requires the continuous-DTI production shape.
    if args.schema == "i90-full":
        if not (args.arm == "dti" and args.continuous):
            print("--schema i90-full requires --arm dti --continuous "
                  "(the production continuous-DTI shape it measures).")
            return 1
        _full = _ffs.build_full_form_plan(
            _ffs.load_schema(), lang=getattr(args, "lang", "en"))
        SCHEMAS["i90-full"] = {"path": I90_SCHEMA_PATH,
                               "questions": _full["questions"],
                               "expected": _full["expected"],
                               "auto_apply": _full["auto_apply"]}
    elif getattr(args, "events", "none") != "none" or getattr(args, "reactivity", None):
        print("--events / --reactivity are only defined for --schema i90-full.")
        return 1

    schema = load_schema(args.schema)
    # Drift guard (bd jnjj.7): abort BEFORE spending live-Gemini money if the
    # expected-canon table no longer matches the kit's option vocabulary.
    _assert_expected_canon_matches_schema(
        {f["id"]: f for f in schema.get("fields", [])},
        SCHEMAS[args.schema].get("expected") or {})
    # Default (args.questions is None) runs the WHOLE plan for the chosen schema, so
    # a default --schema i90 run exercises all 3 sections completely (a fixed default
    # of 20 silently truncated the 25-question I-90 plan mid-section-3; fresh-eyes
    # bd jnjj.24). An explicit --questions N still caps the run.
    _all_questions = SCHEMAS[args.schema]["questions"]
    plan = _all_questions if args.questions is None else _all_questions[: args.questions]

    # Scenario events (bd polyglot-pdf-eh1h): weave the event script into the
    # plan. `steps` is what the driver walks; `plan` stays the QUESTION list
    # (fill scoring + section mapping). Legacy schemas: steps == plan.
    expected_tbl = dict(SCHEMAS[args.schema].get("expected") or {})
    planted_groups: list = []
    reactivity_event = None
    if getattr(args, "reactivity", None):
        suite = {r["name"]: r for r in _se.REACTIVITY_SUITE}
        if args.reactivity not in suite:
            print(f"--reactivity must be one of {sorted(suite)}")
            return 1
        r = suite[args.reactivity]
        plan = plan[: r["questions"]]
        reactivity_event = dict(r["event"])
        steps = list(plan) + [reactivity_event]
        if (reactivity_event.get("event") == "navigate_back"
                and reactivity_event.get("expected_after") is not None):
            expected_tbl[reactivity_event["target_field_id"]] = \
                reactivity_event["expected_after"]
    elif getattr(args, "events", "none") != "none":
        ev_script = list(_se.STANDARD_EVENTS)
        mix = args.mix_unhappy
        if args.events == "unhappy":
            ev_script += _se.UNHAPPY_EXTRA_PLANTS
            mix = 0  # E3 runs --path unhappy globally; no per-step mix
        steps, expected_tbl, planted_groups = _se.weave_events(
            plan, ev_script, expected_tbl, mix_unhappy_every=mix)
    else:
        steps = list(plan)

    secs = sections_in_plan(schema, plan)

    # Localized confirmation/decline utterances (bd polyglot-pdf-lo37): the
    # persona says yes/no in the session language, not English-with-an-accent
    # (the English fixtures transcribed as Devanagari phonetics in hi and as
    # German/Spanish garbage in the unbiased ru run, confounding the input-
    # transcription evidence). English keeps the module defaults so the
    # committed en fixture cache stays valid. Distinct local names on purpose:
    # shadowing CONFIRM_YES here would UnboundLocalError every earlier read
    # (the websocket_routes local-shadow trap).
    _lang_phrases = (_ffs.multilang_phrases().get(args.lang) or {}) if args.lang != "en" else {}
    confirm_utt = _lang_phrases.get("confirm_yes", CONFIRM_YES)
    reject_utt = _lang_phrases.get("reject", REJECT)

    # Pre-synth all audio (cache-aware).
    utterances = {confirm_utt, reject_utt}
    for q in steps:
        for key in ("say", "wrong", "skip_say", "planted_say",
                    "correction_say"):
            u = q.get(key)
            if u:
                utterances.add(u)
        p = q.get("plant") or {}
        if p.get("correct_say"):
            utterances.add(p["correct_say"])
    for u in sorted(utterances):
        synth_cached(u, lang=getattr(args, "lang", "en"))
    print(f"audio cache ready: {len(utterances)} utterances "
          f"({AUDIO_CACHE})")
    if args.synth_only:
        return 0

    model_name = MODELS[args.model]
    if args.vertex and args.model == "2.5":
        # The 2.5 native-audio model has a DIFFERENT id on Vertex than on AI
        # Studio (backend/config.py MODEL_NATIVE_STANDARD_VERTEX; the deployed
        # demo uses this id). Pricing resolves by family, so rates are identical.
        model_name = MODEL_NATIVE_STANDARD_VERTEX
    rates = get_pricing_for_model(model_name)
    settings = _make_settings(args.arm, args.trigger, args.window, args.compression,
                              continuous=bool(getattr(args, "continuous", False)))
    # Install the arm's settings so EVERY get_settings() consumer sees it. A bare
    # `_config.get_settings = ...` is NOT enough: modules that did
    # `from backend.config import get_settings` at import time (ai_context,
    # callback_handler, form_filling_service) hold their OWN reference and would
    # keep reading the default flags -- so a `dti`/`section-reset-jit` arm would
    # silently render the wrong SI (bd jnjj.25: the DTI branch never fired under the
    # old single-module swap). Patch the name on _config AND on each by-reference
    # holder on the SI-build path; restore them all in the finally block. (Modules
    # that import get_settings LOCALLY inside a function -- e.g. live_ai_gemini --
    # re-read _config at call time, so the _config swap covers them.)
    import backend.services.ai_context as _ai_context_mod
    import backend.services.callback_handler as _callback_mod
    import backend.services.form_filling_service as _ffs_mod
    _patch_targets = [_config, _ai_context_mod, _callback_mod, _ffs_mod]
    _orig_get_settings = [(m, m.get_settings) for m in _patch_targets if hasattr(m, "get_settings")]
    for m, _ in _orig_get_settings:
        m.get_settings = lambda s=settings: s

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _comp_tag = "_comp" if args.compression and args.arm != "sliding-window" else ""
    _cont_tag = "_cont" if getattr(args, "continuous", False) else ""
    base_name = f"costs_{args.schema}_{args.model}_{args.arm}{_cont_tag}{_comp_tag}_{args.path}_{stamp}"
    meta: dict = {
        "bead": "polyglot-pdf-4loz", "model": model_name, "tier": args.model,
        "schema": args.schema,
        "arm": args.arm, "path": args.path, "questions": len(plan),
        "compression": bool(args.compression),
        "trigger": args.trigger if (args.arm == "sliding-window" or args.compression) else None,
        "window": args.window if (args.arm == "sliding-window" or args.compression) else None,
        "continuous": bool(getattr(args, "continuous", False)),
        "schema_scope": ("continuous-full-plan" if getattr(args, "continuous", False)
                         else "per-section" if args.arm in ("section-reset", "section-reset-jit", "dti")
                         else "full-form"),
        "started": stamp, "turns": [], "per_question_tools": {},
        "prompt_curve": [], "errors": [], "rates_per_token": rates,
        "vad": "neutralized (explicit activity brackets; labeled deviation)",
    }

    log_sink: list[dict] = []
    usage_dumps: list[dict] = []
    # (q_at_call, tool_name) for the legacy per_question_tools view; also a
    # timestamped record (bd jnjj.39) so attribution can be recomputed by which
    # question WINDOW the call's timestamp falls in, not the mutable counter.
    tool_log: list[tuple[int, str]] = []
    tool_io: list[dict] = []          # bd jnjj.39: {ts, q_at_call, tool, args, response}
    input_transcript: list[dict] = []  # bd jnjj.39: {ts, text} what the model HEARD
    q_windows: list[dict] = []        # bd jnjj.39: {q, fid, t_start, t_end} for attribution
    rows: list[dict] = []
    current_q = {"n": 0}
    DEBUG = bool(getattr(args, "debug", False))

    # Text sidecar wiring (bd polyglot-pdf-eh1h): default ON for the full-form
    # stress schema (deploy fidelity: production always wires the secretary +
    # validator), OFF for the legacy schemas so historical arms measure
    # exactly what they always measured. --text-ai / --no-text-ai override.
    if getattr(args, "no_text_ai", False):
        use_text_ai = False
    else:
        use_text_ai = bool(getattr(args, "text_ai", False)) or args.schema == "i90-full"
    text_ledger_calls: list[dict] = []   # per-call {caller, t_start, dur_s}
    seam_tool_records: list[dict] = []   # ask_secretary/switch/skip tool I/O
    _module_logs = {"ffs": _ffs_mod._log, "cb": _callback_mod._log}
    meta["text_ai_wired"] = use_text_ai
    meta["events_mode"] = getattr(args, "events", "none")
    meta["reactivity"] = getattr(args, "reactivity", None)
    meta["lang"] = getattr(args, "lang", "en")
    meta["spoken_language"] = getattr(args, "spoken_language", None) or "English"
    # Language-bias flag states (bd kcia note 3): capture the m1lg
    # speech-language and the y25o transcription-hint kill-switches so an A/B
    # run's arm is machine-readable from the meta, not distinguishable only by
    # findings prose. Read off the same settings object the run patched in.
    meta["speech_language_code_enabled"] = getattr(
        settings, "SPEECH_LANGUAGE_CODE_ENABLED", None)
    meta["transcription_language_hint_enabled"] = getattr(
        settings, "TRANSCRIPTION_LANGUAGE_HINT_ENABLED", None)
    meta["planted_groups"] = [sorted(g) for g in planted_groups]
    meta["step_kinds"] = [
        (s.get("event") or ("skip" if s.get("skip") else
                            "plant" if s.get("plant") else
                            "question")) for s in steps]
    t_run_start = time.monotonic()

    try:
        if args.vertex:
            adapter = LiveAIGemini(
                model=model_name, vertexai=True,
                project=os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709"),
                location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
        else:
            adapter = LiveAIGemini(api_key=os.getenv("GEMINI_API_KEY"), model=model_name)
        adapter.set_session_context(
            form_session_id=f"4loz-{args.arm}-{args.path}-{stamp}",
            form_id=f"INTAKE-{args.schema.upper()}")
        adapter._log = _LogTap(adapter._log, log_sink, _INFO_EVENTS)
        adapter._on_raw_usage = lambda u: usage_dumps.append({
            "prompt": getattr(u, "prompt_token_count", None),
            "total": getattr(u, "total_token_count", None)})

        # Text sidecar (bd polyglot-pdf-eh1h): wire the REAL TextAIGemini so
        # the secretary tool + validator run in-session, exactly as production
        # wires them (backend/dependencies.py get_text_ai). Model is PINNED to
        # flash-lite at construction (the config default MODEL_LABELING is
        # 2.5-flash, whose Vertex thinking-on default is the #1 cost-estimate
        # buster); the lite fallback chain mirrors TextAIGemini's default.
        text_ai = None
        if use_text_ai or bool(getattr(args, "pro_pass", False)):
            from backend.adapters.text_ai_gemini import TextAIGemini
        if use_text_ai:
            if args.vertex:
                text_ai = TextAIGemini(
                    model="gemini-2.5-flash-lite", vertexai=True,
                    project=os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709"),
                    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"))
            else:
                text_ai = TextAIGemini(api_key=os.getenv("GEMINI_API_KEY"),
                                       model="gemini-2.5-flash-lite")
            text_ai._log = _LogTap(text_ai._log, log_sink, _INFO_EVENTS)
            _tag_text_ai(text_ai, text_ledger_calls)

        # W6 pro pass (bd polyglot-pdf-gbus, mirrored 0cyu): --pro-pass wires a
        # SECOND text model -- gemini-2.5-pro, bounded thinking, EMPTY fallback
        # chain -- mirroring backend/dependencies.py get_text_ai_pro exactly
        # (same model/thinking-budget knobs off Settings, same "fail-open, never
        # downgrade to lite" contract). Opt-in like use_text_ai's --text-ai:
        # FORM_COMPLETE_PRO_VALIDATOR defaults OFF in production (a real
        # operational-cost dependency), so a default harness run must not
        # silently start paying for it. Only meaningful once use_text_ai is on
        # (the pro pass rides the same drain/enqueue client machinery).
        use_pro_pass = bool(getattr(args, "pro_pass", False)) and use_text_ai
        text_ai_pro = None
        if use_pro_pass:
            if args.vertex:
                text_ai_pro = TextAIGemini(
                    model=settings.VALIDATOR_PRO_MODEL, vertexai=True,
                    project=os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709"),
                    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
                    fallback_models=(),
                    thinking_budget=settings.VALIDATOR_PRO_THINKING_BUDGET)
            else:
                text_ai_pro = TextAIGemini(
                    api_key=os.getenv("GEMINI_API_KEY"),
                    model=settings.VALIDATOR_PRO_MODEL,
                    fallback_models=(),
                    thinking_budget=settings.VALIDATOR_PRO_THINKING_BUDGET)
            text_ai_pro._log = _LogTap(text_ai_pro._log, log_sink, _INFO_EVENTS)
            _tag_text_ai(text_ai_pro, text_ledger_calls, validate_caller="pro")
        meta["pro_pass_wired"] = use_pro_pass
        if DEBUG:
            # bd jnjj.39: observe the INPUT transcript (what the model heard) so the
            # debug artifact can answer "did it parse the synthetic-audio digits?".
            # Default-off diagnostic observer; production never sets it (PHI).
            adapter._on_input_transcript = lambda text: input_transcript.append(
                {"ts": time.monotonic(), "text": str(text)})

        service = FormFillingService(live_ai=adapter, settings=settings,
                                     text_ai=text_ai, text_ai_pro=text_ai_pro)
        if text_ai is not None:
            # The service module's info events (ask_secretary_*,
            # validator_steer_*, validator_windows_complete) go through the
            # MODULE logger, not an instance attr -- tap it (restored in
            # finally with the get_settings patches).
            _ffs_mod._log = _LogTap(_module_logs["ffs"], log_sink, _INFO_EVENTS)
            _callback_mod._log = _LogTap(_module_logs["cb"], log_sink, _INFO_EVENTS)

        # Arm-dependent schema scope: section-reset (full-SI baseline) and
        # section-reset-jit (JIT manifest SI) BOTH use the production per-section
        # sub-schema flow; the JIT arm additionally synthesizes the handshake_jit
        # schema (manifest + one-field `fields`) so build_form_context renders the
        # reduced JIT SI (bd polyglot-pdf-jnjj.6). The single-session arms get the
        # whole form (what "no sections" honestly costs with today's SI machinery).
        # section-reset (full-SI baseline), section-reset-jit (JIT manifest SI), and
        # dti (Dynamic Turn Injection) ALL use the production per-section sub-schema
        # flow. section-reset-jit and dti additionally synthesize the JIT-shaped
        # handshake (manifest + one-field `fields`) -- build_form_context renders the
        # JIT SI under USE_JIT_SCHEMA and the tiny DTI SI under USE_DTI (bd jnjj.6/.25).
        # --continuous (bd polyglot-pdf-ctu8): ONE uninterrupted DTI session over the
        # whole plan -- no section resets, no restart re-greeting. This is the ctu8
        # CANDIDATE arm (continuous DTI + compression window replaces section resets);
        # section boundaries in the plan are simply ignored and the client's active
        # field set is the entire plan. Only defined for the dti arm.
        continuous = bool(getattr(args, "continuous", False))
        if continuous and args.arm != "dti":
            print("--continuous is only defined for --arm dti")
            return 1
        is_section_reset = (args.arm in ("section-reset", "section-reset-jit", "dti")
                            and not continuous)
        uses_jit_handshake = args.arm in ("section-reset-jit", "dti")
        if continuous:
            # DTI-shaped handshake spanning the WHOLE plan: manifest carries every
            # plan field, `fields` carries only field 1 (the DTI drip supplies the
            # rest via confirm_field). One synthetic "section" -- the run never
            # switches.
            plan_fids = {q["field_id"] for q in plan}
            whole = {"form_metadata": schema.get("form_metadata", {}),
                     "fields": [f for f in schema["fields"] if f["id"] in plan_fids]}
            arm_schema = jit_handshake_schema(
                whole, "continuous", "Full Form (continuous)")
            si_kwargs = dict(section_number=1, total_sections=1,
                             section_label="Full Form (continuous)",
                             previous_spoken_names=[])
            current_section_id = "continuous"
        elif is_section_reset:
            sec = secs[0]
            sub = section_subschema(schema, sec["id"])
            if uses_jit_handshake:
                arm_schema = jit_handshake_schema(sub, sec["id"], sec["label"])
            else:
                arm_schema = sub
            si_kwargs = dict(section_number=1, total_sections=len(secs),
                             section_label=sec["label"], previous_spoken_names=[])
            current_section_id = sec["id"]
        else:
            arm_schema = {"form_metadata": schema.get("form_metadata", {}),
                          "fields": schema["fields"]}
            si_kwargs = dict(section_number=1, total_sections=1,
                             section_label="Full Form", previous_spoken_names=[])
            current_section_id = secs[0]["id"]

        client = FakeClientWebSocket(schema, plan, dti_mode=(args.arm == "dti"))
        client.service = service
        if is_section_reset:
            client.set_active_section(
                [q for q in plan
                 if (client.schema_fields[q["field_id"]].get("section_id")
                     or "section-1") == secs[0]["id"]])

        # Auto-applied fields (i90-full: copy_from page headers + signature
        # widgets): the frontend fills these without the voice loop, so the
        # harness seeds them confirmed before the session starts. They are not
        # in the plan manifest, so the model never asks them; they DO ride the
        # validator payload, as production's buildValidatorFields includes them.
        for aa in (SCHEMAS[args.schema].get("auto_apply") or []):
            client.state[aa["field_id"]] = {
                "value": aa["value"], "confirmed": True}

        si = service.build_form_context_message(arm_schema, {}, **si_kwargs)
        meta["system_instruction_chars"] = len(si)
        # Session SPOKEN language (bd polyglot-pdf-6mzi): mirror websocket_routes'
        # handshake seeding -- set BEFORE start_session so the per-connect ASR
        # language bias (bd y25o) and the ow1e option-label translation task both
        # see it, exactly as production does. Defaults to English so historical
        # arms (incl. E6, which measured Spanish AUDIO against an English-speaking
        # model) are unchanged unless --spoken-language is passed.
        spoken_language = getattr(args, "spoken_language", None) or "English"
        service._spoken_language = spoken_language
        await service.start_session(
            websocket=client, session_id=f"4loz-{stamp}",
            accept_connection=True, schema=arm_schema, current_values={},
            system_instruction=si,
            form_session_id=f"4loz-{args.arm}-{args.path}-{stamp}",
            current_section_id=current_section_id,
            # Full-form catalog for the secretary (mirror websocket_routes'
            # handshake pass-through, bd p68s) -- only when the sidecar is wired.
            full_schema=(schema if use_text_ai else None),
            # bd jnjj.39: in --debug, request the model's OUTPUT transcript so the
            # FakeClient can capture what it SAID per turn. Off by default -- normal
            # runs neither request nor pay for transcription.
            send_transcript=DEBUG)

        # The validation seam is now the CLIENT's own machinery (W2/W3 landed,
        # bd polyglot-pdf-0cyu): client.maybe_emit_validate_windows() /
        # client._drain_findings() mirror webFormConnection.ts directly. Only
        # armed when the sidecar is wired AND we run the continuous full form
        # (same gating the old seam used).
        validator_armed = bool(use_text_ai and continuous)

        # Tap tool calls AFTER start_session wired the real chain. The tap wraps the
        # REAL callback; it must be RE-INSTALLED after every switch_to_section, which
        # calls start_session -> set_callbacks and overwrites adapter._on_tool_call
        # with the un-wrapped handler (Codex PR #246). Without re-install the tap --
        # and per_question_tools -- silently stop capturing after section 1, the very
        # multi-section case the debug artifact exists to diagnose. _install_tool_tap
        # captures the CURRENT underlying callback each time so a re-install never
        # double-wraps a prior tap.
        def _install_tool_tap():
            orig_tool_cb = adapter._on_tool_call

            async def _tool_tap(tool_name, arguments):
                tool_log.append((current_q["n"], tool_name))
                _ts = time.monotonic()
                try:
                    resp = await orig_tool_cb(tool_name, arguments)
                    if tool_name in ("ask_secretary", "switch_to_field",
                                     "skip_field"):
                        # Seam tools always recorded (event scoring needs the
                        # response -- e.g. the secretary's sync answer vs
                        # {"status": "pending"}). LOCAL-ONLY artifact data,
                        # synthetic persona.
                        seam_tool_records.append(
                            {"ts": _ts, "step": current_q["n"],
                             "tool": tool_name, "args": _jsonable(arguments),
                             "response": _jsonable(resp)})
                    if DEBUG:
                        # bd jnjj.39: the exact args the model SENT and the response it
                        # GOT back -- the single most useful diagnosis signal (was
                        # missing). The response carries the message + next_field_guidance.
                        tool_io.append({"ts": _ts, "q_at_call": current_q["n"],
                                        "tool": tool_name, "args": _jsonable(arguments),
                                        "response": _jsonable(resp)})
                    return resp
                except Exception as _e:
                    # bd polyglot-pdf-jnjj.38: the adapter logs a tool-callback exception
                    # via _log.exception (traceback DEV-only, str(e) scrubbed for PHI), so
                    # a CRASHING handler is otherwise invisible in the harness output --
                    # the fill silently never lands and reads as a model "skip"/"drift".
                    # Record the exception type per question so a handler bug can never
                    # again masquerade as model behavior. (Caught a real FormField-vs-dict
                    # AttributeError during jnjj.38 diagnosis.)
                    meta.setdefault("tool_callback_exceptions", []).append(
                        {"q": current_q["n"], "tool": tool_name,
                         "error_type": type(_e).__name__})
                    if DEBUG:
                        tool_io.append({"ts": _ts, "q_at_call": current_q["n"],
                                        "tool": tool_name, "args": _jsonable(arguments),
                                        "response": {"_exception": type(_e).__name__}})
                    raise

            adapter._on_tool_call = _tool_tap

        # Auto-reinstall the tap whenever the adapter's callbacks are (re)set. A
        # section switch runs set_callbacks AND sends the new-section greeting INSIDE
        # the single switch_to_section call (start_session -> set_callbacks ->
        # send_initiating_message), so reinstalling only AFTER switch_to_section
        # returns leaves the greeting response -- where a DTI recall (ask_secretary)
        # tool call can occur -- running on the raw callback (Codex PR #246 round 2).
        # Wrapping set_callbacks re-applies the tap the instant callbacks are set,
        # BEFORE the greeting, closing that gap for every section.
        _orig_set_callbacks = adapter.set_callbacks

        def _set_callbacks_then_tap(*a, **k):
            _orig_set_callbacks(*a, **k)
            _install_tool_tap()

        adapter.set_callbacks = _set_callbacks_then_tap
        _install_tool_tap()  # initial install (first start_session already ran)

        for _ in range(150):
            if getattr(adapter, "_session_ready", False):
                break
            await asyncio.sleep(0.1)
        else:
            print("session never became ready; aborting")
            meta["errors"] = log_sink
            return 2

        tracker = CounterTracker(adapter)
        last_total = 0

        # Production greeting: initiating message, then the greeting turn.
        await service.send_initiating_message(spoken_language, client.next_hint() or "")
        last_total = await _wait_turn(adapter, last=last_total)
        meta["greeting_tokens"] = tracker.snapshot()["_session_total_tokens"]
        tracker.base = tracker.snapshot()
        # bd jnjj.39 (Codex PR #246): each question's window STARTS where the previous
        # one ended, not when we begin speaking this answer -- the AI's PROMPT for
        # this field is emitted at the tail of the prior turn (q1's prompt is in the
        # greeting). Anchoring t_start to the prior window's end captures that prompt
        # in THIS field's model_said instead of losing it / mis-filing it on the prior
        # field. Initialized to the post-greeting instant.
        _prev_q_end = time.monotonic()

        _last_activity_end = {"ts": _prev_q_end}  # bd jnjj.39: window boundary anchor

        async def speak(text: str, label: str):
            nonlocal last_total
            pcm = synth_cached(text, lang=getattr(args, "lang", "en"))
            client.first_audio_at = None
            await service.send_activity_start()
            for chunk in _pcm_chunks(pcm):
                await service.stream_audio(chunk)
                await asyncio.sleep(_CHUNK_MS / 1000.0)
            t_end = time.monotonic()
            await service.send_activity_end()
            # bd jnjj.39 / Codex PR #246: the question-window boundary is the user's
            # activity_end (BEFORE awaiting Gemini's response), so the response that
            # carries the NEXT field's prompt falls into the NEXT window's model_said.
            _last_activity_end["ts"] = t_end
            new_total = await _wait_turn(adapter, last=last_total)
            stalled = new_total == last_total
            last_total = new_total
            meta["turns"].append({
                "q": current_q["n"], "label": label, "stalled": stalled,
                "latency_s": (round(client.first_audio_at - t_end, 3)
                              if client.first_audio_at and client.first_audio_at > t_end
                              else None)})
            if stalled:
                print(f"    [warn] turn stalled: q{current_q['n']} {label}")

        # ------- stress-test event machinery (bd polyglot-pdf-eh1h) -------
        event_records: list[dict] = []   # recall / navigate_back / skip outcomes
        steer_records: list[dict] = []   # validator steer -> switch compliance
        _vr_handled = {"n": 0}

        async def _drain_before_reconnect():
            """Settle in-flight async work before tearing the session down
            (mirror of what a production reconnect implies): validate_windows
            tasks, in-flight drain_findings round-trips, and detached secretary
            delivers. Whatever cannot finish is COUNTED, not silently lost."""
            if validator_armed:
                dropped = await client.drain_pending_windows(timeout=8.0)
                if dropped:
                    meta.setdefault("validation_dropped_reconnect", 0)
                    meta["validation_dropped_reconnect"] += dropped
                dropped_drains = await client.drain_pending_drains(timeout=8.0)
                if dropped_drains:
                    meta.setdefault("dropped_drains", 0)
                    meta["dropped_drains"] += dropped_drains
            pend = [t for t in (getattr(service, "_secretary_deliver_tasks", None) or [])
                    if not t.done()]
            if pend:
                _, still = await asyncio.wait(pend, timeout=5.0)
                if still:
                    meta.setdefault("secretary_delivers_dropped_reconnect", 0)
                    meta["secretary_delivers_dropped_reconnect"] += len(still)

        async def run_recall(ev):
            """Mid-fill ask_secretary query: speak it, assert the tool fired,
            score the sync answer (a detached 'pending' answer is counted, not
            scored -- it arrives on a later turn)."""
            n0 = len(seam_tool_records)
            await speak(ev["say"], "recall")
            recs = [r for r in seam_tool_records[n0:]
                    if r["tool"] == "ask_secretary"]
            rec = {"type": "recall", "step": current_q["n"],
                   "tool_fired": bool(recs), "pending_detached": False,
                   "answer_correct": None}
            if recs:
                resp = recs[0].get("response") or {}
                if isinstance(resp, dict) and resp.get("status") == "pending":
                    rec["pending_detached"] = True
                else:
                    answer = resp.get("answer") if isinstance(resp, dict) else None
                    contains = ev.get("expect_contains")
                    if contains is not None and answer:
                        rec["answer_correct"] = (
                            _se._canon(contains) in _se._canon(answer))
            event_records.append(rec)

        async def run_navigate_back(ev):
            """'Go back to X': speak it, wait (bounded) for switch_to_field,
            speak the correction, confirm. Seam latency = utterance
            activity_end -> the client's switch_field round-trip receipt."""
            n0 = len(client.switch_events)
            await speak(ev["say"], "navigate-back")
            t_end = _last_activity_end["ts"]
            deadline = time.monotonic() + 20.0
            while (len(client.switch_events) <= n0
                   and time.monotonic() < deadline
                   and not client.go_away_pending):
                await asyncio.sleep(0.25)
            rec = {"type": "navigate_back", "step": current_q["n"],
                   "target": ev["target_field_id"], "switched_to": None,
                   "hit_target": False, "seam_latency_s": None}
            if len(client.switch_events) > n0:
                sw = client.switch_events[-1]
                rec["switched_to"] = sw.get("field_id")
                rec["hit_target"] = sw.get("field_id") == ev["target_field_id"]
                rec["seam_latency_s"] = round(sw["ts"] - t_end, 3)
            await speak(ev["correction_say"], "navigate-correct")
            await speak(confirm_utt, "confirm")
            event_records.append(rec)

        async def check_steers():
            """Drive the correction rail for any NEWLY-DELIVERED drains: wait
            (bounded) for the model's switch_to_field, then speak the matching
            plant's correction and confirm. On a timeout the correction is
            spoken anyway -- the model has voiced the steer and is waiting on
            the user; silence would desync the next scripted step.

            KEYS OFF drain_findings_result (client.drain_results), NOT
            validation_result (bd polyglot-pdf-0cyu): the W3 report/drain split
            means a validation_result conflict is only a CANDIDATE the client
            enqueues -- the steer is not actually voiced into the Live session
            until handle_drain_findings composes+injects it, confirmed by a
            drain_findings_result with non-empty `delivered`. Measuring
            steer_to_switch_s from validation_result would time a promise, not
            the delivery; an undelivered drain (empty `delivered`) is not a
            steer at all and must not start this clock."""
            new = client.drain_results[_vr_handled["n"]:]
            _vr_handled["n"] = len(client.drain_results)
            for dr in new:
                delivered = dr.get("delivered")
                if not delivered:  # None (still in flight) or 0 (undelivered)
                    continue
                t_delivered = dr["t_result"]
                rec = {"t_result": t_delivered, "conflicts": delivered,
                       "steer_to_switch_s": None, "outcome": None}
                steer_records.append(rec)
                n0 = len(client.switch_events)
                deadline = time.monotonic() + 30.0
                while (len(client.switch_events) <= n0
                       and time.monotonic() < deadline
                       and not client.go_away_pending):
                    await asyncio.sleep(0.5)
                target = None
                if len(client.switch_events) > n0:
                    sw = client.switch_events[-1]
                    rec["steer_to_switch_s"] = round(sw["ts"] - t_delivered, 3)
                    target = sw.get("field_id")
                plant = None
                # THIS drain's delivered field ids (recorded on the drain_
                # results entry by _handle_drain_findings_result) -- NOT every
                # steered field in client.state, which can carry a stale
                # marker from an earlier "overridden_unplanted" ack that never
                # cleared (a genuine value change is the only thing that
                # clears steered, W4).
                flagged_ids = set(dr.get("field_ids") or [])
                for s in steps:
                    p = s.get("plant")
                    if p and (target in p["conflict_group"]
                              or (target is None
                                  and flagged_ids & set(p["conflict_group"]))):
                        plant = p
                        break
                if plant is None:
                    # Unplanted conflict: before conceding "both correct",
                    # check whether the validator caught an ORGANIC error --
                    # a flagged field whose current value canon-mismatches
                    # the plan's expected answer (E1 run 1: the model wrote
                    # "Denver" for Hanoi and the validator flagged it; the
                    # old always-override reply threw that catch away). A
                    # real user corrects to their truth: re-speak the
                    # original scripted answer for the mismatched field.
                    say_by_fid = {s["field_id"]: s.get("say") for s in steps
                                  if "event" not in s}
                    organic = None
                    for ofid in flagged_ids:
                        exp_o = expected_tbl.get(ofid)
                        if exp_o in (None, ""):
                            continue
                        exp_set = ({_canon_value(e) for e in exp_o}
                                   if isinstance(exp_o, (list, tuple))
                                   else {_canon_value(exp_o)})
                        written_o = client.state.get(ofid, {}).get("value")
                        if _canon_value(written_o) not in exp_set and say_by_fid.get(ofid):
                            organic = ofid
                            break
                    if organic is not None:
                        await speak(f"No, that is wrong. {say_by_fid[organic]}",
                                    "steer-organic-correct")
                        await speak(confirm_utt, "steer-confirm")
                        rec["outcome"] = "corrected_organic"
                        rec["organic_field"] = organic
                        continue
                if plant is not None:
                    await speak(plant["correct_say"], "steer-correct")
                    await speak(confirm_utt, "steer-confirm")
                    rec["outcome"] = ("corrected" if target is not None
                                      else "corrected_no_switch")
                else:
                    # A conflict on un-planted fields (a genuine false positive
                    # or a knock-on flag): acknowledge and keep both values.
                    await speak("Both of those are correct as I gave them.",
                                "steer-override")
                    rec["outcome"] = "overridden_unplanted"

        sec_idx = 0
        for i, q in enumerate(steps, 1):
            current_q["n"] = i
            is_event = "event" in q
            fid = q.get("field_id") if not is_event else None
            f_sec = ((client.schema_fields[fid].get("section_id") or "section-1")
                     if fid else None)

            # Continuous-arm GoAway reconnect (production-faithful, bd c5t/ctu8):
            # the Vertex Live CONNECTION caps at ~9-10 min and announces the close
            # via go_away. Production's client reconnects and the stateless backend
            # rebuilds context from the fresh handshake; mirror that here -- rebuild
            # the continuous handshake with the REMAINING unconfirmed plan fields
            # (next field first, as computeNextField would supply) and restart the
            # session via the same switch_to_section path production reconnects use.
            # Also fires if the session died WITHOUT a go_away (belt-and-suspenders).
            # Dead-session detection (E2 run-1 wedge, bd polyglot-pdf-0cyu): a
            # spontaneous 1011/1006 drop kills the adapter's receive task but
            # can leave _session_ready stale-True, so ALSO check
            # is_session_active() (bg task alive) -- production's client
            # reconnects on spontaneous drops (bd ppfy); without this the
            # driver burned 180 consecutive 40s stall timeouts (~2h) against a
            # dead session. A stall STREAK is the belt-and-suspenders trigger:
            # 3 consecutive stalled turns forces a reconnect even if the
            # adapter still looks alive.
            _recent = [t.get("stalled") for t in meta["turns"][-3:]]
            _stall_streak = len(_recent) == 3 and all(_recent)
            if continuous and (client.go_away_pending
                               or not getattr(adapter, "_session_ready", False)
                               or not adapter.is_session_active()
                               or _stall_streak):
                was_announced = client.go_away_pending
                client.go_away_pending = False
                if _stall_streak:
                    meta.setdefault("stall_streak_reconnects", 0)
                    meta["stall_streak_reconnects"] += 1
                    # Consume the streak so the next loop iteration does not
                    # immediately re-trigger on the same three turns.
                    meta["turns"].append({"q": i, "label": "stall-streak-reset",
                                          "stalled": False, "latency_s": None})
                _t_reconnect0 = time.monotonic()
                # Settle async validator/secretary work first; count drops
                # instead of losing them silently (bd polyglot-pdf-eh1h).
                await _drain_before_reconnect()
                remaining = [client.schema_fields[p["field_id"]] for p in plan
                             if not client.state.get(p["field_id"], {}).get("confirmed")]
                if remaining:
                    sub = {"form_metadata": schema.get("form_metadata", {}),
                           "fields": remaining}
                    cont_schema = jit_handshake_schema(
                        sub, "continuous", "Full Form (continuous)")
                    await service.switch_to_section(
                        cont_schema, {},
                        {"section_id": "continuous", "section_number": 1,
                         "total_sections": 1,
                         "section_label": "Full Form (continuous)",
                         "previous_spoken_names": []},
                        initial_field_hint=client.next_hint())
                    for _ in range(150):
                        if getattr(adapter, "_session_ready", False):
                            break
                        await asyncio.sleep(0.1)
                    last_total = await _wait_turn(adapter, last=0)  # re-greeting
                    _prev_q_end = time.monotonic()
                    meta.setdefault("continuous_reconnects", []).append(
                        {"before_q": i, "announced": was_announced,
                         "downtime_s": round(time.monotonic() - _t_reconnect0, 3)})
                    print(f"    [reconnect] continuous session restarted before "
                          f"q{i} (go_away={'yes' if was_announced else 'no'})")
                    # handleSessionReady parity (webFormConnection.ts:864-887,
                    # mirrored 0cyu): a reconnect re-checks window eligibility
                    # AND re-drains a findings queue that survived the drop --
                    # a contradiction found just before the drop must still be
                    # voiced after reconnect.
                    if validator_armed:
                        client.maybe_emit_validate_windows()
                        client._drain_findings()

            # Section boundary (section-reset, section-reset-jit, dti arms):
            # production restart. The JIT-handshake arms (section-reset-jit, dti)
            # rebuild the handshake_jit schema for the new section so the restarted
            # SI is still the reduced JIT SI / tiny DTI SI (jnjj.6 / jnjj.25).
            if is_section_reset and fid and f_sec != secs[sec_idx]["id"]:
                sec_idx += 1
                sec = secs[sec_idx]
                spoken_prev = [client.schema_fields[p["field_id"]].get("name", p["field_id"])
                               for p in plan[: i - 1]]
                client.set_active_section(
                    [p for p in plan
                     if (client.schema_fields[p["field_id"]].get("section_id")
                         or "section-1") == sec["id"]])
                if uses_jit_handshake:
                    switch_schema = jit_handshake_schema(
                        section_subschema(schema, sec["id"]), sec["id"], sec["label"])
                else:
                    switch_schema = section_subschema(schema, sec["id"])
                await service.switch_to_section(
                    switch_schema, {},
                    {"section_id": sec["id"], "section_number": sec["number"],
                     "total_sections": len(secs), "section_label": sec["label"],
                     "previous_spoken_names": spoken_prev},
                    initial_field_hint=client.next_hint())
                for _ in range(150):
                    if getattr(adapter, "_session_ready", False):
                        break
                    await asyncio.sleep(0.1)
                # The tap was already re-applied inside switch_to_section (the
                # set_callbacks wrapper above runs before the section greeting), so
                # nothing to reinstall here. _on_raw_usage / _on_input_transcript /
                # _log survive set_callbacks untouched.
                last_total = await _wait_turn(adapter, last=0)  # new-session greeting
                # A section restart re-greets; the new section's first-field prompt is
                # in THAT greeting, so anchor the next window to post-greeting here
                # (don't reach back across the session boundary). bd jnjj.39.
                _prev_q_end = time.monotonic()

            # Window starts where the previous question ended (captures this field's
            # AI prompt, emitted at the tail of the prior turn). bd jnjj.39 / PR #246.
            _q_t_start = _prev_q_end
            if is_event:
                # Standalone scenario events (bd polyglot-pdf-eh1h).
                if q["event"] == "recall":
                    await run_recall(q)
                elif q["event"] == "navigate_back":
                    await run_navigate_back(q)
                else:
                    raise SystemExit(f"unknown event step: {q}")
            elif q.get("skip"):
                # Voice-skip event: the user cannot answer this field.
                n_skips0 = len(client.skip_events)
                await speak(q["skip_say"], "skip-request")
                recorded = any(e.get("outcome") == "recorded"
                               and e.get("field_id") == fid
                               for e in client.skip_events[n_skips0:])
                if not recorded:
                    # The model may verify before skipping -- allow one yes turn
                    # (mirrors probe_confirm_field's documented variance).
                    await speak(confirm_utt, "skip-confirm")
                    recorded = any(e.get("outcome") == "recorded"
                                   and e.get("field_id") == fid
                                   for e in client.skip_events[n_skips0:])
                event_records.append({"type": "skip", "step": i,
                                      "field_id": fid, "recorded": recorded})
            elif q.get("plant"):
                # A planted contradiction: fill the wrong-but-plausible value
                # and confirm; detection is the VALIDATOR's job at a later
                # boundary (check_steers drives the correction rail then).
                await speak(q["planted_say"], "plant-value")
                await speak(confirm_utt, "confirm")
            elif (q.get("path") or args.path) == "happy":
                await speak(q["say"], "value")
                await speak(confirm_utt, "confirm")
            else:
                await speak(q["wrong"], "wrong-value")
                await speak(reject_utt, "reject")
                await speak(q["say"], "corrected-value")
                await speak(confirm_utt, "confirm")
            # End the window at the LAST user activity_end (set by speak), NOT now:
            # Gemini's confirm response after it carries the NEXT field's prompt, which
            # must fall into the next window's model_said (Codex PR #246 round 2).
            #
            # KNOWN TRADEOFF (bd polyglot-pdf-jnjj.44, a deliberate single-boundary
            # limitation, not a bug): one Gemini turn both CONFIRMS field N and ASKS
            # field N+1, so a single time-boundary cannot perfectly split them. With
            # this activity_end boundary the next PROMPT attributes correctly to N+1,
            # but field N's confirm_field tool call -- emitted in that same post-
            # activity_end response -- also buckets to N+1's tool_io. The proper fix
            # (attribute tool calls vs transcript by SEPARATE rules) is jnjj.44.
            _prev_q_end = _last_activity_end["ts"]
            if DEBUG:
                q_windows.append({"q": i, "fid": fid or q.get("event", "?"),
                                  "t_start": _q_t_start, "t_end": _prev_q_end})

            # W2/W3 validator seam (landed client mirror, bd polyglot-pdf-0cyu;
            # only armed on continuous full-form runs with the sidecar wired):
            # re-check settledness-window eligibility on this confirm/skip/
            # manual-edit seam (the harness analogue of every state-change
            # trigger maybeEmitValidateWindows fires on), then drive any steer
            # the async verdicts produced. check_steers also runs when no new
            # window fired -- a verdict from an earlier window can land turns
            # later (async).
            if validator_armed:
                client.maybe_emit_validate_windows()
                await check_steers()

            d = tracker.delta_and_advance()
            ti, ai = d["_session_text_input_tokens"], d["_session_audio_input_tokens"]
            to, ao = d["_session_text_output_tokens"], d["_session_audio_output_tokens"]
            rows.append({
                "question number": i,
                "audio in tokens": ai,
                "audio in token cost": round(ai * rates["audio_input"], 6),
                "audio out tokens": ao,
                "audio out token cost": round(ao * rates["audio_output"], 6),
                "text in tokens": ti,
                "text in token cost": round(ti * rates["text_input"], 6),
                "text out tokens": to,
                "text out token cost": round(to * rates["text_output"], 6),
                "total tokens": ti + ai + to + ao,
                "total cost": round(ti * rates["text_input"] + ai * rates["audio_input"]
                                    + to * rates["text_output"] + ao * rates["audio_output"], 6),
            })
            meta["per_question_tools"][str(i)] = [t for (qq, t) in tool_log if qq == i]
            print(f"[q{i:02d}] {fid or q.get('event')}: {rows[-1]['total tokens']} tok "
                  f"(${rows[-1]['total cost']:.4f}) tools={meta['per_question_tools'][str(i)]}",
                  flush=True)

        # Terminal boundary (mirror form_complete, the terminal drain): a final
        # window-eligibility check (the tail window settles once the LAST
        # field confirms -- no separate isFormComplete release needed, mirror
        # computeReadyWindows' own doc comment), settle any in-flight lite
        # validator/drain work, THEN the W6 whole-form gemini-2.5-pro pass
        # (bd polyglot-pdf-gbus, mirrored 0cyu) -- form_complete's SOLE
        # end-of-form report, run at the SAME point production's form_complete
        # handler spawns _run_pro_complete_and_push. Its conflicts ride the
        # SAME validation_result -> enqueue -> drain path with zero new
        # client-side machinery (that is the whole point of the shared
        # envelope), so drive one more drain settle + check_steers after it.
        if validator_armed:
            client.maybe_emit_validate_windows()
            dropped = await client.drain_pending_windows(timeout=20.0)
            if dropped:
                meta["validation_dropped_at_end"] = dropped
            dropped_drains = await client.drain_pending_drains(timeout=20.0)
            if dropped_drains:
                meta.setdefault("dropped_drains", 0)
                meta["dropped_drains"] += dropped_drains
            await check_steers()

            pro_pass_meta = {"ran": False, "model": None, "conflicts": 0}
            if use_pro_pass:
                _pro_t0 = time.monotonic()
                whole_form_fields = client.validation_fields()
                try:
                    pro_verdict = await service.handle_form_complete_pro(
                        whole_form_fields)
                except Exception as exc:  # fail-open, mirror the route's guard
                    pro_verdict = {"conflicts": [], "_error": type(exc).__name__}
                pro_conflicts = pro_verdict.get("conflicts", [])
                pro_pass_meta = {
                    "ran": True, "model": settings.VALIDATOR_PRO_MODEL,
                    "latency_s": round(time.monotonic() - _pro_t0, 3),
                    "conflicts": len(pro_conflicts),
                    # WHICH pairs the pro pass caught (E3 instrumentation gap:
                    # the count alone cannot show a far-pair catch).
                    "conflict_field_ids": [c.get("field_ids")
                                           for c in pro_conflicts],
                }
                if pro_conflicts:
                    # Same envelope handle_form_complete_pro's caller pushes in
                    # production (_run_pro_complete_and_push): a validation_
                    # result, so it rides the existing enqueue -> drain path.
                    await client.send_json(
                        {"type": "validation_result", "conflicts": pro_conflicts})
                    dropped_drains = await client.drain_pending_drains(timeout=20.0)
                    if dropped_drains:
                        meta.setdefault("dropped_drains", 0)
                        meta["dropped_drains"] += dropped_drains
                    await check_steers()
            meta["pro_pass"] = pro_pass_meta

            meta["validation_records"] = list(client.validation_records)
            meta["drain_records"] = list(client.drain_results)
            meta["steer_records"] = steer_records
        meta["event_records"] = event_records
        meta["seam_tool_records"] = seam_tool_records
        meta["text_ledger_calls"] = text_ledger_calls

        try:
            await adapter.finalize()
        except Exception:
            pass
    finally:
        for _m, _orig in _orig_get_settings:
            _m.get_settings = _orig
        _ffs_mod._log = _module_logs["ffs"]
        _callback_mod._log = _module_logs["cb"]

    prompts = [d["prompt"] or 0 for d in usage_dumps]
    meta["prompt_curve"] = prompts
    meta["eviction_drops"] = [[i + 2, prompts[i], prompts[i + 1]]
                              for i in range(len(prompts) - 1)
                              if prompts[i + 1] < prompts[i] - 50]
    meta["errors"] = [s for s in log_sink if s["event"] in _ERROR_EVENTS
                      or s["level"] in ("error", "exception", "critical")]
    meta["client_confirmed_fields"] = [fid for fid, e in client.state.items()
                                       if e.get("confirmed")]
    # G3 fill-correctness (bd polyglot-pdf-jnjj.7): the clean instrument the noisy
    # jnjj.25 confirm-counts could not be. Scores whether the model wrote the RIGHT
    # value per field (canon-compared to the expected answer). The get_field_value
    # recall-lookup arm was removed with that tool (bd polyglot-pdf-p5h2/2wod).
    # expected_tbl carries the event-script overrides (plants corrected, skips
    # expect-empty) on top of the schema's expected canon.
    expected = expected_tbl or (SCHEMAS[args.schema].get("expected") or {})
    meta["fill_accuracy"] = score_fill_accuracy(client, plan, expected)
    _fa = meta["fill_accuracy"]
    print(f"fill accuracy: {_fa['matched']}/{_fa['total']} "
          f"({_fa['accuracy']:.0%})")
    meta["fill_failure_modes"] = _se.classify_fill_failures(
        _fa["detail"], expected)
    meta["wall_clock_s"] = round(time.monotonic() - t_run_start, 1)

    csv_path = out_dir / f"{base_name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    meta["auto_apply_fids"] = [aa["field_id"]
                               for aa in (SCHEMAS[args.schema].get("auto_apply") or [])]
    (out_dir / f"{base_name}.meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8")
    summary = build_summary(meta, rows, log_sink, client, planted_groups,
                            {q["field_id"] for q in plan})
    (out_dir / f"{base_name}.summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {csv_path}")
    print(f"wrote {out_dir / (base_name + '.meta.json')}")
    print(f"wrote {out_dir / (base_name + '.summary.json')}")
    print(f"all-in: ${summary['headline']['all_in_usd']} "
          f"(voice ${summary['headline']['voice_usd']} + "
          f"text ${summary['headline']['text_usd']}); "
          f"wall clock {summary['headline']['wall_clock_s']}s")
    total = sum(r["total cost"] for r in rows)
    print(f"run total: {sum(r['total tokens'] for r in rows)} tokens, ${total:.4f}; "
          f"evictions detected: {len(meta['eviction_drops'])}; "
          f"confirmed fields: {len(meta['client_confirmed_fields'])}/{len(plan)}")

    if DEBUG:
        _write_debug_artifact(out_dir / f"{base_name}.debug.json", q_windows,
                              tool_io, client.transcript_chunks, input_transcript,
                              meta["per_question_tools"])
        print(f"wrote {out_dir / (base_name + '.debug.json')}  "
              f"(LOCAL-ONLY -- contains transcripts/field values)")
    return 0


def _chunks_in_window(chunks, w):
    """Join transcript chunks whose ts falls in window w into one de-chunked string."""
    parts = [c["text"] for c in chunks if w["t_start"] <= c["ts"] <= w["t_end"]]
    return "".join(parts).strip()


def _write_debug_artifact(path, q_windows, tool_io, transcript_chunks,
                          input_transcript, legacy_per_q_tools):
    """Assemble the bd jnjj.39 per-run debug file: per question, what the model HEARD
    (input transcript), what it SAID (output transcript, de-chunked), and the exact
    tool ARGS it sent + RESPONSE it got back -- all attributed by TIME WINDOW, not
    the mutable loop counter. Also surfaces the reliable attribution vs the legacy
    per_question_tools so the two can be compared (criterion 2). LOCAL-ONLY:
    transcripts + tool args/responses are user data; the harness is a never-deployed
    spike (mirrors the DEV_LOGGING precedent)."""
    # One attribution, used for BOTH tool_io and tools_reliable so they agree: a
    # call attributed to qN appears in qN's tool_io with its args/response, even a
    # late call that lands after the window closed (Codex PR #246).
    by_q = _attribute_records_by_window(tool_io, q_windows)
    questions = []
    for w in q_windows:
        q = w["q"]
        q_recs = by_q.get(str(q), [])
        questions.append({
            "q": q,
            "field_id": w["fid"],
            "model_heard": _chunks_in_window(input_transcript, w),
            "model_said": _chunks_in_window(transcript_chunks, w),
            "tool_io": [{"tool": r["tool"], "args": r["args"],
                         "response": r["response"]} for r in q_recs],
            "tools_reliable": [r["tool"] for r in q_recs],
            "tools_legacy": legacy_per_q_tools.get(str(q), []),
        })
    # Tool calls attributed to q0 -- before q1's window (the greeting), the only
    # genuinely out-of-question bucket now that late calls attach to their last
    # passed question above.
    out_of_window = [{"tool": r["tool"], "args": r["args"],
                      "response": r["response"], "q_at_call": r["q_at_call"]}
                     for r in by_q.get("0", [])]
    # The GREETING turn's speech falls before q1's window and would otherwise be
    # dropped -- but it is the single richest register/language sample of the
    # session (bd polyglot-pdf-6mzi multilingual assessment reads it).
    greeting_said = ""
    greeting_heard = ""
    if q_windows:
        t0 = q_windows[0]["t_start"]
        greeting_said = "".join(
            c["text"] for c in transcript_chunks if c["ts"] < t0).strip()
        greeting_heard = "".join(
            c["text"] for c in input_transcript if c["ts"] < t0).strip()
    artifact = {
        "note": ("bd polyglot-pdf-jnjj.39 debug artifact. LOCAL-ONLY -- holds "
                 "transcripts + field values (user data). Per question: model_heard "
                 "(input transcript), model_said (output speech), tool_io (exact args "
                 "sent + response received), and tools_reliable (timestamp-window "
                 "attribution) vs tools_legacy (the old mutable-counter attribution)."),
        "greeting_model_said": greeting_said,
        "greeting_model_heard": greeting_heard,
        "questions": questions,
        "out_of_window_tool_io": out_of_window,
    }
    path.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Per-question token/cost CSV instrument (bd polyglot-pdf-4loz).")
    ap.add_argument("--model", choices=["2.5", "3.1"], default="2.5")
    ap.add_argument("--schema", choices=["demo", "i90", "i90-full"], default="demo",
                    help="form schema + question plan: 'demo' (the legacy "
                         "adult-intake demo, default for back-compat), 'i90' "
                         "(the REAL form-kits/i-90 first 4 sections, 34 "
                         "questions; bd polyglot-pdf-jnjj.24), or 'i90-full' "
                         "(the WHOLE I-90 stress-test plan generated from the "
                         "g1b answer key -- ~113 questions; requires --arm dti "
                         "--continuous; bd polyglot-pdf-n86b)")
    ap.add_argument("--arm",
                    choices=["unbounded", "section-reset", "section-reset-jit", "dti", "sliding-window"],
                    default="unbounded")
    ap.add_argument("--path", choices=["happy", "unhappy"], default="happy")
    ap.add_argument("--questions", type=int, default=None,
                    help="cap the run to the first N questions; default runs the "
                         "WHOLE plan for the chosen --schema (demo=20, i90=34, "
                         "i90-full=~113)")
    ap.add_argument("--events", choices=["none", "standard", "unhappy"],
                    default="none",
                    help="i90-full only: weave the scenario-event script into "
                         "the plan (bd polyglot-pdf-eh1h). 'standard' = the E2 "
                         "realistic session (recalls, navigate-backs, a skip, "
                         "2 planted contradictions); 'unhappy' adds the E3 "
                         "extra plants (4 total, 1 far pair)")
    ap.add_argument("--mix-unhappy", type=int, default=5,
                    help="with --events standard: flag every Nth question as "
                         "unhappy (the 80/20 realistic mix at 5). 0 disables.")
    ap.add_argument("--allow-path-mismatch", action="store_true",
                    help="override the --events unhappy / --path happy guard "
                         "(bd polyglot-pdf-3gt9). --events unhappy is the E3 "
                         "scenario and is meant to run on --path unhappy "
                         "globally; combining it with the --path default "
                         "(happy) silently measures a mostly-happy session "
                         "mislabeled as the unhappy arm. Pass this flag only "
                         "if you deliberately want that combination.")
    ap.add_argument("--reactivity", default=None,
                    help="i90-full only: run ONE reactivity micro-scenario "
                         "(E4) by name -- see scenario_events.REACTIVITY_SUITE")
    ap.add_argument("--lang", default="en",
                    help="spoken-answer language for fixture synthesis (E6 "
                         "Spanish arm: 'es'; phrasing templates must exist in "
                         "full_form_script for non-'en' -- code-native es, or "
                         "a fixtures/multilang_phrases.json entry: zh/fr/hi/ru)")
    ap.add_argument("--spoken-language", default=None,
                    help="session SPOKEN language NAME sent to the model (e.g. "
                         "'Spanish', 'Chinese') -- the language Gemini SPEAKS, "
                         "seeded pre-connect exactly as the production handshake "
                         "does (ASR bias + option-label translation follow). "
                         "Default English, preserving historical arms: the E6 "
                         "run measured Spanish USER audio against an English-"
                         "speaking model. Pass BOTH --lang and --spoken-language "
                         "for a fully in-language session (bd polyglot-pdf-6mzi).")
    ap.add_argument("--text-ai", action="store_true",
                    help="wire the REAL TextAIGemini sidecar (secretary + "
                         "validator) into the run. Default ON for --schema "
                         "i90-full (deploy fidelity), OFF for legacy schemas "
                         "so historical arms measure unchanged.")
    ap.add_argument("--no-text-ai", action="store_true",
                    help="force the text sidecar OFF (overrides the i90-full "
                         "default; ask_secretary then fail-opens as production "
                         "does without a wired text model)")
    ap.add_argument("--pro-pass", action="store_true",
                    help="wire the W6 end-of-form gemini-2.5-pro whole-form "
                         "validator pass (bd polyglot-pdf-gbus), mirroring "
                         "backend/dependencies.py get_text_ai_pro (same model/"
                         "thinking-budget Settings knobs, empty fallback chain). "
                         "Opt-in: FORM_COMPLETE_PRO_VALIDATOR defaults OFF in "
                         "production (a real operational-cost dependency), so a "
                         "default harness run must not silently pay for it. "
                         "Only takes effect when the text sidecar is wired "
                         "(--text-ai / --schema i90-full).")
    ap.add_argument("--trigger", type=int, default=12_000,
                    help="sliding-window trigger_tokens; size it ABOVE the "
                         "unevictable SI+tools base (~8.2k on the full-form "
                         "scope) or compression fires on turn 1 and the data "
                         "is incomparable")
    ap.add_argument("--window", type=int, default=9_000,
                    help="sliding-window target_tokens; must exceed the SI "
                         "base for any evictable mass to exist")
    # Vertex is the DEFAULT (bd polyglot-pdf-kbi1; AI Studio is not currently
    # available to this project, so defaulting to the key path errored
    # outright). --no-vertex keeps the AI-Studio route reachable for a
    # deliberate run (e.g. future 3.1-Live experimentation on purchased
    # credits), and 3.1 still REQUIRES it -- see the --model 3.1 guard in run().
    ap.add_argument("--vertex", action=argparse.BooleanOptionalAction,
                    default=True,
                    help="use Vertex AI via ADC (DEFAULT; deploy-faithful). "
                         "Project/location from GOOGLE_CLOUD_PROJECT / "
                         "GOOGLE_CLOUD_LOCATION, defaulting to the demo "
                         "project. On 2.5 this also swaps to the Vertex model "
                         "id (MODEL_NATIVE_STANDARD_VERTEX). Pass --no-vertex "
                         "with GEMINI_API_KEY for a deliberate AI Studio run "
                         "(required for --model 3.1, which has no Vertex id).")
    ap.add_argument("--continuous", action="store_true",
                    help="ONE uninterrupted DTI session over the whole plan -- no "
                         "section resets (bd polyglot-pdf-ctu8 candidate arm). Only "
                         "valid with --arm dti; combine with --compression so the "
                         "window bounds the continuous session's growth.")
    ap.add_argument("--compression", action="store_true",
                    help="layer calibrated context-window eviction onto a non-"
                         "sliding-window arm (the jnjj.25-folded eviction test): "
                         "set --trigger/--window just above the arm's unevictable "
                         "SI+tools floor. The WINNING DTI-on-i90 calibration was "
                         "--trigger 2800 --window 2200 (-21% unhappy); a LOOSER "
                         "window (2500/3500) barely evicted and did NOT help -- use "
                         "the tight values. Lets the accumulated per-field guidance "
                         "be evicted turn-over-turn instead of replayed.")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data"))
    ap.add_argument("--synth-only", action="store_true",
                    help="build the audio cache and exit (no live calls)")
    ap.add_argument("--debug", action="store_true",
                    help="model-behavior visibility (bd polyglot-pdf-jnjj.39): write a "
                         "per-run <base>.debug.json with, per question, the model's "
                         "OUTPUT transcript, the exact tool ARGS it sent + the tool "
                         "RESPONSE it got back, and timestamp-attributed tool calls. "
                         "LOCAL-ONLY (the file holds transcripts/field values = user "
                         "data); off by default so normal cost/fill runs stay clean.")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
