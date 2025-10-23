# Voice Form Filler - Technical Architecture Guide

**Last Updated**: October 22, 2025  
**Purpose**: Technical reference for navigating and understanding the codebase

---

## Architecture Overview

### Core Principle
> **Client = source of truth for all form state.**  
> Backend stores ONLY schema. All values live in sessionStorage.

**Why**: HIPAA compliance (zero PHI), scalability, simplicity

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

**Core Files**:
- `config.py` - System instructions, tool definitions, all configuration
- `services/form_filling_service.py` - Business logic, state management
- `adapters/live_ai_gemini.py` - Gemini Live API integration
- `routes/websocket_routes.py` - WebSocket handlers, idle timeout

**Configuration Layers**:
1. `config.py` - Default values (production-safe)
2. `.env` file - Local overrides (dev only)
3. Environment variables - Production deployment

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

---

## Audio Pipeline

### Recording (User → Gemini)
1. getUserMedia: 16kHz mono
2. AudioWorklet: Convert to PCM16
3. VAD: Detect speech start/end
4. WebSocket: Send base64 chunks
5. Backend: Forward to Gemini Live

### Playback (Gemini → User)
1. Gemini: 24kHz PCM16 audio
2. Backend: Forward via WebSocket
3. Frontend: Decode base64
4. AudioContext: Play at 24kHz
5. Barge-in: Stop on user speech

### VAD Configuration
- **Model**: @ricky0123/vad-web (Silero)
- **Thresholds**: 0.90 positive, 0.70 negative
- **Pre-buffer**: 700ms (full VAD window)
- **Barge-in delay**: 450ms validation
- **Assets**: Self-hosted on GCS (~5MB)

---

## Gemini Integration

### Configuration

**Model**: `gemini-2.0-flash-exp` (always use latest)

**Session Config**:
```python
config = {
    "generation_config": {
        "response_modalities": ["AUDIO"],
        "speech_config": {
            "voice_config": {"prebuilt_voice_config": {"voice_name": "Aoede"}},
        },
    },
    "automatic_activity_detection": {"disabled": True},  # For manual signals
    "tools": [update_form_fields_tool, get_form_status_tool]
}
```

### Manual Activity Signals

**Critical**: When using manual `activity_start`/`activity_end`, set `DISABLE_GEMINI_VAD = True`

**Signal Flow**:
1. Frontend: `connectionManager.sendActivityStart()`
2. WebSocket: `{type: 'vad_activity_start'}`
3. Backend: Routes to service → adapter
4. Adapter: `session.send_realtime_input(activity_start=...)`
5. Gemini: Processes turn between signals

### Tool Definitions

**update_form_fields**:
- Batch field updates
- Returns next field hint embedded
- Backend validates, rejects empty calls
- Validation errors include specific constraints and allowed values
- Fuzzy matching suggestions when field names don't match

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

### Unit Tests
```bash
# Backend (69/73 passing)
pytest backend/tests/unit/ -v
pytest backend/tests/unit/test_idle_timeout.py

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
