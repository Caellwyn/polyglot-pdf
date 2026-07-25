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
    ... --no-verify                  # skip the verify/rectify gate (bd 9djc;
                                     # default ON via TRANSLATION_VERIFY_ENABLED)
    ... --flags-out flags.json       # write the full flag list (messages
                                     # included) as a JSON artifact

Flag surfacing (bd polyglot-pdf-9djc): a write run prints a FLAGS summary
block -- counts by rule plus each flag's rule + kit path. Flag MESSAGES may
quote foreign-script strings, so the console block never prints them (the
cp1252 rule above); --flags-out carries the complete findings, ensure_ascii.
Flags are WARNINGs by contract and never change the exit code.

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


def _ascii(text: str) -> str:
    """cp1252-safe console form of a possibly non-ASCII string (rule in the
    module docstring): escape, never crash the Windows default console."""
    return str(text).encode("ascii", "backslashreplace").decode("ascii")


def _resolve_verify(check: bool, no_verify: bool) -> tuple[bool, str | None]:
    """The effective verify-gate state + the skip reason to surface (bd 9djc).

    --check is report-only (zero model calls), so the gate is force-off there
    with no message -- nothing gets verified because nothing gets translated.
    Otherwise --no-verify wins, then TRANSLATION_VERIFY_ENABLED (the bake
    would resolve the same setting itself; resolving it HERE lets the CLI say
    so -- the opt-out must be discoverable on this surface).
    """
    if check:
        return False, None
    if no_verify:
        return False, "--no-verify"
    from backend.config import get_settings  # noqa: E402 lazy (heavy import)
    if not get_settings().TRANSLATION_VERIFY_ENABLED:
        return False, "TRANSLATION_VERIFY_ENABLED=false"
    return True, None


def translate_kit(
    schema_path: str,
    languages: dict[str, str],
    *,
    check: bool,
    force: bool,
    model: str,
    project: str | None,
    location: str,
    no_verify: bool = False,
    flags_out: str | None = None,
) -> int:
    """Bake translations into one schema file. Returns the exit code."""
    with open(schema_path, encoding="utf-8") as fh:
        schema = json.load(fh)

    if check:
        # Report-only: a stub adapter that translates nothing tells us exactly
        # what a write run WOULD request, with zero API calls (the bake's
        # forward path is translate_items -- bd polyglot-pdf-alry -- and an
        # empty result also keeps the verify gate dormant: no fresh strings).
        class _Probe:
            async def translate_items(self, items, name, code, *,
                                      form_name=None, glossary_context=None):
                return {"items": {}, "ambiguous": []}
        text_ai = _Probe()
    else:
        text_ai = _build_text_ai(model, project, location)

    verify, skip_reason = _resolve_verify(check, no_verify)
    if not check:
        # The verify gate's state is part of the CLI surface (bd 9djc exit
        # criterion): baking UNVERIFIED must be visible, not silent.
        print("verify: ON (flags surface below)" if verify
              else f"verify: skipped ({skip_reason}) -- translations bake "
                   f"UNVERIFIED")

    report = asyncio.run(bake_label_translations(
        schema, text_ai, languages, only_missing=not force, verify=verify))

    mode = "CHECK" if check else "PATCH"
    missing_total = 0
    for name in sorted(report["languages"]):
        entry = report["languages"][name]
        # Spoken-name gaps count toward the --check exit code too (bd tupu.1);
        # .get keeps the CLI tolerant of an older bake report shape.
        missing_total += entry["missing"] + entry.get("names_missing", 0)
        verify_counts = entry.get("verify") or {}
        verify_note = ""
        if verify_counts:
            if verify_counts.get("available"):
                verify_note = (
                    f" verify=checked:{verify_counts.get('checked', 0)}"
                    f"/rectified:{verify_counts.get('rectified', 0)}"
                    f"/unresolved:{verify_counts.get('unresolved', 0)}")
            else:
                verify_note = " verify=UNAVAILABLE (baked unverified)"
        print(f"[{mode}] {schema_path} {name}: labels={entry['labels']} "
              f"missing={entry['missing']} translated={entry['translated']} "
              f"options_updated={entry['options_updated']} "
              f"names={entry.get('spoken_names', 0)} "
              f"names_missing={entry.get('names_missing', 0)} "
              f"names_translated={entry.get('names_translated', 0)} "
              f"fields_updated={entry.get('fields_updated', 0)}"
              + verify_note
              + (" FAILED" if entry["failed"] else ""))

    # FLAGS summary block (bd 9djc): rule + path only on the console (messages
    # can quote foreign-script strings -- cp1252 hazard); the full findings go
    # to --flags-out. Ambiguity self-flags flow here even with verify off (they
    # come from the forward call), so this block is not gated on `verify`.
    flags = report.get("flags") or []
    if flags:
        by_rule: dict[str, int] = {}
        for flag in flags:
            rule = str(flag.get("rule", "?"))
            by_rule[rule] = by_rule.get(rule, 0) + 1
        summary = ", ".join(f"{r}={n}" for r, n in sorted(by_rule.items()))
        print(f"FLAGS: {len(flags)} ({summary}) -- human-review worklist; "
              f"WARNINGs only, never blocks")
        shown = flags[:20]
        for flag in shown:
            print(f"  {_ascii(flag.get('rule'))} {_ascii(flag.get('path'))}")
        if len(flags) > len(shown):
            print(f"  ... and {len(flags) - len(shown)} more "
                  f"(--flags-out carries the full list)")
    if flags_out:
        # Written even when empty so automation can rely on the artifact
        # existing; ensure_ascii (the default) keeps it cp1252-safe to cat.
        artifact = {
            "schema": schema_path,
            "verify_enabled": verify,
            "flags": flags,
            # Semantics note (bd polyglot-pdf-kpar): verify_counts tally
            # verified SOURCE STRINGS per language; `flags` carries one
            # finding per KIT LOCATION (a source fans out to every field/
            # option repeating it), so len(flags) can exceed the counts --
            # they agree after deduping findings by (rule, source).
            "verify_counts_note": (
                "verify_counts are per verified SOURCE STRING; flags are "
                "per KIT LOCATION (fan-out) -- equal after deduping flags "
                "by (rule, source)"),
            "verify_counts": {
                name: entry["verify"]
                for name, entry in sorted(report["languages"].items())
                if entry.get("verify")
            },
        }
        with open(flags_out, "w", encoding="utf-8") as fh:
            json.dump(artifact, fh, indent=2)
            fh.write("\n")
        print(f"wrote flags artifact {flags_out}")

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
    ap.add_argument("--no-verify", action="store_true",
                    help="Skip the verify/rectify gate (bd 9djc); the default "
                         "is ON (TRANSLATION_VERIFY_ENABLED) and bakes only "
                         "verified translations. Skipping bakes UNVERIFIED.")
    ap.add_argument("--flags-out", default=None, metavar="PATH",
                    help="Write the full verify/ambiguity flag list (messages "
                         "included) as a JSON artifact at PATH.")
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
        no_verify=args.no_verify, flags_out=args.flags_out,
    )


if __name__ == "__main__":
    sys.exit(main())
