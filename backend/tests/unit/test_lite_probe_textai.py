"""bd polyglot-pdf-u0kcc: the probe recording adapter must capture what the
shipped TextAIGemini path hides -- usage incl. thinking + cached tokens, the
raw reply, transport errors -- and keep concurrent calls' records apart."""

from __future__ import annotations

import asyncio
import types

from backend.scripts.lite_probe_textai import RecordingTextAI, new_record, pct


class _FakeModels:
    def __init__(self, replies):
        self._replies = replies

    async def generate_content(self, model, contents, config=None):
        reply = self._replies[contents[-1]]
        await asyncio.sleep(reply.get("delay", 0))
        if "raise" in reply:
            raise reply["raise"]
        usage = types.SimpleNamespace(
            prompt_token_count=reply["prompt"], cached_content_token_count=reply["cached"],
            candidates_token_count=reply["out"], thoughts_token_count=reply["thoughts"],
            total_token_count=0)
        return types.SimpleNamespace(text=reply["text"], usage_metadata=usage)


def _ai(replies):
    ai = RecordingTextAI("gemini-3.1-flash-lite")
    ai._client = types.SimpleNamespace(aio=types.SimpleNamespace(models=_FakeModels(replies)))
    return ai


def test_records_usage_including_thoughts_and_cache_and_raw():
    ai = _ai({"FIELDS:\n{}": {"prompt": 400, "cached": 300, "out": 20, "thoughts": 7,
                              "text": '{"conflicts": []}'}})

    async def go():
        rec = new_record()
        await ai.validate({"stable_prefix": ["SI"], "fresh_tail": ["FIELDS:\n{}"]})
        return rec
    rec = asyncio.run(go())
    assert rec["usage"] == {"prompt": 400, "cached": 300, "output": 20, "thoughts": 7,
                            "total": 0}
    assert rec["raw"] == '{"conflicts": []}'
    assert rec["error"] is None and rec["latency_s"] is not None


def test_records_transport_error_the_adapter_fail_opens():
    ai = _ai({"T": {"raise": RuntimeError("boom")}})

    async def go():
        rec = new_record()
        verdict = await ai.validate({"stable_prefix": ["SI"], "fresh_tail": ["T"]})
        return rec, verdict
    rec, verdict = asyncio.run(go())
    assert verdict == {"conflicts": []}          # the adapter hid it ...
    assert rec["error"] == "RuntimeError"         # ... the record did not


def test_concurrent_calls_keep_separate_records():
    ai = _ai({
        "A": {"prompt": 1, "cached": 0, "out": 1, "thoughts": 0, "text": "{}", "delay": 0.05},
        "B": {"prompt": 2, "cached": 0, "out": 2, "thoughts": 0, "text": "{}", "delay": 0.0},
    })

    async def one(tail):
        rec = new_record()
        await ai.validate({"stable_prefix": ["SI"], "fresh_tail": [tail]})
        return rec

    async def go():
        return await asyncio.gather(one("A"), one("B"))
    ra, rb = asyncio.run(go())
    assert ra["usage"]["prompt"] == 1 and rb["usage"]["prompt"] == 2


def test_fallback_chain_is_empty():
    # 3.1, not 3.5: 3.5 IS the default fallback, so a 3.5 chain dedups to one
    # model either way and could not catch a restored fallback.
    assert RecordingTextAI("gemini-3.1-flash-lite")._model_chain == ["gemini-3.1-flash-lite"]


def test_pct_nearest_rank():
    assert pct([1, 2, 3, 4], 50) == 2 and pct([1, 2, 3, 4], 100) == 4 and pct([], 90) is None
