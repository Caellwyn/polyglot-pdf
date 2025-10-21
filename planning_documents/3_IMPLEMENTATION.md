# Implementation Guide

Last Updated: October 18, 2025  
Status: Phase 2 COMPLETE + Token Optimization + Delayed Barge-In + Audio Fallback + User-First Protocol

---

## User-First Protocol (October 18, 2025)

**Design**: Patient-led interaction - user speaks first after connection.

**Implementation**:

**Backend** (`backend/adapters/live_ai_gemini.py`):
- Lines 603-670: Entire initial message block commented out
- Connection opens silently
- Gemini waits for user to initiate conversation
- Comment header explains user-first model and references

**Frontend** (`frontend/src/demo/VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx`):
- **Greeting Carousel**: Visual welcome component
  - Shows rotating friendly prompts (3-second intervals)
  - Examples: "Hi! I'm here to help", "Just start speaking"
  - Non-audio, non-intrusive guidance
  - Auto-dismisses when user or Gemini speaks
  - `carouselDismissedRef` prevents re-showing after dismissal
- **Collapsible Overlay**: 
  - Collapse button (▲/▼) in header
  - `isCollapsed` state hides panel body
  - CSS transition for smooth animation
  - Prevents blocking form fields when expanded

**Benefits**:
- Reduces patient anxiety (no immediate AI voice)
- User controls conversation start
- Better for multilingual scenarios (time to gather thoughts)
- Visual guidance without audio pressure
- Cleaner, more flexible UI

**Code Locations**:
- Backend: `backend/adapters/live_ai_gemini.py:603-670`
- Desktop overlay: `frontend/src/demo/VoiceOverlay.tsx:49-50, 280-291`
- Mobile overlay: `frontend/src/demo/VoiceOverlayMobile.tsx:42, 284-295`
- Greeting component: `frontend/src/demo/GreetingCarousel.tsx`

---

## Token Optimization (Next Field Hint)

**Implemented**: October 12, 2025  
**Updated**: October 14, 2025 (Handshake-based initialization)  
**Goal**: Reduce token usage by 50% by eliminating separate model turns for field navigation.

### Architecture Pattern: Handshake + Async Request/Response

**Initial Field Hint** (session start):
Frontend computes hint synchronously before connection and includes in handshake:

```typescript
// Frontend computes hint before connection
const initial_field_hint = computeNextFieldHintString(
    schema, 
    current_values
);

// Frontend includes in handshake
await websocket.send({
    type: "handshake",
    schema: schema,
    current_values: current_values,
    initial_field_hint: initial_field_hint  // Pre-computed
});

// Backend extracts synchronously (no async request needed)
initial_field_hint = message.get("initial_field_hint")
if initial_field_hint:
    initial_message = f"{initial_message} {initial_field_hint}"
else:
    initial_message = f"{initial_message} the first unfilled field."
```

**Subsequent Field Hints** (after updates):
Backend and frontend use async request/response pattern for stateless hint computation:

```typescript
// Backend sends request
await websocket.send_json({
    type: "get_next_field_hint",
    request_id: "uuid-123"
})

// Backend awaits response
future = asyncio.Future()
pending_requests[request_id] = future
hint = await asyncio.wait_for(future, timeout=2.0)

// Frontend computes and responds
websocket.send_json({
    type: "next_field_hint_response", 
    request_id: "uuid-123",
    hint: "Next unfilled field: email (Email)"
})

// Backend resolves future
future.set_result(hint)
```

### Two Integration Points

**1. Initial Message** (session start):
- Frontend: `computeNextFieldHintString()` → computes hint synchronously
- Frontend: Includes hint in handshake message (no async request)
- Backend: Extracts `initial_field_hint` from handshake
- Backend: Appends hint to `INITIAL_MESSAGE`
- Result: `"Begin with warm greeting and ask for: firstName (First Name)"`
- **Benefit**: No deadlock risk - hint available before WebSocket accept()

