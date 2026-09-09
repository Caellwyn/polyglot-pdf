"""E2E probe: the validator -> switch_to_field correction rail (bd polyglot-pdf-oiok).

Exit criterion 1 of the correction-rail bead: prove the FULL chain works end to
end against REAL services, not a mock of any one link:

  seeded contradiction (contract-2 fields payload)
    -> REAL flash-lite validator verdict (backend.services.validator_service)
    -> REAL steer composer (FormFillingService._compose_validator_steer)
    -> injected into a REAL live Gemini session running the PRODUCTION
       continuous-DTI system instruction + PRODUCTION tool declarations
    -> the model's tool calls are captured and asserted against the expected
       sequence:
         switch_to_field (on a flagged field)
           -> [we ack with the field's current value + guidance]
         [user gives a verbal correction]
           -> update_form_fields (the corrected value)
           -> confirm_field

This is a BEHAVIORAL probe, not a unit test: it drives a real
`client.aio.live.connect()` session (Vertex only -- see _client()) with the
production SI/tools/config, so a run costs real Gemini spend. The orchestrator
runs it live; this script is only WRITTEN + wired here (do not invoke without
--dry-run in this environment).

MODELED ON backend/scripts/probe_confirm_field.py: reuses its _drain-one-turn
loop (collect tool_call function_calls, stop at turn_complete, wall-clock
bounded) and _send_tool_responses (echo the call id, per bd polyglot-pdf-0ux)
pattern. Two structural differences from that probe:
  1. VERTEX ONLY (maintainer directive; see _client(), mirrors
     probe_secretary_recall.py's client construction).
  2. The system instruction, tool declarations, and Live connect config are
     built by calling the REAL production code paths (ai_context.build_form_context,
     FormFillingService._build_tool_declarations, LiveAIGemini._build_live_config)
     rather than a hand-rolled config -- deploy-fidelity rule
     (docs/standards/testing.md): a probe that hand-rolls its own SI/tool/config
     shape can pass while production (a different shape) fails, or vice versa.

THE SEEDED CONTRADICTION: the West-Virginia-state / Iowa-ZIP mailing-address
pair, the canonical case from backend/scripts/g1_corpus.py's zip_state class,
built over REAL I-90 field ids (form-kits/i-90/schema.json). ~8 filled fields
total (name, A-number, DOB, and the 5-field mailing-address cluster including
the contradiction pair) so the validator sees a realistic-shaped payload, not
just the two conflicting fields in isolation.

THE VALIDATOR VERDICT is REAL (backend.services.validator_service.ValidatorService
over backend.adapters.text_ai_gemini.TextAIGemini, flash-lite on Vertex) -- the
probe ABORTS if the verdict reports no conflict (that would be a validator-recall
failure, not a rail-wiring failure, and this probe is not the place to
characterize recall; see probe_g1_contradiction_recall.py for that).

W3 (bd polyglot-pdf-pr3i) note -- the FINDING-DRIVEN drain: production reaches this
same rail via the client queue + drain_findings round-trip
(handle_drain_findings), NOT inline in handle_validation_windows (which is
report-only since W3). This probe still exercises the rail FAITHFULLY because the
steer composer + inject path it drives (_compose_validator_steer ->
send_client_content) is the SAME code handle_drain_findings runs -- W3 changed WHO
composes the steer (the drain handler, off a client round-trip) and WHEN, not the
composer or the rail behavior. So a green rail here proves the drain path's live
behavior; the report-only enqueue + drain round-trip itself is covered
deterministically by the FE tests (webFormConnection.drainfindings.test.ts) +
the drain service tests (test_drain_findings.py).

THE STEER is REAL (FormFillingService._compose_validator_steer), byte-identical
to what production sends, and is injected into the Live session the same way
LiveAIGemini.send_client_content -> _send_text_turn does for the 2.5 family:
session.send_client_content(turns={"parts": [{"text": message}]}, turn_complete=True)
(backend/adapters/live_ai_gemini.py:1136-1139 -- the 2.5 branch; the probe pins
a 2.5-family model, see MODEL below, so the 3.1 send_realtime_input branch is
never exercised here).

TOOL-RESPONSE ACK SHAPES mirror the production callback_handler.py handlers
byte-for-byte (the probe does not invoke the WS-bound RequestCoordinator
round-trip -- there is no live frontend -- so it fabricates the ack a
frontend WOULD have returned, matching what those handlers thread onto the
Gemini-visible tool response):
  - switch_to_field success: {"success": True, "message": ...,
    "current_value": <if present>, "field_guidance": <if schema supplied>}
    (backend/services/callback_handler.py _handle_switch_to_field_tool,
    the `response` dict built at line ~1175-1179).
  - update_form_fields success: {"success": True, "applied_fields": [...],
    "message": "Fields updated successfully."}
    (callback_handler.py _build_update_fields_response, the else-branch,
    line ~1367-1371).
  - confirm_field success: {"success": True, "field_confirmed": <id>,
    "next_field_hint": None, "message": "Field '<id>' confirmed. ..."}
    (callback_handler.py _handle_confirm_field_tool, the `response` dict at
    line ~906-911).

Usage (Vertex is the ONLY supported path -- maintainer directive, bd memory
all-live-model-work-runs-on-vertex):
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_validator_rail.py
    GOOGLE_CLOUD_PROJECT=... PYTHONPATH=. python backend/scripts/probe_validator_rail.py --trials 3
    # wiring-only check, no network (stubs the client + validator + Live session):
    PYTHONPATH=. python backend/scripts/probe_validator_rail.py --dry-run

ASCII only (CLAUDE.md scar #6).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import sys

# Allow running as a module from repo root (PYTHONPATH=.) or directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.config import MODEL_NATIVE_STANDARD, MODEL_NATIVE_STANDARD_VERTEX, Settings  # noqa: E402
from backend.services.ai_context import build_form_context  # noqa: E402
from backend.services.form_filling_service import FormFillingService  # noqa: E402
from backend.services.validator_service import ValidatorService  # noqa: E402

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "scripts", "spikes", "data",
)

MAX_CONNECT_RETRIES = 2  # cap retries per connect; a repeat 1011/1008 aborts the trial.

# ---------------------------------------------------------------------------
# The seeded contradiction: West Virginia mailing state + an Iowa ZIP code,
# the canonical zip_state case from g1_corpus.py, over REAL I-90 field ids.
# ---------------------------------------------------------------------------

ALIEN_NUM = ("p1_line1_aliennumber", "Alien Registration Number. (A. Number). ")
FAMILY_NAME = ("p1_line3a_familyname", "Family Name (Last Name)")
GIVEN_NAME = ("p1_line3b_givenname", "Given Name (First Name). ")
DOB = ("p1_line9_dateofbirth", "as 2-digit Month, 2-digit Day, and 4-digit Year. ")
M_STREET = ("p1_line6b_streetnumbername", "Street Numberand Name")
M_CITY = ("p1_line6d_cityortown", "City or Town")
M_STATE = ("p1_line6e_state", "Select State from List of States")
M_ZIP = ("p1_line6f_zipcode", "ZIP Code")
M_COUNTRY = ("p1_line6i_country", "Country")

# The contradiction pair: West Virginia state token + a real Iowa ZIP (the
# g1_corpus.py doc example, case zip_state_0).
CONTRA_STATE_VALUE = "west_virginia"  # option token for "West Virginia"
CONTRA_ZIP_VALUE = "50301"  # a real Iowa ZIP code

CORRECTED_STATE_VALUE = "iowa"  # what the simulated user corrects it to
CORRECTED_STATE_LABEL = "Iowa"


def _f(field_id: str, name: str, value: str, steered: bool = False) -> dict:
    return {"field_id": field_id, "name": name, "value": value, "steered": steered}


def build_seeded_fields() -> list:
    """The contract-2 client-state payload (docs/standards/validation-delegation.md
    contract 2): ~8 filled fields including the West-Virginia/Iowa-ZIP
    contradiction pair, so the validator sees a realistic-shaped state rather
    than just the two conflicting fields in isolation."""
    return [
        _f(*ALIEN_NUM, "A123456789"),
        _f(*FAMILY_NAME, "Rivera"),
        _f(*GIVEN_NAME, "Elena"),
        _f(*DOB, "03/14/1990"),
        _f(*M_STREET, "123 Main St"),
        _f(*M_CITY, "Springfield"),
        _f(*M_STATE, CONTRA_STATE_VALUE),
        _f(*M_ZIP, CONTRA_ZIP_VALUE),
        _f(*M_COUNTRY, "United States"),
    ]


def build_i90_schema() -> dict:
    """Load the real I-90 schema (form-kits/i-90/schema.json), the same file
    probe_g1_contradiction_recall.py / probe_secretary_recall.py read."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    path = os.path.join(root, "form-kits", "i-90", "schema.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def field_schema_by_id(schema: dict, field_id: str) -> dict:
    for f in schema.get("fields", []):
        if f.get("id") == field_id:
            return f
    return {}


