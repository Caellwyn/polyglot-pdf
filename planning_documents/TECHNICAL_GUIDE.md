# Voice Form Filler - Technical Architecture Guide

**Last Updated**: October 30, 2025
**Purpose**: Technical reference for navigating and understanding the codebase

**Recent Updates**:
- ✅ Hallucination Reduction Features (Oct 30, 2025)
  - Audio preprocessing filters (noise gate + high-pass)
  - Push-to-Talk (PTT) mode as default
  - Single-field tool constraint
  - Enhanced confirmation workflow
  - Proactive audio filtering

---

## Architecture Overview

### Core Principle
> **Client = source of truth for all form state.**  
> Backend stores ONLY schema. All values live in sessionStorage.

**Why**: HIPAA compliance (zero PHI), scalability, simplicity

### Modular Backend Architecture (October 2025 Refactoring)

The backend was refactored from a monolithic 1,660-line service into **6 specialized modules**:

**Benefits Achieved**:
- ✅ **48% code reduction** in main orchestrator (1,660 → 869 lines)
- ✅ **100% test coverage** for extracted modules (107 tests)
- ✅ **Zero breaking changes** - all existing functionality preserved
- ✅ **Improved maintainability** - clear separation of concerns
- ✅ **Better testability** - each module independently testable

**Module Responsibilities**:
1. **FormFillingService** (orchestrator) - Session lifecycle, Gemini integration
2. **CallbackHandler** - Routes Gemini callbacks to appropriate handlers
3. **RequestCoordinator** - Async WebSocket request/response patterns
4. **ValidationHandler** - Field matching, validation, fuzzy search
5. **AudioHandler** - Audio streaming, activity signals
6. **FieldUtils** - Schema processing, field extraction

### System Flow

```
CLIENT (sessionStorage)
├── schema, current_values, session_id
├── DOM (source of truth on conflicts)
└── WebSocket → sends schema/audio/hints

BACKEND (Stateless)
├── Stores schema ONLY (for AI context)
├── Proxies: audio ↔ Gemini, tool calls
└── NEVER stores: field values, PHI

GEMINI LIVE API
└── Audio streams (ephemeral), no persistence
```

---

## Session Lifecycle

### Connection Flow

1. **Handshake**: Client sends schema + optional current_values → Backend stores schema, returns session_id
2. **User-First Protocol**: Connection opens silently with visual greeting carousel. User must speak first
3. **Voice Loop**: User speaks → Gemini calls tools → Backend validates → Client updates → Next hint sent
4. **Idle Timeout**: After 60s inactivity → Backend sends `idle_timeout` → Manual reconnect required
5. **Cleanup**: Tab close = sessionStorage auto-clears

### Connection Management

**WebSocket States**:
```typescript
export type ConnectionStatus = 
  | "disconnected"
  | "connecting"      // WebSocket handshake
  | "connected"       // WebSocket + audio ready
  | "switching_section"
  | "reconnecting"    // Auto-reconnect (errors)
  | "idle_timeout"    // Manual reconnect needed
  | "error";
```

**Idle Timeout Implementation**:
- Backend watchdog checks every 5s for activity
- After 60s idle: sends `idle_timeout` message, closes gracefully
- Frontend sets `idleTimedOut` flag, prevents auto-reconnect
- User must click "Reconnect to Voice" button

---

## Project Structure

### Backend (`backend/`)

**Core Services** (`services/`):
- `form_filling_service.py` - **Orchestrator** (869 lines) - Session lifecycle, Gemini integration, section switching
- `callback_handler.py` - **Event Router** (448 lines) - Gemini Live callbacks (form_update, transcript, audio, tool_call)
- `request_coordinator.py` - **Async Coordinator** (380 lines) - WebSocket request/response patterns with Future-based waiting
- `validation_handler.py` - **Field Validator** (188 lines) - Field matching, fuzzy search, constraint validation
- `audio_handler.py` - **Audio Manager** (163 lines) - Audio streaming, activity signals, context hints
- `field_utils.py` - **Schema Processor** (138 lines) - Field extraction, spoken name handling

**Adapters**:
- `live_ai_gemini.py` - Gemini Live API integration, audio streaming, tool call handling

**Routes**:
- `websocket_routes.py` - WebSocket handlers, idle timeout, message routing

**Utilities**:
- `utils/tool_call_logger.py` - Privacy-safe tool call logging (no PHI)
- `utils/dev_logger.py` - Development-time verbose logging

**Configuration**:
- `config.py` - System instructions, tool definitions, all settings
- `.env` file - Local overrides (dev only)
- Environment variables - Production deployment

**Architecture Benefits**:
- **Separation of Concerns**: Each module has single responsibility
- **Testability**: 107 unit tests for extracted modules (100% pass rate)
- **Maintainability**: 48% code reduction (1,660 → 869 lines in orchestrator)
- **Reusability**: Validation, field matching, and audio logic extracted for reuse

### Frontend (`frontend/`)

**Shared Modules** (`src/shared/`):
- `connection.ts` - WebSocket connection manager
- `audioManager.ts` - Microphone & AI audio playback (16kHz/24kHz PCM16)
- `fieldManager.ts` - Form field updates & manual edit detection
- `config.ts` - Backend URL resolution
- `languages.ts` - 18 spoken + 80 fill languages
- `greetingPrompts.ts` - Carousel phrases

