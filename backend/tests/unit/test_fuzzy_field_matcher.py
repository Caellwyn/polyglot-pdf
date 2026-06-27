"""
Unit tests for backend.utils.fuzzy_field_matcher.

FOCUS (bd polyglot-pdf-jnjj.46): the field id (with its positional prefix stripped)
is now indexed as a last-resort searchable text so that when the model hallucinates
a plausible id VARIANT in update_form_fields -- preserving the semantic tail
("familyname") while mangling the positional head ("p1_line1_" for "p1_line3a_") --
the variant fuzzy-resolves to the real field instead of being rejected as unknown.

The headline RISK this guards against is a SILENT MIS-FILL: a naive id match pulls a
hallucinated id onto whatever present field shares its prefix / incidental letters
and applies the value there (worse than rejecting). The tests therefore pin BOTH the
recovery behavior AND the rejections that must happen:
  - a semantic synonym ("first_name" for "given name") must NOT resolve;
  - a hallucinated id whose real target is ABSENT (DTI merge-timing gap) must NOT
    resolve to some other present field.

The matcher had NO direct test coverage before this bead.
"""
import pytest

from backend.models.form_models import FormField
from backend.utils.fuzzy_field_matcher import (
    build_searchable_index,
    fuzzy_match_hint,
    normalize_text,
    strip_positional_prefix,
)


def _field(field_id: str, name: str, spoken_name: str, **kw) -> FormField:
    """Build a minimal FormField (section_id is required by the model)."""
    return FormField(
        id=field_id,
        name=name,
        type="text",
        spoken_name=spoken_name,
        section_id=kw.pop("section_id", "p1"),
        **kw,
    )


@pytest.fixture
def i90_fields():
    """The real I-90 fields whose ids the model hallucinated (from the bead)."""
    return [
        _field("p1_line1_aliennumber", "Alien Registration Number", "alien number"),
        _field("p1_line2_acctidentifier", "USCIS Online Account Number", "account identifier"),
        _field("p1_line3a_familyname", "Family Name", "family name"),
        _field("p1_line3b_givenname", "Given Name", "given name"),
    ]


class TestStripPositionalPrefix:
    @pytest.mark.parametrize(
        "field_id,expected",
        [
            ("p1_line3a_familyname", "familyname"),
            ("p1_line1_aliennumber", "aliennumber"),
            ("p2_part3_signature", "signature"),
            ("email", "email"),  # no positional prefix -> unchanged
            # "p1_" alone is not stripped without a following line/part segment --
            # conservative: a bare page prefix on a non-line id is left intact.
            ("p1_unit_type6c_unit", "p1_unit_type6c_unit"),
        ],
    )
    def test_strip(self, field_id, expected):
        assert strip_positional_prefix(field_id) == expected

    def test_positional_only_id_falls_back_to_original(self):
        # Never return empty: a degenerate all-prefix id keeps its original form.
        assert strip_positional_prefix("p1_line2_") == "p1_line2_"


class TestIdIndexing:
    """The stripped id is part of the searchable index, flagged is_id (jnjj.46)."""

    def test_index_includes_stripped_id_flagged(self, i90_fields):
        index = build_searchable_index(i90_fields)
        assert "familyname" in index
        field, original, is_id = index["familyname"]
        assert field.id == "p1_line3a_familyname"
        assert is_id is True

    def test_spoken_name_entry_not_flagged_as_id(self, i90_fields):
        index = build_searchable_index(i90_fields)
        _, _, is_id = index["family name"]
        assert is_id is False


class TestIdVariantRecovery:
    """Positional-mangled id variants resolve to the real field (the fix's job).

    These cases MUST exercise the id-recovery path (via_id=True). Asserting via_id
    is what keeps the test honest: without it, a case whose semantic tail also
    matches the spoken name would pass via the OLD spoken-name codepath and stay
    green even if the id-indexing fix were reverted (fresh-eyes Gap 2).
    """

    @pytest.mark.parametrize(
        "hallucinated,expected_id",
        [
            # tail absent from spoken-name tokens -> can ONLY resolve via the id path
            ("p1_line1_familyname", "p1_line3a_familyname"),
            ("p1_line1_givenname", "p1_line3b_givenname"),
        ],
    )
    def test_resolves_via_id_path(self, i90_fields, hallucinated, expected_id):
        result = fuzzy_match_hint(hallucinated, i90_fields)
        assert result.status == "resolved"
        assert result.top_candidate.field.id == expected_id
        # Proves the recovery came from the id index, not an incidental spoken match.
        assert result.top_candidate.via_id is True

    def test_reverting_id_index_would_drop_these(self, i90_fields):
        # Belt-and-suspenders for Gap 2: the spoken-name normalization of these
        # hallucinated ids does NOT match any field's spoken name above threshold,
        # so the ONLY thing that resolves them is the id index. (If someone reverts
        # the id-indexing, test_resolves_via_id_path fails outright -- this just
        # documents WHY.)
        from backend.utils.fuzzy_field_matcher import build_searchable_index
        index = build_searchable_index(i90_fields)
        # 'familyname'/'givenname' keys exist ONLY because the id pass added them.
        assert index["familyname"][2] is True  # is_id
        assert index["givenname"][2] is True

    def test_account_variant_recovers_via_spoken_name(self, i90_fields):
        # 'p1_line2_uscis_account' is too far from the id 'acctidentifier' to clear
        # the strict id bar, but the spoken-name path ('account identifier') still
        # catches it -- the two paths are complementary. This one is via_id=False.
        result = fuzzy_match_hint("p1_line2_uscis_account", i90_fields)
        assert result.status == "resolved"
        assert result.top_candidate.field.id == "p1_line2_acctidentifier"
        assert result.top_candidate.via_id is False