def field_current_value(field_id: str, fields: list) -> str:
    for f in fields:
        if f.get("field_id") == field_id:
            return f.get("value", "")
    return ""


def field_name(field_id: str, fields: list) -> str:
    for f in fields:
        if f.get("field_id") == field_id:
            return f.get("name", field_id)
    return field_id


# ---------------------------------------------------------------------------
# Client construction -- VERTEX ONLY (maintainer directive; bd memory
# all-live-model-work-runs-on-vertex). Mirrors probe_secretary_recall.py's
# _client(): VERTEXAI=true (default) -> ADC + GOOGLE_CLOUD_PROJECT; a
# deliberate AI Studio run requires VERTEXAI=false + GEMINI_API_KEY.
# ---------------------------------------------------------------------------

def _client():
    from google import genai

    if os.environ.get("VERTEXAI", "true").lower() == "true":
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            print(
                "VERTEXAI mode but GOOGLE_CLOUD_PROJECT unset; relying on ADC's "
                "default project (gcloud config get-value project).",
                flush=True,
            )
        return genai.Client(
            vertexai=True,
            project=project,
            location=os.environ.get("VERTEX_LOCATION", "us-central1"),
        )
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("VERTEXAI=false but NO KEY in env GEMINI_API_KEY", flush=True)
        sys.exit(2)
    return genai.Client(api_key=key)


