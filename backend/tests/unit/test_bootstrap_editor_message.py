"""The operator-facing message on the editor grant path (bd polyglot-pdf-onsd6).

I wrote the original message during bd hn0jq: "They must sign in once before a
role can be granted." There is no product path that lets a brand-new person do
that -- the hosted editor's gate is a free-text access code
(AccessCodeGate.tsx), not a Firebase sign-in, so the account cannot create
itself by someone trying to use the editor. The message told an operator to
wait for something that cannot happen, which is worse than telling them
nothing.

The sibling voice tool's identical phrasing is CORRECT and deliberately left
alone: the voice app has real sign-up (AuthContext.tsx:
createUserWithEmailAndPassword / signInWithPopup), so a new person there
genuinely can sign in once. Same words, different truth -- which is why this
pins the EDITOR script specifically rather than banning a phrase repo-wide.
"""
import pathlib
import re

import pytest

pytestmark = pytest.mark.real_editor_auth

_SCRIPT = (pathlib.Path(__file__).resolve().parents[3]
           / "scripts" / "bootstrap_editor_user.py")


def _grant_path_message() -> str:
    """The unknown_email string on the GRANT path, unwrapped.

    Reads the source rather than importing: the module needs firebase_admin at
    import time. Wrapped string literals are joined first -- a single-line
    search missed this exact message when the bead was filed, because it spans
    two lines.
    """
    src = _SCRIPT.read_text(encoding="utf-8")
    # Slice to the GRANT path FIRST. My first version took the last match and
    # got the REVOKE message, which legitimately needs no remedy -- that person
    # already has an account. Anchor on the grant call itself.
    i = src.index("status, detail = stamp_editor_role(")
    flat = re.sub(r'"\s*\n\s*(?:")?', "", src[i:])
    hits = re.findall(r'"unknown_email":\s*\(?\s*f?"([^"]*)"', flat)
    assert hits, "no unknown_email message on the grant path -- shape changed?"
    return hits[0]


def test_the_message_names_a_path_the_operator_can_actually_TAKE():
    """An ALLOWLIST, not a banned word.

    Banning "sign in" is one synonym from defeat, and it would also flag a
    future message that correctly says "...once bd yswp3 ships sign-in".
    Assert instead that the message names at least one way to create the
    account that EXISTS today.
    """
    msg = _grant_path_message()

    remedies = ("Firebase console", "Admin SDK", "gcloud")
    assert any(r.lower() in msg.lower() for r in remedies), (
        "the unknown_email message does not tell the operator how to create "
        "the account. One of {} must appear: {!r}".format(remedies, msg))


def test_the_message_does_not_promise_a_sign_in_flow_that_does_not_exist():
    """The specific falsehood, pinned as the residue check.

    Paired with the allowlist above: the allowlist says the message is USEFUL,
    this says it is not also MISLEADING. Either alone passes a bad message --
    a message can name the console AND still tell someone to wait for a
    sign-in screen.
    """
    msg = _grant_path_message().lower()

    assert "must sign in" not in msg, (
        "the message still tells the operator the person can sign in to "
        "create their account; the hosted editor has no sign-in flow until "
        "bd polyglot-pdf-yswp3 ships one: {!r}".format(msg))


def test_the_editor_and_VOICE_messages_are_allowed_to_differ():
    """Guards against a future sweep 'fixing' the voice script to match.

    The voice app HAS real sign-up, so its identical phrasing is true there.
    A repo-wide search-and-replace would break a correct message; this records
    why the two differ.
    """
    voice = (_SCRIPT.parent / "bootstrap_voice_dev.py").read_text(encoding="utf-8")
    assert "sign in once" in re.sub(r'"\s*\n\s*(?:")?', "", voice), (
        "the voice script's 'sign in once' message is gone. If that was "
        "deliberate, delete this test; if it was a sweep matching the editor "
        "script, it removed a message that is TRUE for the voice app")
