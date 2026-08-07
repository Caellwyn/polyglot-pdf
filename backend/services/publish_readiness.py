"""THE definition of a form kit's publish readiness (sprint-18 C4, bd
polyglot-pdf-g687; plan docs/sprint_18_editor-ux-overhaul_plan.md decisions
2 + 4).

One function answers "how much of this kit has a human actually reviewed, and
may it be published?" -- and every surface that shows or gates on that number
routes through it: the editor's bottom strip (via its pinned client mirror),
the readiness STAMP this module's counts are written into at save time, the
catalogue card that renders the stamp, and (bd polyglot-pdf-apmo / C2) the
/status publish gate. Before this existed the same question had a client-only
answer, which is how a confident "100%" strip could sit beside a 409 refusal.

A field counts REVIEWED exactly when:

  * ``_review.status == "reviewed_correct"`` -- human sign-off, never the
    machine's opinion (bd polyglot-pdf-g63j);
  * no lint ERROR is anchored to it;
  * its guidance ack is CURRENT -- i.e. if a guidance-staleness finding names
    the field, ``_review.guidance_ack_sha1`` must equal the field's identity
    hash computed NATIVELY here (guidance_contract.identity_sha1), never
    parsed out of a finding path;
  * no finding anchored to it is NEWER than the sign-off, where "newer" means
    its fingerprint is absent from ``_review.seen_fingerprints`` (the
    timeliness rule).

The client mirror is schema-editor/src/utils/reviewStatus.ts
(isCountedReviewed); both sides consume the same inputs (_review + the lint
findings + the schema), so both compute the identical number. The mirror
equality is test-pinned -- see backend/tests/unit/test_publish_readiness.py
and the schema-editor's own parity fixture.

IGNORED (quarantined) fields sit outside fields[] by construction, so they are
outside the denominator by construction too -- there is no ignore filter here
to drift.
"""
from __future__ import annotations

import math
import re
# `field` is aliased: this module uses `field` as a local variable name
# throughout (a schema field), and importing dataclasses.field unaliased would
# shadow it confusingly at every use site.
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, Iterable, List, Optional, Sequence

from backend.services.guidance_contract import identity_sha1
from backend.services.schema_lint import LintFinding, SEVERITY_ERROR, field_id_of

# The rule id whose finding means "this field's guidance may no longer match
# its content". Its presence is what arms the ack gate below; the ack itself is
# compared against a NATIVELY computed hash, not the one in the finding path.
GUIDANCE_STALE_RULE = "guidance-identity-stale"

# --------------------------------------------------------------------------- #
# Finding fingerprints -- byte-identical to the client's findingFingerprint
# (schema-editor/src/utils/lintFindings.ts). The sign-off stamps these strings
# into _review.seen_fingerprints, and this module compares against them, so any
# divergence here silently breaks the timeliness rule in the demote-everything
# direction. Keep the two implementations in lockstep; the parity is pinned by
# test_publish_readiness.py's fingerprint cases, which mirror the TS unit tests.
# --------------------------------------------------------------------------- #

_IDENTITY_TOKEN_RE = re.compile(r"\[identity:[0-9a-f]+\]")
_CONTAINER_INDEX_RE = re.compile(r"\b(fields|sections|parts)\[\d+\]")

# Rules whose PATH does not localize the defect (the offending value lives only
# in the message), so their fingerprint folds in a bounded content hash. Must
# match MESSAGE_LOCALIZED_RULES on the client exactly.
_MESSAGE_LOCALIZED_RULES = frozenset({"option-value-duplicate"})


def strip_identity_suffix(path: str) -> str:
    return _IDENTITY_TOKEN_RE.sub("", path or "")


def strip_container_indices(path: str) -> str:
    p = path or ""
    # A `widget '<name>'` path carries a raw AcroForm NAME, not path structure,
    # and PDF widget names legitimately contain `fields[0]`-shaped segments.
    # Rewriting those would collapse two distinct widgets into one fingerprint.
    if p.startswith("widget "):
        return p
    return _CONTAINER_INDEX_RE.sub(r"\1[]", p)