**Demo Application** (`src/demo/`):
- `main.tsx` - React entry point
- `AdultIntakeDemo.tsx` - Main component, stream creation
- `VoiceOverlay.tsx` - Desktop UI
- `VoiceOverlayMobile.tsx` - Mobile UI (FAB design)
- `GreetingCarousel.tsx` - Visual welcome
- `useDemoVAD.ts` - VAD integration hook

**State Management**:
- `webFormState.ts` - Form state (sessionStorage)
- `webFormConnection.ts` - WebSocket message handling

**Schema-Driven Forms** (`schema-forms/`):
- `types/schema.ts` - TypeScript types mirroring backend Pydantic models
- `state/schemaFormState.ts` - Schema form state manager (sessionStorage)
- `components/SchemaForm.tsx` - Main schema-driven form renderer
- `components/SectionRenderer.tsx` - Section-based form rendering
- `components/fields/` - Field-specific renderers (TextField, CheckboxField, etc.)
- `utils/pdfFiller.ts` - Backend PDF filling integration
- `utils/validation.ts` - Client-side validation

---

## PDF Schema Integration (Phase 3A - November 2025)

### Overview

Phase 3A implements round-trip PDF filling for USCIS forms. Users fill schema-driven web forms, which can be exported back to the original PDF with all values populated.

**Key Features**:
- ✅ Backend PDF filling using PyMuPDF (handles XFA forms)
- ✅ Full XFA path mapping (e.g., `form1[0].#subform[0].P1_Line3a_FamilyName[0]`)
- ✅ Stateless passthrough (receives values → fills PDF → returns bytes)
- ✅ Text, date, and select fields working
- ✅ **Radio buttons and checkboxes working** (Nov 4, 2025 - Fixed with direct PDF structure manipulation)

### Architecture Decision: Backend PDF Filling

**Why Backend?**
- XFA (XML Forms Architecture) forms used by USCIS are Adobe-specific
- Frontend libraries (pdf-lib, jsPDF) don't support XFA
- PyMuPDF (backend) handles XFA perfectly

**Flow**:
```
Frontend → POST /api/fill-pdf
  ├── pdf_filename: "i-90.pdf"
  ├── field_values: { "p1_line3a_familyname": "Smith", ... }
  └── form_schema: { fields: [...], ... }

Backend (PyMuPDF)
  ├── Load PDF from disk
  ├── Map schema field IDs → XFA paths
  ├── Fill fields with values
  └── Return filled PDF bytes

Frontend → Download to user
```

**Stateless Design**:
- No user data stored on backend
- Data flow: Request → Process → Response
- Same privacy model as Gemini audio passthrough

### XFA Field Path Structure

USCIS PDFs use hierarchical XFA paths that vary by page/section:

```javascript
// Page 1 fields
"form1[0].#subform[0].P1_Line3a_FamilyName[0]"

// Page 2 fields (different subform)
"form1[0].#subform[1].P1_Line10_CityTownOfBirth[0]"

// Special areas
"form1[0].#subform[0].#area[1].P1_Line1_AlienNumber[0]"
```

**Schema Updates** (Nov 3, 2025):
- I-90 schema updated with full XFA paths in `pdf_field_name` property
- 116 fields mapped successfully (100% coverage)
- Backup saved before modification

### Backend Endpoint: `/api/fill-pdf`

**Location**: `backend/routes/pdf_fill_routes.py`

**Request**:
```python
class PDFFillRequest(BaseModel):
    pdf_filename: str  # e.g., "i-90.pdf"
    field_values: Dict[str, Any]  # field_id → value
    form_schema: Dict[str, Any]  # Full schema with mappings
```

**Process**:
1. Load PDF from `pdf_schema_extractor/test_schemas/test_pdfs/{form}/{filename}`
2. Extract field mappings from schema (`field.id` → `field.pdf_field_name`)
3. Iterate through `field_values`, find widgets in PDF by XFA path
4. Fill widgets using appropriate method (see Field Type Handling below)
5. Set `NeedAppearances` flag for PDF viewer compatibility
6. Save with full rewrite (not incremental) to ensure XFA compatibility
7. Return PDF as bytes with Content-Disposition header

**Response**:
- `200 OK`: PDF bytes (application/pdf)
- `404 Not Found`: PDF file doesn't exist
- `500 Internal Server Error`: Filling failed

### Field Type Handling

**Text, Date, Select Fields** (Standard Method):
```python
widget.field_value = str(value)
widget.update()
```

**Radio Buttons & Checkboxes** (Direct PDF Structure Manipulation):

Due to XFA form limitations in PyMuPDF, button fields require direct manipulation of the PDF's internal structure:

```python
# For XFA forms, we need to set both /V and /AS keys directly
# widget.field_value doesn't persist correctly for XFA
# IMPORTANT: Do NOT call widget.update() after this!
try:
    # Set /V (value) key - the actual field value
    doc.xref_set_key(widget.xref, "V", f"/{target_value}")
    # Set /AS (appearance state) key - tells which appearance stream to use
    doc.xref_set_key(widget.xref, "AS", f"/{target_value}")
except Exception as e:
    # Fallback to widget API (for non-XFA forms)
    widget.field_value = target_value
    widget.update()
```

**Why This Works**:
- XFA forms have two representations: XFA XML data (dynamic) and AcroForm fallback (static)
- PyMuPDF's `widget.field_value` API works with the XFA layer, which doesn't persist correctly
- Direct `xref_set_key()` modifies the AcroForm layer, which persists across save/load cycles
- `/V` stores the actual field value (e.g., `/Y` or `/Off`)
- `/AS` tells the PDF viewer which appearance stream to render
- Skipping `widget.update()` for buttons prevents overwriting these direct modifications

