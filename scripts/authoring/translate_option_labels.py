#!/usr/bin/env python3
"""Bake option label_translations into an EXISTING form-kit schema
(bd polyglot-pdf-2h9j, extraction-time option translations).

The runtime secretary translation (bd ow1e) translates option labels per
process at session start; this tool bakes STOCK translations into the kit JSON
instead, so the runtime call short-circuits via the kit-precedence rule and
the translations become deterministic, reviewable artifacts. The bake itself
lives in backend/services/option_translation.py::bake_label_translations (ONE
shared implementation for this CLI, the extraction pipeline, and the hosted
editor route): unique labels are deduped, ONE batched translate call per
language covers what the kit lacks, and results fan out to every option under
the canonical key (the lowercase spoken-language name).

Idempotent: an option already covered for a language (under ANY accepted key
form) is never re-requested or rewritten, so a second run is a no-op and
future language additions re-use this same tool. --force retranslates and
overwrites the canonical key (the remedy for translations gone stale after an
option label was renamed in the editor).

Calls Gemini on Vertex (ADC; the repo default for all live-model work) with
OPTION_TRANSLATION_MODEL-class quality: pro tier by default -- authoring is a
one-off per form, so quality beats per-call cost (same doctrine as
EXTRACTOR_MODEL). The fallback chain is disabled on purpose: an explicitly
chosen tier fails LOUD instead of silently degrading to the lite chain.

ASCII only (cp1252 safe): prints counts, never translated strings; writes
json with ensure_ascii (same convention as extract_form.py and the committed
schema files).

Usage:
    python scripts/authoring/translate_option_labels.py --kit form-kits/i-90
    ... --schema path/schema.json
    ... --check                      # report only, write nothing
    ... --languages spanish,french   # subset (lowercase names)
    ... --force                      # retranslate + overwrite canonical keys

Exit codes:
    0  fully covered (nothing missing) / clean write, all languages succeeded
    1  --check found missing translations (a write run would change the file)
    2  one or more languages failed (write mode still writes the partial
       result -- re-run to fill the gap)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from backend.services.option_translation import bake_label_translations  # noqa: E402
from backend.utils.language_codes import SPOKEN_LANGUAGE_BCP47  # noqa: E402

DEFAULT_MODEL = os.getenv("OPTION_TRANSLATION_MODEL", "gemini-2.5-pro")
# 2.5-pro cannot disable thinking; a bounded budget keeps the call cheap
# (W6 pattern, backend/config.py VALIDATOR_PRO_MODEL).
PRO_THINKING_BUDGET = 512


def _resolve_languages(spec: str | None) -> dict[str, str]:
    """The {lowercase-name: bcp47} set to bake: all supported spoken languages
    minus english (labels are already English), or the --languages subset."""
    supported = {n: c for n, c in SPOKEN_LANGUAGE_BCP47.items() if n != "english"}
    if not spec:
        return supported
    picked = {}
    for raw in spec.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        if name not in supported:
            valid = ", ".join(sorted(supported))
            raise SystemExit(
                f"ERROR: unknown/unsupported language '{name}' (valid: {valid})")
        picked[name] = supported[name]
    if not picked:
        raise SystemExit("ERROR: --languages resolved to an empty set")
    return picked


def _build_text_ai(model: str, project: str | None, location: str):
    """Vertex/ADC adapter with the fallback chain disabled (fail loud, never
    silently degrade a deliberately chosen tier)."""
    from backend.adapters.text_ai_gemini import TextAIGemini  # noqa: E402 lazy

    thinking = PRO_THINKING_BUDGET if "pro" in model else None
    return TextAIGemini(
        model=model,
        vertexai=True,
        project=project or os.getenv("GOOGLE_CLOUD_PROJECT"),
        location=location,
        fallback_models=(),
        thinking_budget=thinking,
    )


def translate_kit(
    schema_path: str,
    languages: dict[str, str],
    *,
    check: bool,
    force: bool,
    model: str,
    project: str | None,
    location: str,
) -> int:
    """Bake translations into one schema file. Returns the exit code."""
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)

    if check:
        # Report-only: a stub adapter that translates nothing tells us exactly
        # what a write run WOULD request, with zero API calls.
        class _Probe:
            async def translate_labels(self, labels, name, code):
                return {}
        text_ai = _Probe()
    else:
        text_ai = _build_text_ai(model, project, location)

    report = asyncio.run(bake_label_translations(
        schema, text_ai, languages, only_missing=not force))

    mode = "CHECK" if check else "PATCH"
    missing_total = 0
    for name in sorted(report["languages"]):
        entry = report["languages"][name]
        missing_total += entry["missing"]
        print(f"[{mode}] {schema_path} {name}: labels={entry['labels']} "
              f"missing={entry['missing']} translated={entry['translated']} "
              f"options_updated={entry['options_updated']}"
              + (" FAILED" if entry["failed"] else ""))

    if check:
        # A write run changes the file when labels need translating OR when an
        # existing kit translation would fan out to an uncovered twin option
        # (report["changed"] catches the latter -- the probe translates nothing,
        # so any change it produced was model-free fan-out).
        if missing_total or report["changed"]:
            print(f"  {missing_total} label-language pairs missing; a write "
                  f"run would change the file")
            return 1
        print("  fully covered")
        return 0

    if report["changed"]:
        with open(schema_path, "w", encoding="utf-8") as fh:
            json.dump(schema, fh, indent=2)
            fh.write("\n")  # committed kits end with a newline; keep diffs quiet
        print(f"  wrote {schema_path}")
    else:
        print("  no changes")

    if report["failed_languages"]:
        print(f"  FAILED languages: {', '.join(report['failed_languages'])} "
              f"-- re-run to fill the gap")
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Bake option label_translations (all supported spoken "
                    "languages) into a form-kit schema.json.")
    ap.add_argument("--kit", help="Kit directory holding schema.json "
                                  "(e.g. form-kits/i-90)")
    ap.add_argument("--schema", help="Explicit schema.json path")
    ap.add_argument("--check", action="store_true",
                    help="Report only; write nothing, call no model. Exit 1 "
                         "if a write run would change the file.")
    ap.add_argument("--languages",
                    help="Comma-separated lowercase language names to bake "
                         "(default: every supported spoken language)")
    ap.add_argument("--force", action="store_true",
                    help="Retranslate everything and overwrite the canonical "
                         "(lowercase-name) keys -- use after option labels "
                         "were renamed.")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help=f"Gemini model for the batch calls "
                         f"(default: {DEFAULT_MODEL})")
    ap.add_argument("--project", default=None,
                    help="GCP project for Vertex (default: "
                         "GOOGLE_CLOUD_PROJECT)")
    ap.add_argument("--location", default="us-central1",
                    help="Vertex location (default: us-central1)")
    args = ap.parse_args(argv)

    if args.kit:
        if args.schema:
            ap.error("pass EITHER --kit OR --schema, not both")
        schema_path = os.path.join(args.kit, "schema.json")
    elif args.schema:
        schema_path = args.schema
    else:
        ap.error("pass --kit DIR or --schema FILE")

    if not os.path.exists(schema_path):
        print(f"ERROR: {schema_path} not found")
        return 2

    languages = _resolve_languages(args.languages)
    return translate_kit(
        schema_path, languages,
        check=args.check, force=args.force,
        model=args.model, project=args.project, location=args.location,
    )


if __name__ == "__main__":
    sys.exit(main())