def _live_model(vertexai: bool) -> str:
    """The LIVE model id differs between Vertex and AI Studio (backend/config.py).
    This probe is Vertex-only by default; the AI-Studio id is kept only for the
    explicit VERTEXAI=false override path."""
    return MODEL_NATIVE_STANDARD_VERTEX if vertexai else MODEL_NATIVE_STANDARD


def _is_vertex() -> bool:
    return os.environ.get("VERTEXAI", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Production SI + tools + Live connect config -- built by calling the REAL
# code paths, not a hand-rolled shape (deploy-fidelity rule,
# docs/standards/testing.md).
# ---------------------------------------------------------------------------

def build_production_si(settings: Settings) -> str:
    """The continuous-DTI system instruction, exactly as production builds it
    (backend.services.ai_context.build_form_context). Continuous-DTI defaults
    are ON (Settings.USE_DTI default True since bd 7872), and build_form_context
    reads get_settings() internally for the USE_DTI branch -- so as long as the
    process env has not overridden USE_DTI=false, this returns the same
    DTI_SYSTEM_INSTRUCTION constant production sends. schema/current_values are
    passed through but are IGNORED by the DTI branch (it is fully static --
    see config.py's DTI_SYSTEM_INSTRUCTION docstring); passing the real schema
    keeps this call shaped like every other build_form_context call site."""
    schema = build_i90_schema()
    return build_form_context(
        schema=schema,
        current_values={},
        fill_language="English",
        section_number=1,
        total_sections=1,
        section_label="Part 1 - Information About You",
    )


def build_production_tools(settings: Settings) -> list:
    """Tool declarations exactly as production builds them
    (FormFillingService._build_tool_declarations): continuous mode (the
    default) drops switch_section. live_ai=None is fine -- this call needs
    only the tool-declaration builder, not a live session."""
    svc = FormFillingService(live_ai=None, settings=settings)
    return svc._build_tool_declarations()


def build_live_config(settings: Settings, system_instruction: str, tools: list,
                       model_name: str) -> dict:
    """The Live connect config exactly as the production adapter sends it
    (LiveAIGemini._build_live_config), including the thinking_budget=0 cost
    guard for the 2.5 family and output/input transcription so we can log
    what the model SAID (native-audio emits AUDIO, not TEXT -- bd memory
    native-audio-models-not-cascade)."""
    from backend.adapters.live_ai_gemini import LiveAIGemini

    adapter = LiveAIGemini.__new__(LiveAIGemini)
    adapter._function_declarations = tools
    adapter._system_instruction = system_instruction
    adapter._model_name = model_name
    adapter._enable_transcripts = True
    adapter._on_user_activity = None
    import structlog
    adapter._log = structlog.get_logger().bind(probe="validator_rail")
    return adapter._build_live_config(settings)


# ---------------------------------------------------------------------------
# Drain / tool-response plumbing -- mirrors probe_confirm_field.py.
# ---------------------------------------------------------------------------

def _report_fc(path: str, fc) -> dict:
    """Pull id/name/args off a function_call object. PII: args can carry field
    VALUES (e.g. update_form_fields {value: ...}); print only name/id/field_id/
    value-length, never the value itself (mirrors probe_confirm_field.py)."""
    args = getattr(fc, "args", None)
    args_dict = dict(args) if args else {}
    info = {
        "path": path,
        "name": getattr(fc, "name", None),
        "id": getattr(fc, "id", None),
        "args": args_dict,
    }
    value = args_dict.get("value")
    value_len = len(str(value)) if value is not None else 0
    print(
        "  [tool_call] path={path} name={name!r} id={id!r} field_id={fid!r} "
        "field={field!r} value_len={vlen}".format(
            path=path, name=info["name"], id=info["id"],
            fid=args_dict.get("field_id"), field=args_dict.get("field"),
            vlen=value_len,
        ),
        flush=True,
    )
    return info


async def _drain(session, label: str, max_msgs: int = 400, turn_timeout: float = 30.0) -> dict:
    """Drain one turn: collect tool calls + transcript text, stop at
    turn_complete. Bounded by wall-clock turn_timeout (a native-audio turn does
    not always deliver a clean turn_complete after a tool response). Mirrors
    probe_confirm_field.py._drain, plus it also captures the OUTPUT
    TRANSCRIPTION TEXT itself (not just a length) -- this probe's whole point
    is to show the read-back happened, so unlike probe_confirm_field's PII-safe
    char-count-only logging, we keep the transcript text in the returned dict
    for the run log / JSON artifact. The transcript is SYNTHETIC (fabricated
    values from build_seeded_fields()), so recording it is acceptable here the
    same way the g1/secretary-recall probes treat their synthetic corpora --
    never do this with real user data."""
    found = []
    transcript_parts = []
    count = 0
    timed_out = False
    it = session.receive().__aiter__()
    try:
        while True:
            try:
                msg = await asyncio.wait_for(it.__anext__(), timeout=turn_timeout)
            except asyncio.TimeoutError:
                timed_out = True
                print(f"  [{label}] TURN TIMEOUT after {turn_timeout}s "
                      f"(no turn_complete) -- returning {len(found)} call(s) so far", flush=True)
                break
            except StopAsyncIteration:
                break
            count += 1
            tc = getattr(msg, "tool_call", None)
            if tc and getattr(tc, "function_calls", None):
                for fc in tc.function_calls:
                    found.append(_report_fc("event.tool_call", fc))
            sc = getattr(msg, "server_content", None)
            if sc is not None:
                mt = getattr(sc, "model_turn", None)
                if mt and getattr(mt, "parts", None):
                    for p in mt.parts:
                        pfc = getattr(p, "function_call", None)
                        if pfc:
                            found.append(_report_fc("model_turn.parts", pfc))
                ot = getattr(sc, "output_transcription", None)
                if ot is not None and getattr(ot, "text", None):
                    transcript_parts.append(ot.text)
                if getattr(sc, "turn_complete", False):
                    break
            if count >= max_msgs:
                print(f"  [{label}] hit max_msgs without turn_complete", flush=True)
                break
    except Exception as e:
        print(f"  [{label}] RECEIVE ERROR: {type(e).__name__}: {e}", flush=True)
    finally:
        try:
            await it.aclose()
        except Exception:
            pass
    transcript = "".join(transcript_parts)
    if transcript:
        print(f"  [{label}] spoke: {transcript!r}", flush=True)
    return {"calls": found, "timed_out": timed_out, "transcript": transcript}


async def _send_tool_responses(session, calls: list, payload_for) -> None:
    """Reply to each tool call with a realistic response, echoing the id
    (bd polyglot-pdf-0ux)."""
    from google.genai import types

    responses = []
    for c in calls:
        fr_kwargs = {"name": c["name"], "response": payload_for(c)}
        if c["id"]:
            fr_kwargs["id"] = c["id"]
        responses.append(types.FunctionResponse(**fr_kwargs))
    if responses:
        await session.send_tool_response(function_responses=responses)


async def _send_text_turn(session, text: str, model_name: str) -> None:
    """Inject a user-role text turn exactly as LiveAIGemini._send_text_turn
    does for the 2.5 family (backend/adapters/live_ai_gemini.py:1130-1139):
    2.5 uses send_client_content with no explicit role (SDK defaults to
    'user'); 3.1 uses send_realtime_input(text=). This probe pins a 2.5-family
    model (see MODEL_NATIVE_STANDARD_VERTEX), so the 2.5 branch is the one
    exercised; the 3.1 branch is mirrored here only for completeness /
    future-proofing if the probe is ever pointed at a 3.1 model."""
    from backend.config import model_family

    if model_family(model_name) == "3.1":
        await session.send_realtime_input(text=text)
    else:
        await session.send_client_content(
            turns={"parts": [{"text": text}]},
            turn_complete=True,
        )


# ---------------------------------------------------------------------------
# Tool-response ack builders -- mirror callback_handler.py's success shapes
# (see module docstring for the exact line references).
# ---------------------------------------------------------------------------

def make_switch_to_field_ack(field_id: str, fields: list, schema: dict) -> dict:
    """Mirrors callback_handler.py _handle_switch_to_field_tool's success
    response (the `response` dict built ~line 1175-1179): {"success": True,
    "message": ..., "current_value": <if the field has one>, "field_guidance":
    <if we can render one>}. There is no live frontend in this probe, so this
    fabricates the ack a real client's request_switch_field round-trip would
    have returned."""
    current_value = field_current_value(field_id, fields)
    name = field_name(field_id, fields)
    fschema = field_schema_by_id(schema, field_id)
    state_note = (
        "It already holds an unconfirmed value -- read it back and verify it "
        "with the user." if current_value else "It is currently unanswered -- "
        "ask the user for it."
    )
    response = {
        "success": True,
        "message": f"Now on field '{name}'. {state_note}",
    }
    if current_value:
        response["current_value"] = current_value
    if fschema:
        # A compact guidance string -- the real render_field_guidance formats
        # more richly, but the model only needs field_id/spoken_name/type here.
        response["field_guidance"] = (
            f"Field: {fschema.get('spoken_name') or name} "
            f"(field_id: {field_id}, type: {fschema.get('type', 'text')})"
        )
    return response


def make_update_ack(applied_field_id: str) -> dict:
    """Mirrors callback_handler.py _build_update_fields_response's success
    branch (line ~1367-1371)."""
    return {
        "success": True,
        "applied_fields": [applied_field_id],
        "message": "Fields updated successfully.",
    }


def make_confirm_ack(field_id: str) -> dict:
    """Mirrors callback_handler.py _handle_confirm_field_tool's success
    response (the `response` dict at line ~906-911), the not-hint-timed-out /
    no-next-field-hint variant (single-field probe, nothing to advance to)."""
    return {
        "success": True,
        "field_confirmed": field_id,
        "next_field_hint": None,
        "message": f"Field '{field_id}' confirmed. All fields confirmed.",
    }


# ---------------------------------------------------------------------------
# Real validator + real steer.
# ---------------------------------------------------------------------------

async def run_real_validator(fields: list, dry_run: bool) -> dict:
    """Run the REAL flash-lite validator over the seeded fields. Returns the
    contract-1 verdict {"conflicts": [...]}. In --dry-run, stubs the network
    call but exercises the SAME ValidatorService code path via a stub ITextAI."""
    if dry_run:
        class _StubTextAI:
            async def validate(self, payload: dict, session_ctx: dict | None = None) -> dict:
                return {"conflicts": [{"field_ids": [M_STATE[0], M_ZIP[0]],
                                        "reason": "stub: state/zip mismatch"}]}
        return await ValidatorService(_StubTextAI()).validate(fields)

    from backend.adapters.text_ai_gemini import TextAIGemini

    text_ai = TextAIGemini(
        vertexai=_is_vertex(),
        project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
        location=os.environ.get("VERTEX_LOCATION", "us-central1"),
    )
    return await ValidatorService(text_ai).validate(fields)


# ---------------------------------------------------------------------------
# One trial.
# ---------------------------------------------------------------------------

async def run_trial(client, model_name: str, settings: Settings, schema: dict,
                     trial_idx: int, dry_run: bool) -> dict:
    print(f"\n=== TRIAL {trial_idx} ===", flush=True)
    fields = build_seeded_fields()

    # -- 1. REAL validator verdict.
    verdict = await run_real_validator(fields, dry_run)
    conflicts = verdict.get("conflicts", []) if isinstance(verdict, dict) else []
    if not conflicts:
        print("  ABORT: validator reported NO conflicts on a seeded West-Virginia/"
              "Iowa-ZIP contradiction. This is a VALIDATOR-RECALL failure, not a "
              "rail-wiring failure -- do not fabricate a steer. See "
              "probe_g1_contradiction_recall.py to characterize recall.", flush=True)
        return {"trial": trial_idx, "aborted": "validator_no_conflict", "verdict": verdict}
    flagged_ids = sorted({fid for c in conflicts for fid in c.get("field_ids", [])})
    print(f"  validator verdict: {len(conflicts)} conflict(s), flagged={flagged_ids}",
          flush=True)

    # -- 2. REAL steer composer.
    steer_message = FormFillingService._compose_validator_steer(conflicts, fields)
    print(f"  steer composed: {len(steer_message)} chars", flush=True)

    result = {
        "trial": trial_idx,
        "aborted": None,
        "verdict": verdict,
        "steer_message": steer_message,
        "assertions": {
            "steer_delivered": False,
            "switch_to_field_called": False,
            "switch_to_field_id": None,
            "update_carried_correction": False,
            "update_value": None,
            "confirm_field_called": False,
        },
        "turns": [],
    }

    if dry_run:
        print("  [dry-run] skipping live session connect; wiring verified up to "
              "the network boundary.", flush=True)
        result["dry_run"] = True
        return result

    # -- 3/4/5. Connect + inject + drain, with a bounded retry on a spontaneous
    # 1011/1008 drop (cap MAX_CONNECT_RETRIES; never loop forever).
    attempt = 0
    while True:
        attempt += 1
        try:
            await _run_live_turns(client, model_name, settings, schema, fields,
                                   flagged_ids, steer_message, result)
            break
        except Exception as exc:  # noqa: BLE001 -- classify below, never hang
            from websockets.exceptions import ConnectionClosed
            code = getattr(exc, "code", None)
            is_closed = isinstance(exc, ConnectionClosed)
            spontaneous = is_closed and code in (1011, 1008)
            print(f"  connect/turn ERROR (attempt {attempt}/{MAX_CONNECT_RETRIES + 1}): "
                  f"{type(exc).__name__}: {exc} (close_code={code})", flush=True)
            result["error"] = f"{type(exc).__name__}: {exc}"
            result["close_code"] = code
            if not spontaneous or attempt > MAX_CONNECT_RETRIES:
                result["aborted"] = "connect_error" if attempt == 1 else "connect_error_retries_exhausted"
                break
            print("  spontaneous 1011/1008 drop -- retrying trial", flush=True)
            continue

    return result


async def _run_live_turns(client, model_name: str, settings: Settings, schema: dict,
                           fields: list, flagged_ids: list, steer_message: str,
                           result: dict) -> None:
    """The connect + turn-flow body for one trial attempt. Raises on a
    connect/session error so run_trial's retry loop can classify it; appends
    per-turn logs into result["turns"] and sets result["assertions"] in place."""
    system_instruction = build_production_si(settings)
    tools = build_production_tools(settings)
    config = build_live_config(settings, system_instruction, tools, model_name)

    assertions = result["assertions"]

    async with client.aio.live.connect(model=model_name, config=config) as session:
        # (b) a short user-role context turn -- the SI is static DTI; field
        # state lives client-side in production, so we do NOT pre-drive a
        # whole fill. This just gives the model a plausible reason to be
        # mid-form when the steer lands.
        await _send_text_turn(session, "I have finished filling the form.", model_name)
        ctx_turn = await _drain(session, "context")
        result["turns"].append({"label": "context", **ctx_turn})

        # (c) inject the REAL steer.
        await _send_text_turn(session, steer_message, model_name)
        assertions["steer_delivered"] = True

        # (d) drain -> EXPECT switch_to_field naming a flagged field.
        switch_turn = await _drain(session, "post-steer (expect switch_to_field)")
        result["turns"].append({"label": "post_steer", **switch_turn})
        switch_calls = [c for c in switch_turn["calls"] if c["name"] == "switch_to_field"]
        target_field_id = None
        if switch_calls:
            call = switch_calls[0]
            raw_target = str(call["args"].get("field") or "").strip()
            # The model may pass the field_id or the exact spoken name (tool
            # contract); resolve either against the flagged set / schema.
            if raw_target in flagged_ids:
                target_field_id = raw_target
            else:
                for fid in flagged_ids:
                    fs = field_schema_by_id(schema, fid)
                    if fs.get("spoken_name") == raw_target or fs.get("name") == raw_target:
                        target_field_id = fid
                        break
            if target_field_id:
                assertions["switch_to_field_called"] = True
                assertions["switch_to_field_id"] = target_field_id

        if not switch_calls:
            print("  >>> FAIL: no switch_to_field call on the post-steer turn.", flush=True)
        elif not target_field_id:
            print(f"  >>> FAIL: switch_to_field called but target "
                  f"{switch_calls[0]['args'].get('field')!r} does not resolve to a "
                  f"flagged field {flagged_ids}.", flush=True)
        else:
            print(f"  PASS: switch_to_field -> {target_field_id}", flush=True)

        # (e) ack the switch_to_field call(s) with the production ack shape.
        if switch_calls:
            ack_field_id = target_field_id or flagged_ids[0]

            def _switch_ack(_call, _fid=ack_field_id):
                return make_switch_to_field_ack(_fid, fields, schema)

            await _send_tool_responses(session, switch_calls, _switch_ack)

        # (f) drain -> the model should voice a read-back and ask the user.
        readback_turn = await _drain(session, "read-back")
        result["turns"].append({"label": "readback", **readback_turn})

        # send the user's correction.
        await _send_text_turn(
            session,
            f"Oh you're right, the state should be {CORRECTED_STATE_LABEL}.",
            model_name,
        )

        # (g) drain -> EXPECT update_form_fields with the corrected value.
        update_turn = await _drain(session, "post-correction (expect update_form_fields)")
        result["turns"].append({"label": "post_correction", **update_turn})
        update_calls = [c for c in update_turn["calls"] if c["name"] == "update_form_fields"]
        corrected_field_id = None
        if update_calls:
            call = update_calls[0]
            sent_id = call["args"].get("field_id")
            sent_value = call["args"].get("value")
            carries_correction = (
                sent_id == M_STATE[0]
                and isinstance(sent_value, str)
                and sent_value.strip().lower() in (
                    CORRECTED_STATE_VALUE, CORRECTED_STATE_LABEL.lower(),
                    # The standard state ABBREVIATION is an equally correct
                    # spelling of the correction -- trial 1 of the first run
                    # sent 'IA' and was a checker false-negative (the rail
                    # behavior itself was correct; see the run artifact).
                    "ia",
                )
            )
            assertions["update_value"] = sent_value
            if carries_correction:
                assertions["update_carried_correction"] = True
                corrected_field_id = sent_id

        if not update_calls:
            print("  >>> FAIL: no update_form_fields call after the correction.", flush=True)
        elif not assertions["update_carried_correction"]:
            print(f"  >>> FAIL: update_form_fields called for "
                  f"{update_calls[0]['args'].get('field_id')!r}="
                  f"{update_calls[0]['args'].get('value')!r}, expected "
                  f"{M_STATE[0]!r}={CORRECTED_STATE_VALUE!r}/{CORRECTED_STATE_LABEL!r}.",
                  flush=True)
        else:
            print(f"  PASS: update_form_fields carried the correction "
                  f"({M_STATE[0]}={CORRECTED_STATE_VALUE!r})", flush=True)

        # ack update_form_fields.
        if update_calls:
            ack_id = corrected_field_id or M_STATE[0]

            def _update_ack(_call, _fid=ack_id):
                return make_update_ack(_fid)

            await _send_tool_responses(session, update_calls, _update_ack)

        # (h) drain -> EXPECT confirm_field (or a combined confirm).
        confirm_turn = await _drain(session, "post-update (expect confirm_field)")
        result["turns"].append({"label": "post_update", **confirm_turn})
        confirm_calls = [c for c in confirm_turn["calls"] if c["name"] == "confirm_field"]
        # A well-behaved model may voice the verify question here without a
        # tool call yet, needing one more "yes" round-trip -- give it one
        # extra turn before declaring failure (mirrors probe_confirm_field's
        # early-vs-post-yes finding).
        if not confirm_calls and confirm_turn.get("transcript"):
            await _send_text_turn(session, "Yes, that's correct.", model_name)
            extra_turn = await _drain(session, "post-yes (expect confirm_field)")
            result["turns"].append({"label": "post_yes", **extra_turn})
            confirm_calls = [c for c in extra_turn["calls"] if c["name"] == "confirm_field"]

        confirmed_field_id = None
        if confirm_calls:
            call = confirm_calls[0]
            sent_id = call["args"].get("field_id")
            if sent_id == corrected_field_id or sent_id == M_STATE[0] or not sent_id:
                confirmed_field_id = sent_id or M_STATE[0]
                assertions["confirm_field_called"] = True

        if not confirm_calls:
            print("  >>> FAIL: no confirm_field call after the correction was filled.",
                  flush=True)
        else:
            print(f"  PASS: confirm_field called (field_id={confirm_calls[0]['args'].get('field_id')!r})",
                  flush=True)

        # (i) ack + stop.
        if confirm_calls:
            def _confirm_ack(_call, _fid=confirmed_field_id or M_STATE[0]):
                return make_confirm_ack(_fid)

            await _send_tool_responses(session, confirm_calls, _confirm_ack)


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def _print_verdict(results: list) -> None:
    print("\n=== VERDICT ===", flush=True)
    for r in results:
        idx = r["trial"]
        if r.get("aborted"):
            print(f"  trial {idx}: ABORTED ({r['aborted']})", flush=True)
            continue
        a = r["assertions"]
        checks = [
            ("steer_delivered", a["steer_delivered"]),
            ("switch_to_field_called", a["switch_to_field_called"]),
            ("update_carried_correction", a["update_carried_correction"]),
            ("confirm_field_called", a["confirm_field_called"]),
        ]
        all_pass = all(v for _, v in checks)
        status = "PASS" if all_pass else "FAIL"
        detail = ", ".join(f"{name}={'PASS' if v else 'FAIL'}" for name, v in checks)
        print(f"  trial {idx}: {status} -- {detail}", flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=1,
                    help="Number of trials to run (fresh session each).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Verify wiring with a stub validator/client, no network calls.")
    args = ap.parse_args()

    settings = Settings()
    vertexai = _is_vertex()
    model_name = _live_model(vertexai)
    print(f"=== validator rail probe: model={model_name} vertexai={vertexai} "
          f"trials={args.trials} dry_run={args.dry_run} ===", flush=True)

    schema = build_i90_schema()
    client = None if args.dry_run else _client()

    results = []
    for i in range(1, args.trials + 1):
        r = await run_trial(client, model_name, settings, schema, i, args.dry_run)
        results.append(r)

    _print_verdict(results)

    if args.dry_run:
        print("\n[dry-run] wiring verified end-to-end up to (excluding) network calls.",
              flush=True)
        return

    os.makedirs(OUT_DIR, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = os.path.join(OUT_DIR, f"validator_rail_{stamp}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({
            "bead": "polyglot-pdf-oiok",
            "stamp": stamp,
            "model": model_name,
            "vertexai": vertexai,
            "trials": results,
        }, fh, indent=2)
    print(f"\nwrote {out_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
