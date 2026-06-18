"""Per-question token/cost measurement instrument (bd polyglot-pdf-4loz, epic hcsl).

Drives the REAL form-filling stack -- FormFillingService + CallbackHandler +
RequestCoordinator + LiveAIGemini, the production system instruction built by
build_form_context_message from the real demo schema, the production
TOOL_DECLARATIONS -- against live Gemini with scripted gTTS audio, simulating
the frontend client (the stateless contract's other half) over a fake
WebSocket. Deploy fidelity per docs/standards/testing.md ("Live-endpoint
probes and spikes"); the one labeled deviation is turn injection via explicit
activity brackets with server VAD neutralized (synthetic audio needs
deterministic turn boundaries; bd h04c ran 51 sessions this way).

Outputs, per run:
  - <out>/costs_<model>_<arm>_<path>_<stamp>.csv -- one row per question 1..N,
    EXACTLY these 11 columns (epic criterion 2): question number, audio in
    tokens, audio in token cost, audio out tokens, audio out token cost, text
    in tokens, text in token cost, text out tokens, text out token cost, total
    tokens, total cost
  - the same name + .meta.json -- run config, per-turn latency (activity_end ->
    first audio byte), per-question tool-call record (compliance), the raw
    prompt-token curve + detected eviction drops, captured errors.

Arms (--arm):
  unbounded      one session, no compression, no resets (raw growth curve)
  section-reset  the CURRENT production flow: per-section sub-schema, session
                 restart at each section boundary via switch_to_section (the
                 restart + re-greeting tokens are attributed to the FIRST
                 question of the new section -- that IS the cost of advancing)
  sliding-window one session with ContextWindowCompressionConfig on
                 (--trigger/--window)

Question scripts (--path):
  happy    2 turns/question: value, positive confirmation
  unhappy  4 turns/question: wrong value, rejection, corrected value,
           positive confirmation

Audio is gTTS-synthesized once and cached as PCM16@16k under
scripts/spikes/fixtures/audio_cache/ (committed; reruns are network-free).
--synth-only builds the cache and exits without touching the live endpoint.

Run from repo root with GEMINI_API_KEY (a 20-question happy run is ~5-8 min):

    backend/.venv/Scripts/python.exe scripts/spikes/measure_form_session_costs.py \
        --model 2.5 --arm unbounded --path happy
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _rc = getattr(_stream, "reconfigure", None)
    if _rc is not None:
        try:
            _rc(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass

import numpy as np  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.adapters.live_ai_gemini import LiveAIGemini  # noqa: E402
from backend import config as _config  # noqa: E402
from backend.config import (  # noqa: E402
    MODEL_NATIVE_PREMIUM,
    MODEL_NATIVE_STANDARD,
    get_pricing_for_model,
)
from backend.services.form_filling_service import FormFillingService  # noqa: E402

MODELS = {"2.5": MODEL_NATIVE_STANDARD, "3.1": MODEL_NATIVE_PREMIUM}

# Schema sources (bd polyglot-pdf-jnjj.24). The harness was hardcoded to the DEMO
# schema, which is non-representative (flat 'description' on 2/174 fields, no nested
# 'help', no parts/sections arrays). The REAL I-90 (form-kits/i-90/schema.json:
# parts/sections arrays, help.instructions on 132/132 fields) is what forward
# cost/JIT/DTI/secretary measurement must use. --schema selects the source +
# its matching question plan.
DEMO_SCHEMA_PATH = _REPO_ROOT / "frontend" / "public" / "adult_intake_demo_schema.json"
I90_SCHEMA_PATH = _REPO_ROOT / "form-kits" / "i-90" / "schema.json"
AUDIO_CACHE = Path(__file__).resolve().parent / "fixtures" / "audio_cache"
_AUDIO_RATE = 16000
_CHUNK_MS = 40

CONFIRM_YES = "Yes, that's correct."
REJECT = "No, that's not right."

# The DEMO 20-question plan: 12 client-info + 5 reasons + 3 living-situation fields
# from the demo schema, in schema order, with realistic FICTIONAL answers
# (no real PII). "wrong" is the unhappy path's first (rejected) value.
DEMO_QUESTIONS = [
    {"field_id": "firstName", "say": "My first name is Maria.",
     "wrong": "My first name is Mario."},
    {"field_id": "middleName", "say": "My middle name is Elena.",
     "wrong": "My middle name is Elaine."},
    {"field_id": "lastName", "say": "My last name is Vasquez.",
     "wrong": "My last name is Vargas."},
    {"field_id": "preferredName", "say": "Please call me Mari.",
     "wrong": "Please call me Ria."},
    {"field_id": "pronouns", "say": "My pronouns are she her.",
     "wrong": "My pronouns are they them."},
    {"field_id": "dob",
     "say": "I was born on March fourteenth, nineteen eighty eight.",
     "wrong": "I was born on May fourteenth, nineteen eighty eight."},
    {"field_id": "age", "say": "I am thirty eight years old.",
     "wrong": "I am thirty five years old."},
    {"field_id": "genderIdentity", "say": "Cisgender female.",
     "wrong": "Non binary."},
    {"field_id": "sexualOrientation", "say": "I am heterosexual.",
     "wrong": "I am bisexual."},
    {"field_id": "maritalStatus", "say": "I am married.",
     "wrong": "I am single."},
    {"field_id": "partnerSpouseName",
     "say": "My spouse's name is Daniel Vasquez.",
     "wrong": "My spouse's name is David Vasquez."},
    {"field_id": "legalCustodian", "say": "I do not have a legal custodian.",
     "wrong": "My legal custodian is my mother."},
    {"field_id": "mandatedBy", "say": "I was not mandated by anyone, I came voluntarily.",
     "wrong": "I was mandated by the court."},
    {"field_id": "otherReason", "say": "I have been feeling anxious about work.",
     "wrong": "I have been feeling sad about school."},
    {"field_id": "problemStart", "say": "The problems began about two years ago.",
     "wrong": "The problems began about two months ago."},
    {"field_id": "desiredChanges",
     "say": "I want to manage my anxiety better and sleep through the night.",
     "wrong": "I want to stop arguing with my coworkers."},
    {"field_id": "strengths",
     "say": "I am persistent and I have a supportive family.",
     "wrong": "I am creative and I have a good sense of humor."},
    {"field_id": "primaryHousehold",
     "say": "I live with my spouse and our daughter.",
     "wrong": "I live alone."},
    {"field_id": "householdMembers",
     "say": "There are three people in my household.",
     "wrong": "There are five people in my household."},
    {"field_id": "member1_name",
     "say": "The first household member is Daniel Vasquez.",
     "wrong": "The first household member is David Vasquez."},
]

# The REAL I-90 question plan (bd polyglot-pdf-jnjj.24): the first 3 sections of
# form-kits/i-90/schema.json -- Part 1 "Information About You" (sec 1), the mailing
# address (sec 2), and the physical address (sec 3). FICTIONAL answers (no real PII).
# spoken_name is the natural phrasing the model asks by. The plan scripts EVERY
# field that is visible in a section given the scripted conditional answers, in
# SCHEMA ORDER, so the section-reset SI's field list and the next-field hint never
# contradict -- otherwise the model could ask for an SI-listed field the plan never
# answers and stall the run (fresh-eyes for this bead):
#   - the name-change radio (p1_checkbox4) is answered "no", so the show_if
#     previous-name fields (p1_line5a/b/c) stay HIDDEN and are correctly NOT scripted;
#   - each unit-type radio (p1_unit_type6c/7b) IS answered, which makes its show_if
#     apt-number field (p1_line6c/7b_aptsteflrnumber) VISIBLE -- so that apt-number
#     field IS scripted (a real apartment filer fills it);
#   - the always-visible optional province/postalcode fields are scripted too, with
#     a US-filer "not applicable" answer, so no visible field is left unanswered.
I90_QUESTIONS = [
    # --- Section 1: Part 1 - Information About You ---
    # Answer the A-Number as BARE DIGITS (no "A" prefix): the a_number A-strip
    # normalizer is currently broken (bd polyglot-pdf-cn0e -- it reads top-level
    # format_preset but the schema nests it under validation.format_preset), so an
    # "A..."-prefixed answer fails the ^\d{7,9}$ pattern and adds validation noise to
    # the cost measurement. Bare digits validate cleanly today; revert to a natural
    # "A12345678" phrasing once cn0e lands.
    {"field_id": "p1_line1_aliennumber", "say": "My alien registration number is one two three four five six seven eight.",
     "wrong": "My alien registration number is eight seven six five four three two one."},
    {"field_id": "p1_line2_acctidentifier", "say": "My USCIS online account number is 1234567890.",
     "wrong": "My USCIS online account number is 9876543210."},
    {"field_id": "p1_line3a_familyname", "say": "My current family name is Vasquez.",
     "wrong": "My current family name is Vargas."},
    {"field_id": "p1_line3b_givenname", "say": "My current given name is Maria.",
     "wrong": "My current given name is Mario."},
    {"field_id": "p1_line3c_middlename", "say": "My current middle name is Elena.",
     "wrong": "My current middle name is Elaine."},
    {"field_id": "p1_checkbox4", "say": "No, my name has not changed.",
     "wrong": "Yes, my name has changed."},
    # --- Section 2: mailing address ---
    {"field_id": "p1_line6a_incareofname", "say": "In care of Daniel Vasquez.",
     "wrong": "In care of David Vasquez."},
    {"field_id": "p1_line6b_streetnumbername", "say": "Twelve thirty four Maple Street.",
     "wrong": "Fifty six seventy eight Oak Street."},
    {"field_id": "p1_unit_type6c_unit", "say": "Apartment.",
     "wrong": "Suite."},
    # apt-number is show_if (unit_type is_not_empty) -- now visible, so scripted.
    {"field_id": "p1_line6c_aptsteflrnumber", "say": "Apartment number twelve B.",
     "wrong": "Apartment number fourteen C."},
    {"field_id": "p1_line6d_cityortown", "say": "My mailing city is Austin.",
     "wrong": "My mailing city is Houston."},
    {"field_id": "p1_line6e_state", "say": "Texas.",
     "wrong": "Florida."},
    {"field_id": "p1_line6f_zipcode", "say": "My mailing zip code is seven three seven zero one.",
     "wrong": "My mailing zip code is seven seven zero zero one."},
    {"field_id": "p1_line6g_province", "say": "I do not have a province, I am in the United States.",
     "wrong": "My province is Ontario."},
    {"field_id": "p1_line6h_postalcode", "say": "I do not have a postal code, I am in the United States.",
     "wrong": "My postal code is K1A 0B1."},
    {"field_id": "p1_line6i_country", "say": "United States.",
     "wrong": "Canada."},
    # --- Section 3: physical address (schema order: ...zipcode, province, postalcode, country) ---
    {"field_id": "p1_line7a_streetnumbername", "say": "Twelve thirty four Maple Street.",
     "wrong": "Ninety nine Pine Avenue."},
    {"field_id": "p1_unit_type7b_unit", "say": "Apartment.",
     "wrong": "Floor."},
    {"field_id": "p1_line7b_aptsteflrnumber", "say": "Apartment number twelve B.",
     "wrong": "Apartment number fifteen D."},
    {"field_id": "p1_line7c_cityortown", "say": "My physical city is Austin.",
     "wrong": "My physical city is Dallas."},
    {"field_id": "p1_line7d_state", "say": "Texas.",
     "wrong": "Arizona."},
    {"field_id": "p1_line7e_zipcode", "say": "My physical zip code is seven three seven zero one.",
     "wrong": "My physical zip code is eight five zero zero one."},
    {"field_id": "p1_line7f_province", "say": "I do not have a province, I am in the United States.",
     "wrong": "My province is Quebec."},
    {"field_id": "p1_line7g_postalcode", "say": "I do not have a postal code, I am in the United States.",
     "wrong": "My postal code is K1A 0B1."},
    {"field_id": "p1_line7h_country", "say": "United States.",
     "wrong": "Mexico."},
]

# --schema registry: source path + matching question plan. Default is "demo" for
# back-compat with the pre-jnjj.24 callers; "i90" is the production-faithful set.
SCHEMAS = {
    "demo": {"path": DEMO_SCHEMA_PATH, "questions": DEMO_QUESTIONS},
    "i90": {"path": I90_SCHEMA_PATH, "questions": I90_QUESTIONS},
}

CSV_COLUMNS = [
    "question number",
    "audio in tokens", "audio in token cost",
    "audio out tokens", "audio out token cost",
    "text in tokens", "text in token cost",
    "text out tokens", "text out token cost",
    "total tokens", "total cost",
]


# ---------------------------------------------------------------- audio cache

def synth_cached(text: str) -> bytes:
    """gTTS -> mono PCM16 @ 16 kHz, disk-cached so committed runs are repeatable."""
    AUDIO_CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]
    cached = AUDIO_CACHE / f"{key}.pcm"
    if cached.exists():
        return cached.read_bytes()
    from gtts import gTTS
    import soundfile as sf

    buf = io.BytesIO()
    gTTS(text, lang="en").write_to_fp(buf)
    buf.seek(0)
    y, sr = sf.read(buf, dtype="float32")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != _AUDIO_RATE:
        n_out = int(len(y) * _AUDIO_RATE / sr)
        y = np.interp(np.linspace(0, len(y), n_out, endpoint=False),
                      np.arange(len(y)), y).astype("float32")
    pcm = (np.clip(y, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    cached.write_bytes(pcm)
    return pcm


def _pcm_chunks(pcm: bytes) -> list[bytes]:
    n = int(_AUDIO_RATE * (_CHUNK_MS / 1000.0)) * 2
    return [pcm[i:i + n] for i in range(0, len(pcm), n)]


# ------------------------------------------------------------- schema helpers

def load_schema(schema_key: str = "demo") -> dict:
    return json.loads(SCHEMAS[schema_key]["path"].read_text(encoding="utf-8"))


def sections_in_plan(schema: dict, plan: list[dict]) -> list[dict]:
    """Ordered distinct sections covered by the plan, with labels from the schema.

    Label resolution prefers, in order: a field's own `section_label` (the demo
    schema shape), then the schema-root `sections[]` entry's `label` (the I-90 shape
    -- its fields carry no section_label, so without this the SI would announce the
    raw snake_case section_id like "part_1_2_addresses" instead of the production
    "Part 1.2 Mailing Address"; bd polyglot-pdf-jnjj.24 fresh-eyes), then the id.
    """
    by_id = {f["id"]: f for f in schema["fields"]}
    section_labels = {s.get("id"): s.get("label")
                      for s in schema.get("sections", []) if s.get("id")}
    seen: list[dict] = []
    for q in plan:
        f = by_id[q["field_id"]]
        sid = f.get("section_id") or "section-1"
        if not any(s["id"] == sid for s in seen):
            label = f.get("section_label") or section_labels.get(sid) or sid
            seen.append({"id": sid, "label": label, "number": len(seen) + 1})
    return seen


def section_subschema(schema: dict, section_id: str) -> dict:
    """What the production frontend hands the backend per section: that
    section's fields only, same metadata."""
    return {
        "form_metadata": schema.get("form_metadata", {}),
        "fields": [f for f in schema["fields"]
                   if (f.get("section_id") or "section-1") == section_id],
    }


