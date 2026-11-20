"""Simulated-user actor core (bd polyglot-pdf-ctzze, epic polyglot-pdf-ya4vi).

Each turn the actor gets what Gemini just said (text) and returns ONE move
{move, field_key} drawn from closed enums. The HARNESS renders the words
(`render`), never the actor, so every value spoken is a fact-sheet string:
"no off-sheet value" holds by construction.

Pieces:
  - Persona / load_persona: the synthetic fact sheet (answer key).
  - move_schema / validate_decision: the strict structured-output contract.
  - render: move -> spoken text, templates + fact strings only.
  - StubActor: deterministic offline backend (and the fallback).
  - HaikuActor: Claude Haiku 5.5 via the Claude API (anthropic SDK,
    ANTHROPIC_API_KEY), strict JSON output. Deliberately NOT Vertex: Vertex
    bills Google pay-as-you-go, the Claude API uses Anthropic credits.

Offline-importable: the `anthropic` package is imported lazily in
HaikuActor only. ASCII only.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

MOVES = ("answer", "confirm", "reject_and_correct", "spell",
         "repeat_request", "acknowledge")
FIELD_MOVES = frozenset({"answer", "spell", "reject_and_correct"})
NONE_KEY = "none"

HAIKU_MODEL = "claude-haiku-5-5"
# Claude API list price, USD per million tokens, for prompts of 100K tokens or
# fewer.
HAIKU_55_USD_PER_MTOK = {"input": 0.10, "output": 0.50}
# Cache multipliers are the standard Anthropic ratios (read 0.1x, 5-min write
# 1.25x of the input rate); an assumption, not a measured figure.
_CACHE_READ_MULT = 0.10
_CACHE_WRITE_MULT = 1.25

PERSONA_DIR = Path(__file__).resolve().parent / "personas"


# --------------------------------------------------------------------------
# Persona
# --------------------------------------------------------------------------
@dataclass
class Persona:
    persona_id: str
    form: str
    description: str
    behavior: dict
    facts: dict


def load_persona(path) -> Persona:
    """Load and structurally validate a persona JSON. Raises ValueError."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict):
        raise ValueError("persona must be a JSON object")
    for k in ("persona_id", "form", "description", "behavior", "facts"):
        if k not in raw:
            raise ValueError("persona missing key: %s" % k)
    for k in ("persona_id", "form", "description"):
        if not isinstance(raw[k], str) or not raw[k]:
            raise ValueError("persona %s must be a non-empty string" % k)
    if not isinstance(raw["behavior"], dict) or not isinstance(
            raw["behavior"].get("spells_unprompted"), bool):
        raise ValueError("behavior.spells_unprompted must be a bool")
    facts = raw["facts"]
    if not isinstance(facts, dict) or not facts:
        raise ValueError("persona facts must be a non-empty object")
    if NONE_KEY in facts:
        raise ValueError("'none' is reserved and cannot be a fact key")
    for fid, f in facts.items():
        if not isinstance(f, dict):
            raise ValueError("fact %s must be an object" % fid)
        for k in ("value", "label", "answer", "spoken"):
            if not isinstance(f.get(k), str):
                raise ValueError("fact %s: %s must be a string" % (fid, k))
        for k in ("label", "answer", "spoken"):
            if not f[k]:
                raise ValueError("fact %s: %s must be non-empty" % (fid, k))
        kws = f.get("keywords")
        if (not isinstance(kws, list) or not kws
                or not all(isinstance(x, str) and x for x in kws)):
            raise ValueError("fact %s: keywords must be a non-empty list of strings" % fid)
        if not isinstance(f.get("spellable"), bool):
            raise ValueError("fact %s: spellable must be a bool" % fid)
        if f["spellable"] and not (isinstance(f.get("spell"), str) and f["spell"]):
            raise ValueError("fact %s: spellable fact needs a 'spell' string" % fid)
        if not f["spellable"] and "spell" in f:
            raise ValueError("fact %s: 'spell' only allowed when spellable" % fid)
    return Persona(raw["persona_id"], raw["form"], raw["description"],
                   raw["behavior"], facts)


def load_default_persona() -> Persona:
    return load_persona(PERSONA_DIR / "w7_ana_nospell.json")


# --------------------------------------------------------------------------
# Strict schema + validation
# --------------------------------------------------------------------------
def move_schema(facts: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            "move": {"type": "string", "enum": list(MOVES)},
            "field_key": {"type": "string", "enum": list(facts) + [NONE_KEY]},
        },
        "required": ["move", "field_key"],
        "additionalProperties": False,
    }