**2. Tool Response** (each field update):
- Backend: `send_form_update()` sends `form_updated` WITH `request_next_field_hint=true`
- Frontend: `handleFormUpdated()` detects flag → computes hint → responds immediately
- Backend: Awaits hint (2s timeout) → includes in tool response `message` field
- Result: Tool response contains next field hint, no separate model turn needed

### Implementation Files

**Backend**:
- `routes/websocket_routes.py`:
  - Lines 172-220: Extract `initial_field_hint` from handshake
  - Lines 402: `initial_field_hint = message.get("initial_field_hint")`
  - Lines 206-213: Append hint to initial message or use fallback
  - Lines 265-273: `next_field_hint_response` handler
  
- `services/form_filling_service.py`:
  - `start_session()`: Receives `initial_field_hint` as parameter (not async request)
  - `send_form_update()`: Lines 218-258 (piggybacks hint request)
  - `handle_next_field_hint_response()`: Lines 848-867 (resolves futures)
  - Tool handler: Line 349 (uses hint in response message)

**Frontend**:
- `src/webFormConnection.ts`:
  - `connect()`: Lines 1010-1020 (computes hint before connection)
  - Handshake: Line 1020 (includes `initial_field_hint` in message)
  - `handleFormUpdated()`: Lines 280-300 (detects and responds to hint requests)
  - `computeNextFieldHintString()`: Lines 450-475 (computes hint from sessionStorage)

**Config**:
- `config.py`:
  - `SYSTEM_INSTRUCTION`: Includes "Use tool response hint → ask next field"
  - `INITIAL_MESSAGE`: Template for initial greeting (hint appended)

### Testing

**Unit Tests**: `backend/tests/integration/test_initial_field_hint.py`
- `test_initial_field_hint_in_handshake`: Verifies hint extracted from handshake
- `test_initial_field_hint_fallback_when_missing`: Verifies fallback to "first unfilled field"
- `test_no_blocking_on_websocket_before_accept`: Ensures no async deadlock
- All tests passing (3/3)

**Verification**: `scripts/verify_hint_optimization.py`
- Checks all code patterns are in place
- Provides manual testing instructions
- Confirms optimization is complete

### Turn Complete Detection (October 16, 2025)

**Purpose**: Signal-based detection of when Gemini finishes speaking, eliminating timeout guessing for Level 3 farewell disconnect.

**Protocol**: Backend sends `{type: "turn_complete"}` WebSocket message when Gemini's `output_transcription` event arrives (after all audio chunks sent).

**Implementation**:

**Backend** (`backend/services/form_filling_service.py`):
- `on_transcript` callback: Emits turn_complete signal after forwarding transcript
- Line ~277: `await self._websocket.send_json({"type": "turn_complete"})`

**Frontend Message Routing** (`frontend/src/webFormConnection.ts`):
- Message handler: Routes turn_complete to global callback
- Line ~226: `case "turn_complete": if (window.vffOnTurnComplete) { window.vffOnTurnComplete(); } break;`

**Frontend Type Declarations** (`frontend/src/shared/connection.ts`):
- Window interface: Added `vffOnTurnComplete?: () => void` callback type

**Desktop Overlay** (`frontend/src/demo/VoiceOverlay.tsx`):
- Added `waitingForFarewellRef` flag to track Level 3 state (line ~54)
- Level 3 handler: Sets flag, sends recovery prompt (line ~383)
- Turn complete callback: Checks flag, disconnects immediately (line ~241)

**Mobile Overlay** (`frontend/src/demo/VoiceOverlayMobile.tsx`):
- Added `waitingForFarewellRef` flag (line ~46)
- Level 3 handler: Sets flag, sends recovery prompt (line ~314)
- Turn complete callback: Checks flag, disconnects immediately (line ~181)

**Benefits**:
- ✅ Full farewell message plays before disconnect (no cutoff)
- ✅ Precise timing using Gemini's own completion signal
- ✅ No timeout guessing or race conditions
- ✅ Consistent behavior regardless of speech speed or network latency
- Provides manual testing instructions
- Confirms optimization is complete