def jit_handshake_schema(sub: dict, section_id: str, section_label: str) -> dict:
    """The JIT-shaped schema the backend synthesizes from a handshake_jit, post-A2
    (bd polyglot-pdf-jnjj.9). Mirrors frontend getJITHandshakePayload +
    websocket_routes' JIT branch: a manifest carrying the full section
    field_id|spoken_name pairs, plus only the FIRST field's full schema in `fields`
    (the rest arrive on demand). This is what build_form_context consumes in JIT
    mode -- so the cost harness's section-reset-jit arm measures the REAL repaired
    JIT SI, not the full per-section dump."""
    section_fields = sub["fields"]
    manifest_fields = [
        {"field_id": f["id"], "spoken_name": f.get("spoken_name", f.get("name", f["id"]))}
        for f in section_fields
    ]
    first_field = section_fields[0] if section_fields else None
    return {
        "source": "web",
        "jit_mode": True,
        "form_metadata": sub.get("form_metadata", {}),
        # JIT mode carries only the first field's full schema; the rest are in the
        # manifest (id|spoken_name) and stream in via the confirm_field drip.
        "fields": [first_field] if first_field else [],
        "manifest": {
            "current_section": {
                "section_id": section_id,
                "section_label": section_label,
                "fields": manifest_fields,
            },
            "previous_sections": [],
            "parts": [{"id": section_id, "order": 1, "label": section_label}],
        },
        "loaded_field_ids": [],
        "parts": [{"id": section_id, "order": 1, "label": section_label}],
    }


