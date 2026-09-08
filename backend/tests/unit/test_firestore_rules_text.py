"""Every ADMIN-SDK-ONLY collection carries an explicit client deny block
(bd polyglot-pdf-lo88, generalized to a set by bd polyglot-pdf-li9x0).

firestore.rules has no emulator/rules-unit-testing harness in this repo, so
this is the cheap regression guard: the shipped rules FILE must carry an
explicit deny-all block for each collection no browser may ever touch.
(Whether the DEPLOYED project enforces it is the documented manual verify in
docs/components/auth.md -- rules ship only on a frontend/full deploy or an
explicit firebase deploy --only firestore:rules.)

WHY A SET AND NOT A TEST PER COLLECTION (CLAUDE.md scar #8, enumerate the
set). This file used to assert ONE block, for firms/{firmId}. The next
Admin-SDK-only collection (admin_audit_log) would have arrived as a second
hand-written copy of the same assertion, and the one after that (Epic 2's
credit ledger) as a third -- with the omission of any one of them invisible.
The list below is now the ONE home for "which collections are
Admin-SDK-only", and a later bead extends the LIST rather than the
assertions. Adding a collection to ADMIN_SDK_ONLY_COLLECTIONS without adding
its block to firestore.rules fails HERE.

ASCII only.
"""
import re
from pathlib import Path

import pytest

_RULES = Path(__file__).resolve().parents[3] / "firestore.rules"

# THE SET. Every Firestore collection the Admin SDK owns exclusively -- no
# client-SDK read, no client-SDK write, ever. Each entry is the collection
# name and the wildcard variable its match block uses, because the block's
# text is what this test greps for.
#
# EXTEND THIS LIST, not the assertions, when a bead adds an Admin-SDK-only
# collection. Epic 2 adds the credit ledger and the links/redemption
# collections; Epic 4 adds deployments.
#
# NOT LISTED, deliberately: users/{userId} (a signed-in user reads and writes
# their OWN profile from the browser -- AuthContext.onAuthStateChanged) and
# authorized_emails/{doc} (read UNAUTHENTICATED during email signup, before
# the account exists). Both are client-facing by design; asserting a deny on
# either would pin the opposite of the intended behaviour.
ADMIN_SDK_ONLY_COLLECTIONS = (
    # bd polyglot-pdf-lo88 -- firm profiles + allowed-kits allowlists.
    ("firms", "firmId"),
    # bd polyglot-pdf-li9x0 -- the admin audit log.
    ("admin_audit_log", "rowId"),
    # bd polyglot-pdf-bg313 -- per-channel runtime config (the per-link USD
    # spend ceiling lives here; a client-writable copy would let a browser
    # raise its own).
    ("app_config", "channel"),
    # Epic 2 bead A1 -- the per-firm credit ledger. A NESTED subcollection
    # (firms/{firmId}/ledger/{entryId}): its "collection" entry carries the
    # full path because a parent's deny block does not cascade to a
    # subcollection in Firestore's rules language, so this needs its OWN
    # block and its OWN entry here.
    ("firms/{firmId}/ledger", "entryId"),
    # Epic 2 bead A1 -- kit commercial docs (credit_cost, burn_cap_usd).
    ("kits", "kitId"),
    # Epic 2 bead A1 -- the client-link mint record, demo + staging channels
    # (backend/services/links_store.py, mirroring link_redemptions.py's
    # channel-suffix convention).
    ("links", "jti"),
    ("links_staging", "jti"),
    # Epic 2 bead A1 fold-in: link_redemptions predates this rules-set test
    # (bd polyglot-pdf-ugm6, channel isolation bd polyglot-pdf-3q9qn) and
    # had NO deny block until now, despite being Admin-SDK-only by access
    # pattern since it shipped.
    ("link_redemptions", "jti"),
    ("link_redemptions_staging", "jti"),
)


def _rules_text() -> str:
    return _RULES.read_text(encoding="utf-8")


# Matches ANY `match /<collection>/{<wildcard>} { ... }` block in the file,
# for the both-directions scan (does every full-deny block in the file have
# a listed entry, and vice versa). The collection group allows ONE extra
# `/{wildcard}/segment` hop before the final wildcard, so a NESTED
# subcollection match (firms/{firmId}/ledger/{entryId}) is captured as the
# single string "firms/{firmId}/ledger" rather than being silently invisible
# to this scan (a parent's deny block does not cascade to a subcollection in
# Firestore's rules language, so the nested block needs its own list entry,
# and this pattern is what lets that entry round-trip against the file).
_ANY_MATCH_BLOCK = (
    r"match /([A-Za-z0-9_]+(?:/\{[A-Za-z0-9_]+\}/[A-Za-z0-9_]+)?)"
    r"/\{[A-Za-z0-9_]+\}\s*\{([^}]*)\}"
)


def _deny_block_body(text: str, collection: str, wildcard: str):
    """The body of `match /<collection>/{<wildcard>} { ... }`, or None."""
    pattern = r"match /{}/\{{{}\}}\s*\{{([^}}]*)\}}".format(
        re.escape(collection), re.escape(wildcard))
    found = re.search(pattern, text)
    return found.group(1) if found else None


