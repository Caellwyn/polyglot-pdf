"""Does the model ASK for the spelling of a name? (bd polyglot-pdf-ku69b)

THE DEFECT. On the live demo the model stopped asking users to spell their name:
it asks for the name, fills what it hears, and the spell-back clip then reads
back a value that may already be wrong. The DTI SI has always said to ask for
the spelling first -- but DTI_SPELLBACK_SI_ADDENDUM is appended LAST and was
pure prohibition ("do NOT read the value back", "stop speaking"), so the model's
final and most specific naming instruction told it only to be silent.

WHAT THIS MEASURES. The model's reply when the user ANSWERS A NAME FIELD WITH A
SPOKEN NAME ONLY (PROBE_SCENARIO=spoken_name, the default), scored for whether it
asks for the SPELLING -- and, separately, whether it FILLED A GUESSED SPELLING,
which is the harmful outcome. This is a behavioral check: a unit test can only
prove the words are in the SI, never that the model obeys them. SI-only fixes
have a poor track record in this repo, so the fix does not count as verified
until this probe shows a rate change.

SCENARIO CHOICE IS LOAD-BEARING. The defect does NOT reproduce on a bare, empty
name field -- there both arms ask ~6/6, which is why `bare_field` is kept only
as a CONTROL. Run the default.

THE A/B IS THE POINT. `fixed` (the shipped SI) vs `prohibition_only` (the SI as
it was BEFORE this bead, reconstructed by stripping the two added sentences).
Without the baseline arm a good `fixed` rate proves nothing -- the model might
have asked anyway. Repo scar: "run the BASELINE arm before blaming a candidate."

SCORING is deliberately crude and printed verbatim so a human can audit every
verdict: ASKED_SPELLING requires a spelling word ("spell", "letter by letter",
etc.) in the model's first question. Read the transcripts, do not trust the
tally alone.

Usage (Vertex is the default -- all live-model work runs on Vertex):
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. \
        backend/.venv/Scripts/python.exe backend/scripts/probe_ask_for_spelling.py
    PROBE_RUNS=8 PROBE_ARM=fixed ... (one arm, more samples)
    PROBE_SCENARIO=bare_field ... (the control; expect NO delta)

MEASURED RESULT (2026-08-12, 2.5-native-audio on Vertex, temperature 0.4),
POOLED over two runs of n=8 -- a single run of 8 is NOT enough to pin the rate
(the two runs gave 1/8 and 3/8 on the baseline arm):
    spoken_name  prohibition_only  asked  4/16 (25%)
                 fixed             asked 15/16 (94%)
    bare_field   both arms         asked  6/6        <- control: no delta

The fixed arm's one miss was a TRUNCATED transcript that was in fact asking, so
94% is a floor. Filling a guessed spelling -- the harmful outcome -- appeared in
only ONE sample across all runs, which is precisely why it reached production:
a clean run is not evidence of absence.

COST: PROBE_RUNS x 2 arms LIVE AUDIO Live-API sessions (response_modalities
AUDIO), not text turns -- budget accordingly before raising PROBE_RUNS. The turn
is non-deterministic: run enough samples to see a RATE, never a single sample.
ASCII only (scar #6).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from backend.config import Settings  # noqa: E402

RUNS = int(os.environ.get("PROBE_RUNS", "5"))
MODEL = os.environ.get("PROBE_MODEL", "gemini-live-2.5-flash-native-audio")

# SCENARIOS. The DEFAULT must be the one that reproduces the defect: the user
# ANSWERING with a spoken name. Getting this wrong is not academic -- an earlier
# revision of this probe defaulted to `bare_field` (a greeting on an empty
# field), which is the scenario the ku69b investigation already REFUTED: both
# arms ask 6/6 there, so the probe reports no delta and its own verdict logic
# prints "THE SI FIX DID NOT HELP" for a fix that measurably does. A probe that
# silently answers the wrong question is worse than no probe.
SCENARIOS = {
    # THE DEFECT (default). The model has asked; the user replies with the
    # NAME only. Does it ask for the spelling, or fill its own guess?
    "spoken_name": {
        "opener": "My last name is Nguyen.",
        "context": (
            "\n\nFORM CONTEXT:\nCurrent field: family_name (Family Name / "
            "Last Name). Nothing is filled yet."
        ),
    },
    # CONTROL, kept deliberately. Both arms ask ~6/6 here. Its job is to show
    # the arms are NOT globally different -- the fix targets one condition.
    # A future run where this one also diverges means something else changed.
    "bare_field": {
        "opener": "Hi, I'm ready to start.",
        "context": (
            "\n\nFORM CONTEXT:\nCurrent field: family_name (Family Name / "
            "Last Name). Nothing is filled yet. Ask the user for this field now."
        ),
    },
}
SCENARIO = os.environ.get("PROBE_SCENARIO", "spoken_name")
if SCENARIO not in SCENARIOS:
    raise SystemExit("unknown PROBE_SCENARIO %r -- pick one of: %s"
                     % (SCENARIO, ", ".join(SCENARIOS)))
USER_OPENER = SCENARIOS[SCENARIO]["opener"]
FORM_CONTEXT = SCENARIOS[SCENARIO]["context"]

# A model that fills its guess instead of asking says something like "I will
# store that as N G U Y E N. Is that correct?" -- the maintainer's verbatim
# report. Scored separately from "did not ask" because it is the HARMFUL
# outcome: the spell-back clip then verifies a spelling nobody gave.
GUESS_MARKERS = ("saved the spelling", "store that as", "accepted with value",
                 "i have saved", "stored as")

SPELLING_MARKERS = (
    "spell", "spelling", "letter by letter", "letter-by-letter",
    "how is it written", "letters",
)


def build_si(arm: str) -> str:
    """Assemble the SI for an arm.

    `fixed` is the SHIPPED text. `prohibition_only` reconstructs the pre-bead
    SI by removing the two sentences this bead added, so the arms differ ONLY
    in those sentences.
    """
    s = Settings()
    si = s.DTI_SYSTEM_INSTRUCTION
    addendum = s.DTI_SPELLBACK_SI_ADDENDUM
    if arm == "fixed":
        return si + addendum + FORM_CONTEXT
    if arm == "prohibition_only":
        # FAIL LOUD IF THE RECONSTRUCTION STOPS WORKING. str.replace() on a
        # missing substring is a silent no-op, so if these constants are ever
        # reworded, the "baseline" would quietly become a copy of `fixed`, the
        # measured delta would collapse to zero, and a future reader would
        # conclude "the fix stopped mattering" when in truth the HARNESS broke.
        # A broken baseline arm is indistinguishable from a refuted fix, so it
        # must crash rather than mislead.
        scope = ("This changes only how a spelling is READ BACK. It does NOT "
                 "change how you ASK: you still ask every person's name by "
                 "asking for its SPELLING up front, every time, exactly as "
                 "instructed above -- never just the name.\n")
        closer = "So the shape of every name field is"
        guard = ("Never accept just the spoken name and fill your best guess "
                 "at its spelling -- if they answer with the name alone, ask "
                 "for the spelling before you fill anything. ")
        for label, needle, haystack in (
            ("addendum scope sentence", scope, addendum),
            ("addendum closing shape line", closer, addendum),
            ("names-block no-guess sentence", guard, si),
        ):
            if needle not in haystack:
                raise SystemExit(
                    "BASELINE ARM IS BROKEN: cannot find the %s in the shipped "
                    "SI, so 'prohibition_only' would NOT reconstruct the "
                    "pre-fix text and the A/B would compare two identical "
                    "arms. The SI was reworded -- update this probe's literals "
                    "to match before trusting any number it prints." % label)
        stripped = addendum.replace(scope, "")
        stripped = stripped[:stripped.find(closer)].rstrip()
        return si.replace(guard, "") + stripped + FORM_CONTEXT
    raise SystemExit("unknown arm: %s" % arm)


def _client():
    from google import genai

    if os.getenv("VERTEXAI", "true").lower() != "false":
        return genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709"),
            location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        )
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


async def one_run(arm: str) -> tuple[bool, str]:
    """Return (asked_for_spelling, the model's first question)."""
    from google import genai  # noqa: F401

    settings = Settings()
    config = {
        "response_modalities": ["AUDIO"],
        "system_instruction": build_si(arm),
        "output_audio_transcription": {},
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {
                    "voice_name": settings.LIVE_VOICE_NAME
                }
            }
        },
    }
    raw_temp = (getattr(settings, "LIVE_TEMPERATURE", "") or "").strip()
    if raw_temp:
        config["temperature"] = float(raw_temp)

    client = _client()
    said: list[str] = []
    async with client.aio.live.connect(model=MODEL, config=config) as session:
        await session.send_client_content(
            turns={"role": "user", "parts": [{"text": USER_OPENER}]},
            turn_complete=True,
        )
        msgs = 0
        async for msg in session.receive():
            msgs += 1
            sc = getattr(msg, "server_content", None)
            if sc is not None:
                out = getattr(sc, "output_transcription", None)
                if out is not None and getattr(out, "text", None):
                    said.append(out.text)
                if getattr(sc, "turn_complete", False):
                    break
            if msgs > 400:
                break

    text = "".join(said).strip()
    low = text.lower()
    asked = any(m in low for m in SPELLING_MARKERS)
    guessed = any(m in low for m in GUESS_MARKERS)
    return asked, guessed, text