**PDF Object Structure Example**:
```
<<
  /Type /Annot
  /Subtype /Widget
  /FT /Btn
  /V /Y              ← Value key (set via xref_set_key)
  /AS /Y             ← Appearance state (set via xref_set_key)
  /AP << /N << /Off 2476 0 R /Y 2478 0 R >> >>  ← Appearance dictionary (pre-existing)
>>
```

**Button On-State Detection**:
```python
def get_button_on_state(widget) -> str:
    """Extract the 'on' state from a button widget's button_states()"""
    try:
        states = widget.button_states()
        if states and 'normal' in states:
            normal_states = states['normal']
            if isinstance(normal_states, list):
                for state in normal_states:
                    if state and state.lower() not in ['off', '']:
                        return state
    except:
        pass
    return 'Yes'  # Fallback
```

Different PDFs use different on-state values: `Y`, `Yes`, `1`, `1a`, etc. This function extracts the correct value from the widget's appearance dictionary.

**Radio Button Group Handling**:

Radio buttons require setting ALL options in the group (selected + deselected):

```python
for option in radio_group_options:
    is_selected = (option.value == selected_value)
    for widget in find_widgets_for_option(option):
        if is_selected:
            doc.xref_set_key(widget.xref, "V", f"/{on_state}")
            doc.xref_set_key(widget.xref, "AS", f"/{on_state}")
        else:
            doc.xref_set_key(widget.xref, "V", "/Off")
            doc.xref_set_key(widget.xref, "AS", "/Off")
```

This ensures radio button exclusivity (only one selected per group).

**Save Configuration**:
```python
# Set NeedAppearances flag for PDF viewer compatibility
doc.need_appearances(True)

# Save with full rewrite (not incremental)
doc.save(
    temp_path,
    garbage=4,          # Maximum garbage collection
    clean=True,         # Clean up unused objects
    deflate=True,       # Compress streams
    incremental=False,  # Full rewrite (critical for XFA)
    expand=255          # Expand all object streams
)
```

### Frontend Integration

**File**: `frontend/src/schema-forms/utils/pdfFiller.ts`

**Environment Handling**:
```typescript
// Development: http://localhost:8000
// Production: https://voice-form-filler-773443099751.us-central1.run.app
// Override: window.__VFF_BACKEND_URL (auto-converts ws:// → http://)
```

**Usage**:
```typescript
import { fillPDF, downloadPDF } from '../utils/pdfFiller';

const pdfBytes = await fillPDF('/pdfs/i-90.pdf', fieldValues, schema);
downloadPDF(pdfBytes, 'i-90-filled-2025-11-03.pdf');
```

### Testing & Verification

**Tested with i-90 Form** (Nov 4, 2025):
- ✅ Text fields: Family name, given name, etc.
- ✅ Date fields: Date of birth, admission date
- ✅ Select dropdowns: State, country
- ✅ Radio buttons: Gender selection, name change status
- ✅ Checkboxes: Single and group selections
- ✅ Read-only fields: Properly skipped
- ✅ PDF opens correctly in Adobe Reader, Chrome PDF viewer, macOS Preview

**Key Learnings**:

1. **XFA Limitation**: PyMuPDF's `widget.field_value` API doesn't work reliably for XFA button fields. Values revert to 'Off' after save/reopen when using the widget API.

2. **The Fix**: Direct PDF structure manipulation via `doc.xref_set_key()` bypasses the XFA layer and modifies the AcroForm directly, which persists correctly.

3. **Critical Bug**: Calling `widget.update()` AFTER setting xref keys overwrites the direct modifications. Must only call `widget.update()` for non-button fields.

4. **Appearance Streams**: XFA forms have pre-existing appearance dictionaries (`/AP`). The `/AS` key selects which appearance to display. Setting both `/V` and `/AS` ensures visual rendering.

### Future Work

**Additional Forms**:
- Test with other USCIS forms (I-589, N-400, etc.)
- Verify approach works across different XFA implementations
- Handle edge cases (conditional fields, calculated values)

**Complex Field Types**:
- Tables with dynamic rows
- Signature fields
- File attachments
- Barcode generation (if needed)

**Schema Extractor**:
- Currently preserves full XFA paths correctly
- Consider auto-detecting button on-states during extraction
- Add validation for appearance dictionary completeness

---

## Audio Pipeline

### Recording (User → Gemini)
1. getUserMedia: 16kHz mono
2. AudioWorklet: Audio preprocessing + Convert to PCM16
   - **High-pass filter**: 80Hz cutoff (Q=0.7) - removes low-frequency rumble
   - **Noise gate**: -40dB threshold (gentle) - filters background noise while preserving quiet speakers
   - **PCM16 conversion**: Float32 → Int16 for Gemini
3. VAD: Detect speech start/end (or PTT manual control)
4. WebSocket: Send base64 chunks
5. Backend: Forward to Gemini Live

### Playback (Gemini → User)
1. Gemini: 24kHz PCM16 audio
2. Backend: Forward via WebSocket
3. Frontend: Decode base64
4. AudioContext: Play at 24kHz
5. Barge-in: Stop on user speech

### Input Modes

**Push-to-Talk (PTT) - Default Mode** (Oct 30, 2025):
- User manually controls audio transmission via button/spacebar
- Mic stays recording but sends silence when button not pressed
- Gemini's automatic VAD processes audio only during button press
- **Desktop**: Toggle switch (🎤 Auto / ⌨️ PTT) + PTT button + Spacebar hotkey
- **Mobile**: Toggle switch + full-width bar button
- **Why default**: Reduces false positives, gives users explicit control

