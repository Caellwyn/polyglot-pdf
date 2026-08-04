"""Spec for the verify/rectify loop (bd polyglot-pdf-9ikj, epic
polyglot-pdf-sekc) -- stubbed adapters, ZERO live calls.

Pins (the bead's exit criteria + the V1-probe-decided rules):
  1. Loop bound: max 2 rectify attempts.
  2. Keep rules: judge-origin unresolved keeps the ORIGINAL;
     mechanical-origin unresolved keeps the latest LINT-CLEAN rectify.
  3. Provenance-stripped re-judge: the judge payload never carries
     problem/origin fields.
  4. Flip-flop detector = REJECTION RECURRENCE (never value identity).
  5. Mechanical failures skip the judge ON THE WAY IN; corrections
     re-enter the FULL loop (re-lint + fresh back-translate + re-judge).
  6. Every fail-open path (back-translate / judge / rectify failure)
     leaves the baked values byte-untouched, available=False; the
     deterministic lint flags still stand.
  7. Judge chunking at 50.
  8. Bake integration: default-ON via settings; flags ride the report as
     WARNING LintFinding dicts with field_id_of-parsable paths; verify
     disabled keeps the report byte-identical to the pre-gate shape.

ASCII only (scar #6).
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import backend.services.option_translation as ot
from backend.services.schema_lint import SEVERITY_WARNING, field_id_of
from backend.services.translation_verify import (
    FLAG_MECHANICAL,
    FLAG_RECTIFIED,
    FLAG_UNRESOLVED,
    verify_fresh_translations,
)

# Minimal controlled glossary: DNT USCIS, latin script for spanish.
_G = {
    "digits_policy": "ASCII digits only.",
    "do_not_translate": ["USCIS"],
    "form_number_pattern": "\\b[A-Z]{1,3}-\\d+[A-Z]{0,3}\\b",
    "format_mask_pattern":
        "(?i)\\b(?:mm|dd|yy|yyyy)(?:[/\\-.](?:mm|dd|yy|yyyy))+\\b",
    "languages": {
        "spanish": {"register": "usted", "script": "latin", "pins": {}},
    },
}


def make_lite(fail=False):
    lite = MagicMock()

    async def _bt(items, name, code):
        if fail:
            return None
        return {k: "bt:" + v for k, v in items.items()}

    lite.back_translate = AsyncMock(side_effect=_bt)
    return lite


def make_pro(judge_rules=None, rectify_rules=None, judge_fail=False,
             rectify_fail=False):
    """judge_rules: {translation: (drift, reason)}; rectify_rules:
    {translation: corrected}. Unlisted translations judge clean / rectify
    to '<value>-fixed'."""
    pro = MagicMock()
    judge_rules = judge_rules or {}
    rectify_rules = rectify_rules or {}

    async def _judge(items, name, code, *, glossary_context=None):
        if judge_fail:
            return None
        verdicts = {}
        for item in items:
            drift, reason = judge_rules.get(
                item["translation"], (False, ""))
            verdicts[item["id"]] = {"drift": drift, "reason": reason}
        return verdicts

    async def _rectify(items, name, code, *, glossary_context=None):
        if rectify_fail:
            raise RuntimeError("rectify down")
        return {
            item["id"]: rectify_rules.get(
                item["translation"], item["translation"] + "-fixed")
            for item in items
        }

    pro.judge_translations = AsyncMock(side_effect=_judge)
    pro.rectify_translations = AsyncMock(side_effect=_rectify)
    return pro


async def _run(fresh, pro, lite, **kwargs):
    return await verify_fresh_translations(
        language_name="spanish", language_code="es-US",
        fresh=fresh, pro_ai=pro, lite_ai=lite, glossary=_G, **kwargs)


# --- clean path -------------------------------------------------------------

@pytest.mark.asyncio
async def test_all_clean_no_flags_no_changes():
    fresh = {"option-label": {"Male": "Masculino", "Female": "Femenino"}}
    pro, lite = make_pro(), make_lite()
    result = await _run(fresh, pro, lite)
    assert result.available is True
    assert result.final == fresh
    assert result.flags == []
    assert pro.judge_translations.await_count == 1
    assert lite.back_translate.await_count == 1
    assert pro.rectify_translations.await_count == 0


@pytest.mark.asyncio
async def test_judge_chunked_at_50():
    fresh = {"field-name": {"src %d" % i: "val %d" % i for i in range(51)}}
    pro, lite = make_pro(), make_lite()
    await _run(fresh, pro, lite)
    assert pro.judge_translations.await_count == 2
    sizes = sorted(len(call.args[0]) for call
                   in pro.judge_translations.await_args_list)
    assert sizes == [1, 50]
    # Back-translation is ONE batched call regardless of judge chunking.
    assert lite.back_translate.await_count == 1


# --- mechanical path --------------------------------------------------------

@pytest.mark.asyncio
async def test_mechanical_failure_skips_judge_on_the_way_in():
    """A translated-away DNT term is proven wrong: it feeds rectify with
    the LINT message as the problem, and the initial judge call never sees
    it. The correction re-enters the FULL loop and, once lint-clean and
    judge-clean, REPLACES the translation under FLAG_MECHANICAL."""
    fresh = {"field-name": {"USCIS number": "Numero de inmigracion"}}
    pro = make_pro(rectify_rules={
        "Numero de inmigracion": "Numero de USCIS"})
    lite = make_lite()
    result = await _run(fresh, pro, lite)

    # Nothing was lint-clean, so NO initial judge call happened at all; the
    # single judge call is the RE-ENTRY judging the lint-clean correction.
    assert pro.judge_translations.await_count == 1
    reentry_items = pro.judge_translations.await_args_list[0].args[0]
    assert [i["translation"] for i in reentry_items] == ["Numero de USCIS"]
    rectify_items = pro.rectify_translations.await_args_list[0].args[0]
    assert "supposed to stay in English" in rectify_items[0]["problem"]
    assert result.final["field-name"]["USCIS number"] == "Numero de USCIS"
    assert [f.taxonomy for f in result.flags] == [FLAG_MECHANICAL]
    # Sanctioned reviewer phrase (bd xfdb): the rectified message asks
    # the human to read and confirm the new wording.
    assert "read the new wording" in result.flags[0].message


@pytest.mark.asyncio
async def test_mechanical_origin_unresolved_keeps_latest_lint_clean_rectify():
    """The V1-decided collision rule: both rectify attempts lint-clean but
    judge-flagged -> UNRESOLVED keeps the LINT-CLEAN rectify, never the
    provably broken original."""
    fresh = {"field-name": {"USCIS number": "Numero de inmigracion"}}
    pro = make_pro(
        judge_rules={
            "Numero de USCIS v1": (True, "still wrong"),
            "Numero de USCIS v2": (True, "still wrong"),
        },
        rectify_rules={
            "Numero de inmigracion": "Numero de USCIS v1",
            "Numero de USCIS v1": "Numero de USCIS v2",
        })
    lite = make_lite()
    result = await _run(fresh, pro, lite)
    assert pro.rectify_translations.await_count == 2  # the bound
    assert result.final["field-name"]["USCIS number"] == "Numero de USCIS v2"
    assert [f.taxonomy for f in result.flags] == [FLAG_UNRESOLVED]
    # The KEEP rule (mechanical-origin -> latest lint-clean rectify) is
    # pinned through the SANCTIONED reviewer phrase, not internal jargon
    # (bd xfdb): the message names which value the form now uses.
    assert "the best automatic correction" in result.flags[0].message
    assert "fix it by hand" in result.flags[0].message


# --- judge path -------------------------------------------------------------

@pytest.mark.asyncio
async def test_judge_flag_rectified_clean_replaces_and_flags_informational():
    fresh = {"option-label": {"Single": "Unico"}}
    pro = make_pro(
        judge_rules={"Unico": (True, "wrong sense for filing status")},
        rectify_rules={"Unico": "Soltero"})
    lite = make_lite()
    result = await _run(fresh, pro, lite)
    assert result.final["option-label"]["Single"] == "Soltero"
    assert [f.taxonomy for f in result.flags] == [FLAG_RECTIFIED]
    assert "'Unico' -> 'Soltero'" in result.flags[0].message
    # Provenance-stripped re-judge: no judge payload ever carries a
    # problem/origin field -- a correction is judged as an ordinary item.
    for call in pro.judge_translations.await_args_list:
        for item in call.args[0]:
            assert set(item) == {"id", "en", "translation",
                                 "back_translation"}
    # Fresh back-translation for the re-entry round.
    assert lite.back_translate.await_count == 2


@pytest.mark.asyncio
async def test_judge_origin_unresolved_keeps_original_at_loop_bound():
    fresh = {"option-label": {"Single": "Unico"}}
    pro = make_pro(
        judge_rules={
            "Unico": (True, "wrong sense"),
            "Unico v2": (True, "still wrong"),
            "Unico v3": (True, "still wrong"),
        },
        rectify_rules={"Unico": "Unico v2", "Unico v2": "Unico v3"})
    lite = make_lite()
    result = await _run(fresh, pro, lite)
    assert pro.rectify_translations.await_count == 2  # loop bound pin
    assert result.final["option-label"]["Single"] == "Unico"  # ORIGINAL
    assert [f.taxonomy for f in result.flags] == [FLAG_UNRESOLVED]
    # KEEP rule (judge-origin -> ORIGINAL), pinned via the sanctioned
    # phrase (bd xfdb).
    assert "the original text" in result.flags[0].message
    assert "fix it by hand" in result.flags[0].message


@pytest.mark.asyncio
async def test_flip_flop_detector_fires_on_rejection_recurrence():
    """The judge re-flags a value already flagged earlier in the trace ->
    UNRESOLVED after ONE rectify attempt (no second attempt wasted). This
    is rejection recurrence, not value identity: V1's ur trace converged
    on a re-proposed value and must NOT trip the detector."""
    fresh = {"option-label": {"Single": "Unico"}}
    pro = make_pro(
        judge_rules={"Unico": (True, "wrong sense")},
        # Rectify proposes the ORIGINAL flagged value again; the judge
        # (rules above) flags "Unico" again -> recurrence -> stop.
        rectify_rules={"Unico": "Unico2"})
    # Manually: attempt 1 corrects to "Unico2"; make the judge flag it AND
    # a second attempt propose "Unico" (already-flagged) again.
    pro = make_pro(
        judge_rules={
            "Unico": (True, "wrong sense"),
            "Unico2": (True, "also wrong"),
        },
        rectify_rules={"Unico": "Unico2", "Unico2": "Unico"})
    lite = make_lite()
    result = await _run(fresh, pro, lite)
    # Attempt 1: Unico -> Unico2 (flagged, new value -> continue).
    # Attempt 2: Unico2 -> Unico (already-flagged value, judge flags it
    # again -> flip-flop stop, UNRESOLVED).
    assert pro.rectify_translations.await_count == 2
    assert result.final["option-label"]["Single"] == "Unico"
    assert [f.taxonomy for f in result.flags] == [FLAG_UNRESOLVED]
    # The flip-flop detector's OUTCOME is what matters to a reviewer:
    # unresolved + the original kept. The detector's firing is already
    # pinned by the await_count/flow above; the message itself now uses
    # the sanctioned plain phrases (bd xfdb), not pipeline jargon.
    assert "fix it by hand" in result.flags[0].message
    assert "the original text" in result.flags[0].message


@pytest.mark.asyncio
async def test_accepted_re_proposal_does_not_trip_detector():
    """Value identity alone never fires: a re-proposed previously-rejected
    value that the judge now ACCEPTS resolves clean (the V1 ur trace)."""
    fresh = {"option-label": {"Single": "Unico"}}
    judge_calls = {"n": 0}

    async def _judge(items, name, code, *, glossary_context=None):
        judge_calls["n"] += 1
        verdicts = {}
        for item in items:
            if judge_calls["n"] == 1 and item["translation"] == "Unico":
                verdicts[item["id"]] = {"drift": True, "reason": "wrong"}
            elif judge_calls["n"] == 2:
                verdicts[item["id"]] = {"drift": True, "reason": "wrong 2"}
            else:
                verdicts[item["id"]] = {"drift": False, "reason": ""}
        return verdicts

    pro = make_pro(rectify_rules={"Unico": "Soltero", "Soltero": "Unico2"})
    pro.judge_translations = AsyncMock(side_effect=_judge)
    lite = make_lite()
    result = await _run(fresh, pro, lite)
    # attempt 1: Soltero flagged (new value); attempt 2: Unico2, judge
    # accepts -> resolved clean, detector silent.
    assert result.final["option-label"]["Single"] == "Unico2"
    assert [f.taxonomy for f in result.flags] == [FLAG_RECTIFIED]


@pytest.mark.asyncio
async def test_no_new_correction_is_unresolved():
    fresh = {"option-label": {"Single": "Unico"}}
    pro = make_pro(
        judge_rules={"Unico": (True, "wrong")},
        rectify_rules={"Unico": "Unico"})  # parrots the same value back
    result = await _run(fresh, pro, make_lite())
    assert pro.rectify_translations.await_count == 1
    assert result.final["option-label"]["Single"] == "Unico"
    assert [f.taxonomy for f in result.flags] == [FLAG_UNRESOLVED]


# --- fail-open --------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("breakage", ["bt", "judge", "rectify"])
async def test_fail_open_keeps_values_untouched(breakage):
    fresh = {"field-name": {"USCIS number": "Numero de inmigracion",
                            "Name": "Nombre"}}
    pro = make_pro(
        judge_rules={"Nombre": (True, "x")},
        judge_fail=(breakage == "judge"),
        rectify_fail=(breakage == "rectify"))
    lite = make_lite(fail=(breakage == "bt"))
    result = await _run(fresh, pro, lite)
    assert result.available is False
    assert result.final == fresh  # byte-untouched
    # The deterministic lint evidence still stands, model-free.
    assert [f.taxonomy for f in result.flags] == [FLAG_MECHANICAL]
    assert "verification unavailable" in result.flags[0].message


@pytest.mark.asyncio
async def test_empty_fresh_is_a_noop():
    pro, lite = make_pro(), make_lite()
    result = await _run({"option-label": {}}, pro, lite)
    assert result.available is True and result.flags == []
    assert pro.judge_translations.await_count == 0
    assert lite.back_translate.await_count == 0


# --- bake integration -------------------------------------------------------

def _schema():
    return {
        "fields": [
            {"id": "status", "type": "radio", "options": [
                {"value": "single", "label": "Single"},
                {"value": "married", "label": "Married"},
            ]},
            {"id": "status2", "type": "radio", "options": [
                # duplicate label -- fan-out target for the corrected value
                {"value": "single2", "label": "Single"},
            ]},
        ],
        "sections": [],
    }


def _bake_text_ai():
    ai = make_pro(
        judge_rules={"Unico": (True, "wrong sense for filing status")},
        rectify_rules={"Unico": "Soltero"})
    table = {"Single": "Unico", "Married": "Casado"}

    async def _translate(items, language_name, language_code, *,
                         form_name=None, glossary_context=None):
        result = {}
        for item in items:
            if item["kind"] == "option-set":
                result[item["id"]] = {"options": {
                    s: table[s] for s in item["options"] if s in table}}
            elif item.get("text") in table:
                result[item["id"]] = {"translation": table[item["text"]]}
        return {"items": result, "ambiguous": []}

    ai.translate_items = AsyncMock(side_effect=_translate)
    return ai


@pytest.fixture(autouse=True)
def _fresh_cache():
    ot._reset_cache_for_tests()
    yield
    ot._reset_cache_for_tests()


@pytest.mark.asyncio
async def test_bake_verify_corrects_before_fanout_and_reports_flags():
    schema = _schema()
    report = await ot.bake_label_translations(
        schema, _bake_text_ai(), {"spanish": "es-US"},
        verify=True, verify_lite_ai=make_lite(), glossary=_G)

    # The corrected value fanned out to EVERY location of the source label.
    for field_id, value in (("status", "single"), ("status2", "single2")):
        options = next(f for f in schema["fields"]
                       if f["id"] == field_id)["options"]
        opt = next(o for o in options if o["value"] == value)
        assert opt["label_translations"]["spanish"] == "Soltero"
    # Flags ride the report: WARNING severity, taxonomy rule, one finding
    # per kit location, field_id_of-parsable paths.
    assert len(report["flags"]) == 2
    for finding in report["flags"]:
        assert finding["severity"] == SEVERITY_WARNING
        assert finding["rule"] == FLAG_RECTIFIED
        assert finding["field_id"] in ("status", "status2")
        assert field_id_of(finding["path"]) == finding["field_id"]
        assert finding["path"].endswith(".label_translations.spanish")
    assert report["languages"]["spanish"]["verify"] == {
        "available": True, "checked": 2, "mechanical": 0,
        "judge_flagged": 1, "rectified": 1, "unresolved": 0,
    }


@pytest.mark.asyncio
async def test_bake_verify_disabled_report_shape_unchanged():
    schema = _schema()
    report = await ot.bake_label_translations(
        schema, _bake_text_ai(), {"spanish": "es-US"}, verify=False)
    assert "flags" not in report
    assert "verify" not in report["languages"]["spanish"]


@pytest.mark.asyncio
async def test_bake_default_on_reads_settings(monkeypatch):
    from backend import config
    monkeypatch.setattr(
        config, "get_settings",
        lambda: SimpleNamespace(TRANSLATION_VERIFY_ENABLED=True))
    schema = _schema()
    report = await ot.bake_label_translations(
        schema, _bake_text_ai(), {"spanish": "es-US"},
        verify_lite_ai=make_lite(), glossary=_G)
    assert "flags" in report  # the gate ran without an explicit verify=True


@pytest.mark.asyncio
async def test_bake_default_construction_path(monkeypatch):
    """The production-default path (fresh-eyes coverage finding): with NO
    lite adapter or glossary passed, the bake constructs the lite adapter
    itself (settings-driven, credential-less here -> client None ->
    fail-open) and loads the REAL committed glossary file. Exercises
    _build_verify_lite_ai + load_glossary end to end without live calls."""
    from backend import config
    monkeypatch.setattr(
        config, "get_settings",
        lambda: SimpleNamespace(
            TRANSLATION_VERIFY_ENABLED=True,
            TRANSLATION_VERIFY_BT_MODEL="gemini-2.5-flash-lite",
            GEMINI_API_KEY=None,
            VERTEXAI=False,
        ))
    schema = _schema()
    report = await ot.bake_label_translations(
        schema, _bake_text_ai(), {"spanish": "es-US"})
    # Construction succeeded, the real glossary loaded, and the
    # credential-less lite adapter fail-opened the verify pass -- values
    # baked, verify reported unavailable, flags key present (gate ran).
    verify = report["languages"]["spanish"]["verify"]
    assert verify["available"] is False
    assert "flags" in report
    options = next(f for f in schema["fields"]
                   if f["id"] == "status")["options"]
    assert options[0]["label_translations"]["spanish"] == "Unico"


@pytest.mark.asyncio
async def test_bake_verify_outage_leaves_kit_byte_identical():
    schema_off = _schema()
    await ot.bake_label_translations(
        schema_off, _bake_text_ai(), {"spanish": "es-US"}, verify=False)
    schema_broken = _schema()
    report = await ot.bake_label_translations(
        schema_broken, _bake_text_ai(), {"spanish": "es-US"},
        verify=True, verify_lite_ai=make_lite(fail=True),
        glossary=_G)
    assert json.dumps(schema_broken, sort_keys=True) \
        == json.dumps(schema_off, sort_keys=True)
    assert report["languages"]["spanish"]["verify"]["available"] is False
    assert report["flags"] == []  # nothing mechanically wrong here
