"""The verify/rectify loop for freshly baked translations (bd
polyglot-pdf-9ikj, V3 of epic polyglot-pdf-sekc; plan
docs/sprint_14_translation-quality-gate_plan.md Part B; discrimination
evidence: the V1 probe, scripts/spikes/translation_gate_findings.md).

Pipeline per language, batched (never per string):
  0. deterministic mechanical lint (translation_lint -- free, proof of
     wrongness; failures skip the judge ON THE WAY IN);
  1. independent back-translation (LITE adapter -- supporting evidence);
  2. bilingual judge (PRO adapter, chunked at 50 -- the V1 A/B pin);
  3. bounded rectify (PRO, max 2 attempts), every correction re-entering
     the FULL loop: re-lint + fresh back-translate + provenance-stripped
     re-judge.

V1-decided rules baked in here:
- KEEP rules: a correction replaces the translation ONLY on a
  lint-clean + judge-clean re-entry. Unresolved after the bound:
  mechanical-origin keeps the latest LINT-CLEAN rectify attempt when one
  exists (the live V1 collision: keep-original would have shipped a
  provably wrong digit); judge-origin keeps the ORIGINAL (a twice-rejected
  rectify may be appeasement drift). Both flag UNRESOLVED.
- FLIP-FLOP detector, keyed on REJECTION RECURRENCE: the judge flagging a
  candidate value that was already flagged earlier in the item's trace
  ends the loop early (UNRESOLVED). Never value identity alone -- V1's ur
  trace converged on a re-proposed value.

Fail-open throughout: a missing/failed back-translate, judge, or rectify
leg leaves every original baked translation in place (`available=False`,
a "verification unavailable" note in the report); the deterministic lint
flags gathered before the failure still stand (they need no model). The
gate can never make a kit worse than today's unverified state.

Flags are data records the bake converts to schema_lint.LintFinding
(severity WARNING -- never ERROR, so no flag can block kit publish;
shipping decisions on flags stay human). ASCII-only source (scar #6).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

from backend.services.translation_lint import (
    glossary_prompt_context,
    lint_translation,
)

_log = structlog.get_logger(__name__)

JUDGE_CHUNK_SIZE = 50   # V1 A/B: identical verdicts at 25 vs 50 on the
                        # validated set; 50 halves the judge calls.
MAX_RECTIFY_ATTEMPTS = 2

FLAG_RECTIFIED = "translation-drift-rectified"
FLAG_UNRESOLVED = "translation-drift-unresolved"
FLAG_MECHANICAL = "translation-mechanical"


@dataclass
class VerifyFlag:
    """One verify outcome worth surfacing, keyed by SOURCE string -- the
    bake resolves kit paths after fan-out (a source may land in several
    schema locations; one LintFinding is emitted per location)."""

    taxonomy: str          # FLAG_RECTIFIED | FLAG_UNRESOLVED | FLAG_MECHANICAL
    kind: str              # option-label | field-name | section-title
    source: str            # the English source string
    message: str


@dataclass
class VerifyResult:
    available: bool
    final: Dict[str, Dict[str, str]]   # kind -> {source: final translation}
    flags: List[VerifyFlag] = field(default_factory=list)
    # counts tally verified SOURCE STRINGS (one per unique string checked:
    # checked/mechanical/judge_flagged/rectified/unresolved). Downstream,
    # the bake fans each VerifyFlag out to EVERY kit location its source
    # appears at (one LintFinding per location), so an artifact's flags
    # list can legitimately be LONGER than these counts -- they agree after
    # deduping findings by (rule, source). Do not "reconcile" one to the
    # other (bd polyglot-pdf-kpar).
    counts: Dict[str, int] = field(default_factory=dict)


@dataclass
class _Item:
    item_id: str
    kind: str
    source: str
    original: str
    current: str
    back_translation: str = ""
    lint_messages: List[str] = field(default_factory=list)
    mechanical_origin: bool = False
    problem: str = ""
    flagged_values: List[str] = field(default_factory=list)
    latest_lint_clean_rectify: Optional[str] = None
    resolved: Optional[str] = None     # a fully clean replacement
    unresolved: bool = False
    trace: List[str] = field(default_factory=list)


class _VerifyUnavailable(Exception):
    """A model leg failed -- fail open, keep originals."""


def _unavailable(fresh: Dict[str, Dict[str, str]], checked: int,
                 lint_flags: List[VerifyFlag], stage: str) -> VerifyResult:
    _log.warning("translation_verify_unavailable", stage=stage)
    return VerifyResult(
        available=False,
        final={kind: dict(values) for kind, values in fresh.items()},
        flags=lint_flags,   # deterministic evidence stands, model-free
        counts={"checked": checked, "unavailable": 1},
    )


async def verify_fresh_translations(
    *,
    language_name: str,
    language_code: str,
    fresh: Dict[str, Dict[str, str]],
    pro_ai: Any,
    lite_ai: Any,
    glossary: Optional[Dict[str, Any]],
    chunk_size: int = JUDGE_CHUNK_SIZE,
    max_attempts: int = MAX_RECTIFY_ATTEMPTS,
) -> VerifyResult:
    """Run the loop over one language's freshly baked strings.

    `fresh` maps kind -> {source: translation} for exactly the strings this
    bake translated (already-covered kit strings are NOT re-verified --
    idempotent re-runs stay cheap). Returns the final (possibly corrected)
    maps + flags; on any model-leg failure returns the originals untouched
    with available=False (the deterministic lint flags still included).
    """
    items: List[_Item] = []
    for kind, values in (fresh or {}).items():
        for source, translation in (values or {}).items():
            if isinstance(source, str) and isinstance(translation, str) \
                    and translation.strip():
                items.append(_Item(
                    item_id="%s:%d" % (kind, len(items)),
                    kind=kind, source=source,
                    original=translation, current=translation,
                ))
    if not items:
        return VerifyResult(available=True, final={
            kind: dict(values) for kind, values in (fresh or {}).items()})

    # Stage 0 -- deterministic lint (free; PROOF of wrongness).
    lint_flags: List[VerifyFlag] = []
    for item in items:
        failures = lint_translation(
            item.source, item.current, language_name, glossary)
        if failures:
            item.lint_messages = [f.message for f in failures]
            item.mechanical_origin = True
            item.problem = "; ".join(item.lint_messages)
            item.flagged_values.append(item.current)
            item.trace.append("lint: " + item.problem)

    glossary_context = glossary_prompt_context(glossary, language_name)
    try:
        flagged = await _initial_round(
            items, language_name, language_code, pro_ai, lite_ai,
            glossary_context, chunk_size)
        if flagged:
            await _rectify_rounds(
                flagged, language_name, language_code, pro_ai, lite_ai,
                glossary, glossary_context, chunk_size, max_attempts)
    except _VerifyUnavailable as exc:
        # The lint flags for mechanically failed items still stand.
        for item in items:
            if item.mechanical_origin:
                lint_flags.append(VerifyFlag(
                    taxonomy=FLAG_MECHANICAL, kind=item.kind,
                    source=item.source,
                    message=item.problem + " -- automatic verification "
                            "unavailable right now, so this was left "
                            "as-is; review it by hand",
                ))
        return _unavailable(fresh, len(items), lint_flags, str(exc))

    return _finalize(items, fresh)


async def _initial_round(
    items: List[_Item],
    language_name: str,
    language_code: str,
    pro_ai: Any,
    lite_ai: Any,
    glossary_context: Optional[Dict[str, Any]],
    chunk_size: int,
) -> List[_Item]:
    """Back-translate everything, judge the lint-clean set. Returns the
    flagged items (mechanical + judge-drift) headed to rectify."""
    await _back_translate(items, language_name, language_code, lite_ai)
    clean = [item for item in items if not item.mechanical_origin]
    verdicts = await _judge(
        clean, language_name, language_code, pro_ai, glossary_context,
        chunk_size)
    flagged: List[_Item] = [i for i in items if i.mechanical_origin]
    for item in clean:
        verdict = verdicts.get(item.item_id) or {}
        if verdict.get("drift"):
            item.problem = verdict.get("reason") or "drift"
            item.flagged_values.append(item.current)
            item.trace.append("judge: " + item.problem)
            flagged.append(item)
    return flagged


async def _rectify_rounds(
    flagged: List[_Item],
    language_name: str,
    language_code: str,
    pro_ai: Any,
    lite_ai: Any,
    glossary: Optional[Dict[str, Any]],
    glossary_context: Optional[Dict[str, Any]],
    chunk_size: int,
    max_attempts: int,
) -> None:
    current = flagged
    for attempt in range(1, max_attempts + 1):
        payload = [{
            "id": item.item_id, "en": item.source,
            "translation": item.current,
            "back_translation": item.back_translation,
            "problem": item.problem,
        } for item in current]
        corrections = await _call(
            pro_ai.rectify_translations(
                payload, language_name, language_code,
                glossary_context=glossary_context),
            stage="rectify")

        # Full-loop re-entry: every corrected candidate re-lints FIRST; a
        # lint-failed candidate goes straight to the next rectify attempt
        # (its failure is proven, no judge needed on the way in), a
        # lint-clean candidate gets a fresh back-translation and a
        # provenance-stripped re-judge.
        lint_failed_this_round: List[_Item] = []
        judge_set: List[_Item] = []
        for item in current:
            corrected = corrections.get(item.item_id)
            if not corrected or corrected == item.current:
                item.unresolved = True
                item.trace.append(
                    "attempt %d: no new correction" % attempt)
                continue
            item.current = corrected
            failures = lint_translation(
                item.source, corrected, language_name, glossary)
            if failures:
                item.lint_messages = [f.message for f in failures]
                item.problem = "; ".join(item.lint_messages)
                item.flagged_values.append(corrected)
                item.trace.append(
                    "attempt %d: lint-failed: %s" % (attempt, item.problem))
                lint_failed_this_round.append(item)
                continue
            item.lint_messages = []
            if item.mechanical_origin:
                item.latest_lint_clean_rectify = corrected
            judge_set.append(item)

        await _back_translate(
            judge_set, language_name, language_code, lite_ai)
        verdicts = await _judge(
            judge_set, language_name, language_code, pro_ai,
            glossary_context, chunk_size)
        still: List[_Item] = list(lint_failed_this_round)
        for item in judge_set:
            verdict = verdicts.get(item.item_id) or {}
            if not verdict.get("drift"):
                item.resolved = item.current
                item.trace.append("attempt %d: clean" % attempt)
                continue
            reason = verdict.get("reason") or "drift"
            # FLIP-FLOP detector (rejection recurrence): the judge just
            # flagged a value that was ALREADY flagged earlier in this
            # item's trace -> stop, UNRESOLVED (V1's zh-g11 oscillation).
            if item.current in item.flagged_values:
                item.unresolved = True
                item.trace.append(
                    "attempt %d: flip-flop (re-flagged a previously "
                    "flagged value): %s" % (attempt, reason))
                continue
            item.flagged_values.append(item.current)
            item.problem = reason
            item.trace.append("attempt %d: judge: %s" % (attempt, reason))
            still.append(item)
        current = [i for i in still if not i.unresolved and not i.resolved]
        if not current:
            break
    for item in current:
        item.unresolved = True
        item.trace.append("attempt bound reached")


async def _back_translate(items: List[_Item], language_name: str,
                          language_code: str, lite_ai: Any) -> None:
    if not items:
        return
    payload = {item.item_id: item.current for item in items}
    result = await _call(
        lite_ai.back_translate(payload, language_name, language_code),
        stage="back_translate")
    for item in items:
        item.back_translation = result.get(item.item_id, "")


async def _judge(items: List[_Item], language_name: str, language_code: str,
                 pro_ai: Any, glossary_context: Optional[Dict[str, Any]],
                 chunk_size: int) -> Dict[str, Dict[str, Any]]:
    verdicts: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(items), max(1, chunk_size)):
        chunk = items[start:start + max(1, chunk_size)]
        payload = [{
            "id": item.item_id,
            "en": "%s (%s)" % (item.source, item.kind),
            "translation": item.current,
            "back_translation": item.back_translation,
        } for item in chunk]
        result = await _call(
            pro_ai.judge_translations(
                payload, language_name, language_code,
                glossary_context=glossary_context),
            stage="judge")
        verdicts.update(result)
    return verdicts


async def _call(coro: Any, stage: str) -> Any:
    """Await one adapter leg; a None result or an exception is the
    fail-open signal for the whole verify pass."""
    try:
        result = await coro
    except Exception as exc:  # noqa: BLE001 -- fail-open by design
        raise _VerifyUnavailable(
            "%s:%s" % (stage, type(exc).__name__)) from exc
    if result is None:
        raise _VerifyUnavailable(stage)
    return result


def _plain_reason(trace_entry: str) -> str:
    """Strip the internal stage prefix -- exactly 'lint: ' or 'judge: ',
    the only two prefixes trace[0] can carry (_initial_round is the sole
    writer of the first entry) -- so the remaining reason, which the
    lint/judge legs already write as prose, can be quoted in a
    reviewer-facing message without leaking pipeline jargon. Later trace
    entries ('attempt N: judge: ...') are NOT handled: pass trace[0]
    only."""
    reason = trace_entry
    for prefix in ("lint: ", "judge: "):
        if reason.startswith(prefix):
            reason = reason[len(prefix):]
    return reason


def _finalize(items: List[_Item],
              fresh: Dict[str, Dict[str, str]]) -> VerifyResult:
    final = {kind: dict(values) for kind, values in fresh.items()}
    flags: List[VerifyFlag] = []
    counts = {"checked": len(items), "mechanical": 0, "judge_flagged": 0,
              "rectified": 0, "unresolved": 0}
    for item in items:
        if item.mechanical_origin:
            counts["mechanical"] += 1
        elif item.flagged_values:
            counts["judge_flagged"] += 1
        if item.resolved is not None:
            counts["rectified"] += 1
            final[item.kind][item.source] = item.resolved
            taxonomy = FLAG_MECHANICAL if item.mechanical_origin \
                else FLAG_RECTIFIED
            flags.append(VerifyFlag(
                taxonomy=taxonomy, kind=item.kind, source=item.source,
                message="a problem was found here (%s) and automatically "
                        "corrected: '%s' -> '%s' -- read the new wording "
                        "and confirm it says the right thing"
                        % (_plain_reason(item.trace[0]),
                           item.original, item.resolved),
            ))
        elif item.unresolved or (item.flagged_values
                                 and item.resolved is None):
            counts["unresolved"] += 1
            # KEEP rules (V1-decided): mechanical-origin keeps the latest
            # lint-clean rectify when one exists; judge-origin keeps the
            # ORIGINAL.
            if item.mechanical_origin \
                    and item.latest_lint_clean_rectify:
                final[item.kind][item.source] = \
                    item.latest_lint_clean_rectify
                kept = ("the form currently uses the best automatic "
                        "correction ('%s')"
                        % item.latest_lint_clean_rectify)
            else:
                final[item.kind][item.source] = item.original
                kept = ("the form currently uses the original text ('%s')"
                        % item.original)
            flags.append(VerifyFlag(
                taxonomy=FLAG_UNRESOLVED, kind=item.kind,
                source=item.source,
                message="this translation still looks wrong after "
                        "automatic correction was tried -- review it and "
                        "fix it by hand; %s. First problem found: %s"
                        % (kept, _plain_reason(item.trace[0])),
            ))
    _log.info(
        "translation_verify_complete",
        checked=counts["checked"], mechanical=counts["mechanical"],
        judge_flagged=counts["judge_flagged"],
        rectified=counts["rectified"], unresolved=counts["unresolved"],
    )
    return VerifyResult(available=True, final=final, flags=flags,
                        counts=counts)