**Auto VAD Mode** (Optional):
- **Model**: @ricky0123/vad-web (Silero)
- **Thresholds**: 0.90 positive, 0.70 negative
- **Pre-buffer**: 700ms (full VAD window)
- **Barge-in delay**: 450ms validation
- **Assets**: Self-hosted on GCS (~5MB)
- User can toggle back to this mode if preferred

---

## Gemini Integration

### Configuration

**Model**: `gemini-2.0-flash-exp` (always use latest)

**Session Config**:
```python
config = {
    "response_modalities": ["AUDIO"],
    "tools": tools_config,
    "proactivity": {
        "proactive_audio": True  # Ignore dirty/choppy audio, background conversation
    },
    "realtime_input_config": {
        "automatic_activity_detection": vad_settings  # Gemini's server-side VAD
    },
    "input_audio_transcription": {},   # Optional: See what Gemini hears
    "output_audio_transcription": {},  # Optional: See Gemini's responses
    "system_instruction": system_instruction
}
```

**Key Settings** (Oct 30, 2025):
- `proactive_audio: True` - Helps Gemini ignore irrelevant/noisy audio inputs
- Server-side VAD controlled via `DISABLE_GEMINI_VAD`, `VAD_START_SENSITIVITY`, `VAD_END_SENSITIVITY` in config
- System instruction emphasizes single-field updates and mandatory confirmation

### Manual Activity Signals

**Critical**: When using manual `activity_start`/`activity_end`, set `DISABLE_GEMINI_VAD = True`

**Signal Flow**:
1. Frontend: `connectionManager.sendActivityStart()`
2. WebSocket: `{type: 'vad_activity_start'}`
3. Backend: Routes to service → adapter
4. Adapter: `session.send_realtime_input(activity_start=...)`
5. Gemini: Processes turn between signals

### Tool Definitions

**update_form_fields** (Oct 30, 2025 - Single-Field Only):
```json
{
  "field_id": "firstName",  // Exact field ID from schema
  "value": "John"           // Field value (string, boolean, or allowed_value)
}
```
- **CRITICAL**: Updates EXACTLY ONE field per call (no batch updates)
- Returns next field hint embedded in response
- Backend validates, rejects 0 or 2+ field calls
- Validation errors include specific constraints and allowed values
- Fuzzy matching suggestions when field names don't match
- **Why single-field**: Multi-field updates correlated with 5-10x higher hallucination rates
- **Workflow**: Ask → Update → Confirm → Next (mandatory confirmation step)

**get_form_status**:
- Query current form state
- Includes greeting for latency coverage
- Returns section progress

**get_field_value**:
- Look up field value by spoken name from any section
- Uses fuzzy matching (rapidfuzz) for typo tolerance
- Distinguishes between "field exists but empty" vs "field doesn't exist"
- Returns actionable error messages with suggestions:
  - Close match: "Did you mean 'Phone Number'?"
  - Multiple matches: Lists top 3 similar field names
  - No matches: Shows available field names
- Threshold: 52% similarity (same as PDF field normalization)

**switch_section**:
- Navigate between form sections by number or label
- Gracefully restarts Gemini session with new context
- Preserves completed section data

**complete_section**:
- Mark current section complete and advance
- Requires user confirmation per policy
- Handles final section (no auto-advance)

### System Instructions

**Structure**:
1. Persona & role
2. Conversational rules (ordered steps)
3. Tool specifications (when to invoke)
4. Guardrails (what NOT to do)

**Templates** (`backend/config.py`):
- `SYSTEM_INSTRUCTION`: Full form-filling rules
- `INITIATING_MESSAGE`: Language selection prompt
- Tool descriptions with invocation conditions

---

## Hallucination Reduction (October 30, 2025)

### Overview

Comprehensive changes to minimize AI hallucinations and improve accuracy, targeting < 1% hallucination rate (from baseline ~5-10%).

### Problem Patterns Addressed

1. **Missing Confirmations**: Gemini skipping verbal confirmation before moving to next field
2. **Phantom Field Filling**: Filling fields without user input (e.g., "Last Name: Doe" after language change)
3. **Incorrect Values**: Recording wrong values and not reading them back
4. **Background Noise**: Responding to irrelevant audio, background conversation

### Solution: 5-Layer Defense

#### 1. Audio Preprocessing (Frontend)
**Location**: `frontend/src/shared/audio-processor.worklet.ts`

**Filters Applied Before VAD**:
- **High-Pass Filter**: 80Hz cutoff, Q=0.7 (Biquad IIR)
  - Removes low-frequency rumble (HVAC, traffic, handling noise)
  - Preserves speech frequencies (100Hz+)
- **Noise Gate**: -40dB threshold (gentle)
  - Filters background noise during pauses
  - Preserves quiet speakers (threshold chosen to avoid false positives)

**Pipeline**: Raw Audio → High-Pass → Noise Gate → PCM16 Conversion → VAD/PTT

#### 2. Push-to-Talk (PTT) Mode - Default
**Location**: `frontend/src/demo/VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`

**Why Default**: Explicit user control eliminates:
- False VAD triggers
- Accidental barge-ins
- Background conversation pickup

**UI Components**:
- Desktop: Toggle switch (🎤 Auto / ⌨️ PTT) + PTT button + Spacebar hotkey
- Mobile: Toggle switch + full-width bar button (optimized for touch)

**Behavior**:
- Mic stays recording (for heartbeat/connection)
- Sends silence when button not pressed
- Sends real audio when button pressed
- User can toggle back to Auto VAD if preferred

