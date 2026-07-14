"""Cross-field contradiction validator service -- Pillar B of the SI-reduction
epic (bd polyglot-pdf-jnjj.15, "B3").

The LIVE voice model fills the form field-by-field; field-level validation
(backend/utils/field_validator.py) checks one value against its own schema
constraints but CANNOT see cross-field contradictions (a ZIP that does not match
the stated state, a US state filled alongside a foreign country, a future-dated
birthday). This service runs a SECOND-PASS net at section / form boundaries: it
renders the client's current form state into a minimal payload, asks the cheap
flash-lite TEXT model (via the ITextAI port) to flag the named contradiction
classes, and returns the contract-1 verdict.

Defense-in-depth, NOT a replacement: post-RESCOPE (2026-06-17), the in-SI
ADDRESS CONSISTENCY prose STAYS as the primary check; this validator is an
additive net (flash-lite: recall 0.853, precision 1.000 on the G1 corpus -- it
adds zero false positives, so it is safe to run as an extra pass).

Contracts (docs/standards/validation-delegation.md):
  - Input:  contract 2 -- the minimal client-state payload, a list of
            {field_id, name, value, steered} dicts (only non-empty values).
  - Output: contract 1 -- {"conflicts": [{"field_ids": [...], "reason": "..."}]},
            an EMPTY list when all clear.
  - Failure: contract 6 -- FAIL-OPEN. On flash-lite timeout / error /
            unparseable output the caller advances UNCHECKED (a voice UX must
            never block on an auxiliary text-model outage). A missed
            contradiction is a soft degradation; a blocked advance is a hard UX
            failure. Logged as a degraded check. Bead-recorded consequence:
            post-B1 there is no inline fallback, so a sustained flash-lite outage
            silently disables detection -- accepted and recorded.

The contradiction prompt here reproduces the candidate B3 pinned and scored GO by
the G1 keystone probe (backend/scripts/probe_g1_contradiction_recall.py
FLASH_LITE_PROMPT) so the deployed validator matches what the gate measured.

PII (contract 6): this service handles full form PII/PHI (names, addresses, DOBs)
but logs ONLY counts (field_count / conflict_count / dropped_malformed) and
exception types -- NEVER the payload, the field values, the field ids, or the
verdict reason text. The verdict `reason` may quote values; it rides the in-band
steering message to the Live model (bead B5), which is NOT a log sink. The wider
"ids / counts / lengths" allowance is the callback_handler discipline this mirrors
(contract 6); this service simply emits a strict subset of it.

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import datetime
import json

import structlog

from backend.ports.text_ai_port import ITextAI

# The contradiction-checker system instruction. VERBATIM-faithful to the
# FLASH_LITE_PROMPT the G1 keystone probe pinned and scored GO, MINUS the trailing
# "FIELDS:\n{state}" -- the form state rides the fresh_tail (see
# render_validator_payload), not the prompt template, so the cacheable prefix
# stays value-free and byte-stable within a session. "{today}" is the only
# substitution; it is constant within a session, so the prefix is still stable.
CONTRADICTION_SI = (
    "You are a contradiction checker for a USCIS I-90 immigration form. You are "
    "given the form's currently-filled fields as JSON. Find cross-field "
    "contradictions a human reviewer would flag, using world knowledge:\n"
    "- a US ZIP code that does not belong to the stated US state\n"
    "- a US state filled together with a foreign country\n"
    "- a foreign province filled together with a US state\n"
    "- a US city that is not located in the stated US state\n"
    "- a date of birth in the future (today is {today})\n"
    "- a date of admission that precedes the date of birth\n\n"
    "Do NOT flag coherent addresses, foreign addresses (province + postal code + "
    "foreign country, no US state), US territories (Puerto Rico, Guam, Virgin "
    "Islands and their ZIPs are valid), two different but internally-coherent "
    "addresses (a mailing address and a separate physical address), or sparse "
    "state with too little to compare.\n\n"
    "Return JSON ONLY:\n"
    '{{"conflicts": [{{"field_ids": ["<field_id>", ...], "reason": "<short>"}}]}}\n'
    "Use the exact field_id values from the input. Empty list if no contradiction."
)


# W6 (bd polyglot-pdf-gbus): the WHOLE-FORM gemini-2.5-pro system instruction for
# the end-of-form pro pass. Distinct from CONTRADICTION_SI (the flash-lite window
# prompt, kept byte-stable for its implicit-cache prefix). This prompt:
#   - keeps the base contradiction classes,
#   - ADDS the FAR-PAIR rule ("the same fact stated two different ways in different
#     places") -- the cross-page class the ~20-field lite windows cannot see and the
#     reason the whole-form pro pass exists (W5 measured recall 1.000 with it),
#   - carries the g1c ANTI-HEDGING + numbered "NOT contradictions" precision block
#     (the pattern that lifted flash-lite precision 0.77->0.96, bd g1c/08zv), and
#   - ADDS the W6 anti-over-flag items for the two buckets W5 measured pro
#     over-flagging at whole-form scale (precision 0.750): the Part 5/6
#     preparer-and-interpreter CERTIFICATION block, and BRACKETED-REPEAT /
#     continuation fields. Precision is the W6 work; recall is already solved.
# The trailing "already-adjudicated fields" line is filled per-call from the
# steered markers (see render_validator_payload) so the pro pass does NOT re-report
# a contradiction the user already saw and resolved mid-form.
WHOLE_FORM_PRO_SI = (
    "You are a contradiction checker for a USCIS I-90 immigration form. You are "
    "given the form's ENTIRE set of currently-filled fields as JSON. Find "
    "cross-field contradictions a human reviewer would flag, using world "
    "knowledge:\n"
    "- a US ZIP code that does not belong to the stated US state\n"
    "- a US state filled together with a foreign country\n"
    "- a foreign province filled together with a US state\n"
    "- a US city that is not located in the stated US state\n"
    "- a date of birth in the future (today is {today})\n"
    "- a date of admission that precedes or contradicts the date of birth\n"
    "- THE SAME FACT stated two different ways in different places (e.g. a date of "
    "birth given in one field and restated with a different year in a free-text "
    "field far away; a length-of-residence statement that contradicts the date of "
    "admission). These cross-page repeats are the reason you see the WHOLE form.\n\n"
    "ANTI-HEDGING RULE -- this is the most common mistake, do not make it: only "
    "flag a field pair when one value makes the other GENUINELY IMPOSSIBLE. If a "
    "set of fields is internally consistent, DO NOT flag it, even if it looks "
    "unusual. When uncertain whether something is a real contradiction, DO NOT "
    "flag it.\n\n"
    "These are NOT contradictions (never flag them):\n"
    "1. A FOREIGN address: a city + a foreign province/region + a postal code + a "
    "foreign country, with NO US state (e.g. 'Toronto, Ontario, M5H 2N2, Canada'). "
    "A foreign province is only a problem if a US STATE is ALSO filled.\n"
    "2. A US TERRITORY: Puerto Rico (ZIPs 006xx-009xx), Guam (969xx), and the US "
    "Virgin Islands (008xx) are US locations -- their city + territory + ZIP + "
    "'United States' is coherent, even though the territory is not one of the 50 "
    "states.\n"
    "3. TWO DIFFERENT addresses: a mailing address and a SEPARATE physical address "
    "may be in different cities/states and both be valid. Only flag a SINGLE "
    "address that is internally impossible.\n"
    "4. BIRTH abroad: it is NORMAL for the applicant's COUNTRY OF BIRTH or "
    "CITY/TOWN OF BIRTH to differ from their US mailing address -- an immigrant "
    "born abroad living in the US is expected. Never flag it.\n"
    "5. The PREPARER-AND-INTERPRETER CERTIFICATION block (Part 5 / Part 6): a "
    "statement that an interpreter or a preparer HELPED the applicant, that they "
    "read/translated the form in some language, or their name/contact/signature, "
    "is a CERTIFICATION about who assisted -- it is NOT a contradiction with the "
    "applicant's own answers. A preparer's or interpreter's details differing from "
    "the applicant's is EXPECTED (they are different people). Never flag the "
    "certification block against the applicant's fields.\n"
    "6. BRACKETED-REPEAT / CONTINUATION fields: fields whose ids differ only by a "
    "bracket index or an [] suffix (e.g. 'p1_line3a_familyname' vs "
    "'p1_line3a_familyname[1]', or 'x' vs 'x[]') are the SAME logical field's "
    "continuation entries -- they hold parts of one answer, never a contradiction "
    "with each other.\n\n"
    "{adjudicated}"
    "Return JSON ONLY:\n"
    '{{"conflicts": [{{"field_ids": ["<field_id>", ...], "reason": "<short>"}}]}}\n'
    "Use the exact field_id values from the input. Empty list if no contradiction."
)


def _today_str(today: datetime.date | str | None) -> str:
    """Resolve the 'today' the date-sanity checks anchor on. A caller may pin a
    fixed date (tests / reproducibility); otherwise use the real UTC date.
    Module-level code never calls datetime.now() (it would not be deterministic
    and would defeat the byte-stable prefix across a session)."""
    if today is None:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    if isinstance(today, str):
        return today
    return today.strftime("%Y-%m-%d")


def render_validator_payload(
    fields: list,
    today: datetime.date | str | None = None,
    si: str | None = None,
    steered_field_ids: list | None = None,
) -> dict:
    """Render the contract-2 client-state payload into the {stable_prefix,
    fresh_tail, field_count} dict TextAIGemini.validate() consumes.

    stable_prefix: [the SI with today substituted] -- value-free and
                   session-stable (today is constant within a session), the
                   implicit-cache target. Defaults to CONTRADICTION_SI (the
                   flash-lite window prompt); W6 (bd polyglot-pdf-gbus) passes
                   WHOLE_FORM_PRO_SI for the end-of-form pro pass.
    fresh_tail:    [the form-state JSON] -- the small, fresh, per-boundary part.
    field_count:   telemetry only (PII-safe; never the values).

    W6: `steered_field_ids` are the fields already flagged + adjudicated mid-form.
    When the SI carries an `{adjudicated}` slot (WHOLE_FORM_PRO_SI does), it is
    filled with a "do NOT re-report contradictions involving these fields"
    instruction -- the prompt-layer half of the not-re-flag guarantee (the
    authoritative half is the _suppress_already_steered dedupe backend-side). The
    default CONTRADICTION_SI has no such slot, so the arg is ignored for the lite
    path. The steered IDs are field IDS only (not values), so this is PII-safe to
    place in the prompt.

    `fields` is the contract-2 list; non-list / malformed input renders an empty
    state (the validate() path then fail-opens on it). Field values are NOT logged
    here -- this only builds the request body sent to the same Gemini trust
    boundary the Live model already uses (contract 6 sign-off).
    """
    safe_fields = fields if isinstance(fields, list) else []
    state_json = json.dumps({"fields": safe_fields}, indent=2)
    template = si if si is not None else CONTRADICTION_SI
    fmt: dict = {"today": _today_str(today)}
    # Only the pro SI has an {adjudicated} slot; fill it (or blank it) when present.
    if "{adjudicated}" in template:
        ids = [str(i) for i in (steered_field_ids or []) if i]
        fmt["adjudicated"] = (
            (
                "ALREADY ADJUDICATED (do NOT re-report any contradiction that "
                "involves these fields -- the user was already asked about them and "
                "resolved or intentionally kept them): "
                + ", ".join(ids)
                + ".\n\n"
            )
            if ids
            else ""
        )
    return {
        "stable_prefix": [template.format(**fmt)],
        "fresh_tail": ["FIELDS:\n" + state_json],
        "field_count": len(safe_fields),
    }


def _sanitize_conflicts(conflicts: list) -> list:
    """Coerce the raw verdict's conflicts to the contract-1 shape, dropping any
    item that cannot be made well-formed. Each kept conflict has a non-empty
    `field_ids` list of strings (1+ ids -- a single-field semantic error like a
    future DOB is valid) and a string `reason`. A malformed item is dropped
    rather than raised, so one bad conflict never fails the whole verdict."""
    out = []
    for c in conflicts:
        if not isinstance(c, dict):
            continue
        ids = c.get("field_ids", [])
        if not isinstance(ids, list):
            continue
        clean_ids = [str(i) for i in ids if isinstance(i, (str, int)) and str(i)]
        if not clean_ids:
            continue
        reason = c.get("reason", "")
        out.append({"field_ids": clean_ids, "reason": str(reason)})
    return out


class ValidatorService:
    """Runs the cross-field contradiction check over the client-state payload.

    Stateless: holds only the ITextAI port. A fresh instance per call is fine
    (consistent with the get_text_ai shape), but the service keeps no per-session
    state -- the backend is stateless by design, and the payload rides the
    boundary event (contract 4).
    """

    def __init__(self, text_ai: ITextAI):
        self._text_ai = text_ai
        self._log = structlog.get_logger().bind(service="ValidatorService")

    async def validate(
        self,
        fields: list,
        today: datetime.date | str | None = None,
        si: str | None = None,
        steered_field_ids: list | None = None,
    ) -> dict:
        """Run the contradiction check over the contract-2 `fields` payload and
        return the contract-1 verdict {"conflicts": [...]}.

        `si` overrides the default CONTRADICTION_SI prompt (W6 passes
        WHOLE_FORM_PRO_SI for the pro pass); `steered_field_ids` fills the pro SI's
        already-adjudicated slot so it does not re-report resolved fields. Both are
        ignored by the default lite SI (no {adjudicated} slot).

        FAIL-OPEN (contract 6): on ANY non-verdict outcome -- the adapter's own
        fail-open, a bad shape, or an unexpected error here -- return the
        all-clear {"conflicts": []} and log a degraded check. The voice UX never
        blocks on a validator outage.

        PII: logs field_count / conflict_count only -- never values or reasons.
        """
        try:
            payload = render_validator_payload(
                fields, today=today, si=si, steered_field_ids=steered_field_ids
            )
        except Exception as exc:  # noqa: BLE001 -- render must never block advance
            self._log.warning(
                "validator_render_error_fail_open",
                exc_type=type(exc).__name__,
            )
            return {"conflicts": []}

        field_count = payload.get("field_count", 0)
        try:
            verdict = await self._text_ai.validate(payload)
        except Exception as exc:  # noqa: BLE001 -- adapter should fail-open, but
            # belt-and-suspenders: a raising adapter must still not block advance.
            self._log.warning(
                "validator_textai_error_fail_open",
                exc_type=type(exc).__name__,
                field_count=field_count,
            )
            return {"conflicts": []}

        if not isinstance(verdict, dict):
            self._log.warning(
                "validator_bad_verdict_fail_open",
                verdict_type=type(verdict).__name__,
                field_count=field_count,
            )
            return {"conflicts": []}

        raw_conflicts = verdict.get("conflicts", [])
        if not isinstance(raw_conflicts, list):
            self._log.warning(
                "validator_bad_conflicts_type_fail_open",
                conflicts_type=type(raw_conflicts).__name__,
                field_count=field_count,
            )
            return {"conflicts": []}

        conflicts = _sanitize_conflicts(raw_conflicts)
        dropped = len(raw_conflicts) - len(conflicts)
        self._log.info(
            "validator_complete",
            field_count=field_count,
            conflict_count=len(conflicts),
            dropped_malformed=dropped,
        )
        return {"conflicts": conflicts}