### Performance Impact

**Before**: 2 model turns per field (1 for update, 1 for hint)  
**After**: 1 model turn per field (hint embedded in tool response)  
**Token Savings**: ~50% reduction in context sent to model  
**Network Savings**: 50% reduction in WebSocket round trips  
**Reliability**: No deadlock - initial hint computed synchronously before connection

### Bug Fixes (October 14, 2025)

**Issue**: Variable shadowing bug in `form_filling_service.py`
- Lines 217-218 set `system_instruction=None` and `initial_message=None`
- Shadowed function parameters, causing them to be ignored
- **Fix**: Removed variable assignments, parameters now properly passed

**Issue**: Missing `turn_complete` flags in `live_ai_gemini.py`
- Text messages didn't explicitly set `turn_complete=True`
- Could cause Gemini to wait for more input
- **Fix**: Added explicit `turn_complete=True` to text message sending (line 605)

---

## Empty Tool Call Validation (October 18, 2025)

**Problem**: Gemini occasionally calls `update_form_fields` with empty updates `{}`, causing silent failures and confusion.

**Solution**: Backend validation rejects empty tool calls with instructive error message.

### Implementation

**Location**: `backend/services/form_filling_service.py` - `on_tool_call` handler (lines 347-356)

**Validation Logic**:
```python
# After normalizing updates from various Gemini formats
if not normalized_updates:
    _log.warning("empty_tool_call_rejected", session_id=self._session_id)
    return {
        "success": False,
        "applied_fields": [],
        "validation_errors": [],
        "unknown_fields": [],
        "message": "ERROR: update_form_fields called with empty updates. You must provide at least one field to update. If the user hasn't provided information yet, ask them for the specific field value instead of calling this tool with no data."
    }
```

**Error Message Design**:
- **Clear**: Explicitly states the problem (empty updates)
- **Instructive**: Tells Gemini what to do instead (ask for field value)
- **Actionable**: Prevents Gemini from retrying empty call

### System Instructions

**Config** (`backend/config.py` lines 197, 202):
- `"• NEVER call update_form_fields with empty updates {} - ask for clarification instead"`
- Reinforced in both RULES sections for emphasis

### Testing

**Unit Tests**: `backend/tests/unit/test_empty_tool_call_validation.py`
- `test_empty_updates_dict_rejected`: Verifies empty `{}` is caught
- `test_empty_updates_from_gemini_format`: Tests Gemini's `{"updates": {}}` format
- `test_non_empty_updates_accepted`: Control test - valid updates still work
- `test_empty_string_values_accepted`: Empty strings are valid (different from empty dict)
- All tests passing (4/4)

**Manual Test**: `scripts/test_empty_tool_call.py`
- Demonstrates empty vs non-empty tool call handling
- Shows error message that Gemini receives

### Benefits

✅ **No silent failures**: Empty tool calls immediately rejected with clear feedback  
✅ **Better UX**: Gemini knows to ask user for value instead of calling tool with no data  
✅ **Reduced confusion**: Error message guides Gemini to correct behavior  
✅ **Logged for monitoring**: `empty_tool_call_rejected` log event tracks occurrence rate  
✅ **Backward compatible**: Non-empty updates processed normally  

### Edge Cases Handled

- Empty dict `{}`
- Gemini's wrapped format `{"updates": {}}`
- Nested value extraction that results in empty dict
- Array format that produces no key-value pairs

**Not rejected**: Empty string values like `{"middleName": ""}` (valid for optional fields)

---

## Voice Activity Detection (VAD)

### Architecture Evolution (October 2025)

**Previous**: Dual detection system (energy-based + VAD ML model)
- audioManager energy detection (45ms) triggered barge-in
- VAD ML model (250ms) confirmed speech separately
- **Problem**: Fast energy detection interrupted Gemini on noise before VAD confirmed real speech