def validate_decision(obj: Any, facts: dict) -> tuple[bool, str]:
    """Return (ok, reason). Rejects non-enum values, extra/missing keys, and a
    field-requiring move paired with 'none'."""
    if not isinstance(obj, dict):
        return False, "not an object"
    if set(obj) != {"move", "field_key"}:
        return False, "keys must be exactly move, field_key"
    move, key = obj["move"], obj["field_key"]
    if not isinstance(move, str) or move not in MOVES:
        return False, "move not in enum"
    if not isinstance(key, str) or (key != NONE_KEY and key not in facts):
        return False, "field_key not in enum"
    if move in FIELD_MOVES and key == NONE_KEY:
        return False, "move %s requires a field" % move
    return True, ""


# --------------------------------------------------------------------------
# Renderer
# --------------------------------------------------------------------------
@dataclass
class Rendered:
    text: str
    move: str
    field_key: str
    values_spoken: list = field(default_factory=list)


_TEMPLATES = {
    "answer": ["{answer}", "Sure. {answer}", "Okay, {answer}", "Yes. {answer}"],
    "spell": ["It's spelled {spell}.", "Sure, that is {spell}.",
              "Okay. {spell}.", "Letter by letter: {spell}."],
    "confirm": ["Yes, that's right.", "Yes, that is correct.",
                "Correct, thank you.", "Yes, that's right, thanks."],
    "reject_and_correct": ["No, that's not right. {answer}",
                           "No, that is wrong. {answer}",
                           "Sorry, no. {answer}"],
    "repeat_request": ["Sorry, could you say that again?",
                       "Sorry, I didn't catch that. Can you repeat it?",
                       "Could you repeat that, please?"],
    "acknowledge": ["Okay.", "Okay, thank you.", "Alright.", "Got it, thanks."],
}
# Spelling a non-spellable fact degrades to the spoken value, so a bad
# (but schema-valid) decision still cannot produce an off-sheet string.
_SPOKEN_TEMPLATES = ["It is {spoken}.", "That is {spoken}."]


def render(move: str, field_key: str, persona: Persona,
           rng: random.Random) -> Rendered:
    if move not in MOVES:
        raise ValueError("unknown move: %r" % (move,))
    facts = persona.facts
    if move in FIELD_MOVES:
        if field_key not in facts:
            raise ValueError("move %s needs a fact key, got %r" % (move, field_key))
        f = facts[field_key]
        if move == "spell":
            if f.get("spellable"):
                tpl = rng.choice(_TEMPLATES["spell"])
                return Rendered(tpl.format(spell=f["spell"]), move, field_key,
                                [f["spell"]])
            tpl = rng.choice(_SPOKEN_TEMPLATES)
            return Rendered(tpl.format(spoken=f["spoken"]), move, field_key,
                            [f["spoken"]])
        tpl = rng.choice(_TEMPLATES[move])
        return Rendered(tpl.format(answer=f["answer"]), move, field_key,
                        [f["answer"]])
    tpl = rng.choice(_TEMPLATES[move])
    return Rendered(tpl, move, NONE_KEY, [])


# --------------------------------------------------------------------------
# Decision + shared text helpers
# --------------------------------------------------------------------------
@dataclass
class Decision:
    move: str
    field_key: str
    raw: Any = None
    valid: bool = True
    fallback_used: bool = False
    usage: dict = field(default_factory=lambda: {
        "input": 0, "output": 0, "cache_read": 0, "cache_creation": 0})
    latency_s: float = 0.0


def history_entry(model_text: str, decision: Decision) -> dict:
    """The record a caller appends to `history` after each turn."""
    return {"model_text": model_text, "move": decision.move,
            "field_key": decision.field_key}


def _tokens(text: str) -> list:
    """Lowercase alnum tokens; runs of 2+ single-char tokens (spelled letters
    or spoken digits) are merged into one token: 'A - N - A' -> 'ana'."""
    toks = re.findall(r"[a-z0-9]+", (text or "").lower())
    out: list = []
    run: list = []
    for t in toks:
        if len(t) == 1:
            run.append(t)
            continue
        if run:
            out.append("".join(run))
            run = []
        out.append(t)
    if run:
        out.append("".join(run))
    return out


def _contains_seq(hay: list, needle: list) -> bool:
    n = len(needle)
    if n == 0:
        return False
    return any(hay[i:i + n] == needle for i in range(len(hay) - n + 1))


def _kw_score(text_tokens: list, keyword: str) -> int:
    kt = _tokens(keyword)
    return len(keyword) if _contains_seq(text_tokens, kt) else 0


_SPELL_ASK = re.compile(
    r"\b(spell|spelling|letter by letter|letters)\b", re.I)