#### 3. Single-Field Tool Constraint (Backend)
**Location**: `backend/config.py`, `backend/services/callback_handler.py`

**Change**: `update_form_fields` now accepts exactly ONE field per call

**Old Format** (commented out):
```json
{
  "updates": {
    "firstName": "John",
    "lastName": "Smith"
  }
}
```

**New Format** (Oct 30, 2025):
```json
{
  "field_id": "firstName",
  "value": "John"
}
```

**Rationale**: Multi-field updates correlated with 5-10x higher hallucination rates. Single-field forces:
- Deliberate field-by-field processing
- Individual confirmation per field
- Clear error attribution

**Validation**: Backend rejects tool calls with 0 or 2+ fields

#### 4. Mandatory Confirmation Workflow (System Instruction)
**Location**: `backend/config.py` - `SYSTEM_INSTRUCTION`

**8-Step Workflow** (enforced in prompt):
1. Ask user for ONE field
2. User responds with value
3. **IMMEDIATELY** call `update_form_fields` with that ONE field
4. **Read back** the value in user's spoken language
5. **Ask** "Is that correct?" or similar confirmation
6. **Wait** for user confirmation (yes/no)
7. If yes → move to next field; If no → ask for correction, repeat from step 3
8. Never skip steps 4-6 (read back + confirmation + wait)

**Examples Added to Prompt**:
- Correct workflow example (phone number with confirmation)
- Incorrect example (trying to batch firstName + lastName) marked with ❌
- Emphasis on reading back in user's language (critical for non-English speakers)

**Guardrails**:
- NEVER guess or assume field values
- NEVER fill a field without user explicitly providing information
- NEVER move to next field without confirmation
- NEVER skip the read-back step

#### 5. Proactive Audio Filtering (Gemini API)
**Location**: `backend/adapters/live_ai_gemini.py`, `backend/config.py`

**Setting**: `PROACTIVE_AUDIO = True`

**API Config**:
```python
config["proactivity"] = {
    "proactive_audio": True
}
```

**Purpose**: Helps Gemini ignore:
- Choppy/corrupted audio packets
- Background conversations
- Irrelevant ambient sounds
- Low-quality audio segments

**Combined with**: Audio preprocessing filters (layer 1) for comprehensive noise rejection

### Expected Results

**Target Metrics**:
- **Hallucination Rate**: < 1% (from ~5-10%)
- **Confirmation Rate**: 100% (verbal confirmation for every field)
- **Accuracy Rate**: > 99% (with user verification)
- **Background Noise Rejection**: Significantly improved

**Monitoring**:
- Log confirmation workflow completion rate
- Track tool call rejections (0 or 2+ fields)
- Monitor user corrections per field (should decrease)
- Audio filter diagnostics in worklet logs

### Rollback Strategy

All old code preserved with comments and markers:

```python
# HALLUCINATION_REDUCTION (Oct 30, 2025): [Description]
# May revert if single-field proves too restrictive
# OLD CODE:
# [commented out code here]
# NEW CODE:
[new code here]
```

**Rollback Steps**:
1. Uncomment old code sections
2. Update tool definition back to multi-field
3. Revert system instruction changes
4. Set `PROACTIVE_AUDIO = False`
5. Remove audio filters from worklet

**Files with Rollback Markers**:
- `backend/config.py` (tool definition, system instruction)
- `backend/services/callback_handler.py` (argument parsing)
- `frontend/src/demo/VoiceOverlay.tsx` (PTT default)
- `frontend/src/demo/VoiceOverlayMobile.tsx` (PTT default)

### Testing

**Unit Tests**: ✅ All 81 tests passing (no breaking changes)

**Manual Testing Required**:
- [ ] Audio filters with quiet speakers
- [ ] Audio filters with background noise
- [ ] PTT mode on desktop (button + spacebar)
- [ ] PTT mode on mobile (bar button)
- [ ] Single-field validation rejects multi-field calls
- [ ] Confirmation workflow enforced (read back + confirm)
- [ ] Non-English language confirmation (Spanish, etc.)
- [ ] Proactive audio ignores background conversation

### Reference

See `planning_documents/HALLUCINATION_REDUCTION_PLAN.md` for full implementation details.

---

## Language Support

### Spoken Languages (18 confirmed)
English, Spanish, French, German, Italian, Portuguese, Dutch, Polish, Russian, Japanese, Korean, Mandarin Chinese, Hindi, Arabic, Turkish, Swedish, Norwegian, Danish

### Implementation
- **Frontend dropdown**: `SPOKEN_LANGUAGES` in `languages.ts`
- **Backend handler**: `change_spoken_language` message
- **Gemini prompt**: `INITIATING_MESSAGE` template
- **Persistence**: Stored in service `_spoken_language`

---

## Environment Setup

### Backend Configuration

**Authentication Methods**:

1. **Vertex AI** (recommended):
```bash
gcloud auth application-default login
# No API key needed in .env
```

2. **Google AI Studio** (alternative):
```bash
# In backend/.env:
GEMINI_API_KEY=your-api-key-here
```

**Development Settings** (`backend/.env`):
```bash
VFF_DEV_LOGGING=true  # Verbose tool call logging
# Optional:
GOOGLE_CLOUD_PROJECT=your-project-id
```

### Frontend Configuration

**URLs Resolution** (`frontend/src/shared/config.ts`):
1. `window.__VFF_LOCAL_DEV` (runtime override)
2. `import.meta.env.VITE_WS_URL` (build-time)
3. `ws://localhost:8000/ws/fill` (default)