def _hint_for(field: dict, order: int) -> str:
    """The frontend's hint format (frontend/src/navigation.ts)."""
    required = ", required" if field.get("required") else ""
    options = field.get("options") or field.get("allowed_values")
    opt = f", options: [{', '.join(map(str, options))}]" if options else ""
    return (f"Next field to fill is #{order}: '{field.get('name', field['id'])}' "
            f"(field_id: '{field['id']}', type: {field.get('type', 'text')}"
            f"{required}{opt})")


# ----------------------------------------------------------- client simulator

class FakeClientWebSocket:
    """Stands in for both the WebSocket and the frontend client: owns the field
    state (the stateless contract's client half) and answers the coordinator's
    synchronous round-trips (get_form_state / get_next_field_hint /
    confirm_field) the way webFormConnection does."""

    def __init__(self, schema: dict, plan: list[dict], dti_mode: bool = False):
        self.schema_fields = {f["id"]: f for f in schema["fields"]}
        self.plan = plan
        self.active_field_ids: list[str] = [q["field_id"] for q in plan]
        self.state: dict[str, dict] = {}
        self.service: FormFillingService | None = None
        self.first_audio_at: float | None = None
        self.sent_messages: list[str] = []
        # DTI (bd polyglot-pdf-jnjj.25): in DTI mode the client owns the schema and
        # supplies the next field's FULL schema on next_field_hint_response, which
        # the backend renders into the confirm_field next_field_guidance. Mirrors the
        # production frontend (webFormConnection.handleGetNextFieldHintRequest +
        # getFieldSchema). Off for the section-reset/JIT arms.
        self.dti_mode = dti_mode

    # -- WebSocket surface the backend touches
    async def accept(self):
        return None

    async def close(self, *a, **k):
        return None

    async def send_text(self, _data):
        return None

    async def send_bytes(self, _data: bytes):
        if self.first_audio_at is None:
            self.first_audio_at = time.monotonic()

    async def send_json(self, msg: dict):
        mtype = msg.get("type")
        self.sent_messages.append(mtype or "?")
        if mtype == "form_updated":
            data = msg.get("data") or {}
            form_state = data.get("form_state") or {}
            for fid, val in form_state.items():
                value = val.get("value") if isinstance(val, dict) else val
                if fid in self.schema_fields and value not in (None, ""):
                    self.state.setdefault(fid, {})["value"] = value
                    self.state[fid].setdefault("confirmed", False)
        elif mtype == "get_form_state":
            rid = msg.get("request_id")
            want = msg.get("field_ids") or list(self.state.keys())
            snapshot = {fid: {"value": self.state[fid].get("value"),
                              "confirmed": self.state[fid].get("confirmed", False)}
                        for fid in want if fid in self.state}
            self._reply(lambda: self.service.handle_form_state_response(rid, snapshot))
        elif mtype == "get_next_field_hint":
            rid = msg.get("request_id")
            hint = self.next_hint()
            # DTI: also hand the backend the next field's FULL schema (the client
            # owns it) so it renders into next_field_guidance -- otherwise the DTI
            # model gets no per-field guidance past field 1 and stalls.
            nfs = self.next_field_schema() if self.dti_mode else None
            self._reply(lambda: self.service.handle_next_field_hint_response(rid, hint, nfs))
        elif mtype == "confirm_field":
            rid = msg.get("request_id")
            fid = msg.get("field_id")
            entry = self.state.get(fid)
            if entry and entry.get("value") not in (None, ""):
                entry["confirmed"] = True
                self._reply(lambda: self.service.handle_confirm_field_response(rid, True))
            else:
                self._reply(lambda: self.service.handle_confirm_field_response(
                    rid, False, "no_value"))
        # section_switched / transcripts / status messages need no reply

    def _reply(self, fn):
        # Resolve on the next loop tick, like a (very fast) frontend round-trip.
        asyncio.get_event_loop().call_soon(fn)

    # -- frontend navigation logic
    def set_active_section(self, plan_slice: list[dict]):
        self.active_field_ids = [q["field_id"] for q in plan_slice]

    def next_hint(self) -> str | None:
        for order, fid in enumerate(self.active_field_ids, 1):
            entry = self.state.get(fid)
            if not entry or not entry.get("confirmed"):
                return _hint_for(self.schema_fields[fid], order)
        return None

    def next_field_schema(self) -> dict | None:
        """The FULL schema dict of the next unconfirmed field (DTI mode). The client
        owns the full schema, so this is the harness analogue of the frontend's
        getFieldSchema(nextField.id) -- the backend renders it into the confirm_field
        next_field_guidance."""
        for fid in self.active_field_ids:
            entry = self.state.get(fid)
            if not entry or not entry.get("confirmed"):
                return self.schema_fields.get(fid)
        return None


