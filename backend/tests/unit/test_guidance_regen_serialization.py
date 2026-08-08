"""regenerate-guidance concurrency (bd polyglot-pdf-gnb0).

Two races the route had, both silent (a wrong or empty rewrite, never an
error), and both pinned here:

1. LOST UPDATE. The route does load_schema -> mutate across a minutes-long
   model call -> put_schema with no version check. Two overlapping requests
   both read the pre-call schema, and the second write clobbered the first --
   so a per-field rewrite of field A vanished when a rewrite of field B landed
   after it. Fixed by serializing the whole read/enrich/apply/write window
   (_get_guidance_lock), the same guard the extract route already used.

2. SHARED CLI SCRATCH FILE. scripts/bakeoff/llm_providers keyed its
   CLI-transport scratch path on os.getpid(). The backend is ONE process, so
   two concurrent run_json_claude_cli calls used the SAME path: A's `finally`
   deleted the file B was about to read, or B's CLI overwrote A's JSON. Fixed
   by making the path unique per CALL (uuid4).

ASCII only.
"""
import asyncio
import importlib.util
import json
import threading
from pathlib import Path

import pytest

# The route-level fixtures live in the editor-routes suite; import them here
# rather than forking a second app/store/fake-enrich harness that could drift
# from the one the other tests pin behavior against. pytest collects fixtures
# by NAME from the module namespace, so these imports are the wiring.
from backend.tests.unit.test_editor_kit_routes import (  # noqa: F401
    _kit_with_booklet,
    client,
    guidance_enrich,
)

_REPO = Path(__file__).resolve().parents[3]


def _app_of(test_client):
    """The FastAPI app behind the shared `client` fixture's TestClient."""
    return test_client.app


# --------------------------------------------------------------------------- #
# Criterion 2 -- the scratch path is per CALL, not per process
# --------------------------------------------------------------------------- #