**Build Variables**:
```bash
# Local dev
VITE_WS_URL=ws://localhost:8000/ws/fill

# Production build
VITE_WS_URL=wss://your-backend.run.app/ws/fill npm run build:demo
```

---

## Security Patterns

### HIPAA Compliance
- **Never log PHI**: Only log field IDs, types, counts
- **sessionStorage only**: Auto-clears on tab close
- **Stateless backend**: No value storage
- **Ephemeral audio**: Real-time processing only
- **TLS everywhere**: WSS/HTTPS required

### XSS Prevention
```javascript
// NEVER do this:
element.innerHTML = userContent;

// ALWAYS do this:
element.textContent = userContent;
// OR
element.innerHTML = escapeHtml(userContent);
```

### CORS Configuration
```python
# Development
ALLOWED_ORIGINS = ["*"]  # OK for local testing

# Production - MUST restrict!
ALLOWED_ORIGINS = ["https://your-domain.com"]
```

---

## Testing Strategies

### Module Unit Tests

**Extracted Services** (107 tests, 100% passing):
```bash
# Test individual modules
pytest backend/tests/test_field_utils.py -v           # 24 tests - Schema processing
pytest backend/tests/test_validation_handler.py -v    # 20 tests - Field validation
pytest backend/tests/test_audio_handler.py -v         # 24 tests - Audio streaming
pytest backend/tests/test_request_coordinator.py -v   # 26 tests - Async coordination
pytest backend/tests/test_callback_handler.py -v      # 13 tests - Event routing

# Run all module tests
pytest backend/tests/test_*.py -v
```

**Module Test Coverage**:
- ✅ **field_utils.py**: Schema parsing, spoken name extraction, fuzzy field matching
- ✅ **validation_handler.py**: Field updates, constraint validation, error formatting
- ✅ **audio_handler.py**: Audio streaming, activity signals, context hints, manual updates
- ✅ **request_coordinator.py**: WebSocket request/response, timeout handling, concurrent requests
- ✅ **callback_handler.py**: Tool routing, argument parsing, error responses

### Integration Tests
```bash
# Backend integration (178/206 passing)
pytest backend/tests/unit/ -v                        # FormFillingService tests
pytest backend/tests/unit/test_idle_timeout.py       # Idle timeout behavior
pytest backend/tests/integration/ -v                 # WebSocket flows

# Frontend
cd frontend && npm test -- --run
```

### Manual Testing Checklist
1. **Connection**: Verify session_id appears
2. **Audio**: Speech recorded and played back
3. **Fields**: Updates show green outline
4. **State**: Refresh preserves form data
5. **Barge-in**: Interruption stops TTS <50ms
6. **Idle**: 60s timeout shows reconnect button

### VAD Tuning Lab
```bash
cd frontend
npm run build:bookmarklet
npx vite --port 5173
# Open http://localhost:5173/vad-tuning-lab.html
```

**Target Metrics**:
- P95 Latency < 180ms
- Avg Latency < 150ms
- Hallucination Rate < 1%
- False Start Rate < 3%

---

## Production Configuration

### Critical Settings (`backend/config.py`)

**Connection Limits**:
- `WS_IDLE_TIMEOUT_SEC = 60` - Idle disconnect
- `MAX_SESSION_DURATION = 3600` - 1 hour max
- `MAX_CONNECTIONS_PER_IP = 3` - Rate limiting

**Audio Settings**:
- `MAX_AUDIO_CHUNK_SIZE = 64000` - ~2 seconds
- `AUDIO_STREAM_TIMEOUT = 30` - Streaming limit
- `MAX_SILENCE_BEFORE_INTERRUPT = 1.0` - Barge-in

**Tool Call Limits**:
- `MAX_TOOL_CALLS_PER_MINUTE = 30`
- `MAX_CONSECUTIVE_TOOL_ERRORS = 5`
- `MAX_FIELD_UPDATES_PER_CALL = 10`

### Monitoring Alerts

**Set up in Cloud Monitoring**:
- Error rate > 5% of requests
- Session timeout rate > 20%
- Rate limit hits > 10%
- Reconnection rate > 30%

### Deployment Checklist

- [ ] VAD assets downloaded (`download-vad-assets.sh`)
- [ ] ALLOWED_ORIGINS restricted
- [ ] LOG_LEVEL set to INFO
- [ ] Rate limits configured
- [ ] Gemini model name verified
- [ ] Monitoring alerts set up
- [ ] Budget alerts configured

---

## Logging Architecture

### Overview

**Design Principle**: HIPAA-compliant structured logging with zero PHI in production, detailed debugging in development.

**Dual-Mode System**:
- **Production**: Structured JSON logs → stdout → Cloud Run → BigQuery
- **Development**: Daily `.jsonl` files with full Gemini message logs

### Backend Logging (`backend/utils/`)

**Three-Layer Architecture**:

1. **`structured_logger.py`** - Production logging
   ```python
   from backend.utils.structured_logger import get_logger

   logger = get_logger(client_id="demo")
   logger.log_ws_connect(form_id, form_version, form_session_id, ws_session_id)
   logger.log_gemini_api_response(form_id, form_version, form_session_id, ws_session_id, metadata)
   ```
   - Outputs to stdout in Cloud Run format
   - NO PHI - only metadata (field IDs, counts, timestamps)
   - Ready for BigQuery ingestion