_SPELLED_RUN = re.compile(r"\b[A-Za-z](?:\s*[-,.]?\s+[A-Za-z]\b){2,}")
_READBACK = re.compile(
    r"(is that (correct|right|accurate)|is this (correct|right)|"
    r"did i (get|have|hear) (that|it|this)|do i have that|have i got that|"
    r"did i catch that|please confirm|can you confirm|could you confirm|"
    r"to confirm|let me confirm|just to confirm|\bconfirm\b|"
    r"is that what you said|am i right|correct\?|right\?)", re.I)


def _asks_to_spell(text: str) -> bool:
    return bool(_SPELL_ASK.search(text)) and not (
        _SPELLED_RUN.search(text) and _READBACK.search(text))


# --------------------------------------------------------------------------
# StubActor
# --------------------------------------------------------------------------
class StubActor:
    """Deterministic rule-based backend; needs no network. Stateless: the
    'current field' comes from `history`."""

    def __init__(self, persona: Persona):
        self.persona = persona

    def _best_keyword_field(self, text: str) -> Optional[str]:
        tt = _tokens(text)
        best, best_score = None, 0
        for fid, f in self.persona.facts.items():
            s = max([_kw_score(tt, k) for k in f["keywords"]] + [0])
            if s > best_score:
                best, best_score = fid, s
        return best

    def _last_answered(self, history: list) -> Optional[str]:
        for h in reversed(history or []):
            if h.get("move") in FIELD_MOVES and h.get("field_key") in self.persona.facts:
                return h["field_key"]
        return None

    def _value_in_text(self, fid: str, text: str) -> bool:
        f = self.persona.facts[fid]
        tt = _tokens(text)
        cands = [f["spoken"], f["value"]]
        if f.get("spell"):
            cands.append(f["spell"])
        return any(_contains_seq(tt, _tokens(c)) for c in cands if c)

    def _decide_sync(self, model_text: str, history: list) -> tuple[str, str]:
        text = model_text or ""
        kw = self._best_keyword_field(text)
        last = self._last_answered(history)
        if _asks_to_spell(text):
            cur = kw or last
            if cur:
                return "spell", cur
        if _READBACK.search(text):
            cur = kw or last
            if cur:
                if self._value_in_text(cur, text):
                    return "confirm", NONE_KEY
                return "reject_and_correct", cur
        if kw:
            return "answer", kw
        return "acknowledge", NONE_KEY

    async def decide(self, model_text: str, history: list) -> Decision:
        t0 = time.perf_counter()
        move, key = self._decide_sync(model_text, history)
        return Decision(move=move, field_key=key,
                        raw={"move": move, "field_key": key},
                        latency_s=time.perf_counter() - t0)


# --------------------------------------------------------------------------
# HaikuActor
# --------------------------------------------------------------------------
_MOVE_HELP = {
    "answer": "give the fact the interviewer just asked about (needs field_key)",
    "spell": "spell that fact letter by letter -- ONLY when asked to spell (needs field_key)",
    "confirm": "say yes to a read-back that matches the fact (field_key none)",
    "reject_and_correct": "say no and give the right answer when a read-back does not match the fact (needs field_key)",
    "repeat_request": "ask the interviewer to say that again (field_key none)",
    "acknowledge": "neutral okay for disclaimers and transitions (field_key none)",
}


def build_system_prompt(persona: Persona) -> str:
    lines = [
        "You play a simulated applicant in a voice interview. You do NOT write "
        "any words: you only choose ONE move and, where needed, WHICH fact it "
        "is about. A harness speaks the words from the fact sheet.",
        "",
        "Persona: " + persona.description,
        "",
        "Fact sheet (field_key | label | how the user says it | spellable):",
    ]
    for fid, f in persona.facts.items():
        lines.append("- %s | %s | %s | %s" % (
            fid, f["label"], f["spoken"], "yes" if f["spellable"] else "no"))
    lines += ["", "Moves:"]
    for m in MOVES:
        lines.append("- %s: %s" % (m, _MOVE_HELP[m]))
    lines += [
        "",
        "Rules:",
        "- Answer only what was asked; pick the single fact the interviewer is asking about.",
    ]
    if not persona.behavior.get("spells_unprompted", False):
        lines.append("- Never spell unless the interviewer asks you to spell.")
    lines += [
        "- Use confirm only when a read-back matches the fact exactly.",
        "- Use reject_and_correct when a read-back does not match the fact.",
        "- Use repeat_request when the text is cut off or unintelligible.",
        "- Use acknowledge for disclaimers, greetings and transitions.",
        "- Reply with JSON only: {\"move\": ..., \"field_key\": ...}; use field_key \"none\" for moves that need no field.",
    ]
    return "\n".join(lines)