# ------------------------------------------------------------------ log tap

_ERROR_EVENTS = {
    "gemini_session_connection_closed",
    "gemini_session_no_events_received",
    "receive_loop_unexpected_error",
}


class _LogTap:
    """Record warning+ structlog events from the adapter without touching it
    (same pattern as diag_compression_matrix_sdk28.py)."""

    _CAPTURE = ("warning", "error", "exception", "critical")

    def __init__(self, inner, sink: list):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_sink", sink)

    def bind(self, **kw):
        return _LogTap(self._inner.bind(**kw), self._sink)

    def __getattr__(self, name):
        orig = getattr(self._inner, name)
        if name in self._CAPTURE and callable(orig):
            sink = self._sink

            def _wrapped(event, *a, **kw):
                try:
                    sink.append({"level": name, "event": str(event),
                                 "fields": {k: str(v) for k, v in kw.items()}})
                except Exception:
                    pass
                return orig(event, *a, **kw)

            return _wrapped
        return orig


# ------------------------------------------------------------------- driver

def _make_settings(arm: str, trigger: int, window: int, compression: bool = False):
    overrides = {}
    if arm == "sliding-window":
        overrides = {
            "CONTEXT_COMPRESSION_ENABLED": True,
            "CONTEXT_COMPRESSION_TRIGGER_TOKENS": trigger,
            "CONTEXT_COMPRESSION_WINDOW_TOKENS": window,
        }
    elif arm == "section-reset-jit":
        # The JIT cost arm (bd polyglot-pdf-jnjj.6 / G2): same per-section-reset
        # flow as "section-reset", but build_form_context renders the JIT manifest
        # SI instead of the full per-section field dump.
        overrides = {"USE_JIT_SCHEMA": True}
    elif arm == "dti":
        # The Dynamic Turn Injection cost arm (bd polyglot-pdf-jnjj.25): same
        # per-section-reset flow + JIT-shaped handshake, but USE_DTI makes
        # build_form_context render the TINY DTI SI (static backbone + only the
        # current field's guidance) and each next field's guidance rides the
        # confirm_field tool response (client-supplied; the FakeClient sends the
        # next field's schema on next_field_hint_response). This is the production
        # DTI principal path -- jnjj.22.
        overrides = {"USE_DTI": True}

    # --compression layers calibrated context-window eviction onto the arm (the
    # jnjj.25-folded eviction experiment, formerly jnjj.34). jnjj.25 found DTI's
    # per-field guidance ACCUMULATES within a section, cancelling the SI saving;
    # eviction should purge that stale guidance turn-over-turn. Calibration: the
    # window must EXCEED the unevictable SI+tools floor (~1978 tok for the DTI SI on
    # the I-90) -- else compression fires on turn 1 and the data is incomparable --
    # but be tight enough to evict accumulated guidance; the trigger sits above the
    # window so a couple of fields' guidance must pile up before eviction. Defaults:
    # window 2500 (floor + the current field's guidance headroom), trigger 3500.
    if compression and arm != "sliding-window":
        overrides["CONTEXT_COMPRESSION_ENABLED"] = True
        overrides["CONTEXT_COMPRESSION_TRIGGER_TOKENS"] = trigger
        overrides["CONTEXT_COMPRESSION_WINDOW_TOKENS"] = window

    s = _config.Settings(**overrides)
    # Labeled deviation from deploy config: neutralize server VAD so explicit
    # activity brackets give deterministic synthetic-turn boundaries (bd p1t /
    # h04c precedent). Everything else is the deploy default.
    s.VAD_START_SENSITIVITY = "UNSPECIFIED"
    s.VAD_END_SENSITIVITY = "UNSPECIFIED"
    s.VAD_PREFIX_PADDING_MS = None
    s.VAD_SILENCE_DURATION_MS = None
    return s


