"""Connect-verify a Live prebuilt voice name BEFORE deploying it.

WHY THIS EXISTS. An unaccepted LIVE_VOICE_NAME is not a soft degrade: Vertex
closes the session with `1007 Invalid voice name` at connect, so a bad value
breaks EVERY session, and the first symptom is the demo being dead. The repo
carried a "VERIFY BEFORE DEPLOY" warning for this with no way to verify -- the
2026-07-30 probe (bd polyglot-pdf-e1x9) accepted 11 voices but never recorded
which 11, and was never committed.

It is a 30-second local check, not a deploy-time risk: local and demo talk to
the SAME Vertex Live endpoint, so a name that connects here connects there
(maintainer's correction, 2026-08-11 -- an earlier revision of this work wrongly
called it unverifiable before deploy).

USAGE (from repo root, backend venv):
  # check the currently-configured voice
  VERTEXAI=true backend/.venv/Scripts/python.exe backend/scripts/probe_voice_name.py
  # check specific candidates before swapping
  VERTEXAI=true backend/.venv/Scripts/python.exe backend/scripts/probe_voice_name.py \
      Algieba Schedar Achernar

Exit code is 0 only if EVERY probed voice was accepted, so this can gate a
deploy. A run always probes a deliberately-bogus name too: if that were ever
ACCEPTED the probe is not discriminating and its verdicts mean nothing.

Cost: negligible -- each probe opens and immediately closes a session with no
turn. ASCII only (scar #6).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..")))

from backend.config import Settings  # noqa: E402

# If this is ever ACCEPTED, the probe is broken -- see CONTROL below.
CONTROL_VOICE = "NotARealVoiceXYZ"


async def probe_voice(voice: str, model: str) -> tuple[bool, str]:
    """Open and immediately close a Live session using `voice`."""
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=os.getenv("GOOGLE_CLOUD_PROJECT", "polyglot-demo-aa709"),
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
    )
    config = {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {"prebuilt_voice_config": {"voice_name": voice}}
        },
    }
    try:
        async with client.aio.live.connect(model=model, config=config):
            return True, "session opened"
    except Exception as exc:  # noqa: BLE001 -- any failure is a rejection
        return False, str(exc)[:140]


async def main_async(voices: list[str]) -> int:
    settings = Settings()
    model = settings.MODEL_NATIVE
    if not voices:
        voices = [settings.LIVE_VOICE_NAME]
        print("no voices given -- probing the CONFIGURED LIVE_VOICE_NAME")
    print("model: %s\n" % model)

    failures = []
    for voice in voices:
        ok, detail = await probe_voice(voice, model)
        print("%-18s %s  %s" % (voice, "ACCEPTED" if ok else "REJECTED", detail))
        if not ok:
            failures.append(voice)

    # CONTROL: a probe that accepts everything proves nothing. Run the bogus
    # name last so its rejection witnesses that the ACCEPTEDs above are real.
    ok, detail = await probe_voice(CONTROL_VOICE, model)
    print("\ncontrol %-10s %s  %s"
          % (CONTROL_VOICE, "ACCEPTED" if ok else "REJECTED", detail))
    if ok:
        print("\nPROBE IS NOT DISCRIMINATING -- a bogus voice name was accepted, "
              "so the verdicts above are meaningless. Do not deploy on this.")
        return 3

    if failures:
        print("\nDO NOT DEPLOY: %s would 1007 at connect and break EVERY "
              "session." % ", ".join(failures))
        return 1
    print("\nAll probed voices connect cleanly on this tier.")
    return 0


def main() -> int:
    return asyncio.run(main_async(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
