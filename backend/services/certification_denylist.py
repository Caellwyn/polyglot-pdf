"""Refuse to fill interpreter/preparer certification blocks (bd polyglot-pdf-oagt).

THE LEGAL INVARIANT
-------------------
Our position is that we are NOT the preparer of any form: the client
self-prepares with a typing aid, and the reviewing firm takes professional
responsibility. The STRUCTURAL form of that claim is far stronger than the
asserted one -- the tool CANNOT fill the preparer block, therefore it does not
claim to be the preparer. That is a checkable fact about the software, not a
disclaimer.

USCIS I-90 Part 6 is the Interpreter's Certification and Part 7 the Preparer's
Declaration; both are signed under penalty of perjury. Form 1040 has an
equivalent "Paid Preparer Use Only" block. Writing into any of them would have
the software assert, in a signed government filing, that a specific human
performed a professional act.

WHY THIS IS A SERVER-SIDE DENYLIST AND NOT A SCHEMA SETTING
-----------------------------------------------------------
The schema editor's `_ignored_fields` quarantine is an AUTHORING convention: it
removes the field from the schema the client holds. It cannot protect this
invariant, for two independent reasons:

1. `/api/fill-pdf` builds its field map from the `form_schema` in the REQUEST
   BODY, never from the kit's stored schema.json. A client that sends an ignored
   field back -- buggy, stale, or hostile -- gets it written.
2. A convention can be silently flipped by a re-extraction, a schema edit, or a
   contractor authoring a new kit who has never heard of the rule.

So the check lives here, on the write path, and applies REGARDLESS of what the
schema says. Defense in depth: the schema may also ignore these fields, but the
legal position does not depend on it.

MATCHING IS DELIBERATELY BROAD
------------------------------
A false positive means a preparer-block field silently stays empty -- the
correct outcome anyway, since a human must complete that block by hand. A false
negative means we filled a perjury attestation. The asymmetry is total, so these
patterns match generously and are checked against BOTH the schema field id and
the PDF field name (the client controls both, so neither alone is sufficient).
"""

from __future__ import annotations

import re
from typing import Optional

# TWO TIERS, because a single flat list cannot express this correctly.
#
# Fresh-eyes round 2 proved it: `\bp6[_-]` protects the I-90 (Part 6 IS the
# Interpreter's Certification there) but on the N-400 Part 6 is "Information
# About Your Employment and Schools" and Part 7 is "Time Outside the United
# States" -- the APPLICANT'S OWN answers. The same pattern that protects one
# form silently blanks a client's spoken answers on another, and a part number
# means whatever each form says it means. So form-specific facts are scoped to
# the kit that has them; only genuinely universal ROLES are global.

# TIER 1 -- global. A person in one of these roles is never the applicant, on
# any form. Matched case-insensitively against the schema field id AND the PDF
# field name.
#
# NO LEADING \b ON ANY OF THESE. `\b` does not match between "_" and a letter,
# so r"\bptin" never fires on agent_ptin and r"\bfirm" never fires on
# fld_firm_name -- the exact ids these exist to catch. That bug bit THREE times
# in this one bead. Match the token anywhere; anchor only the END where a suffix
# would be wrong.
_CERTIFICATION_PATTERNS = (
    # Third-party professional roles. Each names a person acting in a
    # professional capacity on someone else's behalf -- never the applicant.
    r"interpreter",
    r"preparer",
    # ptin / firm: NO trailing \b either. "ptin\b" misses ptin_number and
    # fld_ptin_number -- the obvious ids for the F1040 PTIN box -- and
    # "firm...\b" misses firm_name_line1, firm_address_2, firm_ein_number.
    # The shipped f1040 happens to use fld_firm_name, so that gap was invisible
    # and would have reopened on the next re-extraction: the same shape as the
    # round-1 W-7 escape (fresh-eyes round 3).
    r"ptin",                         # a preparer's own IRS credential
    r"attorney",
    r"accredited[_\-]?rep",          # accredited representative (USCIS G-28)
    r"g28[_\-]",                     # the G-28 attorney/rep appearance block
    r"notary",
    r"civil[_\-]?surgeon",           # I-693 medical examination
    r"acceptance[_\-]?agent",        # IRS W-7
    # Other third-party roles that sign or attest on someone else's behalf.
    # Every one of these is writable today (fresh-eyes round 3) and appears on
    # a real US immigration / tax / state-court form: I-864 joint sponsor and
    # household member, I-693 panel physician, notarized affidavits, court
    # filings, and any form with a translator's certification.
    r"translator",
    r"translated[_\-]?by",
    r"\bwitness",
    r"affiant",
    r"deponent",
    r"commission[_\-]?expires",      # a notary's own commission
    r"subscribed[_\-]?and[_\-]?sworn",
    r"guardian[_\-]?ad[_\-]?litem",
    r"panel[_\-]?physician",
    r"authorized[_\-]?rep",
    r"joint[_\-]?sponsor",           # I-864
    r"household[_\-]?member",        # I-864A
    # The ACT of certifying, which is what a third party does. NOT a bare
    # r"certif": an applicant's own DOCUMENTS are full of the word
    # (birth_certificate_number, certificate_of_naturalization_number,
    # marriage_certificate_date, police_certificate) and refusing those would
    # break ordinary form-filling while looking like caution.
    r"certification",
    r"certifies",
    r"certifying",
    r"attest",
    r"under[_\-]?penalty",
)

