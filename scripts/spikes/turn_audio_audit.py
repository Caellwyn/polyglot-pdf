"""Per-turn output-audio audit for the Live-model measurement harness.

Stdlib-only (imported by measure_form_session_costs.py, unit-testable without the
backend). Flags the developer-reported gemini-3.8-live audio defects so every
benchmark run reports them instead of silently pricing a broken session:

  silent_turn            the model's OUTPUT transcript has text but the turn
                         carried < SILENT_AUDIO_MS of audio (transcript present,
                         audio empty). Only observable when output transcription
                         is requested (--audit-transcripts / --debug).
  missing_completion     a turn produced audio but no completion boundary
                         (server turn_complete / generation_complete) arrived
                         before the next user turn or the end of the run.
  runaway_audio          one turn streamed more than RUNAWAY_AUDIO_MS of audio.
  silent_after_tool      within one user exchange (activity_end -> next
                         activity_end) the model called a tool and then spoke
                         < SILENT_AUDIO_MS of audio after its last call -- the
                         "ended its turn silently after the tool result" shape.
                         Tools whose contract IS silence (name_spellback: the
                         client plays a TTS clip) are exempt.

Event sources (wired by the harness): output audio bytes the backend forwards
to the client, output transcript chunks, tool-callback invocations, the
adapter's generation-boundary edges (turn_complete / interrupted /
session_close), and the driver's own activity_end. Audio is PCM16 mono at
AUDIO_OUT_RATE, so duration = bytes / (2 * rate).

No transcript TEXT is retained -- only character counts -- so the audit is safe
to write into the normal (non-debug) .meta.json.
"""
from __future__ import annotations

SILENT_AUDIO_MS = 300.0
RUNAWAY_AUDIO_MS = 20_000.0
DEFAULT_AUDIO_RATE = 24_000
# Tools after which the model is SUPPOSED to stay silent.
SILENT_OK_TOOLS = frozenset({"name_spellback"})
# Generation-boundary reasons that close a turn. "buffer_cap" is a dump-buffer
# housekeeping edge, not a generation boundary.
_CLOSE_REASONS = frozenset({"turn_complete", "interrupted", "session_close"})


class TurnAudioAudit:
    def __init__(self, audio_rate: int = DEFAULT_AUDIO_RATE):
        self._bytes_per_ms = 2.0 * audio_rate / 1000.0
        self.turns: list[dict] = []
        self.exchanges: list[dict] = []
        self._turn: dict | None = None
        self._exchange = self._new_exchange(start_ts=None)
        self.empty_boundaries = 0

    # -- event intake -------------------------------------------------------
    def audio(self, nbytes: int, ts: float) -> None:
        ms = nbytes / self._bytes_per_ms
        t = self._open_turn(ts)
        t["audio_ms"] += ms
        ex = self._exchange
        ex["audio_ms"] += ms
        if ex["tool_calls"]:
            ex["audio_ms_after_last_tool"] += ms

    def transcript(self, text: str, ts: float) -> None:
        n = len(text or "")
        if not n:
            return
        self._open_turn(ts)["transcript_chars"] += n
        self._exchange["transcript_chars"] += n

    def tool_call(self, name: str, ts: float) -> None:
        self._open_turn(ts)["tool_calls"].append(name)
        ex = self._exchange
        ex["tool_calls"].append(name)
        ex["audio_ms_after_last_tool"] = 0.0

    def boundary(self, reason: str, ts: float) -> None:
        if reason not in _CLOSE_REASONS:
            return
        if self._turn is None:
            # generation_complete and turn_complete both fire the edge; the
            # second one finds nothing open. Counted, never flagged.
            self.empty_boundaries += 1
            return
        self._close_turn(ts, reason)

    def user_turn_end(self, ts: float) -> None:
        if self._turn is not None:
            self._close_turn(ts, "next_user_turn")
        self._close_exchange(ts)
        self._exchange = self._new_exchange(start_ts=ts)

    def finalize(self, ts: float) -> dict:
        if self._turn is not None:
            self._close_turn(ts, "run_end")
        self._close_exchange(ts)
        self._exchange = self._new_exchange(start_ts=ts)
        return self.summary()

    # -- classification -----------------------------------------------------
    @staticmethod
    def classify_turn(t: dict) -> dict:
        audio = t["audio_ms"]
        return {
            "silent_turn": t["transcript_chars"] > 0 and audio < SILENT_AUDIO_MS,
            "missing_completion": (audio > 0
                                   and t["end_reason"] not in _CLOSE_REASONS),
            "runaway_audio": audio > RUNAWAY_AUDIO_MS,
        }

    @staticmethod
    def classify_exchange(ex: dict) -> dict:
        calls = ex["tool_calls"]
        silent_after_tool = bool(
            calls
            and calls[-1] not in SILENT_OK_TOOLS
            and ex["audio_ms_after_last_tool"] < SILENT_AUDIO_MS)
        return {"silent_after_tool": silent_after_tool}

    def summary(self) -> dict:
        def _count(rows, key):
            return sum(1 for r in rows if r["flags"][key])
        return {
            "thresholds": {"silent_audio_ms": SILENT_AUDIO_MS,
                           "runaway_audio_ms": RUNAWAY_AUDIO_MS,
                           "silent_ok_tools": sorted(SILENT_OK_TOOLS)},
            "turns": len(self.turns),
            "exchanges": len(self.exchanges),
            "transcript_observed": any(t["transcript_chars"] for t in self.turns),
            "silent_turn": _count(self.turns, "silent_turn"),
            "missing_completion": _count(self.turns, "missing_completion"),
            "runaway_audio": _count(self.turns, "runaway_audio"),
            "silent_after_tool": _count(self.exchanges, "silent_after_tool"),
            "empty_boundaries": self.empty_boundaries,
            "max_turn_audio_ms": round(max((t["audio_ms"] for t in self.turns),
                                           default=0.0), 1),
        }

    # -- internals ----------------------------------------------------------
    @staticmethod
    def _new_exchange(start_ts):
        return {"start_ts": start_ts, "audio_ms": 0.0, "transcript_chars": 0,
                "tool_calls": [], "audio_ms_after_last_tool": 0.0}

    def _open_turn(self, ts: float) -> dict:
        if self._turn is None:
            self._turn = {"start_ts": ts, "end_ts": None, "end_reason": None,
                          "audio_ms": 0.0, "transcript_chars": 0,
                          "tool_calls": []}
        return self._turn

    def _close_turn(self, ts: float, reason: str) -> None:
        t = self._turn
        self._turn = None
        t["end_ts"] = ts
        t["end_reason"] = reason
        # True only when the server's own completion edge (turn_complete /
        # generation_complete) closed the turn -- not a barge-in, session
        # close, the next user turn, or the end of the run.
        t["turn_complete"] = reason == "turn_complete"
        t["flags"] = self.classify_turn(t)  # classify on the UNROUNDED value
        t["audio_ms"] = round(t["audio_ms"], 1)
        self.turns.append(t)

    def _close_exchange(self, ts: float) -> None:
        ex = self._exchange
        if ex["start_ts"] is None and not (ex["audio_ms"] or ex["tool_calls"]
                                           or ex["transcript_chars"]):
            return
        ex["end_ts"] = ts
        ex["flags"] = self.classify_exchange(ex)  # classify on UNROUNDED values
        ex["audio_ms"] = round(ex["audio_ms"], 1)
        ex["audio_ms_after_last_tool"] = round(ex["audio_ms_after_last_tool"], 1)
        self.exchanges.append(ex)