**Current**: VAD-only barge-in with privacy-enhanced gated audio
- Only VAD ML model controls barge-in decisions
- VAD state gates audio flow (silence when inactive, real audio when active)
- 400ms pre-buffer prevents speech clipping
- **Benefit**: No false interruptions + privacy protection + no clipping

### Demo: @ricky0123/vad-react (October 12, 2025)

**Library**: Professional VAD solution for React applications  
**Version**: ^0.0.34  
**Package**: `@ricky0123/vad-react` (installed in `frontend/`)  
**License**: ISC (vad-react), MIT (Silero VAD model)

**Implementation**:
- Hook file: `src/demo/useDemoVAD.ts` - React hook wrapper with CDN asset loading
- Integration: `src/demo/VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx`
- **Privacy Gate**: Calls `audioManager.setVADActive(true/false)` to control audio flow
- Async startup: Pending VAD start queue waits for hook to finish loading before calling `start()`
- Shared stream architecture: Single `getUserMedia()` shared between VAD and recording
- Handles speech start/end detection automatically

**Asset Loading** (CDN-based):
```typescript
baseAssetPath: "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.28/dist/"
onnxWASMBasePath: "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.23.0/dist/"
```

**Why version-specific CDN URLs**:
- `vad-web@0.0.28`: Last version before breaking changes in newer releases
- `onnxruntime-web@1.23.0`: First version with required `ort-wasm-simd-threaded.jsep.mjs` files
- Version 1.17.0 missing JSEP assets, causing 404 errors during model initialization

**Configuration** (tuned for reliable detection):
```typescript
positiveSpeechThreshold: 0.95   // 95% confidence to start (prevents false positives)
negativeSpeechThreshold: 0.75   // 75% to end (hysteresis prevents flapping)
minSpeechMs: 250                // 250ms sustained speech (filters noise/echo)
redemptionMs: 400               // 400ms grace period (smoother end detection)
startOnLoad: false              // Wait for user "Connect" action
sharedStream: MediaStream       // Single stream shared with audioManager
```

**Privacy-Enhanced Integration** (`VoiceOverlay.tsx`):
```typescript
const vad = useDemoVAD({
  callbacks: {
    onSpeechStart: () => {
      // Open audio gate: flush 400ms pre-buffer + enable live audio
      audioManager.setVADActive(true)
      
      // Trigger barge-in if Gemini is speaking
      connectionManager.onVADSpeechStart()
    },
    onSpeechEnd: () => {
      // Close audio gate: switch to sending silence (privacy)
      audioManager.setVADActive(false)
      
      // Complete turn
      connectionManager.onVADSpeechEnd()
    }
  },
  sharedStream: sharedStreamRef.current  // Echo cancellation
})
```

**Audio Gate Mechanics** (`audioManager.ts`):
```typescript
// Circular pre-buffer (400ms = minSpeechMs 250ms + margin 150ms)
const audioPreBuffer: Int16Array[] = []
let vadActive = false

// Privacy gate in audio processing
if (!vadActive) {
  // Send silence (zeros) - privacy protection
  const silenceBuffer = new Int16Array(pcmChunk.length)
  onAudioDataCallback(silenceBuffer.buffer)
} else {
  // Send real audio
  onAudioDataCallback(pcmData)
}

// On VAD activation: flush pre-buffer to capture speech start
function setVADActive(active: boolean) {
  if (active && !wasActive) {
    // Flush 400ms of buffered audio (prevents clipping first syllable)
    for (const chunk of audioPreBuffer) {
      onAudioDataCallback(chunk.buffer)
    }
  }
}
```

**Startup Flow**:
1. User clicks "Connect" → Create shared MediaStream with echo cancellation
2. Pass stream to VAD and audioManager (shared reference)
3. `pendingVADStart = true` → Wait for VAD loading
4. Once `vad.loading === false`, call `vad.start()`
5. Microphone activates, speech detection begins
6. **VAD inactive**: audioManager sends silence (privacy mode)
7. **VAD detects speech**: audioManager flushes pre-buffer + sends live audio

