"""Batch uid -> label resolution (bd polyglot-pdf-cpsi0).

EXIT CRITERION 2's shared helper: admin_backend/services/identity_labels.py.
Pins:

  1. ONE batched get_users() call for many uids, never one call per uid.
  2. An unknown/deleted uid falls back to the uid itself, never a blank or
     a crash.
  3. A store failure (get_users itself raises) fails soft: every requested
     uid falls back to itself, and the page still renders.
  4. Per-uid TTL caching: a cached label is reused within the TTL window
     without a second Auth call, and a new call is made after clear_cache()
     (proxy for "the TTL expired").
  5. label_for_actor's precedence: a caller-supplied actor_email always
     wins over the batch-resolved map; the batch map is the fallback for a
     legacy row; the raw actor string is the last resort when both are
     absent (a None actor only).

Each test's docstring names the mutation that must turn it red
(docs/standards/testing.md#test-the-tests).

ASCII only.
"""
from __future__ import annotations

import pytest

import admin_backend.services.identity_labels as identity_labels


class _FakeUserRecord:
    def __init__(self, uid, email):
        self.uid = uid
        self.email = email


class _FakeGetUsersResult:
    def __init__(self, users):
        self.users = users
        self.not_found = []


class _FakeAuth:
    """A minimal stand-in for firebase_admin.auth's get_users surface.

    Records every call's identifiers so a test can prove batching (ONE call
    covering every requested uid, not N calls).
    """

    def __init__(self, directory=None):
        # uid -> email
        self.directory = dict(directory or {})
        self.calls = []  # list of the uid lists each get_users() call saw
        self.boom = None

    def UidIdentifier(self, uid):  # noqa: N802 -- mirrors the real SDK's name
        return uid

    def get_users(self, identifiers):
        uids = list(identifiers)
        self.calls.append(uids)
        if self.boom is not None:
            raise self.boom
        found = [
            _FakeUserRecord(uid, self.directory[uid])
            for uid in uids if uid in self.directory
        ]
        return _FakeGetUsersResult(found)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Every test starts with a cold cache -- the module-level _cache dict
    persists across tests in the same process otherwise, and this file's
    fixture uids repeat across tests."""
    identity_labels.clear_cache()
    yield
    identity_labels.clear_cache()


@pytest.fixture
def fake_auth(monkeypatch):
    auth = _FakeAuth({"uid-1": "one@example.com", "uid-2": "two@example.com"})
    monkeypatch.setattr(identity_labels, "_fb_auth", lambda: auth)
    return auth


def test_resolves_a_known_uid_to_its_email(fake_auth):
    """The happy path: a uid Firebase Auth has an account for resolves to
    that account's email.

    Mutation: return uid instead of email in the found branch -- red."""
    result = identity_labels.labels_for_uids({"uid-1"})
    assert result == {"uid-1": "one@example.com"}


def test_an_unknown_uid_falls_back_to_itself(fake_auth):
    """A uid with no Firebase Auth account (deleted, never existed) must not
    blank the row or raise -- it falls back to the uid string itself, the
    plan's own words.

    Mutation: fall back to None instead of the uid -- red (the console
    would render a blank cell instead of the uid it showed before this
    bead)."""
    result = identity_labels.labels_for_uids({"uid-ghost"})
    assert result == {"uid-ghost": "uid-ghost"}


def test_every_input_uid_is_present_in_the_result_even_mixed(fake_auth):
    """A caller can always index the result with any uid it passed in,
    known or unknown, mixed in one call.

    Mutation: return only the FOUND uids (drop the unknown ones from the
    result dict) -- red (a KeyError-shaped gap: "uid-ghost" missing)."""
    result = identity_labels.labels_for_uids({"uid-1", "uid-ghost"})
    assert result == {"uid-1": "one@example.com", "uid-ghost": "uid-ghost"}


def test_one_batched_call_covers_every_distinct_uid(fake_auth):
    """A page with many rows repeating a few uids must cost ONE Auth call
    naming every distinct uid, never one call per uid or per row.

    Mutation: loop and call labels_for_uids per-uid inside a hand-rolled
    helper instead of this batched one -- this test does not catch a
    caller's own mistake, but it DOES catch a regression inside
    labels_for_uids itself that started looping get_users per uid."""
    identity_labels.labels_for_uids({"uid-1", "uid-2", "uid-1", "uid-2"})
    assert len(fake_auth.calls) == 1
    assert set(fake_auth.calls[0]) == {"uid-1", "uid-2"}


def test_a_store_failure_falls_back_every_requested_uid_to_itself(fake_auth):
    """FAIL-SOFT: when get_users itself raises (an unreachable store, a
    transient API error), every uid that was not already cached falls back
    to itself -- the page must still render, never 500.

    Mutation: re-raise the exception instead of catching it -- red (the
    call raises instead of returning a fallback dict)."""
    fake_auth.boom = RuntimeError("Auth API unreachable")
    result = identity_labels.labels_for_uids({"uid-1", "uid-2"})
    assert result == {"uid-1": "uid-1", "uid-2": "uid-2"}


def test_a_cached_label_is_not_refetched_within_the_ttl(fake_auth, monkeypatch):
    """A second call for the SAME uid within the TTL window must not cost a
    second Auth call -- an active console session's several page loads
    should not re-hit Auth for the same staff roster every time.

    Mutation: never populate _cache after a successful resolution -- red
    (the second call also shows up in fake_auth.calls, so len() == 2)."""
    identity_labels.labels_for_uids({"uid-1"})
    assert len(fake_auth.calls) == 1

    identity_labels.labels_for_uids({"uid-1"})
    assert len(fake_auth.calls) == 1, (
        "a second lookup within the TTL window must be served from cache"
    )


def test_a_stale_cache_entry_is_refetched(fake_auth, monkeypatch):
    """Past the TTL, a uid is looked up again -- proven here by faking the
    clock forward past TTL_SECONDS rather than sleeping in a test.

    Mutation: compare with `<=` instead of `<` in the TTL check, or use the
    WRONG uid's cached timestamp -- this test does not distinguish those
    from a correct implementation, but it DOES catch "the cache never
    expires" (a hardcoded True short-circuit)."""
    real_time = identity_labels.time.time
    now = {"t": real_time()}
    monkeypatch.setattr(identity_labels.time, "time", lambda: now["t"])

    identity_labels.labels_for_uids({"uid-1"})
    assert len(fake_auth.calls) == 1

    now["t"] += identity_labels.TTL_SECONDS + 1
    identity_labels.labels_for_uids({"uid-1"})
    assert len(fake_auth.calls) == 2, (
        "a lookup past the TTL window must hit Auth again, not the stale "
        "cache entry"
    )


