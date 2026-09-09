"""Per-channel runtime config in app_config/{channel} (bd polyglot-pdf-bg313).

The properties that matter, in order:

  1. FALLBACK ORDER on a Firestore failure: last-known-good beats the env
     default. Exit criterion 1 -- lowering the ceiling, then breaking the
     read, must keep the LOWERED value, not silently restore a higher one.
  2. A FRESH process (nothing ever read) with an unreachable store uses the
     env default -- there is no last-known-good to fall back to yet.
  3. The three call sites this bead swaps (link_routes.py's minting flag,
     link_budget.py's ceiling + firm cap) no longer read os.getenv for these
     names anywhere in the shipped sources OUTSIDE this module -- but the
     "env default" in criteria 1+2 above is a LIVE os.getenv read INSIDE
     runtime_config.py itself, not a compiled constant: the deploy scripts'
     LINK_MINTING_ENABLED=true (BACKEND_EXTRA_ENV) must keep working as the
     fallback until an operator seeds app_config/{channel}, or minting
     silently goes dark on the next deploy. CREDITS_ENFORCED -- brand new --
     is never read from env at all, anywhere, including this module.
  4. Unknown keys in a channel doc are ignored, not applied.
  5. The TTL cache bounds how often Firestore is actually read.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.services import runtime_config

REPO_ROOT = Path(__file__).resolve().parents[3]


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return self._data


class _DocRef:
    def __init__(self, store: "_FakeDb", channel: str):
        self._store = store
        self._channel = channel

    def get(self):
        if self._store.read_error is not None:
            raise self._store.read_error
        return _Snap(self._store.docs.get(self._channel))


class _Collection:
    def __init__(self, store: "_FakeDb"):
        self._store = store

    def document(self, channel: str) -> _DocRef:
        return _DocRef(self._store, channel)


class _FakeDb:
    """Stands in for the Firestore client returned by get_db()."""

    def __init__(self, docs=None):
        self.docs = dict(docs or {})
        self.read_error: Exception | None = None

    def collection(self, name: str) -> _Collection:
        assert name == runtime_config.COLLECTION
        return _Collection(self)


@pytest.fixture(autouse=True)
def _clear_cache():
    """The TTL cache and last-known-good map are module-level state -- a
    value one test leaves behind must not leak into the next."""
    runtime_config.clear_cache()
    yield
    runtime_config.clear_cache()


def _patch_db(monkeypatch, db: _FakeDb):
    monkeypatch.setattr("backend.services.auth.get_db", lambda: db)


# ---------------------------------------------------------------------------
# 1 + 2: the fallback order (exit criterion 1)
# ---------------------------------------------------------------------------


def test_a_lowered_ceiling_survives_a_broken_read(monkeypatch):
    """Lower the ceiling, then break the read: the LOWERED value must stick.

    This is exit criterion 1's core claim. Env-first would be wrong here: the
    higher env default reappearing during a Firestore blip would silently
    restore a spend ceiling the operator deliberately lowered.

    Mutation: make _resolve prefer the env default over last-known-good --
    red (would read back 10.0, the env default, instead of 2.0).
    """
    db = _FakeDb({"staging": {"LINK_COST_CEILING_USD": 2.0}})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_cost_ceiling_usd("staging") == 2.0

    # Break the read AND force a refetch by expiring the cache -- otherwise
    # the TTL cache alone would explain the survival, not last-known-good.
    db.read_error = RuntimeError("firestore unreachable")
    runtime_config._cache.pop("staging", None)

    assert runtime_config.link_cost_ceiling_usd("staging") == 2.0


def test_a_fresh_process_with_an_unreachable_store_uses_the_env_default():
    """Nothing was EVER read successfully -> no last-known-good exists yet
    -> the env default is the only fallback available.

    Mutation: change the fallback in _resolve to raise instead of returning
    the env default -- red (this would crash instead of returning 10.0).
    """
    import backend.services.auth as auth_module
    import backend.services.runtime_config as rc

    def _broken_get_db():
        raise RuntimeError("no firestore client configured")

    # Patch at the SOURCE module (backend.services.auth.get_db), matching
    # how _read_channel_doc looks it up (a lazy import of that name).
    orig = auth_module.get_db
    auth_module.get_db = _broken_get_db
    try:
        assert rc.link_cost_ceiling_usd("brand-new-channel") == 10.0
        assert rc.link_firm_cap("brand-new-channel") == 30
        assert rc.minting_enabled("brand-new-channel") is False
        assert rc.credits_enforced("brand-new-channel") is False
    finally:
        auth_module.get_db = orig


def test_store_unreachable_with_env_true_minting_is_enabled(monkeypatch):
    """The deploy-scripts regression this bead fixes: with the store
    unreachable and LINK_MINTING_ENABLED=true in the environment (exactly
    what deploy-staging.sh / deploy-demo.sh set in BACKEND_EXTRA_ENV), a
    fresh process must resolve minting ON -- not fall to the compiled `False`
    constant. A compiled-constant fallback here is precisely what would make
    the deploy scripts' env line inert and silently turn minting off on the
    next deploy of either channel.

    Mutation: replace `_legacy_env_default`'s os.getenv read with the
    compiled `_ENV_DEFAULTS[key]` constant -- red (would read back False
    instead of True).
    """
    import backend.services.auth as auth_module

    monkeypatch.setenv("LINK_MINTING_ENABLED", "true")

    def _broken_get_db():
        raise RuntimeError("no firestore client configured")

    orig = auth_module.get_db
    auth_module.get_db = _broken_get_db
    try:
        assert runtime_config.minting_enabled("brand-new-channel-2") is True
    finally:
        auth_module.get_db = orig


def test_store_unreachable_with_no_env_minting_is_disabled(monkeypatch):
    """Same unreachable-store scenario, but with LINK_MINTING_ENABLED unset --
    the historical fail-safe default (off) must still hold.

    Mutation: hardcode _legacy_env_default to return True for this key --
    red (would read back True instead of False).
    """
    import backend.services.auth as auth_module

    monkeypatch.delenv("LINK_MINTING_ENABLED", raising=False)

    def _broken_get_db():
        raise RuntimeError("no firestore client configured")

    orig = auth_module.get_db
    auth_module.get_db = _broken_get_db
    try:
        assert runtime_config.minting_enabled("brand-new-channel-3") is False
    finally:
        auth_module.get_db = orig


def test_a_lowered_ceiling_survives_a_broken_read_even_with_a_higher_env(
    monkeypatch,
):
    """Exit criterion 1's claim, sharpened: last-known-good must beat the
    LIVE env var too, not just the compiled constant -- a console that
    lowered the ceiling to 2.0 must not see a higher LINK_COST_CEILING_USD
    from the environment reappear during a Firestore blip.

    Mutation: make _resolve fall to _legacy_env_default before
    last-known-good -- red (would read back 20.0, the env value, instead of
    2.0).
    """
    monkeypatch.setenv("LINK_COST_CEILING_USD", "20.0")
    db = _FakeDb({"staging": {"LINK_COST_CEILING_USD": 2.0}})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_cost_ceiling_usd("staging") == 2.0

    db.read_error = RuntimeError("firestore unreachable")
    runtime_config._cache.pop("staging", None)

    assert runtime_config.link_cost_ceiling_usd("staging") == 2.0


def test_a_missing_doc_falls_back_the_same_way(monkeypatch):
    """The channel doc does not exist at all (get_db works, but no doc)."""
    db = _FakeDb({})  # no "staging" key -> snap.exists is False
    _patch_db(monkeypatch, db)

    assert runtime_config.minting_enabled("staging") is False
    assert runtime_config.link_firm_cap("staging") == 30


def test_last_known_good_is_PER_KEY_not_per_channel(monkeypatch):
    """One key surviving a blip must not drag an unrelated key's stale value
    along, or vice versa -- each key falls back independently."""
    db = _FakeDb({"staging": {"LINK_FIRM_CAP": 75}})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_firm_cap("staging") == 75
    # LINK_COST_CEILING_USD was never in the doc -> env default, not a value
    # borrowed from the firm-cap read.
    assert runtime_config.link_cost_ceiling_usd("staging") == 10.0


def test_channels_do_not_share_last_known_good(monkeypatch):
    db = _FakeDb({"demo": {"LINK_COST_CEILING_USD": 3.0}})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_cost_ceiling_usd("demo") == 3.0
    # staging has never been read -> its own env default, not demo's 3.0.
    assert runtime_config.link_cost_ceiling_usd("staging") == 10.0


# ---------------------------------------------------------------------------
# 3: the call-site swap, enumerated from the shipped sources (exit criterion 2)
# ---------------------------------------------------------------------------


# The four keys this bead moves off os.getenv. A name appearing in an
# os.getenv(...) or os.environ[...] call OUTSIDE runtime_config.py (and
# outside this test file, which legitimately quotes the literals) means a
# call site was missed or a new one was added -- exactly what this bead's
# criterion 2 exists to prevent.
_MOVED_KEYS = sorted(runtime_config.RUNTIME_CONFIG_KEYS)

_THIS_FILE = Path(__file__).resolve()


def _iter_source_files():
    for pattern in ("backend/**/*.py", "scripts/**/*.py", "admin_backend/**/*.py"):
        for path in REPO_ROOT.glob(pattern):
            rel_parts = path.relative_to(REPO_ROOT).parts
            if ".venv" in rel_parts or "__pycache__" in rel_parts:
                continue
            if "node_modules" in rel_parts or ".claude" in rel_parts:
                continue
            # This file itself quotes the pattern being searched for (in
            # docstrings and mutation-testing notes) -- excluding it is not
            # weakening the guard, since a REAL regression would land in
            # runtime_config.py or a call-site module, never here.
            if path.resolve() == _THIS_FILE:
                continue
            yield path


_ENV_READ_RE = re.compile(
    r"os\.getenv\(\s*[\"'](\w+)[\"']|os\.environ\[\s*[\"'](\w+)[\"']\]"
    r"|os\.environ\.get\(\s*[\"'](\w+)[\"']"
)


@pytest.mark.parametrize("key", _MOVED_KEYS)
def test_no_shipped_source_reads_this_key_from_env_outside_runtime_config(key):
    """Grep-derived, not a hand-typed pass/fail: a live os.getenv/os.environ
    read of `key` anywhere outside runtime_config.py itself (and the CLI
    script, which legitimately mentions the name in help text/comments but
    performs no env read of it) is exactly the regression criterion 2 guards.

    Mutation: reintroduce `os.getenv("LINK_MINTING_ENABLED", ...)` in
    link_routes.py -- red.
    """
    offenders = []
    for path in _iter_source_files():
        if path.resolve() == (REPO_ROOT / "backend" / "services" / "runtime_config.py").resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for m in _ENV_READ_RE.finditer(text):
            found = next(g for g in m.groups() if g)
            if found == key:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        f"{key} is read from the environment outside runtime_config.py in: "
        f"{offenders} -- bd polyglot-pdf-bg313 moved this key to "
        "app_config/{channel}; no other call site may read it from env."
    )


# The two keys that have NEVER had a pre-bg313 env reader, and must never
# gain one -- CREDITS_ENFORCED (Epic 2 bead A3) and CREDIT_LOW_THRESHOLD
# (Epic 3 bead E3.5, bd polyglot-pdf-bo95a). A frozenset, not a growing
# hand-typed exclusion list of individual `- {...}` subtractions, so the NEXT
# no-env-fallback key added here extends ONE set rather than risking a test
# that still iterates the legacy assertion over a key that was never meant
# to satisfy it (CLAUDE.md scar #8: enumerate the set).
_NO_ENV_FALLBACK_KEYS = frozenset({
    runtime_config.KEY_CREDITS_ENFORCED,
    runtime_config.KEY_CREDIT_LOW_THRESHOLD,
})

_LEGACY_ENV_KEYS = sorted(
    runtime_config.RUNTIME_CONFIG_KEYS - _NO_ENV_FALLBACK_KEYS
)


@pytest.mark.parametrize("key", _LEGACY_ENV_KEYS)
def test_runtime_config_itself_still_reads_the_legacy_env_var(key):
    """The counterpart to the test above: the three legacy keys must NOT
    merely be absent from every OTHER file -- they must be PRESENT as a live
    os.getenv read inside runtime_config.py itself, or the deploy scripts'
    LINK_MINTING_ENABLED=true (and the ceiling/cap env lines) become inert
    the moment Firestore has never been read on this process, silently
    turning link minting off on the next deploy of either channel.

    Mutation: delete the `os.getenv("LINK_MINTING_ENABLED")` line (or its
    ceiling/cap siblings) from _legacy_env_default in runtime_config.py --
    red, because the name would then appear nowhere in the source at all.
    """
    path = REPO_ROOT / "backend" / "services" / "runtime_config.py"
    text = path.read_text(encoding="utf-8")
    found_keys = {
        next(g for g in m.groups() if g) for m in _ENV_READ_RE.finditer(text)
    }
    assert key in found_keys, (
        f"runtime_config.py no longer reads {key} from the environment -- "
        "this is the fallback that keeps the deploy scripts' env line live; "
        "see _legacy_env_default."
    )


@pytest.mark.parametrize("key", sorted(_NO_ENV_FALLBACK_KEYS))
def test_a_no_env_fallback_key_has_no_env_read_anywhere(key):
    """CREDITS_ENFORCED and CREDIT_LOW_THRESHOLD are NEW and were never env
    vars -- neither must ever gain one. Same grep as the offender test above,
    but over EVERY file including runtime_config.py itself: the point is
    that no os.getenv/os.environ call anywhere resolves either key, not
    merely that call sites outside this module are clean.

    Parametrized over the whole set (CLAUDE.md scar #8), not one hand-typed
    case per key: a THIRD no-env-fallback key added later and forgotten here
    would otherwise go unpinned by this test even though it is exactly the
    shape this test exists to catch.

    Mutation: add `os.getenv(key, "false")` inside runtime_config.py -- red.
    """
    offenders = []
    for path in _iter_source_files():
        text = path.read_text(encoding="utf-8")
        for m in _ENV_READ_RE.finditer(text):
            found = next(g for g in m.groups() if g)
            if found == key:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], (
        f"{key} must never be read from the environment (it has no env "
        f"fallback by design), but found a read in: {offenders}"
    )


def test_credits_enforced_defaults_false_and_is_settable(monkeypatch):
    db = _FakeDb({})
    _patch_db(monkeypatch, db)
    assert runtime_config.credits_enforced("staging") is False

    db.docs["staging"] = {"CREDITS_ENFORCED": True}
    runtime_config.clear_cache()
    assert runtime_config.credits_enforced("staging") is True


def test_credit_low_threshold_defaults_10_and_is_settable(monkeypatch):
    db = _FakeDb({})
    _patch_db(monkeypatch, db)
    assert runtime_config.credit_low_threshold("staging") == 10

    db.docs["staging"] = {"CREDIT_LOW_THRESHOLD": 25}
    runtime_config.clear_cache()
    assert runtime_config.credit_low_threshold("staging") == 25


def test_credit_low_threshold_rejects_bool_and_negative(monkeypatch):
    """Same bool-is-an-int-subclass trap LINK_FIRM_CAP already guards, plus
    the sign check -- both fall back to the compiled default (10) rather
    than applying a nonsensical stored value.
    """
    db = _FakeDb({"staging": {"CREDIT_LOW_THRESHOLD": True}})
    _patch_db(monkeypatch, db)
    assert runtime_config.credit_low_threshold("staging") == 10

    db.docs["staging"] = {"CREDIT_LOW_THRESHOLD": -5}
    runtime_config.clear_cache()
    assert runtime_config.credit_low_threshold("staging") == 10


def test_credit_low_threshold_accepts_zero():
    """Zero IS a legitimate threshold (only the exhausted/zero-balance alert
    fires, never the low warning) -- unlike LINK_FIRM_CAP, this is not a
    reject case."""
    assert runtime_config.coerce_value(
        runtime_config.KEY_CREDIT_LOW_THRESHOLD, 0) == 0


# ---------------------------------------------------------------------------
# 4: unknown keys are ignored, not applied
# ---------------------------------------------------------------------------


def test_an_unknown_key_in_the_doc_is_ignored(monkeypatch):
    """A typo'd or retired key in the doc must not silently do nothing while
    LOOKING configured -- and it must not crash the read of the keys that
    ARE recognized."""
    db = _FakeDb({"staging": {
        "LINK_MINTING_ENBALED": True,   # typo -- not a real key
        "LINK_FIRM_CAP": 50,
    }})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_firm_cap("staging") == 50
    # The typo'd key must not have been treated as LINK_MINTING_ENABLED.
    assert runtime_config.minting_enabled("staging") is False


@pytest.mark.parametrize(
    "key,bad_value",
    [
        (runtime_config.KEY_LINK_MINTING_ENABLED, "not-a-bool"),
        (runtime_config.KEY_LINK_COST_CEILING_USD, "free"),
        (runtime_config.KEY_LINK_COST_CEILING_USD, -5.0),
        (runtime_config.KEY_LINK_COST_CEILING_USD, 0),
        (runtime_config.KEY_LINK_FIRM_CAP, "thirty"),
        (runtime_config.KEY_LINK_FIRM_CAP, True),  # bool is an int subclass
        (runtime_config.KEY_CREDITS_ENFORCED, "maybe"),
    ],
)
def test_a_malformed_stored_value_falls_back_rather_than_applying(
    monkeypatch, key, bad_value
):
    """A bad value in Firestore must resolve exactly like an ABSENT key --
    never crash, never silently disable a cap by taking it literally."""
    db = _FakeDb({"staging": {key: bad_value}})
    _patch_db(monkeypatch, db)

    # Whichever getter reads `key`, it must equal the env default, not the
    # bad value nor a coercion crash.
    getter = {
        runtime_config.KEY_LINK_MINTING_ENABLED: runtime_config.minting_enabled,
        runtime_config.KEY_LINK_COST_CEILING_USD: runtime_config.link_cost_ceiling_usd,
        runtime_config.KEY_LINK_FIRM_CAP: runtime_config.link_firm_cap,
        runtime_config.KEY_CREDITS_ENFORCED: runtime_config.credits_enforced,
    }[key]
    assert getter("staging") == runtime_config._ENV_DEFAULTS[key]


# ---------------------------------------------------------------------------
# 5: TTL caching bounds the read rate
# ---------------------------------------------------------------------------


def test_reads_are_cached_within_the_ttl_window(monkeypatch):
    """A second call inside the TTL must not hit the store again."""
    db = _FakeDb({"staging": {"LINK_FIRM_CAP": 10}})
    calls = []
    real_get = _DocRef.get

    def _counting_get(self):
        calls.append(1)
        return real_get(self)

    monkeypatch.setattr(_DocRef, "get", _counting_get)
    _patch_db(monkeypatch, db)

    runtime_config.link_firm_cap("staging")
    runtime_config.link_firm_cap("staging")
    runtime_config.link_firm_cap("staging")

    assert len(calls) == 1


def test_the_cache_expires_after_the_ttl(monkeypatch):
    """After the TTL window, the next read hits the store again and picks up
    a changed value -- this is what makes criterion 3 (flip within the TTL,
    no redeploy) true."""
    db = _FakeDb({"staging": {"LINK_MINTING_ENABLED": False}})
    _patch_db(monkeypatch, db)

    assert runtime_config.minting_enabled("staging") is False

    db.docs["staging"] = {"LINK_MINTING_ENABLED": True}
    # Simulate TTL expiry directly rather than sleeping in a unit test.
    fetched_at, doc = runtime_config._cache["staging"]
    runtime_config._cache["staging"] = (
        fetched_at - runtime_config.TTL_SECONDS - 1, doc
    )

    assert runtime_config.minting_enabled("staging") is True


def test_ttl_is_in_the_documented_30_to_60_second_range():
    """Pins the bead's own stated bound, so a drastic change (e.g. someone
    fat-fingers 4500 instead of 45) is deliberate, not silent."""
    assert 30.0 <= runtime_config.TTL_SECONDS <= 60.0


# ---------------------------------------------------------------------------
# The typed getters actually delegate to _resolve with the right key
# ---------------------------------------------------------------------------


def test_each_getter_reads_its_own_key(monkeypatch):
    db = _FakeDb({"staging": {
        "LINK_MINTING_ENABLED": True,
        "LINK_COST_CEILING_USD": 42.0,
        "LINK_FIRM_CAP": 7,
        "CREDITS_ENFORCED": True,
    }})
    _patch_db(monkeypatch, db)

    assert runtime_config.minting_enabled("staging") is True
    assert runtime_config.link_cost_ceiling_usd("staging") == 42.0
    assert runtime_config.link_firm_cap("staging") == 7
    assert runtime_config.credits_enforced("staging") is True


def test_no_explicit_channel_resolves_via_link_channel(monkeypatch):
    """Callers that omit `channel` get THIS process's channel
    (link_tokens.link_channel()) -- the same resolver the link collections
    already key on."""
    monkeypatch.setenv("LINK_CHANNEL", "staging")
    db = _FakeDb({"staging": {"LINK_FIRM_CAP": 99}})
    _patch_db(monkeypatch, db)

    assert runtime_config.link_firm_cap() == 99