**Benefits**:
- ✅ Battle-tested Silero VAD model (no custom energy detection)
- ✅ **Privacy protection**: Non-speech audio never sent to Gemini
- ✅ **No speech clipping**: 400ms pre-buffer captures first syllable
- ✅ **No false barge-ins**: Only ML-confirmed speech interrupts Gemini
- ✅ **User expectation alignment**: VAD light off = no audio transmitted
- ✅ Built-in hysteresis and timing controls
- ✅ Automatic false positive detection (`onVADMisfire` callback)
- ✅ Clean React integration with loading/error states
- ✅ Professional-grade speech detection
- ✅ Zero local asset bundling (all loaded from CDN)
- ✅ Single shared stream = proper echo cancellation

**Debugging**:
- Check browser console for `[Demo VAD]` prefixed logs
- Check browser console for `[AudioManager]` gate open/close logs:
  - `VAD activated - flushing X samples (Xms) from pre-buffer`
  - `Pre-buffer flushed, now sending live audio`
  - `VAD deactivated - sending silence`
- Speech start/end events logged with audio sample counts
- VAD misfires logged as warnings
- Network tab shows CDN requests for `.onnx` and `.mjs` files

**Note**: Demo uses this CDN-based VAD library. Bookmarklet uses separate AudioWorklet-based VAD (see below).

---

### Bookmarklet: AudioWorklet (Custom VAD)

### Architecture: AudioWorklet (Modern)

**Migration**: October 12, 2025 - Migrated from deprecated ScriptProcessorNode to AudioWorklet API

**Benefits**:
- Runs on separate audio thread (better performance)
- Lower latency and more consistent processing
- No main thread blocking
- Future-proof (ScriptProcessorNode deprecated)

**Implementation**:
- Worklet file: `src/bookmarklet/audio-processor.worklet.ts` (compiled separately)
- Main thread: `src/bookmarklet/audioManager.ts` (loads worklet via Blob URL)
- Build: `npm run build:worklet` → `dist/bookmarklet/audio-processor.worklet.js`

**Deployment**: Both files must be deployed together:
- `bookmarklet.bundle.js` (main code)
- `audio-processor.worklet.js` (audio thread processor)

### Gemini Server-Side

| Parameter | Range | Default |
|-----------|-------|---------|
| start_of_speech_sensitivity | LOW/MED/HIGH | LOW |
| end_of_speech_sensitivity | LOW/MED/HIGH | LOW |
| prefix_padding_ms | 20-150 | 120 |
| silence_duration_ms | 150-350 | 250 |

### Client-Side

ATTACK=2.5, RELEASE=1.7, TTS_BLEED=1.4, MIN_SPEECH=45ms, MIN_SILENCE=200ms

Tuning: frontend/vad-tuning-lab-modular.html

## Production Config

Session: 3600s max, 300s idle, 3 reconnect  
Rates: 10 conn/IP, 1000 calls/session, 60/min  
Gemini: gemini-live-2.5-flash-preview-native-audio, us-central1  
CORS: localhost:* (dev), *.run.app + CDN (prod)

## Critical Notes

NEVER: FunctionResponse with id param

Fields (18): text, textarea, email, tel, number, date, time, datetime-local, url, password, checkbox, radio, combo, select, list, button, signature, unknown

Fuzzy Match: Exact ID → Name fallback, threshold 0.52

## Environment Variables

### Backend Configuration

**Location**: `backend/.env` (loaded by `python-dotenv` in `main.py`)

**Authentication**:
- **Vertex AI** (default, `VERTEXAI=true` in `config.py`):
  - No API key required in `.env`
  - Uses Application Default Credentials from gcloud CLI
  - Run: `gcloud auth application-default login`
  - Backend automatically uses your gcloud credentials