def _content_discriminator(message: str) -> str:
    """djb2-xor over UTF-16 code units, base36 -- the client's exact algorithm.

    Mirrors contentDiscriminator in lintFindings.ts, including its 32-bit
    signed wraparound (JS `| 0`) and unsigned render (`>>> 0`). Python ints are
    unbounded, so the masking is explicit; JS strings are UTF-16, so the code
    units come from surrogate-pair-aware iteration rather than code points --
    an astral character in a lint message would otherwise fingerprint
    differently on the two sides.
    """
    h = 5381
    for unit in _utf16_code_units(message or ""):
        h = (((h << 5) + h + unit) & 0xFFFFFFFF)
        # Re-interpret as a signed 32-bit int, exactly as JS `| 0` does, so the
        # next shift sees the same value the client's would.
        if h >= 0x80000000:
            h -= 0x100000000
    return _base36(h & 0xFFFFFFFF)


def _utf16_code_units(text: str) -> Iterable[int]:
    for ch in text:
        cp = ord(ch)
        if cp > 0xFFFF:
            cp -= 0x10000
            yield 0xD800 + (cp >> 10)
            yield 0xDC00 + (cp & 0x3FF)
        else:
            yield cp


def _base36(value: int) -> str:
    if value == 0:
        return "0"
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out: List[str] = []
    while value:
        value, rem = divmod(value, 36)
        out.append(digits[rem])
    return "".join(reversed(out))


def finding_fingerprint(finding: LintFinding) -> str:
    """rule + field anchor + path-sans-identity-suffix, message EXCLUDED.

    Excluding the message is load-bearing: messages are prose a copy pass
    rewrites, and a message-keyed fingerprint would demote every reviewed field
    on every kit the moment the wording changed.
    """
    path = strip_container_indices(strip_identity_suffix(finding.path))
    fid = field_id_of(finding.path) or ""
    extra = ""
    if finding.rule in _MESSAGE_LOCALIZED_RULES:
        extra = f"|{_content_discriminator(finding.message)}"
    return f"{finding.rule}|{fid}|{path}{extra}"


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #


def _review_of(field: Dict[str, Any]) -> Dict[str, Any]:
    """A field's _review record, defaulted to the neutral state.

    Mirrors the client's getReview: an absent, non-dict, or unrecognized-status
    record collapses to 'unreviewed' rather than throwing, because this runs
    over hand-edited and legacy kits.
    """
    raw = field.get("_review")
    if not isinstance(raw, dict):
        return {"status": "unreviewed"}
    status = raw.get("status")
    if status not in ("reviewed_correct", "needs_followup"):
        return {"status": "unreviewed", **{k: v for k, v in raw.items() if k != "status"}}
    return raw


def _seen_fingerprints(review: Dict[str, Any]) -> Optional[frozenset]:
    """The sign-off's stamped fingerprints, or None when the slot is absent.

    None is the GRANDFATHER case: a sign-off written before the slot existed
    recorded nothing, so treating "absent" as "the empty set" would make every
    pre-existing finding look new and mass-demote every reviewed field on every
    shipped kit -- the exact re-review wave this epic exists to end. Absent
    means "no timeliness claim", so the rule simply does not fire.
    """
    raw = review.get("seen_fingerprints")
    if not isinstance(raw, list):
        return None
    return frozenset(x for x in raw if isinstance(x, str))


_CHOICE_TYPES = frozenset({"select", "radio", "checkbox_group"})


