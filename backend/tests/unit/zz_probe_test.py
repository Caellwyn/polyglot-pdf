from backend.tests.unit.test_kit_lifecycle_statuses import (
    client, _make_kit, _lock, _unlock, _status, _run, HDR, AUTH_HDR, HDR2,
    AUTH_HDR2, ekr)
from backend.services.editor_auth import EditorActor

A_EDITOR = EditorActor(uid="uid-maria", email="maria@example.com", role="editor")
A_EDITOR_B = EditorActor(uid="uid-sam", email="sam@example.com", role="editor")
AN_AUTHOR = EditorActor(uid="uid-josh", email="josh@example.com", role="author")


def test_probe_lock_after_transition_matrix():
    rows = []
    for lockmeta, name in [
        ({"editing_lock": {"role": "editor", "uid": "uid-maria", "label": "m"}}, "person editor maria"),
        ({"editing_lock": {"role": "editor"}}, "LEGACY editor"),
        ({"editing_lock": {"role": "author"}}, "LEGACY author"),
        ({"editing_lock": {"role": "author", "uid": "uid-josh", "label": "j"}}, "person author josh"),
    ]:
        for actor, an in [(A_EDITOR, "maria(ed)"), (A_EDITOR_B, "sam(ed)"), (AN_AUTHOR, "josh(au)")]:
            r = ekr._lock_after_transition(lockmeta, "complete", "draft", actor)
            rows.append((name, an, r))
    for r in rows:
        print("  ", r)


def test_probe_legacy_author_lock_editor_reopen():
    """LEGACY author lock + an EDITOR does the transition. holder='author',
    actor.role='editor' -> mismatch -> None. Fine."""
    pass


def test_probe_refusal_matrix():
    for holder, uid, label in [("editor", None, None), ("editor", "uid-maria", "maria@x"),
                               ("author", None, None), ("author", "uid-josh", "josh@x")]:
        for actor, an in [(A_EDITOR, "maria(ed)"), (A_EDITOR_B, "sam(ed)"), (AN_AUTHOR, "josh(au)")]:
            print("  holder=%s uid=%s actor=%s -> %r" % (
                holder, uid, an, ekr._lock_refusal(holder, actor, uid, label)))