def _load_llm_providers():
    """Load scripts/bakeoff/llm_providers.py by path (it is not a package)."""
    spec = importlib.util.spec_from_file_location(
        "llm_providers_under_test",
        str(_REPO / "scripts" / "bakeoff" / "llm_providers.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_two_concurrent_cli_calls_in_one_pid_do_not_share_a_scratch_file():
    """THE PID BUG, driven directly (criterion 2).

    Two run_json_claude_cli calls on one interpreter, overlapping. The fake
    CLI writes each call's OWN payload to whatever path that call named, and
    the assertion is that each call reads back its own -- which is only true
    when the two paths differ. Under the old os.getpid() naming both calls
    named one path and the payloads collided.
    """
    llm = _load_llm_providers()
    # _parse_helpers lazily imports arm_llm_native (a sibling bakeoff script
    # not on sys.path here). The transport under test only needs "parse the
    # JSON the model wrote", so stub it rather than dragging in the extractor.
    llm._parse_helpers = lambda: (json.loads, lambda x: x)
    seen_paths = []
    barrier = threading.Barrier(2, timeout=10)

    def fake_run(cmd, input=None, capture_output=None, text=None,
                 encoding=None, timeout=None):
        # The scratch path is the last line of the wrapped prompt's path line.
        path = input.split("to this exact file path:\n  ")[1].split("\n")[0]
        seen_paths.append(path)
        payload = {"marker": Path(path).name}
        # Both calls hold their file open at the same moment: this is what
        # makes the collision reachable rather than incidentally serialized.
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        barrier.wait()

        class _P:
            returncode = 0
            stdout = json.dumps({"is_error": False, "result": "WROTE OK",
                                 "usage": {}, "total_cost_usd": 0})
            stderr = ""
        return _P()

    llm.subprocess.run = fake_run  # module-local monkeypatch (loaded by path)

    results = {}

    def call(tag):
        obj, _tok = llm.run_json_claude_cli(f"prompt {tag}", "sonnet")
        results[tag] = obj

    threads = [threading.Thread(target=call, args=(t,)) for t in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(seen_paths) == 2
    assert seen_paths[0] != seen_paths[1], (
        "both calls used ONE scratch path -- the pid-keyed collision is back")
    # Each call read back ITS OWN payload (the collision's real symptom was a
    # call reading the other's JSON, or an empty/missing file).
    assert len(results) == 2
    for tag, obj in results.items():
        assert obj["marker"] in {Path(p).name for p in seen_paths}
    assert results["a"] != results["b"]
    # ...and neither call left its scratch file behind.
    for p in seen_paths:
        assert not Path(p).exists()


def test_scratch_paths_are_unique_across_calls_and_carry_the_kind():
    llm = _load_llm_providers()
    made = [llm._cli_scratch_path("/tmp/out", "json") for _ in range(50)]
    assert len(set(made)) == 50
    assert all("_cli_json_" in Path(p).name for p in made)
    assert llm._cli_scratch_path("/tmp/out", "schema").find("_cli_schema_") != -1


# --------------------------------------------------------------------------- #
# Criterion 1 -- overlapping regenerates serialize, both writes intact
# --------------------------------------------------------------------------- #

def test_overlapping_regenerates_serialize_and_keep_both_writes(
    client, guidance_enrich, monkeypatch
):
    """THE LOST UPDATE, driven through the real route on ONE event loop
    (criterion 1).

    Request A rewrites field "a", request B rewrites field "b", and A's model
    call is held open until B is demonstrably inside the route -- so without
    the lock both read the same pre-call schema and whichever writes last
    erases the other. With it, B queues at the lock, re-reads the store after
    A's write, and both rewrites survive in the stored kit.

    WHY httpx/ASGITransport instead of the TestClient the sibling tests use:
    TestClient runs EACH request on its own fresh event loop (measured -- two
    requests reported two different loop ids), so the per-loop lock map hands
    them two different locks and they can never contend. That is a harness
    artifact, not the deployed shape: uvicorn serves the whole process on ONE
    loop. Driving both requests as concurrent tasks on a single loop is what
    reproduces the race the fix is for -- on the TestClient this test passes
    with the lock REMOVED, which would make it vacuous.
    """
    import backend.routes.editor_kit_routes as ekr
    _c, _store, root = client          # the fixture's app wiring + tmp store
    _kit_with_booklet(root, "race")

    entered = asyncio.Event()
    release = asyncio.Event()
    b_started = asyncio.Event()
    real_enrich = guidance_enrich.enrich_schema
    loop_holder = {}

    def slow_enrich(schema, booklet, form_name, model, chunk_size):
        # Keyed on the FIELD, not arrival order: a first-caller-wins flag is
        # itself racy and could hold B instead, making the test nondeterministic.
        am_first = [f.get("id") for f in schema.get("fields", [])] == ["a"]
        if not am_first:
            # Only reachable in the UNFIXED world (B gets here while A holds
            # the release); with the lock B is still parked and this never
            # runs before the poll above sees `locked()`.
            loop_holder["loop"].call_soon_threadsafe(b_started.set)
        out = real_enrich(schema, booklet, form_name, model, chunk_size)
        if am_first:
            # This runs in anyio's worker THREAD; signal/wait on the loop.
            loop = loop_holder["loop"]
            loop.call_soon_threadsafe(entered.set)
            fut = asyncio.run_coroutine_threadsafe(
                asyncio.wait_for(release.wait(), timeout=10), loop)
            fut.result(timeout=15)
        return out

    monkeypatch.setattr(guidance_enrich, "enrich_schema", slow_enrich)

    async def drive():
        import httpx
        loop_holder["loop"] = asyncio.get_running_loop()
        transport = httpx.ASGITransport(app=_app_of(_c))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as ac:
            async def post(field_id):
                return await ac.post(
                    "/api/editor/kits/race/regenerate-guidance",
                    headers={"X-Editor-Token": "auth-tok"},
                    json={"fieldIds": [field_id]},
                )

            ta = asyncio.create_task(post("a"))
            await asyncio.wait_for(entered.wait(), timeout=10)
            tb = asyncio.create_task(post("b"))
            # Wait until B is DEMONSTRABLY past its own load_schema -- polled
            # on real progress, never a wall-clock sleep (a fixed sleep is a
            # guess that goes false on a loaded runner, and the whole point of
            # this test is that B got far enough to read the schema).
            #   fixed   -> B parks on the lock, which reports itself locked;
            #   unfixed -> B sails through and reaches enrich, which the
            #              b_started event records.
            # Either way the wait ends on an OBSERVED state, so the race is
            # set up identically in both worlds -- which is what makes the
            # mutation (lock removed) genuinely redden this test.
            async def b_is_in_flight() -> bool:
                return b_started.is_set() or ekr._get_guidance_lock().locked()

            for _ in range(200):                    # <= 2s, exits on the event
                if await b_is_in_flight():
                    break
                await asyncio.sleep(0.01)
            else:
                raise AssertionError("request B never entered the route")
            release.set()
            return await asyncio.gather(ta, tb)

    ra, rb = asyncio.run(drive())
    assert ra.status_code == 200, ra.text
    assert rb.status_code == 200, rb.text

    stored = json.loads(
        (root / "race" / "schema.json").read_text(encoding="utf-8"))
    help_by_id = {f["id"]: (f.get("help") or {}).get("instructions")
                  for f in stored["fields"]}
    # BOTH writes intact: the lost update kept only the later one.
    assert help_by_id["a"] == "new guidance for a", (
        f"field a's rewrite was lost: {help_by_id}")
    assert help_by_id["b"] == "new guidance for b", (
        f"field b's rewrite was lost: {help_by_id}")


def test_the_guidance_lock_is_per_event_loop():
    """The onboard lock's trap, inherited: an asyncio.Lock binds to a loop on a
    CONTENDED acquire, so a module-level Lock raises RuntimeError the first
    time two requests contend on a SECOND loop (TestClient runs each request on
    its own). The per-loop map removes that."""
    import backend.routes.editor_kit_routes as ekr

    async def grab():
        return ekr._get_guidance_lock()

    a1 = asyncio.run(grab())
    a2 = asyncio.run(grab())
    assert a1 is not a2, "one lock was reused across event loops"

    async def twice():
        return ekr._get_guidance_lock() is ekr._get_guidance_lock()

    assert asyncio.run(twice()), "the same loop must reuse ONE lock"