def has_uncovered_structural_error(field: Dict[str, Any]) -> bool:
    """The checkFieldComplete ERROR classes NO backend lint rule covers yet.

    The exact mirror of reviewStatus.ts hasUncoveredStructuralError, whose own
    docstring states the server computes the identical clause -- and it must,
    or a field in one of these shapes counts reviewed in the STAMP while the
    open editor renders it red (fresh-eyes gap 3; the two-surfaces-disagree bug
    this bead exists to end).

      - a CHOICE field (select/radio/checkbox_group) with options where neither
        the field nor every option names a PDF widget. The field-backing rule
        exempts choice types (identity legitimately lives per option) and the
        widget-claim rules need a non-empty claim to fire, so this genuinely
        unfillable shape earns a red row with no count-excluding lint ERROR;
      - a field with no id or no type at all (hand-edited/drifted kits).

    Derived from the SCHEMA alone, exactly like the client's. Retire the
    choice-mapping half once the backend rule ships (bd polyglot-pdf-xuub) --
    in BOTH implementations, together.
    """
    if not field.get("id") or not field.get("type"):
        return True
    options = field.get("options")
    options = options if isinstance(options, list) else []
    if (field.get("type") not in _CHOICE_TYPES or not options
            or field.get("pdf_field_name")):
        return False
    return any(
        not (o.get("pdf_field_name") if isinstance(o, dict) else None)
        for o in options
    )


def is_counted_reviewed(
    field: Dict[str, Any],
    findings: Sequence[LintFinding] = (),
) -> bool:
    """Whether ONE field counts as reviewed. `findings` are THIS field's."""
    review = _review_of(field)
    if review.get("status") != "reviewed_correct":
        return False

    if has_uncovered_structural_error(field):
        return False

    for f in findings:
        if f.severity == SEVERITY_ERROR:
            return False

    # The ack gate: a staleness finding on this field demands an ack matching
    # the field's CURRENT identity. Computed natively -- the same function that
    # emits the hash -- so there is no cross-language copy and no path parsing.
    if any(f.rule == GUIDANCE_STALE_RULE for f in findings):
        ack = review.get("guidance_ack_sha1")
        if not isinstance(ack, str) or ack != identity_sha1(field):
            return False

    # The timeliness rule: any finding whose fingerprint the sign-off did not
    # stamp is NEWER than the sign-off, so the sign-off no longer covers the
    # field. Absent slot -> grandfathered (see _seen_fingerprints).
    seen = _seen_fingerprints(review)
    if seen is not None:
        for f in findings:
            # The guidance-staleness rule is EXCLUDED here, exactly as the
            # client excludes it (reviewStatus.ts newFindingsSinceReview): the
            # ack gate above is that rule's SOLE owner. Counting it here too
            # makes sign-off -> drift -> ack a DEAD END -- the ack writer
            # deliberately preserves seen_fingerprints, so the one control that
            # can clear the drift never touches this slot, leaving the field
            # permanently un-reviewed with no exit. Measured: without this
            # clause Python said False where the client said True for the
            # ordinary ack flow (Opus fresh-eyes round 2).
            if f.rule == GUIDANCE_STALE_RULE:
                continue
            if finding_fingerprint(f) not in seen:
                return False

    return True


@dataclass(frozen=True)
class ReadinessCounts:
    """The kit-wide tally. `errors` counts fields carrying a lint ERROR --
    a diagnostic bucket, NOT a third partition: an ERROR field is also a
    to-review field, so the invariant is reviewed + to_review == total, with
    errors <= to_review. (The plan's "errors bucket" landed here rather than on
    the deleted getCompletionStats -- bd polyglot-pdf-q3rm removed that
    function; see this bead's scope note.)
    """

    reviewed: int
    to_review: int
    total: int
    errors: int

    @property
    def percentage(self) -> int:
        if self.total <= 0:
            return 0
        # math.floor(x + 0.5), NOT round(): Python's round() is BANKER'S
        # rounding (ties to even) while the client's Math.round (reviewStatus.ts
        # reviewCounts) rounds ties UP, so any exact .5 ratio stamped one number
        # and displayed another -- 1 of 8 fields stamped 12% while the open
        # editor's strip said 13% (fresh-eyes gap 2, measured). The two surfaces
        # disagreeing about one saved kit is the precise bug this bead exists to
        # end, so the mirror has to match JS semantics, not Python's default.
        return math.floor(self.reviewed / self.total * 100 + 0.5)

    def as_dict(self) -> Dict[str, int]:
        return {
            "reviewed": self.reviewed,
            "toReview": self.to_review,
            "total": self.total,
            "errors": self.errors,
            "percent": self.percentage,
        }