class CounterTracker:
    """Per-question deltas over the adapter's cumulative per-modality counters,
    robust to the counter reset a section-restart causes."""

    FIELDS = ("_session_text_input_tokens", "_session_audio_input_tokens",
              "_session_text_output_tokens", "_session_audio_output_tokens",
              "_session_total_tokens")

    def __init__(self, adapter):
        self.adapter = adapter
        self.base = {f: 0 for f in self.FIELDS}

    def snapshot(self) -> dict:
        return {f: getattr(self.adapter, f, 0) or 0 for f in self.FIELDS}

    def delta_and_advance(self) -> dict:
        cur = self.snapshot()
        if cur["_session_total_tokens"] < self.base["_session_total_tokens"]:
            # Session restarted (section switch): counters reset to 0; the new
            # session's whole accumulation since restart belongs to this delta.
            self.base = {f: 0 for f in self.FIELDS}
        delta = {f: cur[f] - self.base[f] for f in self.FIELDS}
        self.base = cur
        return delta


async def _wait_turn(adapter, tracker_field="_session_total_tokens",
                     last=0, timeout=40.0) -> int:
    waited = 0.0
    while waited < timeout:
        await asyncio.sleep(0.5)
        waited += 0.5
        cur = getattr(adapter, tracker_field, 0) or 0
        if cur > last:
            await asyncio.sleep(1.2)  # settle: trailing usage events
            return getattr(adapter, tracker_field, 0) or 0
    return last  # timed out; caller records a stall