class TestMisFillGuards:
    """The dangerous cases: an id match must REJECT rather than fill the wrong field."""

    def test_semantic_synonym_is_not_mis_filled(self, i90_fields):
        # 'first_name' is a SEMANTIC guess for 'given name' that fuzzy-matches
        # 'family' more than 'given'. Forcing a match corrupts data; the only safe
        # outcome is to not resolve (caller rejects it as unknown).
        result = fuzzy_match_hint("p1_line4a_first_name", i90_fields)
        assert result.status != "resolved"

    def test_absent_target_does_not_resolve_to_other_field(self):
        # DTI merge-timing: the real target field is not yet in the validation set.
        # A naive id match would pull the hallucinated id onto a present field that
        # shares incidental id letters ('givenname' vs 'aliennumber' ~ 0.60) and
        # mis-fill it. The strict id threshold must reject instead.
        present_only = [
            _field("p1_line1_aliennumber", "Alien Registration Number", "alien number"),
            _field("p1_line2_acctidentifier", "USCIS Online Account Number", "account identifier"),
        ]
        for hallucinated in ("p1_line1_familyname", "p1_line1_givenname"):
            result = fuzzy_match_hint(hallucinated, present_only)
            assert result.status != "resolved", hallucinated


class TestSharedTailCollision:
    """A stripped id tail shared by >1 field must NOT identify a single field.

    The I-90 schema has many ids sharing a tail across parts (familyname,
    streetnumbername, ...). If both are in the candidate set, indexing the tail
    would silently route a hallucinated id to whichever claimed the key first --
    the exact mis-fill the fix exists to prevent (fresh-eyes Gap 1).
    """

    @pytest.fixture
    def shared_tail_fields(self):
        return [
            _field("p1_line3a_familyname", "Family Name", "your family name"),
            _field("p7_line1a_familyname", "Preparer Family Name", "preparer family name"),
        ]

    def test_ambiguous_tail_not_indexed_as_id(self, shared_tail_fields):
        index = build_searchable_index(shared_tail_fields)
        # The shared 'familyname' tail is NOT added as an is_id entry (it can't
        # identify one field). The spoken-name entries remain.
        assert "familyname" not in index or index["familyname"][2] is False

    def test_hallucinated_id_with_shared_tail_does_not_resolve(self, shared_tail_fields):
        # A hallucinated id whose tail is shared must reject, not mis-fill.
        result = fuzzy_match_hint("p7_line1_familyname", shared_tail_fields)
        assert result.status != "resolved"

    def test_spoken_names_still_disambiguate_shared_tail(self, shared_tail_fields):
        # The distinct spoken names still resolve each field correctly.
        r1 = fuzzy_match_hint("your family name", shared_tail_fields)
        assert r1.status == "resolved" and r1.top_candidate.field.id == "p1_line3a_familyname"
        r2 = fuzzy_match_hint("preparer family name", shared_tail_fields)
        assert r2.status == "resolved" and r2.top_candidate.field.id == "p7_line1a_familyname"


class TestRegressionGuards:
    """Indexing the id must not change correct existing spoken-name behavior."""

    @pytest.mark.parametrize(
        "spoken,expected_id",
        [
            ("family name", "p1_line3a_familyname"),
            ("given name", "p1_line3b_givenname"),
            ("account identifier", "p1_line2_acctidentifier"),
            ("alien number", "p1_line1_aliennumber"),
        ],
    )
    def test_spoken_name_still_resolves(self, i90_fields, spoken, expected_id):
        result = fuzzy_match_hint(spoken, i90_fields)
        assert result.status == "resolved"
        assert result.top_candidate.field.id == expected_id

    def test_unrelated_garbage_stays_unresolved(self, i90_fields):
        result = fuzzy_match_hint("zzz_totally_unrelated_token", i90_fields)
        assert result.status == "unresolved"

    def test_same_field_indexed_twice_is_not_self_ambiguous(self, i90_fields):
        # 'family name' matches BOTH the spoken-name entry and the stripped-id entry
        # of the SAME field. Per-field de-dup must keep this a clean single-field
        # resolve, not a (top vs its own second entry) "ambiguous".
        result = fuzzy_match_hint("family name", i90_fields)
        assert result.status == "resolved"
        assert result.top_candidate.field.id == "p1_line3a_familyname"