@dataclass(frozen=True)
class ReadinessVerdict:
    """Readiness for publication, plus the counts the stamp records.

    `ready` is the publish verdict C2's /status gate refuses on; `blocking_ids`
    names the fields to show the human (the gate refuses BY NAME, never with a
    bare count).

    `ready` is NOT merely `to_review == 0`: a kit can have every field signed
    off and still be unpublishable because of a SCHEMA-LEVEL lint ERROR -- one
    that no field row can carry, so no field's review can ever clear it. The
    two reachable classes are the holding-section leftover-ids ERROR
    (`to-review-pending` at `sections[i] (id=sec_to_review_x)`, whose id token
    matches no field) and the widget-claim ERROR (`dump-widget-multiclaim` at
    `widget '<name>'`, with no id token at all). The /status gate refuses on ANY
    lint ERROR regardless of anchoring, so a verdict that ignored these would
    stamp ready=True for a kit the gate then 409s -- the confident-then-refused
    shape sprint-18 exists to end, relocated into the stamp (bd
    polyglot-pdf-dm3c8).

    They get their OWN field rather than being folded into the counts: those
    count FIELDS, and `reviewed + to_review == total` is a test-pinned
    invariant. A finding belonging to no field cannot inflate a field tally
    without breaking it.
    """

    ready: bool
    counts: ReadinessCounts
    blocking_ids: List[str]
    # Schema-level lint ERRORs, as human-readable `<rule> at <path>` strings.
    # Non-empty forces ready=False. Kept as strings (not LintFinding) so the
    # verdict stays a plain data shape a stamp can serialize.
    blocking_schema_errors: List[str] = dataclass_field(default_factory=list)


def _positional_name(index: int) -> str:
    """A stand-in name for a blocking field that has no usable id.

    Deliberately NOT id-shaped: a caller rendering these (C2's gate names the
    fields it refuses on) must not present it as something the human can search
    for. It says WHERE the problem is, which is the most the schema affords.
    """
    return f"fields[{index}] (no id)"


def _bucket_by_field(
    findings: Optional[Iterable[LintFinding]],
    field_ids: Optional[set] = None,
) -> Dict[str, List[LintFinding]]:
    """Group findings by the field they anchor to; field-less ones are skipped
    (no field's review can cover a schema-level finding).

    `field_ids` is the set of ids that actually EXIST in fields[]. When given, a
    finding whose parsed id matches no real field is treated as schema-level
    rather than silently dropped -- the `to-review-pending` ERROR carries
    `sections[i] (id=sec_to_review_x)`, which parses to an id token that is a
    SECTION, not a field. The client makes the same distinction for the same
    reason (lintFindings.formLevelFindings keys on "resolves to no field in
    fields[]", not on "has no id token").
    """
    out: Dict[str, List[LintFinding]] = {}
    for f in findings or ():
        fid = field_id_of(f.path)
        if not fid:
            continue
        if field_ids is not None and fid not in field_ids:
            continue
        out.setdefault(fid, []).append(f)
    return out