# TIER 2 -- kit-scoped. Form-specific facts: a part number, or a word that is
# a professional block on THIS form and an ordinary answer elsewhere. Keyed on
# kit_id; the value is a pattern applied only to that kit.
#
# Every entry here is a claim about ONE form's layout, so adding a kit means
# reading that form -- which is the correct amount of friction. A pattern that
# would be right for every form belongs in tier 1 instead.
_KIT_SCOPED_PATTERNS = {
    # I-90 Part 6 = Interpreter's Certification, Part 7 = Preparer's
    # Declaration. The whole part is the attestation, and its inner fields
    # (p7_line1a_familyname) carry no role word of their own -- which is why the
    # prefix is needed at all.
    # These match BOTH the schema ids (p6_line1a_...) and the PDF field names
    # (P6_Line1a_...) because the whole list is compiled IGNORECASE -- an
    # earlier cut listed "P6_"/"P7_" separately, which were exact duplicates
    # that no test could distinguish (fresh-eyes round 3).
    "i-90": (r"p6[_\-]", r"p7[_\-]"),
    # F1040 "Paid Preparer Use Only": the firm block and the self-employed
    # checkbox belong to the PREPARER here. On an N-400 "are_you_self_employed"
    # is the applicant's own answer, so this must not be global.
    "f1040": (r"firm[_\-]", r"self[_\-]?employed"),
    # W-7 "Acceptance Agent's Use ONLY". "agent" cannot be global -- an
    # applicant may legitimately answer agent_orange_exposure or
    # travel_agent_name on another form. "delegate" is the agent's designee.
    "w7": (r"agent[_\-]", r"delegate"),
}

_CERTIFICATION_RE = re.compile("|".join(_CERTIFICATION_PATTERNS), re.IGNORECASE)

def _normalize_kit_id(kit_id: Optional[str]) -> str:
    """Fold the spelling variants kit onboarding actually produces.

    "I-90", "i90", "form-i-90", "  i-90  " and "i-90" must all select the I-90's
    rules. Case, surrounding whitespace, separators, and a leading "form" are
    all noise -- `_derive_kit_id` in editor_kit_routes builds ids from PDF
    filenames, so "Form I-90.pdf" becomes "form-i-90" and "fw7.pdf" becomes
    "fw7".

    This is a convenience, NOT the safety mechanism: an id this does not
    recognize falls through to the all-kits union in is_certification_field,
    so a spelling nobody anticipated still gets maximum protection.
    """
    if not kit_id:
        return ""
    key = re.sub(r"[^a-z0-9]", "", kit_id.strip().lower())
    if key.startswith("form"):
        key = key[len("form"):]
    if key.startswith("f") and key[1:] in {"w7", "1040"}:
        key = key[1:]
    return key


_KIT_SCOPED_RE = {
    _normalize_kit_id(kit): re.compile("|".join(patterns), re.IGNORECASE)
    for kit, patterns in _KIT_SCOPED_PATTERNS.items()
}

