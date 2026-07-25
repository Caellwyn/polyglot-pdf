"""Connect-and-probe: does the production native-audio Live model accept
AudioTranscriptionConfig.language_codes? (bd polyglot-pdf-y25o)

The field is SDK-2.8-present but was never endpoint-verified
(docs/genai_docs/live-api-best-practices.md). This probe mirrors the deploy
config exactly (production tool declarations + the adapter's real
_build_live_config, per docs/standards/testing.md deploy-fidelity rule) and
adds the ONE experimental delta under test: language_codes on the input/output
transcription blocks.

Arms (run serially):
  1. hint-on  : language_codes=["es-US"] on both transcription configs.
  2. hint-off : control -- only runs if arm 1 fails, to distinguish "endpoint
                rejects the hint" from "endpoint/model is broken right now".

Success = session connects, a text turn gets audio back, no 1007/1011 close.
Cost: <= 2 connects x 1 short text turn on the default-tier native-audio model
(well under $0.05; Gate-2 trivial-pilot allowance).

Vertex only (ADC + GOOGLE_CLOUD_PROJECT), per all-live-model-work-runs-on-vertex.

Usage: backend/.venv/Scripts/python.exe scripts/spikes/probe_transcription_lang_codes.py
"""
import asyncio
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend.config import get_settings  # noqa: E402


async def _wait_for_audio(session, timeout: float = 30.0):
    async def _reader():
        async for chunk in session.receive():
            sc = getattr(chunk, "server_content", None)
            if sc is None:
                continue
            mt = getattr(sc, "model_turn", None)
            if mt is None:
                continue
            for part in getattr(mt, "parts", []) or []:
                inline = getattr(part, "inline_data", None)
                data = getattr(inline, "data", None) if inline is not None else None
                if data:
                    return data
        return None

    try:
        return await asyncio.wait_for(_reader(), timeout=timeout)
    except asyncio.TimeoutError:
        return None


async def run_arm(label: str, codes, speech_language_code: str | None = None) -> bool:
    settings = get_settings()
    model = os.getenv("GEMINI_LIVE_MODEL", settings.MODEL_NATIVE)
    api_key = os.getenv("GEMINI_API_KEY")

    adapter = LiveAIGemini(api_key=api_key, model=model, vertexai=settings.VERTEXAI)
    adapter._function_declarations = settings.TOOL_DECLARATIONS
    adapter._system_instruction = (
        "You are a diagnostics bot. When contacted, say the word ACK."
    )
    # Deploy shape: production requests input transcription (liveness) always;
    # output transcription when transcripts are on. Enable both so the probe
    # exercises language_codes on BOTH blocks.
    adapter._enable_transcripts = True
    adapter.set_transcription_language_codes(codes)

    # The flag gates application in _build_live_config; force it on for the
    # probe regardless of env.
    settings.TRANSCRIPTION_LANGUAGE_HINT_ENABLED = True

    config = adapter._build_live_config(settings)
    # bd polyglot-pdf-m1lg: second endpoint-verification delta -- Google's Live
    # docs recommend the API-level speech_config.language_code match the user's
    # language (framed for the cascaded model; native-audio acceptance is
    # unverified). The adapter never sets speech_config today, so this is a
    # pure additive delta on the deploy-shaped config.
    if speech_language_code:
        config["speech_config"] = {"language_code": speech_language_code}
    print(f"[{label}] model={model} vertexai={settings.VERTEXAI}")
    print(f"[{label}] input_audio_transcription={config.get('input_audio_transcription')}")
    print(f"[{label}] output_audio_transcription={config.get('output_audio_transcription')}")
    print(f"[{label}] speech_config={config.get('speech_config')}")

    try:
        async with adapter.connect(model=model, config=config) as session:
            await adapter._send_text_turn(session._session, "Please reply.")
            audio = await _wait_for_audio(session)
            if audio:
                print(f"[{label}] RESULT: OK -- connected, audio reply received ({len(audio)} bytes)")
                return True
            print(f"[{label}] RESULT: NO-AUDIO -- connected but no audio within timeout")
            return False
    except Exception as e:
        print(f"[{label}] RESULT: FAIL -- {type(e).__name__}: {e}")
        traceback.print_exc()
        return False


def _arm_from_argv(argv) -> str | None:
    """The --arm value, accepting BOTH the space form (--arm speech-lang) and
    the equals form (--arm=speech-lang) (bd kcia note 4: the old substring
    check silently ran the DEFAULT arm for the equals form). Returns None
    when --arm is absent."""
    for i, tok in enumerate(argv):
        if tok == "--arm" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--arm="):
            return tok.split("=", 1)[1]
    return None


async def main():
    # bd m1lg: --arm speech-lang probes speech_config.language_code instead of
    # the (already-verified, y25o) transcription language_codes arm.
    arm = _arm_from_argv(sys.argv)
    if arm is not None and arm not in ("speech-lang", "hint"):
        print(f"ERROR: unknown --arm {arm!r} (expected 'speech-lang' or "
              "'hint'/omit for the default transcription-hint arm)")
        sys.exit(2)
    if arm == "speech-lang":
        ok = await run_arm("speech-lang-on", ["es-US"], speech_language_code="es-US")
        if not ok:
            print("speech-lang-on failed; running control (no speech_config) to isolate...")
            control = await run_arm("speech-lang-off", ["es-US"])
            print(f"CONTROL (no speech_config): "
                  f"{'OK -- the endpoint REJECTS speech_config.language_code' if control else 'ALSO FAILED (endpoint/model issue, not the field)'}")
            sys.exit(1)
        print("VERDICT: speech_config.language_code ACCEPTED by the endpoint "
              "(speech-lang-on arm clean)")
        return

    ok = await run_arm("hint-on", ["es-US"])
    if not ok:
        print("hint-on failed; running hint-off control to isolate the cause...")
        control = await run_arm("hint-off", None)
        print(f"CONTROL (no hint): {'OK' if control else 'ALSO FAILED (endpoint/model issue, not the hint)'}")
        sys.exit(1)
    print("VERDICT: language_codes ACCEPTED by the endpoint (hint-on arm clean)")


if __name__ == "__main__":
    asyncio.run(main())