- **Google AI Studio** (alternative):
  - Set `GEMINI_API_KEY=your-api-key` in `.env`
  - Requires manual API key management

**Development Logging**:
- `VFF_DEV_LOGGING=true` - Enables detailed tool call/response output
- Default: `false` (production-safe)
- **Never set in production** - defaults to disabled
- Controlled by `backend/utils/dev_logger.py`

**Example `backend/.env`**:
```bash
# Enable verbose logging for development
VFF_DEV_LOGGING=true

# Vertex AI users: No API key needed!
# Just run: gcloud auth application-default login

# Google AI Studio users: Uncomment and add API key
# GEMINI_API_KEY=your-api-key-here

# Optional: Specify GCP project
# GOOGLE_CLOUD_PROJECT=your-project-id
```

**Production Deployment**:
- Do NOT include `.env` file in Docker image (in `.gitignore`)
- Do NOT set `VFF_DEV_LOGGING` (defaults to false)
- Use service account with Vertex AI permissions
- Set `GOOGLE_CLOUD_PROJECT` as Cloud Run environment variable

**Security**:
- `.env` and `backend/.env` in `.gitignore`
- Never commit secrets to repository
- load_dotenv() called early in `main.py` before config import

**Documentation**: See `backend/ENV_VARIABLES.md` for complete setup guide

### Frontend Configuration

**Location**: `frontend/.env` (Vite environment variables)

**Development**:
```bash
VITE_WS_URL=ws://localhost:8000/ws/fill
```

**Production**: Set during deployment via deploy script override
```bash
VITE_WS_URL="wss://your-backend.run.app/ws/fill" npm run build:demo
```

---

## Security Patterns (Never Violate)

**Never**:
- `.innerHTML` with user/AI content
- `eval()` or `new Function()` (except CSP detection test)
- Log field values (log IDs, counts, timings only)
- Store PHI (sessionStorage for IDs only, cleared on close)
- Infinite retry loops (max 3 attempts)

**Always**:
- Use `textContent` or `escapeHtml()` for display
- Log metadata only: `{fieldId, fieldType, filled: boolean, timestamp}`
- Detect CSP, show error (never bypass)
- Exponential backoff with max retries

**escapeHtml utility** (required):
```
Replace: & → &amp;, < → &lt;, > → &gt;, " → &quot;, ' → &#039;
```

---

## Production Configuration

**Location**: `backend/config.py`  
**Philosophy**: Start conservative, tune iteratively based on production metrics.

---

### WebSocket & Session Management

#### MAX_SESSION_DURATION_SECONDS
**Default**: `1800` (30 minutes)  
**Purpose**: Maximum lifetime of a single voice session  
**Tune If**: Users regularly hit timeout mid-fill

#### IDLE_SESSION_TIMEOUT_SECONDS
**Default**: `300` (5 minutes)  
**Purpose**: Disconnect if no activity for this duration  
**Tune If**: Users frequently leave sessions open

#### MAX_RECONNECT_ATTEMPTS
**Default**: `5`  
**Purpose**: Client-side reconnect retry limit  
**Tune If**: Network instability requires more attempts

#### RECONNECT_BACKOFF_BASE_MS
**Default**: `1000` (1 second)  
**Purpose**: Base delay for exponential backoff  
**Pattern**: 1s, 2s, 4s, 8s, 16s  
**Tune If**: Need faster/slower reconnection

---

### Rate Limiting

#### MAX_CONNECTIONS_PER_IP
**Default**: `3`  
**Purpose**: Maximum concurrent WebSocket connections from single IP  
**Rationale**: Allow multiple tabs, prevent abuse  
**Tune If**: Legitimate users need more concurrent sessions

#### MAX_TOOL_CALLS_PER_SESSION
**Default**: `100`  
**Purpose**: Maximum total tool calls per session  
**Rationale**: Typical form has < 50 fields, allows retries  
**Tune If**: Legitimate forms exceed this