async def run(args) -> int:
    if not os.getenv("GEMINI_API_KEY"):
        print("GEMINI_API_KEY not set; cannot run.")
        return 1
    schema = load_schema(args.schema)
    # Default (args.questions is None) runs the WHOLE plan for the chosen schema, so
    # a default --schema i90 run exercises all 3 sections completely (a fixed default
    # of 20 silently truncated the 25-question I-90 plan mid-section-3; fresh-eyes
    # bd jnjj.24). An explicit --questions N still caps the run.
    _all_questions = SCHEMAS[args.schema]["questions"]
    plan = _all_questions if args.questions is None else _all_questions[: args.questions]
    secs = sections_in_plan(schema, plan)

    # Pre-synth all audio (cache-aware).
    utterances = {CONFIRM_YES, REJECT}
    for q in plan:
        utterances.add(q["say"])
        if args.path == "unhappy":
            utterances.add(q["wrong"])
    for u in sorted(utterances):
        synth_cached(u)
    print(f"audio cache ready: {len(utterances)} utterances "
          f"({AUDIO_CACHE})")
    if args.synth_only:
        return 0

    model_name = MODELS[args.model]
    rates = get_pricing_for_model(model_name)
    settings = _make_settings(args.arm, args.trigger, args.window, args.compression)
    # Install the arm's settings so EVERY get_settings() consumer sees it. A bare
    # `_config.get_settings = ...` is NOT enough: modules that did
    # `from backend.config import get_settings` at import time (ai_context,
    # callback_handler, form_filling_service) hold their OWN reference and would
    # keep reading the default flags -- so a `dti`/`section-reset-jit` arm would
    # silently render the wrong SI (bd jnjj.25: the DTI branch never fired under the
    # old single-module swap). Patch the name on _config AND on each by-reference
    # holder on the SI-build path; restore them all in the finally block. (Modules
    # that import get_settings LOCALLY inside a function -- e.g. live_ai_gemini --
    # re-read _config at call time, so the _config swap covers them.)
    import backend.services.ai_context as _ai_context_mod
    import backend.services.callback_handler as _callback_mod
    import backend.services.form_filling_service as _ffs_mod
    _patch_targets = [_config, _ai_context_mod, _callback_mod, _ffs_mod]
    _orig_get_settings = [(m, m.get_settings) for m in _patch_targets if hasattr(m, "get_settings")]
    for m, _ in _orig_get_settings:
        m.get_settings = lambda s=settings: s

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    _comp_tag = "_comp" if args.compression and args.arm != "sliding-window" else ""
    base_name = f"costs_{args.schema}_{args.model}_{args.arm}{_comp_tag}_{args.path}_{stamp}"
    meta: dict = {
        "bead": "polyglot-pdf-4loz", "model": model_name, "tier": args.model,
        "schema": args.schema,
        "arm": args.arm, "path": args.path, "questions": len(plan),
        "compression": bool(args.compression),
        "trigger": args.trigger if (args.arm == "sliding-window" or args.compression) else None,
        "window": args.window if (args.arm == "sliding-window" or args.compression) else None,
        "schema_scope": ("per-section" if args.arm in ("section-reset", "section-reset-jit", "dti") else "full-form"),
        "started": stamp, "turns": [], "per_question_tools": {},
        "prompt_curve": [], "errors": [], "rates_per_token": rates,
        "vad": "neutralized (explicit activity brackets; labeled deviation)",
    }

    log_sink: list[dict] = []
    usage_dumps: list[dict] = []
    tool_log: list[tuple[int, str]] = []
    rows: list[dict] = []
    current_q = {"n": 0}

    try:
        adapter = LiveAIGemini(api_key=os.getenv("GEMINI_API_KEY"), model=model_name)
        adapter.set_session_context(
            form_session_id=f"4loz-{args.arm}-{args.path}-{stamp}",
            form_id=f"INTAKE-{args.schema.upper()}")
        adapter._log = _LogTap(adapter._log, log_sink)
        adapter._on_raw_usage = lambda u: usage_dumps.append({
            "prompt": getattr(u, "prompt_token_count", None),
            "total": getattr(u, "total_token_count", None)})

        service = FormFillingService(live_ai=adapter, settings=settings)

        # Arm-dependent schema scope: section-reset (full-SI baseline) and
        # section-reset-jit (JIT manifest SI) BOTH use the production per-section
        # sub-schema flow; the JIT arm additionally synthesizes the handshake_jit
        # schema (manifest + one-field `fields`) so build_form_context renders the
        # reduced JIT SI (bd polyglot-pdf-jnjj.6). The single-session arms get the
        # whole form (what "no sections" honestly costs with today's SI machinery).
        # section-reset (full-SI baseline), section-reset-jit (JIT manifest SI), and
        # dti (Dynamic Turn Injection) ALL use the production per-section sub-schema
        # flow. section-reset-jit and dti additionally synthesize the JIT-shaped
        # handshake (manifest + one-field `fields`) -- build_form_context renders the
        # JIT SI under USE_JIT_SCHEMA and the tiny DTI SI under USE_DTI (bd jnjj.6/.25).
        is_section_reset = args.arm in ("section-reset", "section-reset-jit", "dti")
        uses_jit_handshake = args.arm in ("section-reset-jit", "dti")
        if is_section_reset:
            sec = secs[0]
            sub = section_subschema(schema, sec["id"])
            if uses_jit_handshake:
                arm_schema = jit_handshake_schema(sub, sec["id"], sec["label"])
            else:
                arm_schema = sub
            si_kwargs = dict(section_number=1, total_sections=len(secs),
                             section_label=sec["label"], previous_spoken_names=[])
            current_section_id = sec["id"]
        else:
            arm_schema = {"form_metadata": schema.get("form_metadata", {}),
                          "fields": schema["fields"]}
            si_kwargs = dict(section_number=1, total_sections=1,
                             section_label="Full Form", previous_spoken_names=[])
            current_section_id = secs[0]["id"]

        client = FakeClientWebSocket(schema, plan, dti_mode=(args.arm == "dti"))
        client.service = service
        if is_section_reset:
            client.set_active_section(
                [q for q in plan
                 if (client.schema_fields[q["field_id"]].get("section_id")
                     or "section-1") == secs[0]["id"]])

        si = service.build_form_context_message(arm_schema, {}, **si_kwargs)
        meta["system_instruction_chars"] = len(si)
        await service.start_session(
            websocket=client, session_id=f"4loz-{stamp}",
            accept_connection=True, schema=arm_schema, current_values={},
            system_instruction=si,
            form_session_id=f"4loz-{args.arm}-{args.path}-{stamp}",
            current_section_id=current_section_id)

        # Tap tool calls AFTER start_session wired the real chain.
        orig_tool_cb = adapter._on_tool_call

        async def _tool_tap(tool_name, arguments):
            tool_log.append((current_q["n"], tool_name))
            return await orig_tool_cb(tool_name, arguments)

        adapter._on_tool_call = _tool_tap

        for _ in range(150):
            if getattr(adapter, "_session_ready", False):
                break
            await asyncio.sleep(0.1)
        else:
            print("session never became ready; aborting")
            meta["errors"] = log_sink
            return 2

        tracker = CounterTracker(adapter)
        last_total = 0

        # Production greeting: initiating message, then the greeting turn.
        await service.send_initiating_message("English", client.next_hint() or "")
        last_total = await _wait_turn(adapter, last=last_total)
        meta["greeting_tokens"] = tracker.snapshot()["_session_total_tokens"]
        tracker.base = tracker.snapshot()

        async def speak(text: str, label: str):
            nonlocal last_total
            pcm = synth_cached(text)
            client.first_audio_at = None
            await service.send_activity_start()
            for chunk in _pcm_chunks(pcm):
                await service.stream_audio(chunk)
                await asyncio.sleep(_CHUNK_MS / 1000.0)
            t_end = time.monotonic()
            await service.send_activity_end()
            new_total = await _wait_turn(adapter, last=last_total)
            stalled = new_total == last_total
            last_total = new_total
            meta["turns"].append({
                "q": current_q["n"], "label": label, "stalled": stalled,
                "latency_s": (round(client.first_audio_at - t_end, 3)
                              if client.first_audio_at and client.first_audio_at > t_end
                              else None)})
            if stalled:
                print(f"    [warn] turn stalled: q{current_q['n']} {label}")

        sec_idx = 0
        for i, q in enumerate(plan, 1):
            current_q["n"] = i
            fid = q["field_id"]
            f_sec = (client.schema_fields[fid].get("section_id") or "section-1")

            # Section boundary (section-reset, section-reset-jit, dti arms):
            # production restart. The JIT-handshake arms (section-reset-jit, dti)
            # rebuild the handshake_jit schema for the new section so the restarted
            # SI is still the reduced JIT SI / tiny DTI SI (jnjj.6 / jnjj.25).
            if is_section_reset and f_sec != secs[sec_idx]["id"]:
                sec_idx += 1
                sec = secs[sec_idx]
                spoken_prev = [client.schema_fields[p["field_id"]].get("name", p["field_id"])
                               for p in plan[: i - 1]]
                client.set_active_section(
                    [p for p in plan
                     if (client.schema_fields[p["field_id"]].get("section_id")
                         or "section-1") == sec["id"]])
                if uses_jit_handshake:
                    switch_schema = jit_handshake_schema(
                        section_subschema(schema, sec["id"]), sec["id"], sec["label"])
                else:
                    switch_schema = section_subschema(schema, sec["id"])
                await service.switch_to_section(
                    switch_schema, {},
                    {"section_id": sec["id"], "section_number": sec["number"],
                     "total_sections": len(secs), "section_label": sec["label"],
                     "previous_spoken_names": spoken_prev},
                    initial_field_hint=client.next_hint())
                for _ in range(150):
                    if getattr(adapter, "_session_ready", False):
                        break
                    await asyncio.sleep(0.1)
                last_total = await _wait_turn(adapter, last=0)  # new-session greeting

            if args.path == "happy":
                await speak(q["say"], "value")
                await speak(CONFIRM_YES, "confirm")
            else:
                await speak(q["wrong"], "wrong-value")
                await speak(REJECT, "reject")
                await speak(q["say"], "corrected-value")
                await speak(CONFIRM_YES, "confirm")

            d = tracker.delta_and_advance()
            ti, ai = d["_session_text_input_tokens"], d["_session_audio_input_tokens"]
            to, ao = d["_session_text_output_tokens"], d["_session_audio_output_tokens"]
            rows.append({
                "question number": i,
                "audio in tokens": ai,
                "audio in token cost": round(ai * rates["audio_input"], 6),
                "audio out tokens": ao,
                "audio out token cost": round(ao * rates["audio_output"], 6),
                "text in tokens": ti,
                "text in token cost": round(ti * rates["text_input"], 6),
                "text out tokens": to,
                "text out token cost": round(to * rates["text_output"], 6),
                "total tokens": ti + ai + to + ao,
                "total cost": round(ti * rates["text_input"] + ai * rates["audio_input"]
                                    + to * rates["text_output"] + ao * rates["audio_output"], 6),
            })
            meta["per_question_tools"][str(i)] = [t for (qq, t) in tool_log if qq == i]
            print(f"[q{i:02d}] {fid}: {rows[-1]['total tokens']} tok "
                  f"(${rows[-1]['total cost']:.4f}) tools={meta['per_question_tools'][str(i)]}",
                  flush=True)

        try:
            await adapter.finalize()
        except Exception:
            pass
    finally:
        for _m, _orig in _orig_get_settings:
            _m.get_settings = _orig

    prompts = [d["prompt"] or 0 for d in usage_dumps]
    meta["prompt_curve"] = prompts
    meta["eviction_drops"] = [[i + 2, prompts[i], prompts[i + 1]]
                              for i in range(len(prompts) - 1)
                              if prompts[i + 1] < prompts[i] - 50]
    meta["errors"] = [s for s in log_sink if s["event"] in _ERROR_EVENTS
                      or s["level"] in ("error", "exception", "critical")]
    meta["client_confirmed_fields"] = [fid for fid, e in client.state.items()
                                       if e.get("confirmed")]

    csv_path = out_dir / f"{base_name}.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    (out_dir / f"{base_name}.meta.json").write_text(
        json.dumps(meta, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {csv_path}")
    print(f"wrote {out_dir / (base_name + '.meta.json')}")
    total = sum(r["total cost"] for r in rows)
    print(f"run total: {sum(r['total tokens'] for r in rows)} tokens, ${total:.4f}; "
          f"evictions detected: {len(meta['eviction_drops'])}; "
          f"confirmed fields: {len(meta['client_confirmed_fields'])}/{len(plan)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Per-question token/cost CSV instrument (bd polyglot-pdf-4loz).")
    ap.add_argument("--model", choices=["2.5", "3.1"], default="2.5")
    ap.add_argument("--schema", choices=["demo", "i90"], default="demo",
                    help="form schema + question plan: 'demo' (the legacy "
                         "adult-intake demo, default for back-compat) or 'i90' "
                         "(the REAL form-kits/i-90 first 3 sections -- the "
                         "production-faithful set; bd polyglot-pdf-jnjj.24)")
    ap.add_argument("--arm",
                    choices=["unbounded", "section-reset", "section-reset-jit", "dti", "sliding-window"],
                    default="unbounded")
    ap.add_argument("--path", choices=["happy", "unhappy"], default="happy")
    ap.add_argument("--questions", type=int, default=None,
                    help="cap the run to the first N questions; default runs the "
                         "WHOLE plan for the chosen --schema (demo=20, i90=25)")
    ap.add_argument("--trigger", type=int, default=12_000,
                    help="sliding-window trigger_tokens; size it ABOVE the "
                         "unevictable SI+tools base (~8.2k on the full-form "
                         "scope) or compression fires on turn 1 and the data "
                         "is incomparable")
    ap.add_argument("--window", type=int, default=9_000,
                    help="sliding-window target_tokens; must exceed the SI "
                         "base for any evictable mass to exist")
    ap.add_argument("--compression", action="store_true",
                    help="layer calibrated context-window eviction onto a non-"
                         "sliding-window arm (the jnjj.25-folded eviction test): "
                         "set --trigger/--window to the arm's SI floor (for the DTI "
                         "SI on i90, ~window 2500 / trigger 3500 -- above the ~1978 "
                         "unevictable SI+tools floor). Lets the accumulated per-field "
                         "guidance be evicted turn-over-turn instead of replayed.")
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parent / "data"))
    ap.add_argument("--synth-only", action="store_true",
                    help="build the audio cache and exit (no live calls)")
    return asyncio.run(run(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
