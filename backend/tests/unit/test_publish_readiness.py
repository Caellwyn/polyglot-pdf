"""publish_readiness is THE definition of a kit's review progress (sprint-18
C4, bd polyglot-pdf-g687).

Two things are pinned here:

1. The PREDICATE -- which fields count reviewed, and therefore what the stamp
   records and what C2's publish gate will refuse on. Its clauses (sign-off,
   lint ERROR, the guidance ack gate, the timeliness rule) each get a case,
   plus the grandfather rule for sign-offs written before seen_fingerprints
   existed.
2. The cross-language FINGERPRINT parity. The client stamps
   _review.seen_fingerprints using findingFingerprint (lintFindings.ts) and
   this module compares against those strings, so any divergence breaks the
   timeliness rule in the demote-everything direction -- silently, and on every
   kit at once. The parity case list below is byte-compared against values
   produced by the REAL client implementation.

ASCII only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.services.publish_readiness import (
    ReadinessCounts,
    finding_fingerprint,
    has_uncovered_structural_error,
    is_counted_reviewed,
    publish_readiness,
)
from backend.services.guidance_contract import identity_sha1
from backend.services.schema_lint import LintFinding

_REPO = Path(__file__).resolve().parents[3]
_LINT_FINDINGS_TS = _REPO / "schema-editor" / "src" / "utils" / "lintFindings.ts"


def _finding(rule: str, path: str, severity: str = "WARNING",
             message: str = "m") -> LintFinding:
    return LintFinding(severity=severity, rule=rule, path=path, message=message)


def _field(fid: str = "f1", **over) -> dict:
    base = {
        "id": fid,
        "name": fid,
        "type": "text",
        "spoken_name": fid,
        "pdf_field_name": f"{fid}[0]",
    }
    base.update(over)
    return base


def _reviewed(fid: str = "f1", **over) -> dict:
    return _field(fid, _review={"status": "reviewed_correct"}, **over)


# --------------------------------------------------------------------------- #
# The predicate
# --------------------------------------------------------------------------- #


def test_only_human_signoff_counts_reviewed():
    """Green is a human's word: an unreviewed field never counts, however
    clean, and needs_followup never counts (bd polyglot-pdf-g63j)."""
    assert is_counted_reviewed(_reviewed()) is True
    assert is_counted_reviewed(_field()) is False
    assert is_counted_reviewed(
        _field(_review={"status": "needs_followup"})) is False
    # A malformed / unrecognized status collapses to unreviewed, never crashes.
    assert is_counted_reviewed(_field(_review={"status": "bogus"})) is False
    assert is_counted_reviewed(_field(_review="not-a-dict")) is False


def test_lint_error_excludes_even_a_signed_off_field():
    err = _finding("field-unbacked", "fields[0] (id=f1)", severity="ERROR")
    warn = _finding("help-instructions-too-long", "fields[0] (id=f1).help.instructions")
    assert is_counted_reviewed(_reviewed(), [err]) is False
    # A WARNING does NOT exclude -- the sign-off is the human saying they saw it.
    # (Timeliness is what re-raises a warning; severity alone does not.)
    assert is_counted_reviewed(
        _field(_review={"status": "reviewed_correct",
                        "seen_fingerprints": [finding_fingerprint(warn)]}),
        [warn]) is True


def test_guidance_ack_gate_uses_a_natively_computed_hash():
    """A staleness finding demands an ack matching the field's CURRENT identity,
    computed here via identity_sha1 -- never parsed from the finding path."""
    field = _reviewed()
    stale = _finding("guidance-identity-stale",
                     "fields[0] (id=f1).help[identity:deadbeef]")
    seen = [finding_fingerprint(stale)]

    # Signed off + timely, but no ack -> gated.
    ungated = dict(field)
    ungated["_review"] = {"status": "reviewed_correct", "seen_fingerprints": seen}
    assert is_counted_reviewed(ungated, [stale]) is False

    # An ack for the WRONG identity stays gated (no permanent waiver): the
    # path's own hash is deliberately not what we compare against.
    wrong = dict(field)
    wrong["_review"] = {"status": "reviewed_correct", "seen_fingerprints": seen,
                        "guidance_ack_sha1": "deadbeef"}
    assert is_counted_reviewed(wrong, [stale]) is False

    # An ack for the field's real current identity clears it.
    right = dict(field)
    right["_review"] = {"status": "reviewed_correct", "seen_fingerprints": seen,
                        "guidance_ack_sha1": identity_sha1(field)}
    assert is_counted_reviewed(right, [stale]) is True


def test_timeliness_rule_demotes_on_a_finding_newer_than_the_signoff():
    old = _finding("help-instructions-too-long", "fields[0] (id=f1).help.instructions")
    fresh = _finding("help-details-oversize", "fields[0] (id=f1).help.details")
    signed = _field(_review={"status": "reviewed_correct",
                             "seen_fingerprints": [finding_fingerprint(old)]})
    # The stamped finding alone: still reviewed.
    assert is_counted_reviewed(signed, [old]) is True
    # A finding the sign-off never saw demotes the field.
    assert is_counted_reviewed(signed, [old, fresh]) is False


def test_absent_seen_fingerprints_is_grandfathered_not_mass_demoted():
    """A sign-off written before the slot existed makes NO timeliness claim.

    Treating absent as the empty set would demote every reviewed field on every
    shipped kit the moment this rule went live -- the re-review wave the epic
    exists to end. An EXPLICIT empty list is a real claim ('I signed off with no
    findings in hand') and does demote.
    """
    pre_slot = _field(_review={"status": "reviewed_correct"})
    explicit_empty = _field(_review={"status": "reviewed_correct",
                                     "seen_fingerprints": []})
    surprise = _finding("help-details-oversize", "fields[0] (id=f1).help.details")
    assert is_counted_reviewed(pre_slot, [surprise]) is True
    assert is_counted_reviewed(explicit_empty, [surprise]) is False


# --------------------------------------------------------------------------- #
# The kit-wide verdict
# --------------------------------------------------------------------------- #


def test_counts_and_percentage_over_a_mixed_kit():
    schema = {"fields": [_reviewed("a"), _reviewed("b"), _field("c"), _field("d")]}
    v = publish_readiness(schema, [])
    assert v.counts == ReadinessCounts(reviewed=2, to_review=2, total=4, errors=0)
    assert v.counts.percentage == 50
    assert v.ready is False
    assert v.blocking_ids == ["c", "d"]


def test_ready_only_when_every_field_is_reviewed():
    schema = {"fields": [_reviewed("a"), _reviewed("b")]}
    v = publish_readiness(schema, [])
    assert v.ready is True
    assert v.counts.percentage == 100
    assert v.blocking_ids == []


@pytest.mark.parametrize("rule,path", [
    # The holding-section leftover-ids ERROR. Its path DOES carry an (id=)
    # token, but the token names a SECTION -- so a bucketing rule keyed on
    # "has an id token" files it under a field that does not exist and
    # silently drops it. The client draws the same distinction for the same
    # reason (lintFindings.formLevelFindings keys on "resolves to no field in
    # fields[]", not on "has no id token").
    ("to-review-pending", "sections[0] (id=sec_to_review_x)"),
    # The widget-claim ERROR: no id token at all.
    ("dump-widget-multiclaim", "widget 'form1[0].name[0]'"),
])
def test_a_schema_level_ERROR_blocks_a_fully_reviewed_kit(rule, path):
    """ready must be False for a kit the /status gate will 409 on.

    The gate refuses on ANY lint ERROR regardless of anchoring, while the
    review counts only ever see FIELD-anchored findings -- so a schema-level
    ERROR left ready=True for a kit that then 409s: the confident-then-refused
    shape sprint-18 exists to end, relocated into the stamp (bd
    polyglot-pdf-dm3c8). No field's sign-off can clear these, because no field
    row can carry them.
    """
    schema = {"fields": [_reviewed("a"), _reviewed("b")]}
    err = _finding(rule, path, severity="ERROR")
    v = publish_readiness(schema, [err])

    assert v.ready is False
    # ...and the refusal NAMES it (exit criterion 2): a gate that refuses
    # without saying what to fix is unactionable.
    assert v.blocking_schema_errors == [f"{rule} at {path}"]

    # The FIELD counts are untouched: every field really is reviewed, and the
    # percentage stays honest at 100%. Folding a field-less finding into
    # to_review would break the invariant below AND understate the review work
    # actually done (exit criterion 3).
    assert v.counts.reviewed == 2
    assert v.counts.to_review == 0
    assert v.counts.percentage == 100
    assert v.counts.reviewed + v.counts.to_review == v.counts.total
    assert v.blocking_ids == []


def test_both_schema_level_ERROR_classes_at_once_are_each_named():
    """The two classes can co-occur, and BOTH must be named.

    The parametrized test above exercises them one at a time, which cannot
    catch a collection bug that keeps only the first (or the last). A gate that
    reports one of two blockers sends the human back for a second round trip
    (fresh-eyes coverage note).
    """
    schema = {"fields": [_reviewed("a")]}
    sec = _finding("to-review-pending", "sections[0] (id=sec_to_review_x)",
                   severity="ERROR")
    wid = _finding("dump-widget-multiclaim", "widget 'form1[0].name[0]'",
                   severity="ERROR")
    v = publish_readiness(schema, [sec, wid])
    assert v.ready is False
    assert v.blocking_schema_errors == [
        "to-review-pending at sections[0] (id=sec_to_review_x)",
        "dump-widget-multiclaim at widget 'form1[0].name[0]'",
    ]
    assert v.counts.reviewed + v.counts.to_review == v.counts.total


def test_a_schema_level_WARNING_does_not_block():
    """Only ERRORs block -- the gate refuses on ERROR severity alone, and the
    aggregate guidance/translation WARNINGs are field-less by design."""
    schema = {"fields": [_reviewed("a")]}
    warn = _finding("help-instructions-missing", "$.fields")
    v = publish_readiness(schema, [warn])
    assert v.ready is True
    assert v.blocking_schema_errors == []


def test_a_field_anchored_ERROR_is_not_double_counted_as_schema_level():
    """An ERROR a real field OWNS is already handled by the review counts; it
    must not ALSO appear as a schema-level blocker, or the gate would report
    one defect twice under two different headings."""
    schema = {"fields": [_reviewed("a")]}
    err = _finding("field-unbacked", "fields[0] (id=a)", severity="ERROR")
    v = publish_readiness(schema, [err])
    assert v.ready is False                # demoted by its own ERROR
    assert v.blocking_ids == ["a"]         # named as a FIELD...
    assert v.blocking_schema_errors == []  # ...and not again as schema-level
    assert v.counts.errors == 1


def test_findings_may_be_a_one_shot_iterable():
    """The parameter is typed Iterable, and the verdict now consumes it twice
    (bucket per field, then scan for schema-level ERRORs). A generator must not
    arrive exhausted at the second pass."""
    schema = {"fields": [_reviewed("a")]}
    err = _finding("dump-widget-multiclaim", "widget 'x[0]'", severity="ERROR")
    v = publish_readiness(schema, (f for f in [err]))
    assert v.ready is False
    assert len(v.blocking_schema_errors) == 1


def test_an_empty_kit_is_never_ready():
    """0 of 0 is not 'fully reviewed' -- publishing an empty form is not a thing
    a human signed off on, and 0/0 rendering as 100% would gate open."""
    v = publish_readiness({"fields": []}, [])
    assert v.ready is False
    assert v.counts.percentage == 0
    assert v.counts.total == 0


def test_a_malformed_fields_value_is_unmeasurable_not_zero_percent():
    for bad in ("abc", None, {"a": 1}, 7):
        v = publish_readiness({"fields": bad}, [])
        assert v.counts.total == 0
        assert v.ready is False


def test_a_refusal_always_names_something():
    """`ready=False` must never ship with an EMPTY blocking_ids.

    ReadinessVerdict's docstring promises the gate "refuses BY NAME, never with
    a bare count", and C2 surfaces that list to a human. Id-less and malformed
    entries were silently dropped, so a kit made entirely of them refused while
    naming nobody -- an unactionable 409 (confirming Opus outer review).
    """
    # Every entry unusable: malformed, None, and a dict with no id.
    v = publish_readiness({"fields": ["junk", None, {"type": "text"}]}, [])
    assert v.ready is False
    assert v.counts.to_review == 3
    assert len(v.blocking_ids) == 3, "a refusal that names nobody is unactionable"
    # The placeholders say WHERE, and are deliberately not id-shaped so a
    # caller cannot present them as searchable field ids.
    assert all("no id" in name for name in v.blocking_ids)
    assert "fields[0]" in v.blocking_ids[0]

    # Real ids are still used verbatim when present, and the two mix correctly.
    mixed = publish_readiness(
        {"fields": [_field("real"), "junk"]}, [])
    assert mixed.blocking_ids == ["real", "fields[1] (no id)"]


def test_malformed_field_entries_stay_in_the_denominator():
    """A junk entry cannot be reviewed, so it must still count toward total --
    dropping it would let a corrupted kit report a confident 100%."""
    v = publish_readiness({"fields": [_reviewed("a"), "junk", None]}, [])
    assert v.counts.total == 3
    assert v.counts.reviewed == 1
    assert v.ready is False


@pytest.mark.parametrize("reviewed,total,expected", [
    # Exact .5 ratios: Python's round() is BANKER'S rounding (ties to even) and
    # would give 12 / 62 / 38 here, while the client's Math.round ties UP. A
    # mismatch means the stamp and the open editor's strip print different
    # numbers for the SAME saved kit (fresh-eyes gap 2).
    (1, 8, 13),
    (5, 8, 63),
    (3, 8, 38),
    (7, 8, 88),
    (1, 40, 3),
    # Non-tie cases behave identically under either rule.
    (1, 3, 33),
    (2, 3, 67),
    (1, 1, 100),
    (0, 5, 0),
])
def test_percentage_rounds_ties_up_like_the_client(reviewed, total, expected):
    """The percentage must match JS Math.round, not Python round()."""
    counts = ReadinessCounts(
        reviewed=reviewed, to_review=total - reviewed, total=total, errors=0,
    )
    assert counts.percentage == expected


def test_uncovered_structural_error_clause_and_backend_robustness():
    """The clause reviewStatus.ts hasUncoveredStructuralError applies, which
    the server MUST compute identically (fresh-eyes gap 3) -- otherwise a field
    counts reviewed in the stamp while the open editor renders it red.

    The WELL-FORMED cases below are genuine parity claims (and the shared
    fixture reviewPredicateParity.json runs the same shapes through both
    predicates). The malformed-options cases at the end are backend-only
    robustness and say so -- see the comment there.
    """
    signed = {"status": "reviewed_correct"}

    # A choice field where neither the field nor every option names a widget:
    # genuinely unfillable, no lint ERROR covers it -> NOT reviewed.
    unmapped_choice = {
        "id": "c", "type": "select", "_review": signed,
        "options": [{"value": "a", "pdf_field_name": "A[0]"}, {"value": "b"}],
    }
    assert is_counted_reviewed(unmapped_choice) is False
    assert has_uncovered_structural_error(unmapped_choice) is True

    # Every option mapped -> fine.
    mapped_choice = {
        "id": "c", "type": "select", "_review": signed,
        "options": [{"value": "a", "pdf_field_name": "A[0]"},
                    {"value": "b", "pdf_field_name": "B[0]"}],
    }
    assert is_counted_reviewed(mapped_choice) is True

    # A field-level widget covers the whole choice -> fine.
    field_mapped = {
        "id": "c", "type": "select", "_review": signed,
        "pdf_field_name": "C[0]", "options": [{"value": "a"}],
    }
    assert is_counted_reviewed(field_mapped) is True

    # A NON-choice field with no widget is NOT a structural error here (that is
    # the lint layer's field-unbacked rule) -- pinned so the clause does not
    # silently widen and re-break bd polyglot-pdf-q3rm.
    assert is_counted_reviewed(
        {"id": "t", "type": "text", "_review": signed}) is True

    # Missing id or type at all -> uncovered.
    assert is_counted_reviewed({"type": "text", "_review": signed}) is False
    assert is_counted_reviewed({"id": "x", "_review": signed}) is False

    # BACKEND-ONLY robustness -- deliberately NOT a parity claim. On these
    # exact shapes the CLIENT mirror THROWS (options.some is not a function; a
    # property read on null), so asserting them here as "mirrors the client"
    # would document a parity that does not hold (Opus fresh-eyes round 7
    # measured 12 divergent shapes out of 720, all client-throws). The backend
    # degrades instead of throwing because it runs over hand-edited and legacy
    # kits at publish time, where a crash would be a 500 rather than a blank
    # panel. The client-side crash is pre-existing (C1, reviewStatus.ts is
    # untouched by this bead) and tracked as bd polyglot-pdf-93p8; when it is
    # fixed, these shapes belong in the shared parity fixture instead.
    assert has_uncovered_structural_error(
        {"id": "c", "type": "radio", "options": ["junk", None]}) is True
    assert has_uncovered_structural_error(
        {"id": "c", "type": "select", "options": "not-a-list"}) is False


def test_counting_invariant_reviewed_plus_to_review_equals_total():
    """The invariant the strip and the stamp both render. `errors` is a
    DIAGNOSTIC bucket over the same fields, not a third partition."""
    err = _finding("field-unbacked", "fields[0] (id=c)", severity="ERROR")
    schema = {"fields": [_reviewed("a"), _reviewed("b"), _field("c"), _field("d")]}
    v = publish_readiness(schema, [err])
    assert v.counts.reviewed + v.counts.to_review == v.counts.total
    assert v.counts.errors == 1
    assert v.counts.errors <= v.counts.to_review


def test_findings_are_bucketed_to_their_own_field_only():
    """A finding on field b must not demote field a (and a schema-level finding
    demotes nobody -- no field's review can cover it)."""
    on_b = _finding("field-unbacked", "fields[1] (id=b)", severity="ERROR")
    form_level = _finding("help-instructions-missing", "$.fields", severity="ERROR")
    v = publish_readiness({"fields": [_reviewed("a"), _reviewed("b")]},
                          [on_b, form_level])
    assert v.counts.reviewed == 1
    assert v.blocking_ids == ["b"]


# --------------------------------------------------------------------------- #
# Cross-language fingerprint parity
# --------------------------------------------------------------------------- #

# (path, rule, message) -> the fingerprint the CLIENT's findingFingerprint
# produces. Captured by running the real TS implementation
# (schema-editor/src/utils/lintFindings.ts) over these exact inputs. The emoji
# case is load-bearing: it is what catches a UTF-16-vs-code-point mismatch in
# the content discriminator, which would otherwise diverge only for non-BMP
# text.
_PARITY_CASES = [
    ("option-value-duplicate", "fields[3] (id=x).options[1]", "dup a",
     "option-value-duplicate|x|fields[] (id=x).options[1]|491y33"),
    ("guidance-identity-stale", "fields[3] (id=x).help[identity:abc123]", "m",
     "guidance-identity-stale|x|fields[] (id=x).help"),
    ("field-unbacked", "fields[7] (id=z)", "no widget",
     "field-unbacked|z|fields[] (id=z)"),
    ("translation-coverage", "coverage.es", "10 of 17",
     "translation-coverage||coverage.es"),
    ("dump-widget-multiclaim", "widget 'form1[0].fields[0].x[0]'", "twice",
     "dump-widget-multiclaim||widget 'form1[0].fields[0].x[0]'"),
    # Escaped, not literal: this file is ASCII-only (CLAUDE.md scar #6), and on
    # Windows a literal non-BMP character in a Python source file that reaches
    # stdout crashes on cp1252.
    ("option-value-duplicate", "sections[2] (id=s).options[0]",
     "unicode \u00e9\u00e8 \u4e2d\u6587 \U0001f600",
     "option-value-duplicate|s|sections[] (id=s).options[0]|1j8t5v2"),
    ("help-instructions-missing", "$.fields", "12 of 40",
     "help-instructions-missing||$.fields"),
    ("to-review-pending", "sections[0] (id=sec_to_review_x)", "refile",
     "to-review-pending|sec_to_review_x|sections[] (id=sec_to_review_x)"),
    ("option-value-duplicate", "fields[10] (id=q).options[2]", "",
     "option-value-duplicate|q|fields[] (id=q).options[2]|45h"),
]


@pytest.mark.parametrize("rule,path,message,expected", _PARITY_CASES)
def test_fingerprint_matches_the_client_byte_for_byte(rule, path, message, expected):
    assert finding_fingerprint(_finding(rule, path, message=message)) == expected


def test_parity_cases_cover_every_client_rule_that_folds_in_the_message():
    """If the client adds a rule to MESSAGE_LOCALIZED_RULES, the Python mirror
    must gain it too -- otherwise that rule's fingerprints silently diverge and
    every field carrying one gets demoted. Read the TS source so the drift
    fails HERE rather than in production."""
    src = _LINT_FINDINGS_TS.read_text(encoding="utf-8")
    m = re.search(r"MESSAGE_LOCALIZED_RULES\s*=\s*new Set\(\[([^\]]*)\]\)", src)
    assert m, "could not find MESSAGE_LOCALIZED_RULES in lintFindings.ts"
    client_rules = set(re.findall(r"'([a-z0-9-]+)'", m.group(1)))
    from backend.services.publish_readiness import _MESSAGE_LOCALIZED_RULES
    assert client_rules == set(_MESSAGE_LOCALIZED_RULES)


# --------------------------------------------------------------------------- #
# Shared cross-language predicate parity
# --------------------------------------------------------------------------- #

_PARITY_FIXTURE = (
    _REPO / "schema-editor" / "src" / "utils" / "__fixtures__"
    / "reviewPredicateParity.json"
)


def _parity_cases():
    data = json.loads(_PARITY_FIXTURE.read_text(encoding="utf-8"))
    return [(c["name"], c) for c in data["cases"]]


def test_parity_fixture_is_non_trivial():
    """Guards against an emptied or one-sided fixture silently passing."""
    cases = [c for _n, c in _parity_cases()]
    assert len(cases) >= 15
    assert any(c["expected"] for c in cases)
    assert any(not c["expected"] for c in cases)


@pytest.mark.parametrize("name,case", _parity_cases())
def test_predicate_parity_with_the_client(name, case):
    """THE count predicate must return the same answer as the client's.

    The catalogue renders the backend's STAMPED number while the open editor
    renders reviewStatus.isCountedReviewed's -- so a divergence means one saved
    kit shows two percentages, the bug this bead exists to end. The same cases
    run through the TS predicate in
    schema-editor/src/utils/reviewStatus.parity.test.ts.

    This fixture exists because prose could not hold the mirror together: the
    timeliness rule here had omitted the guidance-staleness exclusion the
    client makes, so sign-off -> drift -> ack counted reviewed in the editor and
    NOT in the stamp. Both sides' own unit tests passed (Opus fresh-eyes
    round 2).
    """
    field = json.loads(json.dumps(case["field"]))
    review = field.get("_review")
    # `@identity` in the fixture means "this field's OWN current identity hash",
    # which each language computes natively -- resolve it here rather than
    # hardcoding a value the two sides could disagree about.
    identity = identity_sha1(field)
    if isinstance(review, dict) and "ackSha1" in review:
        # Pop ONCE: the earlier form popped in the condition and again in the
        # else branch, so any literal (non-"@identity") hash raised KeyError
        # instead of asserting -- a trap laid directly in the path the
        # fixture's own header invites future authors down (Opus fresh-eyes
        # round 7).
        raw_ack = review.pop("ackSha1")
        review["guidance_ack_sha1"] = identity if raw_ack == "@identity" else raw_ack
    findings = [
        _finding(
            f["rule"],
            f["path"].replace("@identity", identity),
            severity=f["severity"],
            message=f["message"],
        )
        for f in case["findings"]
    ]
    assert is_counted_reviewed(field, findings) is case["expected"], name


def test_container_indices_are_stripped_but_option_indices_are_not():
    """Position is not identity: fields[3] shifts when an earlier field is
    removed, so it is stripped; options[i] has no id token beside it, so it is
    the only thing naming which choice a finding is about and is KEPT."""
    a = finding_fingerprint(_finding("field-unbacked", "fields[3] (id=x)"))
    b = finding_fingerprint(_finding("field-unbacked", "fields[99] (id=x)"))
    assert a == b
    o1 = finding_fingerprint(_finding("option-value-slug", "fields[3] (id=x).options[1]"))
    o2 = finding_fingerprint(_finding("option-value-slug", "fields[3] (id=x).options[2]"))
    assert o1 != o2


def test_message_is_excluded_from_the_ordinary_fingerprint():
    """A copy pass rewording a message must never demote a reviewed field."""
    a = finding_fingerprint(_finding("field-unbacked", "fields[0] (id=x)", message="old wording"))
    b = finding_fingerprint(_finding("field-unbacked", "fields[0] (id=x)", message="new wording"))
    assert a == b