2. **`dev_file_logger.py`** - Development debugging
   ```python
   from backend.utils.dev_file_logger import get_dev_logger

   dev_logger = get_dev_logger()
   dev_logger.log_tool_call(tool_name, arguments, session_id)
   dev_logger.log_tool_response(tool_name, response, session_id)
   ```
   - Only active when `VFF_DEV_LOGGING=true`
   - Daily rotation: `backend/logs/gemini_YYYY-MM-DD.jsonl`
   - Includes full Gemini messages (tool calls, responses)
   - Errors always output to terminal

3. **`log_schemas.py`** - TypedDict event schemas
   ```python
   class TokenUsageMetadata(TypedDict, total=False):
       prompt_token_count: int
       candidates_token_count: int
       text_input_tokens: int
       audio_input_tokens: int
       ...
   ```

### Token Tracking (October 2025)

**Real-time cost visibility** with TEXT vs AUDIO modality breakdown:

**Pricing (per token)**:
```python
GEMINI_PRICING = {
    "text_input": $0.50 / 1M   = $0.0000005
    "audio_input": $3.00 / 1M  = $0.000003  # 6x text!
    "text_output": $2.00 / 1M  = $0.000002
    "audio_output": $12.00 / 1M = $0.000012 # 6x text!
}
```

**Log Output**:
```json
{
  "event": "gemini_tokens",
  "total_tokens": 1730,
  "prompt_tokens": 1250,
  "response_tokens": 480,

  "text_input": 1200,
  "audio_input": 50,
  "text_output": 20,
  "audio_output": 460,

  "total_cost_usd": 0.00631000,
  "audio_output_cost": 0.00552000,
  "text_input_cost": 0.00060000,

  "session_total_tokens": 5420,
  "session_total_cost_usd": 0.01850000
}
```

**Key Insight**: Audio output typically dominates costs (6-12x more expensive than text).

### Frontend Logging (Planned)

**Client-Side Detailed Log**:
- sessionStorage with PHI allowed (stays local)
- Field change tracking: `{timestamp, fieldId, oldValue, newValue, source: "ai"|"manual"}`
- Sanitized events batched and sent to backend (NO values)
- Auto-clears on tab close

### Log File Structure

```
backend/logs/
├── gemini_2025-10-24.jsonl    # Today's dev logs
├── gemini_2025-10-23.jsonl    # Yesterday
└── gemini_2025-10-22.jsonl    # Older (manual cleanup)
```

**Format**: JSON Lines (one event per line)
```jsonl
{"timestamp": "2025-10-24T12:34:56Z", "direction": "send", "message_type": "tool_response", ...}
{"timestamp": "2025-10-24T12:34:57Z", "direction": "receive", "message_type": "tool_call", ...}
```

**Analysis**:
```python
import pandas as pd
df = pd.read_json('backend/logs/gemini_2025-10-24.jsonl', lines=True)
```

### Security Guarantees

**Backend (Production)**:
- ❌ NEVER logs field values
- ✅ Logs: field IDs, session IDs, timestamps, token counts, costs
- ✅ Structured JSON ready for BigQuery filtering

**Backend (Development)**:
- ⚠️  May log tool arguments (contains field values)
- ✅ Only when `VFF_DEV_LOGGING=true`
- ✅ Files stored locally, not in version control

**Frontend**:
- ✅ PHI allowed (stays in browser sessionStorage)
- ✅ Auto-clears on tab close
- ✅ Only metadata sent to backend

### Environment Variables

```bash
# Development - detailed Gemini message logging
VFF_DEV_LOGGING=true

# Production - structured JSON only
VFF_DEV_LOGGING=false  # or unset
```

### Usage Examples

**Tracking session costs**:
```python
# In live_ai_gemini.py - automatic per API response
# Logs show cumulative burn rate
session_total_cost_usd=0.01850000  # Running total
```

**Debugging tool calls** (dev mode only):
```bash
# View today's tool calls
grep "tool_call" backend/logs/gemini_$(date +%Y-%m-%d).jsonl | jq .
```

**Production monitoring**:
```sql
-- BigQuery query (future)
SELECT
  form_id,
  SUM(total_cost_usd) as total_cost,
  AVG(audio_output_tokens) as avg_audio_output
FROM logs
WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY form_id
ORDER BY total_cost DESC
```

---

## Code Patterns

### Async Request/Response
```python
# Backend requests data from frontend
await self.connection.send_json({"type": "get_form_status"})
response = await self.connection.receive_json()
```

### State Management
```javascript
// Client always source of truth
const formData = sessionStorage.getItem('formData');
if (!formData) {
  // Initialize from DOM
}
```

### Error Handling
```python
try:
    # Gemini operation
except Exception as e:
    logger.error(f"Operation failed: {e}")
    # Never log field values!
    # Continue gracefully
```

---

## Recent Improvements (October 2025)

### Field Query Robustness (`get_field_value`)

**Problem Solved**: Gemini previously received generic errors when querying non-existent or misspelled field names, leading to confusion and failed lookups.

**Improvements**:

1. **Fuzzy Matching with RapidFuzz**:
   - Uses `token_sort_ratio` scorer (robust to word order)
   - 52% similarity threshold (consistent with PDF field normalization)
   - Catches common variations: "phone" → "Phone Number", "dob" → "Date of Birth"

2. **Clear State Distinction**:
   - **Field exists + filled**: Returns value with confirmation message
   - **Field exists + empty**: `found: true, value: null` with prompt to fill
   - **Field doesn't exist**: `found: false` with suggestions or available fields

