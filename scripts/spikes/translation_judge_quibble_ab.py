"""Judge-reframe FP measurement on the V5 quibble set (bd polyglot-pdf-g0ka).

Direct A/B for the language-lock judge reframe: the 14 cases below are V5
judge-origin UNRESOLVED keeps (the old prompt flagged every one, twice) that
the cross-family Claude audit certified acceptable. Run against the CURRENT
judge prompt; the old-prompt baseline is the V5 run itself (14/14 flagged).
Measured 2026-07-25 with the reframed prompt: 9/14 then 8/14 across
two runs (-36% to -43%; data/quibble_ab_results.json), with the
residual flags substantive (omitted 'first name' concepts, Suite->Office
narrowing, the IRSN DNT case bd c6td retires) rather than stylistic.
Spend: ~$0.02/run on Vertex (ADC). Usage:

    python scripts/spikes/translation_judge_quibble_ab.py <repo-root>

ASCII-only source; foreign strings are read from the kits at runtime.
"""
# The strings below are V5 judge-origin UNRESOLVED keeps (old prompt flagged
# every one as drift, 2x each) that the cross-family Claude audit certified
# acceptable. Under the reframed judge they should mostly NOT flag.
# Flow per language: lite back-translate -> pro judge (the real adapter
# path, real glossary context). Spend: a few cents.
import asyncio
import json
import sys
from pathlib import Path

WT = Path(sys.argv[1])
sys.path.insert(0, str(WT))

from backend.adapters.text_ai_gemini import TextAIGemini  # noqa: E402
from backend.services.translation_lint import (  # noqa: E402
    glossary_prompt_context, load_glossary)

# (language, code, field-id/option, source) -- kept translations are read
# from the shipped kits so we judge exactly what shipped.
CASES = [
    ("swedish", "sv-SE", ("i-90", "field", "p1_line5a_familyname")),
    ("swedish", "sv-SE", ("i-90", "field", "p1_line5b_givenname")),
    ("swedish", "sv-SE", ("i-90", "field", "p1_line5c_middlename")),
    ("swedish", "sv-SE", ("i-90", "field", "p7_line3a_streetnumbername")),
    ("swedish", "sv-SE", ("w7", "field", "previously_received_itin")),
    ("ukrainian", "uk-UA", ("i-90", "option", "p1_unit_type6c_unit", "suite")),
    ("ukrainian", "uk-UA", ("i-90", "field", "p1_unit_type6c_unit")),
    ("ukrainian", "uk-UA", ("w7", "field", "prior_name_first")),
    ("russian", "ru-RU", ("i-90", "option", "p1_unit_type6c_unit", "suite")),
    ("russian", "ru-RU", ("w7", "field", "prior_name_first")),
    ("korean", "ko-KR", ("w7", "field", "prior_name_first")),
    ("italian", "it-IT", ("w7", "field", "name_1b_first")),
    ("german", "de-DE", ("i-90", "field", "p6_line3e_zipcode")),
    ("dutch", "nl-NL", ("w7", "field", "irsn_part1")),
]


def resolve(kit_schema, spec, lang):
    if spec[1] == "field":
        for f in kit_schema["fields"]:
            if isinstance(f, dict) and f.get("id") == spec[2]:
                src = f.get("spoken_name") or f.get("name")
                return src, (f.get("spoken_name_translations") or {}).get(lang)
    else:
        for f in kit_schema["fields"]:
            if isinstance(f, dict) and f.get("id") == spec[2]:
                for o in f.get("options") or []:
                    if str(o.get("value")) == spec[3]:
                        return o.get("label"), \
                            (o.get("label_translations") or {}).get(lang)
    return None, None


async def main():
    kits = {k: json.load(open(WT / "form-kits" / k / "schema.json",
                              encoding="utf-8")) for k in ("i-90", "w7")}
    glossary = load_glossary(WT / "form-kits" / "_translation"
                             / "glossary.json")
    pro = TextAIGemini(model="gemini-2.5-pro", vertexai=True,
                       project="polyglot-demo-aa709",
                       location="us-central1", fallback_models=(),
                       thinking_budget=512)
    lite = TextAIGemini(model="gemini-2.5-flash-lite", vertexai=True,
                        project="polyglot-demo-aa709",
                        location="us-central1", fallback_models=())
    by_lang = {}
    for lang, code, spec in CASES:
        src, tr = resolve(kits[spec[0]], spec, lang)
        assert src and tr, (lang, spec)
        by_lang.setdefault((lang, code), []).append(
            {"id": f"{spec[0]}:{spec[2]}", "en": src, "translation": tr})
    total = flagged = 0
    results = []
    for (lang, code), items in by_lang.items():
        back = await lite.back_translate(
            {i["id"]: i["translation"] for i in items}, lang, code)
        for i in items:
            i["back_translation"] = (back or {}).get(i["id"], "")
        verdicts = await pro.judge_translations(
            items, lang, code,
            glossary_context=glossary_prompt_context(glossary, lang))
        for i in items:
            v = (verdicts or {}).get(i["id"], {})
            drift = bool(v.get("drift"))
            total += 1
            flagged += drift
            reason = str(v.get("reason", ""))[:90] if drift else ""
            suffix = (" -- " + reason.encode("ascii", "backslashreplace")
                      .decode("ascii")) if drift else ""
            print(f"{lang} {i['id']}: drift={drift}{suffix}")
            results.append({
                "language": lang, "id": i["id"], "en": i["en"],
                "translation": i["translation"],
                "back_translation": i["back_translation"],
                "drift": drift, "reason": str(v.get("reason", "")),
            })
    print(f"\nQUIBBLE SET: {flagged}/{total} still flagged "
          f"(old prompt: {total}/{total} -- every case was a V5 judge-origin "
          f"unresolved keep)")
    # Committed audit artifact (house convention: every live measurement
    # leaves reproducible data, not prose).
    out = Path(__file__).resolve().parent / "data" / "quibble_ab_results.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({
            "bead": "polyglot-pdf-g0ka",
            "judge_rules_sha": __import__("hashlib").sha256(
                _TAG_RULES().encode("utf-8")).hexdigest()[:16],
            "old_prompt_baseline": f"{total}/{total} flagged (V5 run, "
                                   "docs/research/v5-rebake artifacts)",
            "results": results,
            "flagged": flagged, "total": total,
        }, fh, indent=1)
    print(f"wrote {out}")


def _TAG_RULES():
    from backend.adapters.text_ai_gemini import TextAIGemini
    return TextAIGemini._JUDGE_RULES

asyncio.run(main())