def estimate_cost_usd(usage: dict) -> float:
    rate_in = HAIKU_55_USD_PER_MTOK["input"]
    rate_out = HAIKU_55_USD_PER_MTOK["output"]
    return (usage.get("input", 0) * rate_in
            + usage.get("cache_read", 0) * rate_in * _CACHE_READ_MULT
            + usage.get("cache_creation", 0) * rate_in * _CACHE_WRITE_MULT
            + usage.get("output", 0) * rate_out) / 1_000_000


def _usage_dict(u: Any) -> dict:
    def g(name: str) -> int:
        v = getattr(u, name, 0) if u is not None else 0
        return int(v) if isinstance(v, (int, float)) else 0
    return {"input": g("input_tokens"), "output": g("output_tokens"),
            "cache_read": g("cache_read_input_tokens"),
            "cache_creation": g("cache_creation_input_tokens")}


def _nonempty(text) -> str:
    """The Claude API rejects empty / whitespace-only user content (400). A
    turn with no model speech (e.g. a silent tool turn) is '(silence)'."""
    return text if isinstance(text, str) and text.strip() else "(silence)"


class HaikuActor:
    """Claude Haiku 5.5 actor with strict JSON output, via the Claude API.

    Uses anthropic.Anthropic() with ANTHROPIC_API_KEY. A missing key raises at
    construction rather than letting every turn silently fall back to the stub.
    """

    def __init__(self, persona: Persona, client: Any = None,
                 max_tokens: int = 200):
        if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("HaikuActor needs ANTHROPIC_API_KEY in the "
                               "environment")
        self.persona = persona
        self._client = client
        self.max_tokens = max_tokens
        self.stub = StubActor(persona)
        self.schema = move_schema(persona.facts)
        self.system_text = build_system_prompt(persona)

    def _get_client(self):
        if self._client is None:
            import anthropic  # lazy: keeps the module offline-importable
            self._client = anthropic.Anthropic()
        return self._client

    def build_request(self, model_text: str, history: list) -> dict:
        msgs: list = []
        for h in history or []:
            msgs.append({"role": "user",
                         "content": _nonempty(h["model_text"])})
            msgs.append({"role": "assistant", "content": json.dumps(
                {"move": h["move"], "field_key": h["field_key"]})})
        msgs.append({"role": "user", "content": _nonempty(model_text)})
        return {
            "model": HAIKU_MODEL,
            "max_tokens": self.max_tokens,
            "system": [{"type": "text", "text": self.system_text,
                        "cache_control": {"type": "ephemeral"}}],
            "messages": msgs,
            "output_config": {"format": {"type": "json_schema",
                                         "schema": self.schema},
                              "effort": "low"},
            "thinking": {"type": "disabled"},
        }

    async def _fallback(self, model_text: str, history: list, raw: Any,
                        usage: dict, t0: float) -> Decision:
        d = await self.stub.decide(model_text, history)
        d.raw = raw
        d.valid = False
        d.fallback_used = True
        d.usage = usage
        d.latency_s = time.perf_counter() - t0
        return d

    async def decide(self, model_text: str, history: list) -> Decision:
        t0 = time.perf_counter()
        usage = {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0}
        try:
            req = self.build_request(model_text, history)
            client = self._get_client()
            resp = await asyncio.to_thread(client.messages.create, **req)
            if asyncio.iscoroutine(resp):
                resp = await resp
            usage = _usage_dict(getattr(resp, "usage", None))
            if getattr(resp, "stop_reason", None) == "refusal":
                return await self._fallback(model_text, history,
                                            {"error": "refusal"}, usage, t0)
            text = next((b.text for b in resp.content
                         if getattr(b, "type", None) == "text"), None)
            if text is None:
                return await self._fallback(model_text, history,
                                            {"error": "no text block"}, usage, t0)
            try:
                obj = json.loads(text)
            except ValueError:
                return await self._fallback(model_text, history,
                                            {"error": "bad json", "text": text},
                                            usage, t0)
            ok, why = validate_decision(obj, self.persona.facts)
            if not ok:
                return await self._fallback(model_text, history,
                                            {"error": why, "obj": obj}, usage, t0)
            return Decision(move=obj["move"], field_key=obj["field_key"],
                            raw=obj, valid=True, fallback_used=False,
                            usage=usage, latency_s=time.perf_counter() - t0)
        except Exception as exc:  # noqa: BLE001 -- any backend failure falls back
            return await self._fallback(
                model_text, history,
                {"error": "%s: %s" % (type(exc).__name__, exc)}, usage, t0)