#### MAX_TOOL_CALLS_PER_MINUTE
**Default**: `30`  
**Purpose**: Rate limit tool calls per session per minute  
**Rationale**: ~2 calls per second max (prevent runaway AI)  
**Tune If**: Voice sessions legitimately need faster updates

#### MAX_AUDIO_FRAMES_PER_SECOND
**Default**: `50` (corresponds to 20ms chunks at 24kHz)  
**Purpose**: Rate limit audio frames  
**Tune If**: Audio quality issues or latency problems

---

### Gemini API Configuration

#### GEMINI_MODEL_NAME
**Default**: `"gemini-2.0-flash-exp"` (or current preview)  
**Purpose**: Which Gemini model version to use  
**Tune If**: New model released, or need stable non-preview  
**Note**: Not pinning to date version for MVP

#### VERTEX_AI_LOCATION
**Default**: `"us-central1"`  
**Purpose**: GCP region for Vertex AI API  
**Tune If**: Latency issues or compliance requirements

#### MAX_TOKENS_PER_REQUEST
**Default**: `1000`  
**Purpose**: Token limit for Gemini responses  
**Rationale**: Sufficient for tool calls, not chatty  
**Tune If**: AI responses truncated

#### AUDIO_SAMPLE_RATE
**Default**: `24000` (24kHz)  
**Purpose**: Audio input sample rate  
**Do NOT Change**: Fixed by Gemini API requirement

---

### Logging & Monitoring

#### LOG_LEVEL
**Default**: `"INFO"` (production), `"DEBUG"` (development)  
**Options**: DEBUG, INFO, WARNING, ERROR, CRITICAL  
**Tune If**: Need more detailed logs for debugging

#### LOG_RETENTION_DAYS
**Default**: `7` days  
**Purpose**: How long to keep logs in Cloud Logging  
**Rationale**: Short retention for HIPAA compliance  
**Tune If**: Compliance requires different retention

#### ENABLE_PERFORMANCE_METRICS
**Default**: `True`  
**Purpose**: Send latency/performance metrics to Cloud Monitoring  
**Tune If**: Cost concerns

#### LOG_TOOL_CALL_DETAILS
**Default**: `True` (types only, NO values)  
**Purpose**: Log tool call types for debugging  
**NEVER**: Log actual field values (HIPAA violation)

---

### CORS Configuration

#### ALLOWED_ORIGINS
**Development**: `["*"]`  
**Production**: `["https://your-domain.com"]`  
**CRITICAL**: MUST restrict to specific domains before launch  
**Security Risk**: Leaving as "*" allows any website to use backend

---

### Environment-Specific Overrides

**Development (local)**:
```python
LOG_LEVEL = "DEBUG"
ALLOWED_ORIGINS = ["*"]
MAX_CONNECTIONS_PER_IP = 10
```

**Production (Cloud Run)**:
```python
LOG_LEVEL = "INFO"
ALLOWED_ORIGINS = ["https://your-domain.com"]
MAX_CONNECTIONS_PER_IP = 3
```

**Implementation**: Use environment variables for overrides, fallback to config.py defaults.

---

### Configuration Tuning Process

**Step 1**: Deploy with conservative defaults  
**Step 2**: Monitor for 1-2 weeks  
**Step 3**: Collect metrics (session duration, tool call frequency, error rates)  
**Step 4**: Identify bottlenecks (timeouts, rate limits, performance)  
**Step 5**: Adjust values in config.py  
**Step 6**: Redeploy and monitor impact  
**Step 7**: Document changes in PROGRESS.md  

---

### Monitoring Alerts (Cloud Monitoring)

**Error Rate**:
- **Threshold**: > 5% of requests result in errors
- **Action**: Investigate logs, check Gemini API status

**Session Timeout Rate**:
- **Threshold**: > 20% of sessions hit MAX_SESSION_DURATION
- **Action**: Consider increasing timeout