async def run_arm(arm: str) -> tuple[int, int]:
    """Return (asked_count, guessed_count) over RUNS samples."""
    print("\n%s\n=== ARM: %s ===\n%s" % ("=" * 70, arm, "=" * 70), flush=True)
    asked_count = guessed_count = 0
    for i in range(RUNS):
        try:
            asked, guessed, text = await one_run(arm)
        except Exception as exc:  # noqa: BLE001
            print("  run %d ERROR: %s" % (i + 1, str(exc)[:160]), flush=True)
            continue
        asked_count += int(asked)
        guessed_count += int(guessed)
        # Print the transcript VERBATIM: the scorer is crude on purpose and
        # every verdict must be human-auditable.
        verdict = "ASKED_SPELLING" if asked else "did NOT ask"
        if guessed:
            verdict += " +FILLED_A_GUESS"
        print("  run %d  %-30s %r" % (i + 1, verdict, text[:150]), flush=True)
    print("  -> %d/%d asked, %d/%d filled a guessed spelling"
          % (asked_count, RUNS, guessed_count, RUNS), flush=True)
    return asked_count, guessed_count


async def main_async() -> int:
    only = os.environ.get("PROBE_ARM")
    arms = [only] if only else ["prohibition_only", "fixed"]
    results = {}
    for arm in arms:
        results[arm] = await run_arm(arm)

    print("\n%s\nSUMMARY (%s, scenario=%s, %d runs/arm)\n%s" % (
        "=" * 70, MODEL, SCENARIO, RUNS, "=" * 70))
    for arm, (asked, guessed) in results.items():
        print("  %-18s asked %d/%d, filled a guess %d/%d"
              % (arm, asked, RUNS, guessed, RUNS))
    if len(results) == 2:
        before = results.get("prohibition_only", (0, 0))[0]
        after = results.get("fixed", (0, 0))[0]
        print("\n  baseline %d/%d -> fixed %d/%d" % (before, RUNS, after, RUNS))
        if SCENARIO == "bare_field":
            print("  NOTE: 'bare_field' is the CONTROL scenario -- both arms "
                  "are expected to ask at a similar rate here, so a flat "
                  "result is the EXPECTED outcome and says nothing about the "
                  "fix. Run PROBE_SCENARIO=spoken_name for the real test.")
        elif after <= before:
            print("  THE SI FIX DID NOT HELP on the defect scenario. Do not "
                  "ship it as a fix on this evidence -- the structural option "
                  "(inject the ask deterministically) is the fallback.")
        else:
            print("  The SI fix improved the ask rate. Confirm the sample is "
                  "big enough to mean it before concluding.")
    return 0


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