# Narrow carve-outs for applicant-facing fields whose ID legitimately contains a
# denylisted word (an applicant's own answer is not a third-party attestation).
#
# EMPTY, and that is a measured result, not an oversight. Measured against all
# three deployed kits, WITH each kit's own kit_id supplied:
#     i-90   37 fields   (Parts 6 + 7, interpreter + preparer)
#     f1040   7 fields   ("Paid Preparer Use Only", incl. the firm block)
#     w7      9 fields   ("Acceptance Agent's Use ONLY", incl. the delegate)
# and no applicant-facing field on any shipped kit collides, so no carve-out is
# warranted. (Help text is never matched -- only ids and PDF field names -- so
# the W-7's birth-certificate and certified-translation wording is irrelevant.)
#
# These numbers are pinned by the enumeration tests, so they cannot silently rot.
# An earlier version of this comment said "ZERO W-7" -- which was true only while
# the acceptance-agent block was unprotected, and survived the fix as a false
# statement that would have told the next reader the W-7 has no third-party
# block at all (fresh-eyes rounds 1 and 2).
#
# If a future kit needs an entry: name the exact field id, never a pattern, and
# say why the applicant answering it is not a professional attestation. Every
# entry is a hole in a legal invariant. `test_the_allowlist_stays_empty_or_justified`
# will fail until the reason is written down.
_APPLICANT_FIELD_ALLOWLIST: frozenset[str] = frozenset()


def is_certification_field(
    field_id: str,
    pdf_field_name: Optional[str] = None,
    kit_id: Optional[str] = None,
) -> bool:
    """True if this field belongs to a third-party certification block.

    Checks the schema field id AND the PDF field name: the client supplies both,
    so a mismatch between them must not open a hole. Either one matching is
    enough to refuse.

    kit_id selects the kit-scoped tier, and is matched loosely (case, spacing,
    separators and a leading "form" are folded -- see _normalize_kit_id).

    An UNRECOGNIZED or missing kit_id applies EVERY kit's rules, not none.
    That direction is deliberate: kit_id comes from the untrusted request body,
    and an exact-match lookup once made this invariant depend on a string's
    spelling -- "I-90" instead of "i-90" silently dropped 27 of the I-90's 37
    protections (fresh-eyes round 3). Unknown now means maximally protected, so
    the failure mode is an over-refusal (a blank field a human completes) rather
    than a filled perjury attestation.
    """
    # The allowlist must exempt on EITHER identifier. Two of the three call
    # sites pass field_id="" and only a widget name (fill_widget and the
    # shared-radio xref path read the name off the real PDF widget), so an
    # id-only allowlist could never exempt anything there -- a carve-out would
    # look applied, pass its test, and still silently refuse the field
    # (fresh-eyes round 1).
    if field_id and field_id in _APPLICANT_FIELD_ALLOWLIST:
        return False
    if pdf_field_name and pdf_field_name in _APPLICANT_FIELD_ALLOWLIST:
        return False

    if field_id and _CERTIFICATION_RE.search(field_id):
        return True
    if pdf_field_name and _CERTIFICATION_RE.search(pdf_field_name):
        return True

    # FAIL SAFE ON AN UNRECOGNIZED KIT. kit_id arrives in the same untrusted
    # request body as everything else, and an exact-match lookup made a legal
    # invariant depend on a string's spelling: kit_id="I-90" instead of "i-90"
    # silently dropped 27 of the I-90's 37 protections, no error, no log
    # (fresh-eyes round 3). Kit onboarding really does produce such variants --
    # _derive_kit_id turns the standard "Form I-90.pdf" download into
    # "form-i-90".
    #
    # So: a kit we RECOGNIZE gets exactly its own rules; a kit we do NOT
    # recognize gets EVERY kit's rules. The unknown-kit case is now the most
    # protective, not the least. That can over-refuse on a future form (an
    # N-400 whose kit_id we do not know yet would have its p6_/p7_ applicant
    # fields refused), and that is the right way round for this invariant: an
    # over-refusal leaves a field blank for a human to complete, while an
    # under-refusal fills a perjury attestation. Add the kit to
    # _KIT_SCOPED_PATTERNS to get precise behavior -- which is exactly the
    # moment someone should be reading that form anyway.
    kit_key = _normalize_kit_id(kit_id)
    if kit_key in _KIT_SCOPED_RE:
        kit_res = (_KIT_SCOPED_RE[kit_key],)
    else:
        kit_res = tuple(_KIT_SCOPED_RE.values())

    for kit_re in kit_res:
        if field_id and kit_re.search(field_id):
            return True
        if pdf_field_name and kit_re.search(pdf_field_name):
            return True
    return False