def test_non_string_and_blank_uids_are_filtered_before_the_auth_call(fake_auth):
    """A caller-side bug (None slipping in, an empty string, or a non-string
    truthy value like an int) must not reach the Auth SDK, which would
    raise on a malformed identifier and cost the caller its WHOLE page
    rather than just one blank label.

    Mutation: relax the filter to `if u` (drop the isinstance(u, str) half)
    -- red on the non-string case specifically: 5 is truthy, so it would
    reach get_users() and appear in fake_auth.calls[0]. A blank-string-only
    mutation would NOT be caught by this alone (`if u` already excludes ""
    and None), which is exactly why this test also exercises a non-string
    truthy value rather than only blanks."""
    result = identity_labels.labels_for_uids({"uid-1", None, "", 5, "uid-2"})
    assert None not in fake_auth.calls[0]
    assert "" not in fake_auth.calls[0]
    assert 5 not in fake_auth.calls[0]
    assert result[None] is None
    assert result[""] == ""
    assert result[5] == 5


# --------------------------------------------------- label_for_actor rule


def test_label_for_actor_prefers_the_stored_email(fake_auth):
    """A row's own stamped actor_email wins over the batch map -- no lookup
    is even needed for such a row (the route callers rely on this to skip
    the uid from the batch entirely, but this function's OWN contract is
    the precedence, independent of what is in `labels`).

    Mutation: check `labels` before `actor_email` -- red (the resolved-from-
    uid map value would win over the row's own stamped email)."""
    result = identity_labels.label_for_actor(
        "uid-1", "stored@example.com", {"uid-1": "looked-up@example.com"})
    assert result == "stored@example.com"


def test_label_for_actor_falls_back_to_the_batch_map(fake_auth):
    """No stored actor_email (a legacy row) -- the batch-resolved map value
    is used.

    Mutation: return the raw actor instead of consulting `labels` -- red."""
    result = identity_labels.label_for_actor(
        "uid-1", None, {"uid-1": "looked-up@example.com"})
    assert result == "looked-up@example.com"


def test_label_for_actor_falls_back_to_the_uid_when_absent_from_the_map(fake_auth):
    """A uid absent from the batch map entirely (should not normally happen
    -- labels_for_uids' own contract returns every requested uid -- but
    label_for_actor must not assume its caller upheld that) falls back to
    the raw uid.

    Mutation: return None instead of `actor` in the dict.get default --
    red."""
    result = identity_labels.label_for_actor("uid-orphan", None, {})
    assert result == "uid-orphan"


def test_label_for_actor_returns_none_for_a_none_actor(fake_auth):
    """A null actor (should not happen -- append_entry refuses a blank
    actor -- but this function must not crash on one) returns None rather
    than a string built from nothing.

    Mutation: return "" instead of None -- red."""
    result = identity_labels.label_for_actor(None, None, {})
    assert result is None
