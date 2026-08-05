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

import re
from pathlib import Path

import pytest

from backend.services.publish_readiness import (
    ReadinessCounts,
    finding_fingerprint,
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


def test_malformed_field_entries_stay_in_the_denominator():
    """A junk entry cannot be reviewed, so it must still count toward total --
    dropping it would let a corrupted kit report a confident 100%."""
    v = publish_readiness({"fields": [_reviewed("a"), "junk", None]}, [])
    assert v.counts.total == 3
    assert v.counts.reviewed == 1
    assert v.ready is False


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