def _schema_level_errors(
    findings: Optional[Iterable[LintFinding]],
    field_ids: set,
) -> List[str]:
    """The ERROR findings no field row can carry, as `<rule> at <path>`.

    These are what the /status gate refuses on but no field's sign-off can
    clear: it refuses on ANY lint ERROR, while the review counts only ever see
    field-anchored ones. Ignoring them let a fully-reviewed kit stamp
    ready=True and then 409 at publish (bd polyglot-pdf-dm3c8).

    "No field row can carry it" means either no id token at all (`widget
    '<name>'`) or an id token naming something that is not a field (a section).
    """
    out: List[str] = []
    for f in findings or ():
        if f.severity != SEVERITY_ERROR:
            continue
        fid = field_id_of(f.path)
        if fid and fid in field_ids:
            continue  # a real field owns it; the review counts already saw it
        out.append(f"{f.rule} at {f.path}")
    return out


def publish_readiness(
    schema: Dict[str, Any],
    lint_findings: Optional[Iterable[LintFinding]] = None,
) -> ReadinessVerdict:
    """THE readiness verdict + counts for a schema (see the module docstring).

    `lint_findings` is the kit's CURRENT lint report. Passing None means "no
    report in hand" and is honestly gate-blind on the lint-driven clauses --
    the caller that stamps must then mark the stamp unverified, never present
    the number as a checked result (the "not fully checked" state, decision 4).
    """
    fields = schema.get("fields")
    if not isinstance(fields, list):
        # A schema whose fields are not a list is unmeasurable, not "0% ready":
        # callers distinguish this via total == 0 plus ready == False.
        return ReadinessVerdict(
            ready=False, counts=ReadinessCounts(0, 0, 0, 0), blocking_ids=[],
        )

    # Materialize the findings once: they are consumed twice below (bucketed
    # per field, and scanned for schema-level ERRORs), and the parameter is
    # typed as an Iterable a generator could satisfy -- which the second pass
    # would find already exhausted.
    findings = list(lint_findings) if lint_findings is not None else []
    real_field_ids = {
        f.get("id") for f in fields
        if isinstance(f, dict) and isinstance(f.get("id"), str)
    }
    by_field = _bucket_by_field(findings, real_field_ids)
    schema_errors = _schema_level_errors(findings, real_field_ids)
    reviewed = 0
    errors = 0
    blocking: List[str] = []
    total = 0
    for index, field in enumerate(fields):
        if not isinstance(field, dict):
            # A malformed entry cannot be reviewed. It still occupies the
            # denominator (so the percentage never overstates) AND it is named
            # positionally, because a verdict that refuses without naming
            # anything is unactionable -- see the placeholder note below.
            total += 1
            blocking.append(_positional_name(index))
            continue
        total += 1
        fid = field.get("id")
        own = by_field.get(fid, ()) if isinstance(fid, str) else ()
        if any(f.severity == SEVERITY_ERROR for f in own):
            errors += 1
        if is_counted_reviewed(field, own):
            reviewed += 1
        elif isinstance(fid, str) and fid:
            blocking.append(fid)
        else:
            # An id-less (or non-string-id) field blocks too. Silently dropping
            # it let `ready=False` ship with an EMPTY blocking_ids -- a refusal
            # naming nobody, which ReadinessVerdict's own docstring forbids
            # ("the gate refuses BY NAME, never with a bare count") and which
            # C2's gate would surface to a human as an unactionable 409
            # (confirming Opus outer review). A positional placeholder is not a
            # field id, so it is deliberately unmistakable as one.
            blocking.append(_positional_name(index))

    to_review = total - reviewed
    return ReadinessVerdict(
        # A schema-level ERROR blocks publication no matter how complete the
        # review is: the /status gate refuses on it, and no field's sign-off
        # can clear it. Deliberately NOT folded into to_review -- that counts
        # FIELDS, and reviewed + to_review == total is a pinned invariant.
        ready=total > 0 and to_review == 0 and not schema_errors,
        counts=ReadinessCounts(
            reviewed=reviewed, to_review=to_review, total=total, errors=errors,
        ),
        blocking_ids=blocking,
        blocking_schema_errors=schema_errors,
    )
