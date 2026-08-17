"""Mechanical pin for the firms/** client deny block (bd polyglot-pdf-lo88).

firestore.rules has no emulator/rules-unit-testing harness in this repo, so
this is the cheap regression guard for exit criterion 2: the shipped rules
FILE must carry an explicit deny-all block for firms/{firmId}. (Whether the
DEPLOYED project enforces it is the documented manual verify in
docs/components/auth.md -- rules ship only on a frontend/full deploy or an
explicit firebase deploy --only firestore:rules.)

Mutation: delete the match /firms/ block from firestore.rules -- red.

ASCII only.
"""
import re
from pathlib import Path

_RULES = Path(__file__).resolve().parents[3] / "firestore.rules"


def test_firms_collection_has_explicit_client_deny_block():
    text = _RULES.read_text(encoding="utf-8")
    block = re.search(r"match /firms/\{firmId\}\s*\{([^}]*)\}", text)
    assert block, (
        "firestore.rules must carry an explicit `match /firms/{firmId}` "
        "block (Admin-SDK-only collection, bd polyglot-pdf-lo88)"
    )
    assert re.search(r"allow read, write:\s*if false;", block.group(1)), (
        "the firms/{firmId} block must be a full client deny: "
        "`allow read, write: if false;`"
    )