**Rate Limit Hit Rate**:
- **Threshold**: > 10% of sessions hit rate limits
- **Action**: Evaluate if limits too restrictive

**Reconnection Rate**:
- **Threshold**: > 30% of sessions reconnect at least once
- **Action**: Investigate connection stability

---

## Deployment Strategy

### Environments

1. **Development**: Local testing (current)
2. **Staging**: Internal testing with real websites
3. **Production**: Public release

---

## Recent Improvements (October 18, 2025)

### 1. Fixed VAD Infinite Reinitialization

**Problem**: VAD hook was re-initializing on every render due to changing dependencies (`sharedStream` and `callbacks` objects).

**Solution**: Used `useMemo` to stabilize both callbacks and options objects, preventing unnecessary VAD resets.

**Files Changed**:
- `frontend/src/demo/VoiceOverlay.tsx` - Added `useMemo` for `vadCallbacks` and `vadOptions`
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Same stabilization

### 2. Delayed Barge-In (450ms Validation)

**Problem**: Short noises (throat clears, coughs <450ms) were triggering immediate barge-in, interrupting Gemini unnecessarily.

**Solution**: Only trigger barge-in after speech has lasted ≥450ms. Use `setTimeout` to schedule delayed barge-in check.

**Implementation**:
- `onSpeechStart`: Open audio gate, schedule 450ms delayed barge-in (don't trigger immediately)
- Delayed check: If speech still active after 450ms → trigger barge-in + set `bargeInTriggeredRef = true`
- `onSpeechEnd`: Only send `activity_end` if `bargeInTriggeredRef === true`

**Benefits**:
- ✅ No unnecessary interruptions from throat clears/coughs
- ✅ Gemini speaks smoothly through brief noises
- ✅ Barge-in still fast for real speech (450ms barely noticeable)
- ✅ Symmetric protocol (barge-in and turn completion always paired)

**Files Changed**:
- `frontend/src/demo/VoiceOverlay.tsx` - Added `bargeInTriggeredRef`, delayed barge-in logic
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Same implementation

### 3. Context-Aware Audio Playback Fallback

**Problem**: Gemini's audio sometimes didn't play after connection or section switching, causing silent gaps.

**Solution**: Implemented context-aware fallback with different timeouts for initial connection (3s) vs section switching (1.5s).

**Detection**:
```python
is_section_switch = "Section" in self._initial_message and "moving to" in self._initial_message.lower()
fallback_delay = 1.5 if is_section_switch else 3.0
```

**Mechanism**:
- Send initial message → Start background fallback task
- Track if Gemini responds: `gemini_has_responded = True` on first audio chunk
- If timeout expires without response: Resend initial message
- If response arrives before timeout: Fallback exits cleanly

**Benefits**:
- ✅ Faster recovery during section switching (1.5s vs 3s)
- ✅ Conservative timeout for cold start (3s)
- ✅ Better debugging with detailed logging
- ✅ Context-aware behavior adapts to user engagement

**Files Changed**:
- `backend/adapters/live_ai_gemini.py` - Added `is_section_switch` detection, dynamic `fallback_delay`

---

### Cloud Run Deployment Checklist

**Before deploying**:
- [ ] ALLOWED_ORIGINS restricted to specific domains
- [ ] LOG_LEVEL set to INFO or WARNING
- [ ] Conservative rate limits in place
- [ ] Session timeouts reasonable
- [ ] Gemini model name confirmed
- [ ] All values documented with comments
- [ ] Monitoring alerts configured
- [ ] Budget alerts set up (GCP)

---

## Glossary

- **Token Optimization**: Embedding navigation hints in existing messages to reduce model turns
- **Async Request/Response**: Backend sends request → Frontend computes → Backend awaits response
- **Next Field Hint**: Formatted string telling Gemini which field to ask for next
- **Source of Truth**: Live page DOM (server never stores values)
- **CSP**: Content Security Policy (can block external scripts)
- **SRI**: Subresource Integrity (ensures bundle not tampered)