def _is_full_deny(body: str) -> bool:
    """True only for a COMPLETE client deny.

    Checks the EFFECT, not just the presence of the word "false": a block
    that adds `allow read: if true;` alongside the deny is not a deny, and a
    substring check for `if false` would happily pass it. So the block must
    carry the combined deny AND carry no other allow at all.
    """
    if not re.search(r"allow\s+read,\s*write:\s*if\s+false;", body):
        return False
    allows = re.findall(r"allow\s+[^;]*;", body)
    return len(allows) == 1


@pytest.mark.parametrize("collection,wildcard", ADMIN_SDK_ONLY_COLLECTIONS,
                         ids=[c for c, _ in ADMIN_SDK_ONLY_COLLECTIONS])
def test_admin_sdk_only_collection_has_a_full_client_deny_block(
        collection, wildcard):
    """One parametrization per listed collection. Mutation (per case, not
    once for the file): delete that collection's match block from
    firestore.rules -- that case goes red."""
    text = _rules_text()
    body = _deny_block_body(text, collection, wildcard)
    assert body is not None, (
        "firestore.rules has no `match /{}/{{{}}}` block. {} is "
        "Admin-SDK-only: add an explicit client deny.".format(
            collection, wildcard, collection))
    assert _is_full_deny(body), (
        "the {}/{{{}}} block is not a full client deny. It must be exactly "
        "`allow read, write: if false;` and nothing else; found: {!r}".format(
            collection, wildcard, body.strip()))


def test_the_listed_set_is_the_complete_set_of_deny_blocks():
    """The list and the FILE agree in BOTH directions.

    The parametrized test above catches a listed collection with no block. It
    cannot catch the reverse: a deny block added to firestore.rules for a
    collection nobody added to the list, which then goes un-reviewed here and
    silently drops out of the guard the day someone tidies the rules file.
    Every full-deny block in the file must be accounted for by the list.
    """
    text = _rules_text()
    in_file = {
        m.group(1)
        for m in re.finditer(_ANY_MATCH_BLOCK, text)
        if _is_full_deny(m.group(2))
    }
    listed = {c for c, _ in ADMIN_SDK_ONLY_COLLECTIONS}
    assert in_file == listed, (
        "firestore.rules' full-deny blocks and ADMIN_SDK_ONLY_COLLECTIONS "
        "disagree.\n  denied in the file but not listed: {}\n  listed but "
        "not denied in the file: {}\nBoth directions matter: an unlisted "
        "block sits outside this guard.".format(
            sorted(in_file - listed), sorted(listed - in_file)))


@pytest.mark.parametrize("collection,wildcard", ADMIN_SDK_ONLY_COLLECTIONS,
                         ids=[c for c, _ in ADMIN_SDK_ONLY_COLLECTIONS])
def test_a_listed_collection_without_a_block_is_caught(collection, wildcard):
    """PROVES the set pin fails on a real omission, mechanically, PER ENTRY.

    Exit criterion 3 asks for a test that fails when a LISTED collection
    lacks a deny block. Rather than trusting the assertion shape by
    inspection, this runs the same derivation against rules text with THAT
    entry's block removed and confirms it comes back missing. Parametrized
    over the whole list, not a sample: a regex that happened to match only
    the first collection's block shape would otherwise look proven
    (memory: mutation-verify per parametrization).
    """
    text = _rules_text()
    assert _deny_block_body(text, collection, wildcard) is not None, (
        "fixture assumption broken: {} has no block to remove".format(
            collection))

    stripped = re.sub(
        r"match /{}/\{{{}\}}\s*\{{[^}}]*\}}".format(
            re.escape(collection), re.escape(wildcard)),
        "", text)
    assert _deny_block_body(stripped, collection, wildcard) is None, (
        "removing the {} block did NOT make the derivation report it "
        "missing -- the parametrized test above would not catch a real "
        "omission".format(collection))
    # And the both-directions test would notice too.
    remaining = {
        m.group(1)
        for m in re.finditer(_ANY_MATCH_BLOCK, stripped)
        if _is_full_deny(m.group(2))
    }
    assert collection not in remaining


def test_a_weakened_block_is_caught():
    """A block that still EXISTS but no longer denies must fail too.

    The likelier regression than deletion: someone adds `allow read: if
    request.auth != null;` to a deny block for a console feature. A presence
    check would stay green; _is_full_deny must not. The third assertion is
    the control -- without it, a checker that returned False for everything
    would make the first two pass for the wrong reason.
    """
    assert not _is_full_deny(
        "allow read, write: if false;\nallow read: if request.auth != null;"), (
        "a block carrying an extra allow was treated as a full deny")
    assert not _is_full_deny("allow read: if true;\nallow write: if false;"), (
        "a split read-true/write-false block was treated as a full deny")
    assert _is_full_deny("allow read, write: if false;"), (
        "the real deny shape was rejected -- the checker is too strict and "
        "the tests above would pass for the wrong reason")