3. **Actionable Error Messages**:
   ```json
   // Single close match
   {"message": "Could not find 'phone'. Did you mean 'Phone Number'? Try asking about that field instead."}
   
   // Multiple matches
   {"message": "Could not find 'name'. Did you mean: 'First Name', 'Last Name', 'Full Name'?"}
   
   // No matches
   {"message": "Could not find 'favorite color'. Available fields: 'First Name', 'Last Name'..."}
   ```

4. **Tool Declaration Updates**:
   - Emphasizes using EXACT field names from schema/previous sections
   - Provides clear examples in description
   - System instruction shows proper usage patterns

**Implementation**:
- `backend/services/form_filling_service.py`: `_find_similar_field_names()`, `_get_available_spoken_names()`
- `backend/config.py`: Enhanced tool description and system instruction
- `frontend/src/webFormConnection.ts`: Sends `found: true` for empty fields (distinguishes from missing)
- `backend/routes/websocket_routes.py`: Added `field_value_response` control message handler

**Testing Scenarios**:
- ✅ Exact match (any case)
- ✅ Common abbreviations (phone, dob, etc.)
- ✅ Typos within 40% edit distance
- ✅ Empty field vs. non-existent field
- ✅ Multiple similar field names

### Race Condition Fix: Message Queuing (October 23, 2025)

**Problem Solved**: Messages sent to Gemini immediately after session creation were being dropped because the session wasn't ready yet. This affected section switching and language changes on initial connection.

**Root Cause**:
- `send_client_content()` called immediately after `start_session()`
- Gemini's `setupComplete` arrives ~2 seconds later
- Messages sent before `setupComplete` were dropped with warning: `⚠️ SEND_CLIENT_CONTENT_NO_SESSION`

**Solution**:

1. **Session Readiness Tracking**:
   - Added `_session_ready` flag (starts `False`, set `True` when session established)
   - Added `_pending_client_content` queue for messages sent before ready

2. **Message Queuing**:
   - `send_client_content()` checks if session is ready
   - Queues messages if not ready (logs: `📋 CLIENT_CONTENT_QUEUED`)
   - Sends immediately if ready

3. **Automatic Flushing**:
   - After `setupComplete`, set `_session_ready = True`
   - Send all queued messages in order (logs: `📤 SENDING_QUEUED_CLIENT_CONTENT`)
   - Clear queue after sending (logs: `✅ QUEUED_CLIENT_CONTENT_SENT`)

4. **Cleanup**:
   - Reset `_session_ready = False` in `finalize()`
   - Clear pending queue

**Implementation**:
- `backend/adapters/live_ai_gemini.py`: Added flag, queue, and flushing logic

**Affected Scenarios**:
- ✅ Section switching: Initiating message now reliably sent
- ✅ Language changes on initial load: No longer lost if user clicks quickly
- ✅ Any `send_client_content()` calls during session startup

### Next Field Hint Enhancement (October 23, 2025)

**Problem Solved**: Gemini didn't always know which field to ask about next, leading to generic responses or silence after field updates.

**Issues Fixed**:

1. **Initial Connection**:
   - Handshake didn't include `initial_field_hint`
   - Gemini had to guess where to start

2. **Manual Field Updates**:
   - No `next_field_hint` sent with manual update notification
   - Gemini acknowledged update but didn't guide user to next field

3. **Language Change Bug**:
   - `computeNextField()` called with wrong parameters
   - Returned `null`, fallback was "all fields are complete"
   - Gemini thought there was nothing to do

**Solution**:

1. **Handshake Enhancement** (`frontend/src/webFormState.ts`):
   - `getHandshakePayload()` now computes `initial_field_hint` on page load
   - Uses `computeNextField()` and `formatNextFieldHint()`
   - Gemini knows exactly where to start from first connection

2. **Manual Field Update Enhancement** (`frontend/src/webFormConnection.ts`):
   - `sendManualFieldUpdate()` now computes `next_field_hint` after each manual edit
   - Backend appends hint to notification message
   - Gemini guides user to next field after manual updates

3. **Language Change Fix**:
   - Changed `computeNextField(state.schema, state.current_values)` → `computeNextField(state)`
   - Fixed in both `VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx`
   - Now correctly finds next unfilled field

**Implementation**:
- `frontend/src/webFormState.ts`: Added imports and initial hint computation
- `frontend/src/webFormConnection.ts`: Added next hint to manual updates
- `backend/routes/websocket_routes.py`: Extract and pass next_field_hint
- `backend/services/form_filling_service.py`: Accept and append next_field_hint
- `frontend/src/demo/VoiceOverlay.tsx`: Fixed computeNextField parameters
- `frontend/src/demo/VoiceOverlayMobile.tsx`: Fixed computeNextField parameters

**Result**:
All Gemini communications now include next field guidance:
- ✅ Initial connection (handshake)
- ✅ Section switching (already working)
- ✅ Language changes (already working)
- ✅ Tool responses (already working)
- ✅ Manual field updates (new)

---

## Common Gotchas

1. **VAD Conflict**: If using manual signals, MUST set `DISABLE_GEMINI_VAD = True`
2. **Audio Context**: Safari requires user gesture to start audio
3. **Field IDs**: Gemini sometimes adds quotes - strip them
4. **Reconnect Loops**: Check for idle timeout flag
5. **Silent Connection**: No audio until user speaks first
6. **Stream Timing**: Create stream in parent before overlays render

---

## Next Steps for Development

1. **System Instructions**: Refine confirmation workflow
2. **Form Library**: Pre-map common medical forms
3. **Error Recovery**: Improve correction flows
4. **Performance**: Optimize token usage
5. **Testing**: Expand integration test coverage
