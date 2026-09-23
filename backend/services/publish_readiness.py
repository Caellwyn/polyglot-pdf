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
#
# ACCEPTED LOOSENING during a mass-drift wave (bd polyglot-pdf-cf6v, a
# deliberate design decision, not an oversight): when EVERY compared field's
# identity mismatches at once, the linter suppresses the per-field
# guidance-identity-stale findings in favor of ONE kit-level
# guidance-identity-mass-drift WARNING (see _check_guidance_identity_drift's
# MASS-DRIFT COLLAPSE note). With no per-field finding, this ack gate never
# arms, so a field reviewed before the wave counts reviewed again even though
# its stored guidance_ack_sha1 is stale. That is intended: the measured wave
# (the W-7 case) was a hash-formula change with ZERO author edits -- pure
# false staleness -- and demanding 51 identical re-acks trains editors to
# click through the gate. The kit-level finding carries the honest remedy
# (re-bake / re-verify), and a re-bake re-stamps and restores per-field
# tracking. The interaction is pinned by
# test_mass_drift_wave_disarms_the_ack_gate_by_design in
# backend/tests/unit/test_publish_readiness.py; the client mirror
# (reviewStatus.ts) inherits the same behavior because it keys on the same
# per-field finding.
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
      - a field with no id or no type at all (hand-edited/drifted kits);
      - a checkbox_group carrying a FIELD-LEVEL pdf_field_name, which v2
        forbids outright. That rule is Pydantic _collect_v2_problems, not a
        LintFinding, so no lint ERROR excludes it (bd polyglot-pdf-ufj7);
      - two or more OPTIONS claiming the same widget. The backend's own
        dump-widget-multiclaim covers it but is DUMP-GATED, so it cannot fire
        in this schema-only clause (bd polyglot-pdf-fyc7).

    Derived from the SCHEMA alone, exactly like the client's. Retire the
    choice-mapping half once the backend rule ships (bd polyglot-pdf-xuub) --
    in BOTH implementations, together.

    NOTE THE ORDERING, and keep it identical to the client's. A field-level
    pdf_field_name on select/radio suppresses ONLY the unmapped-option scan
    (that is the legitimate shared-name shape, where options need no own
    name). It must NOT suppress the collision scan. Getting that wrong is how
    the client drifted -- a radio with a field-level name AND two options
    claiming one widget counted reviewed while the row painted red
    (bd polyglot-pdf-pq32y).
    """
    if not field.get("id") or not field.get("type"):
        return True
    options = field.get("options")
    options = options if isinstance(options, list) else []
    field_type = field.get("type")
    if field_type not in _CHOICE_TYPES or not options:
        return False

    is_checkbox_group = field_type == "checkbox_group"
    if is_checkbox_group and field.get("pdf_field_name"):
        return True
    suppress_unmapped_scan = (
        not is_checkbox_group and bool(field.get("pdf_field_name"))
    )

    # Normalize once, then read only the normalized list -- a null/non-dict
    # entry degrades this field's count instead of raising out through the
    # readiness stamp (the Python half of bd polyglot-pdf-93p8).
    names = [
        (o.get("pdf_field_name") if isinstance(o, dict) else None)
        for o in options
    ]

    seen: set = set()
    for name in names:
        if not isinstance(name, str) or name == "":
            continue
        if name in seen:
            return True
        seen.add(name)

    if suppress_unmapped_scan:
        return False
    return any(not name for name in names)


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

    `ready` is the publish verdict C2's /status gate refuses on. The gate
    refuses BY NAME, never with a bare count -- but it must read BOTH name
    lists: `blocking_ids` names the fields, and `blocking_schema_errors` names
    the blockers no field can carry. A fully-reviewed kit held back only by a
    schema-level ERROR has an EMPTY `blocking_ids`, so a caller rendering that
    list alone would produce exactly the unactionable refusal this verdict
    exists to prevent (Opus fresh-eyes).

    `ready` is NOT merely `to_review == 0`: a kit can have every field signed
    off and still be unpublishable because of a SCHEMA-LEVEL lint ERROR -- one
    that no field row can carry, so no field's review can ever clear it. The
    two classes this bead was filed for are the holding-section leftover-ids
    ERROR (`to-review-pending` at `sections[i] (id=sec_to_review_x)`, whose id
    token matches no field) and the widget-claim ERROR
    (`dump-widget-multiclaim` at `widget '<name>'`, with no id token at all);
    see _schema_level_errors for the full set of shapes that qualify. The
    /status gate refuses on ANY
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


_FIELD_INDEX_RE = re.compile(r"^fields\[(\d+)\]")
_FIELD_ID_ANCHOR_RE = re.compile(r"^fields(?:\[\d+\])? \(id=(.*?)\)")


def _field_index_of(path: str, id_to_index: Dict[str, int]) -> Optional[int]:
    """The POSITIONAL field index a finding path anchors to, or None.

    Most field-anchored findings are emitted as `fields[{i}] (id=...)`
    (schema_lint.py) -- the index `i` is always present and unambiguous,
    unlike the id: it survives a MISSING id (`(id=None)`), a NON-STRING id
    (the path still renders `(id=123)`, a valid index either way), and a
    DUPLICATE id shared by two fields (bd polyglot-pdf-ele9z: two fields can
    legally -- if a kit is hand-edited or drift-corrupted -- share one id
    string, and nothing in schema_lint enforces uniqueness; bucketing by
    string id alone would cross-contaminate both fields' findings).

    THREE emitters anchor WITHOUT a bracketed index, all `fields (id=X)...`
    shaped: guidance-identity-stale (schema_lint.py, deliberately -- its own
    comment: "field_id_of() ignores the trailing segment, so the editor's
    click-to-focus still resolves this path"), show-if-cycle (schema_lint.py,
    same shape), and enrich_instructions.py's instructions-rectified /
    instructions-ungrounded-dropped guidance flags (re-emitted into findings
    by _emit_guidance_flags). All three are WARNING severity today, never
    ERROR -- for that shape, fall back to resolving the id through
    `id_to_index` (built from the schema's OWN string ids, each field's own
    id -> its own index) -- this keeps their existing behavior for the
    ordinary (unique-id) case; a duplicate id under this specific unindexed
    shape still resolves to whichever field the dict last saw, a narrower
    and pre-existing ambiguity this fix does not newly introduce (unlike the
    indexed shapes, which never had this problem). If a FUTURE rule ever
    emits an ERROR on this unindexed shape, a duplicate id could make that
    ERROR resolve to the wrong field's index and silently vanish from BOTH
    blocking_ids and blocking_schema_errors (verified unreachable today by
    the current severity set; re-check this if that set ever changes).
    """
    m = _FIELD_INDEX_RE.match(path or "")
    if m:
        return int(m.group(1))
    m = _FIELD_ID_ANCHOR_RE.match(path or "")
    if m:
        fid = m.group(1)
        if fid and fid != "None":
            return id_to_index.get(fid)
    return None


def _bucket_by_field_index(
    findings: Optional[Iterable[LintFinding]],
    id_to_index: Dict[str, int],
) -> Dict[int, List[LintFinding]]:
    """Group findings by the POSITIONAL field index they anchor to (bd
    polyglot-pdf-36kqn / ukch0 / ele9z); index-less (schema/section-anchored)
    findings are skipped -- no field's review can cover those.

    Bucketing by index rather than string id fixes three related bugs in one
    move: a NON-STRING id no longer loses its own findings (36kqn -- the old
    `by_field.get(fid, ()) if isinstance(fid, str) else ()` guard meant an
    int/None id NEVER picked up its own ERROR), an id-less field's own ERROR
    is unambiguously its own rather than being reclassified as schema-level
    (ukch0), and two fields sharing one id string no longer cross-contaminate
    each other's findings for any INDEXED finding (ele9z).
    """
    out: Dict[int, List[LintFinding]] = {}
    for f in findings or ():
        idx = _field_index_of(f.path, id_to_index)
        if idx is None:
            continue
        out.setdefault(idx, []).append(f)
    return out


def _schema_level_errors(
    findings: Optional[Iterable[LintFinding]],
    id_to_index: Dict[str, int],
) -> List[str]:
    """The ERROR findings no field row can carry, as `<rule> at <path>`.

    These are what the /status gate refuses on but no field's sign-off can
    clear: it refuses on ANY lint ERROR, while the review counts only ever see
    field-anchored ones. Ignoring them let a fully-reviewed kit stamp
    ready=True and then 409 at publish (bd polyglot-pdf-dm3c8).

    "No field row can carry it" now means the path resolves to NO field
    position at all (see _field_index_of) -- the only two shapes that reach
    here are a section-anchored ERROR (`sections[i] (id=sec_to_review_x)`,
    the `to-review-pending` rule) and a dump-only ERROR with no schema anchor
    at all (`widget '<name>'`, `dump-widget-multiclaim`). A field WITH a
    resolvable anchor -- including one with a missing/non-string/duplicate id
    -- is never double-reported here (bd polyglot-pdf-ukch0): it is that
    field's own finding, named once in blocking_ids via the field-index
    bucket, never a second time here under a stringified `(id=None)` path.
    """
    out: List[str] = []
    for f in findings or ():
        if f.severity != SEVERITY_ERROR:
            continue
        if _field_index_of(f.path, id_to_index) is not None:
            continue  # a real field (by POSITION) owns it, named in blocking_ids
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
        #
        # It still SAYS SO rather than refusing silently: this path used to
        # return both name lists empty, so a gate rendering the refusal had
        # nothing at all to show -- the unactionable-409 shape the verdict
        # exists to prevent, in the one case where the human most needs a
        # pointer (Opus fresh-eyes). Reported as a schema-level blocker
        # because that is exactly what it is: nothing a field's review can fix.
        return ReadinessVerdict(
            ready=False, counts=ReadinessCounts(0, 0, 0, 0), blocking_ids=[],
            blocking_schema_errors=["unmeasurable-schema at $.fields"],
        )

    # Materialize the findings once: they are consumed twice below (bucketed
    # per field, and scanned for schema-level ERRORs), and the parameter is
    # typed as an Iterable a generator could satisfy -- which the second pass
    # would find already exhausted.
    findings = list(lint_findings) if lint_findings is not None else []
    # Each STRING id's own position -- the fallback _field_index_of uses for
    # the one unindexed-path rule (guidance-identity-stale). Last-write-wins
    # on a duplicate id here is a narrow, pre-existing ambiguity for that one
    # rule only; every indexed-path rule is unaffected (resolved by index).
    id_to_index = {
        f.get("id"): i for i, f in enumerate(fields)
        if isinstance(f, dict) and isinstance(f.get("id"), str)
    }
    # Bucketed by POSITIONAL index (bd polyglot-pdf-36kqn/ukch0/ele9z), not by
    # string id: an id can be missing, non-string, or duplicated across two
    # fields, and none of those may cause a field to lose (or steal) its own
    # findings. See _bucket_by_field_index / _schema_level_errors above.
    by_field_index = _bucket_by_field_index(findings, id_to_index)
    schema_errors = _schema_level_errors(findings, id_to_index)
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
        own = by_field_index.get(index, ())
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
    if total == 0:
        # An EXTRACTED-BUT-EMPTY schema: measurable, but 0 of 0 is not "fully
        # reviewed" -- publishing a form with no fields is not something a
        # human signed off on. It says so rather than refusing silently, for
        # the same reason the unmeasurable-schema return above does: this is
        # the structurally identical twin, and leaving one silent would read as
        # deliberate to the next reader (Opus fresh-eyes; bd
        # polyglot-pdf-4ppnt, which this closes).
        schema_errors = schema_errors + ["empty-schema at $.fields"]
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
