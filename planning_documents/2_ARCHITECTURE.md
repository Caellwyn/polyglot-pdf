# Architecture - Stateless Design

**Last Updated**: October 21, 2025
**Status**: Production Ready (User-First Protocol - Simplified)

**Recent Changes** (October 21, 2025):
- ❌ **Removed**: VAD warmup feature (no longer needed with user-first protocol)
- ❌ **Removed**: Activity watchdog and inactivity recovery system (over-engineered for user-first model)
- ❌ **Removed**: Backend initial message protocols (fully user-initiated now)
- ✅ **Retained**: User speaks first, greeting carousel, delayed barge-in (450ms), shared audio stream

---

## Core Principle

> **Client = source of truth for all form state.**  
> Backend stores ONLY schema. All values live in sessionStorage.

**Why**: HIPAA compliance (zero PHI), scalability, simplicity

---

## System Flow

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

**Handshake**: Client sends schema + optional current_values → Backend stores schema, returns session_id

**User-First Protocol**: Connection opens silently, no AI greeting sent. Visual greeting carousel appears with friendly prompts, but user must speak first to initiate conversation. This establishes a patient-led interaction model.

**Voice Loop**: User speaks → Gemini calls update_form_fields → **Backend validates (rejects empty calls)** → Client updates sessionStorage + DOM → Client sends next_field_hint

**Reconnect**: Client sends schema + current_values → Backend creates new session → State restored

**Cleanup**: Tab close = sessionStorage auto-clears

---

## User-First Protocol (October 18, 2025)

**Design Philosophy**: Patient-led interaction reduces anxiety and gives full control to the user.

**Implementation**:

**Backend** (`backend/adapters/live_ai_gemini.py` lines 603-670):
- Entire initial message block commented out
- No audio greeting sent after connection
- Connection opens silently, waiting for user to speak first

**Frontend** (`frontend/src/demo/VoiceOverlay.tsx` and `VoiceOverlayMobile.tsx`):
- **Greeting Carousel**: Visual welcome that appears on connection
  - Auto-rotates through friendly prompts every 3 seconds
  - Shows phrases like "Hi! I'm here to help with this form", "Just start speaking and I'll fill it out"
  - Dismisses automatically when user or Gemini speaks
  - Tracked with `carouselDismissedRef` to prevent re-showing after dismissal
  - Non-audio, non-intrusive visual cue
- **Silent Connection**: No audio pressure, user speaks when ready
- **Collapsible Overlay**: UI can be minimized with ▲/▼ button to prevent blocking form fields

**Benefits**:
- ✅ Reduces patient anxiety (no immediate AI voice)
- ✅ User controls when conversation starts
- ✅ Visual prompts provide guidance without pressure
- ✅ Aligns with medical best practices (patient-first approach)
- ✅ Better for multilingual scenarios (user can gather thoughts)
- ✅ Cleaner UI (overlay can collapse out of the way)

**Code Locations**:
- Backend no-greeting: `backend/adapters/live_ai_gemini.py:603-670`
- Desktop carousel: `frontend/src/demo/VoiceOverlay.tsx:280-291, 139-142, 322-325`
- Mobile carousel: `frontend/src/demo/VoiceOverlayMobile.tsx:284-295, 131-134, 316-319`
- Greeting component: `frontend/src/demo/GreetingCarousel.tsx` (shared)
- Collapse feature: Both overlay files, collapse button in header, CSS transitions

---

## Tool Call Validation (Backend)

**Purpose**: Ensure Gemini sends well-formed tool calls before processing.

**Empty Update Protection** (October 18, 2025):
- Backend rejects `update_form_fields` calls with empty updates `{}`
- Returns instructive error: _"You must provide at least one field to update. If the user hasn't provided information yet, ask them for the specific field value instead of calling this tool with no data."_
- Prevents silent failures and guides Gemini to correct behavior
- Logged as `empty_tool_call_rejected` for monitoring

**Other Validations**:
- Field ID matching (exact + fuzzy fallback)
- Unknown field detection
- Constraint validation (type, format, min/max, options)

**Implementation**: `backend/services/form_filling_service.py` - `on_tool_call` handler

---

## Audio Initialization & Stream Architecture (October 21, 2025)

**Recent Updates**:
- ✅ **Fixed Race Conditions**: Audio stream now created in parent component BEFORE overlays render
- ✅ **Self-Hosted VAD Assets**: ONNX models served from GCS bucket (5MB, eliminates CDN dependency)
- ✅ **AudioContext Pooling**: Reuse contexts instead of creating new ones (fixes mobile reconnection failures)
- ✅ **Consolidated VAD Control**: Single source of truth for VAD start/stop logic
- ✅ **Connection Polling**: Replaced hard-coded delays with proper status polling
- ✅ **Error Visibility**: Comprehensive error messages for audio failures

### Shared Audio Stream Architecture (Echo Prevention)

**Problem**: Dual `getUserMedia()` calls (one for VAD, one for recording) prevented browser echo cancellation from working properly, causing Gemini's TTS to trigger false VAD events (self-interruption/stuttering).

**Solution**: Single shared audio stream with browser-level AEC, distributed to both VAD and recording systems.

### Audio Stream Flow (Updated October 21, 2025)

```
AdultIntakeDemo Component Mount (PARENT)
  ↓
getUserMedia({
  echoCancellation: true,    // Browser AEC (critical!)
  noiseSuppression: true,     // Reduces background noise
  autoGainControl: true,      // Normalizes mic volume
  channelCount: 1,            // Mono audio
  sampleRate: 16000           // Gemini input rate
})
  ↓
[WAIT FOR STREAM READY] ← FIX #1: Prevent race conditions
  ↓
Pass stream as prop to overlays
  ↓
  ├──→ VoiceOverlay(sharedStream, streamError)
  │      ├──→ useDemoVAD({ sharedStream })
  │      │      └──→ ricky0123/vad-web (Silero VAD)
  │      │             └──→ Self-hosted ONNX from GCS ← FIX #6
  │      │             └──→ Detects speech → sendActivityStart/End
  │      │
  │      └──→ createConnectionManager(sharedStream)
  │             └──→ createAudioManager(sharedStream)
  │                    └──→ AudioContext (pooled) ← FIX #5
  │                           └──→ AudioWorklet → PCM16 → Backend
  │
  └──→ VoiceOverlayMobile(sharedStream, streamError)
         └──→ Same flow as desktop
```

### Browser Echo Cancellation

**How It Works**:
1. Browser's AEC algorithm receives **two signals**:
   - **Microphone input** (user voice + echo from speakers)
   - **Reference signal** (audio being played through speakers - Gemini TTS)
2. AEC subtracts the reference signal from microphone input
3. Result: Clean microphone stream with echo removed
4. This stream (with AEC already applied) is what VAD and recording receive

**Why Single Stream Is Critical**:
- ❌ **Dual streams**: Browser AEC can't correlate microphone with playback → echo leaks through
- ✅ **Single stream**: Browser AEC has unified reference point → echo properly cancelled

### Implementation Details (Updated October 21, 2025)

**AdultIntakeDemo.tsx** (`frontend/src/demo/AdultIntakeDemo.tsx`):
```typescript
// FIX #1: Create stream EARLY in parent component (before overlays render)
// This prevents race conditions where VAD initializes before stream is ready
useEffect(() => {
  let mounted = true

  async function initSharedStream() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, ... }
      })
      if (mounted) {
        setSharedStream(stream)
        setStreamReady(true)  // Signal overlays can render
      } else {
        stream.getTracks().forEach(track => track.stop())
      }
    } catch (err) {
      if (mounted) {
        setStreamError(err.message)  // FIX #4: Show errors to user
        setStreamReady(true)  // Render overlays with error message
      }
    }
  }

  initSharedStream()

  return () => {
    mounted = false
    if (sharedStream) {
      sharedStream.getTracks().forEach(track => track.stop())
    }
  }
}, [])

// Only render overlays when stream is ready
{streamReady && (
  <VoiceOverlay sharedStream={sharedStream} streamError={streamError} />
)}
```

**VoiceOverlay.tsx** (`frontend/src/demo/VoiceOverlay.tsx`):
```typescript
// FIX #1: Accept shared stream as prop (no longer create our own)
interface VoiceOverlayProps {
  sharedStream?: MediaStream | null
  streamError?: string | null  // FIX #4: Display errors
}

// Update ref when prop changes (parent manages lifecycle)
useEffect(() => {
  sharedStreamRef.current = sharedStream || null
}, [sharedStream])
```

**useDemoVAD.ts** (`frontend/src/demo/useDemoVAD.ts`):
```typescript
// FIX #6: Self-hosted VAD assets (eliminates CDN dependency)
function getVADAssetBase(): string {
  if (import.meta.env.DEV) {
    return '/vad-assets/vad-web/'  // Local dev
  }
  const bucket = import.meta.env.VITE_GCS_BUCKET || 'voice-form-filler-demo'
  return `https://storage.googleapis.com/${bucket}/vad-assets/vad-web/`
}

function getORTAssetBase(): string {
  if (import.meta.env.DEV) {
    return '/vad-assets/onnxruntime/'  // Local dev
  }
  const bucket = import.meta.env.VITE_GCS_BUCKET || 'voice-form-filler-demo'
  return `https://storage.googleapis.com/${bucket}/vad-assets/onnxruntime/`
}

export function useDemoVAD(options?: VADOptions) {
  const vad = VAD.useMicVAD({
    // FIX #6: Use self-hosted assets instead of CDN
    baseAssetPath: getVADAssetBase(),
    onnxWASMBasePath: getORTAssetBase(),

    getStream: options?.sharedStream
      ? async () => options.sharedStream  // Reuse shared stream
      : async () => getUserMedia(...)     // Fallback (backward compat)
  })
}
```

**audioManager.ts** (`frontend/src/shared/audioManager.ts`):
```typescript
// Accept optional pre-created stream
export function createAudioManager(existingStream?: MediaStream) {
  const nodes = {
    stream: existingStream || null  // Use provided stream if available
  }

  async function startRecording(...) {
    if (!nodes.stream) {
      // Only create new stream if not provided
      nodes.stream = await getUserMedia(...)
    }

    // FIX #5: AudioContext Pooling - reuse contexts instead of creating new ones
    // Browsers limit AudioContext instances (6-8 desktop, 2-4 mobile)
    if (!nodes.recordingContext) {
      console.log('[AudioManager] 🎵 Creating AudioContext for recording (first time)')
      nodes.recordingContext = new AudioContext({ sampleRate: RECORDING_SAMPLE_RATE })
    } else {
      console.log('[AudioManager] ♻️ Reusing existing recording AudioContext')
      // Resume if suspended (browsers may suspend to save power)
      if (nodes.recordingContext.state === 'suspended') {
        await nodes.recordingContext.resume()
      }
    }

    if (!nodes.playbackContext) {
      console.log('[AudioManager] 🎵 Creating AudioContext for playback (first time)')
      nodes.playbackContext = new AudioContext({ sampleRate: PLAYBACK_SAMPLE_RATE })
    } else {
      console.log('[AudioManager] ♻️ Reusing existing playback AudioContext')
      if (nodes.playbackContext.state === 'suspended') {
        await nodes.playbackContext.resume()
      }
    }
  }
}
```

**connection.ts** (`frontend/src/shared/connection.ts`):
```typescript
// Pass shared stream to audio manager
export function createConnectionManager(
  schema, 
  onStatusChange, 
  initialFillLanguage,
  sharedStream?: MediaStream  // New parameter
) {
  audioManager = createAudioManager(sharedStream)  // Pass through
}
```

### VAD Configuration

**Library**: `@ricky0123/vad-react` v0.0.34 (wraps `@ricky0123/vad-web` v0.0.28)  
**Model**: Silero VAD (ONNX Runtime Web)

**Timing Parameters** (tuned for echo prevention):
- `positiveSpeechThreshold: 0.9` - 90% confidence required (prevents TTS bleed)
- `negativeSpeechThreshold: 0.65` - 65% to end (hysteresis prevents flapping)
- `minSpeechMs: 100` - 100ms sustained speech (up from 45ms, prevents echo triggers)
- `redemptionMs: 300` - 300ms grace period (up from 120ms, smoother end detection)

**Why These Values**:
- Higher `positiveSpeechThreshold` (0.9) → Less sensitive → Fewer false positives from Gemini TTS
- Longer `minSpeechMs` (100ms) → Requires sustained audio → Filters out brief TTS artifacts
- Longer `redemptionMs` (300ms) → More forgiving → Natural speech patterns don't get chopped

### Cleanup & Lifecycle

**Stream Lifecycle**:
1. **Mount**: `getUserMedia()` → Create stream with AEC
2. **Active**: Stream shared between VAD + recording (both use same AEC'd audio)
3. **Unmount**: Stop all audio tracks → Release microphone

**Memory Management**:
- `MediaStream.getTracks().forEach(track => track.stop())` releases hardware
- Browser clears AEC buffers when stream stopped
- No stream leaks (verified: mic indicator disappears on unmount)

### Benefits

✅ **Echo cancellation works**: Single stream allows browser AEC to function properly  
✅ **No self-interruption**: Gemini TTS doesn't trigger VAD (stuttering eliminated)  
✅ **Efficient**: One `getUserMedia()` call instead of two  
✅ **Backward compatible**: Falls back to dual streams if shared stream not provided  
✅ **Clean separation**: Audio layer doesn't know about VAD, VAD doesn't know about recording  

### Testing Results

**Before (Dual Streams)**:
- ❌ Gemini interrupted herself during TTS playback
- ❌ Console showed: `[VFF Metrics] 🎤 Mic activity detected` during silence
- ❌ Console showed: `[VFF Metrics] 🔇 TTS paused - Barge-in latency: 0.7ms`

**After (Shared Stream)**:
- ✅ No VAD triggers during Gemini TTS
- ✅ Smooth, uninterrupted AI responses
- ✅ Barge-in still works instantly when user speaks
- ✅ Console shows: `[AudioManager] 🔗 Reusing existing microphone stream (shared with VAD)`

**Verified in**: Noisy environments (crowded bar), quiet environments, with headphones, with speakers

### Self-Hosted VAD Assets (October 21, 2025)

**Problem**: VAD library loaded ~5MB of ONNX models from jsdelivr CDN on each page load:
- Slow initialization on poor connections (10-30 seconds)
- External CDN dependency (reliability risk)
- No control over caching
- Extra DNS lookup + TLS handshake for different domain

**Solution**: Download and self-host VAD assets on GCS bucket

**Assets** (~5MB total):
- `silero_vad.onnx` (~1.8MB) - Silero VAD model
- `vad.worklet.bundle.min.js` - VAD worklet processor
- `ort-wasm-simd-threaded.wasm` (~2-3MB) - ONNX Runtime WASM files
- Supporting WASM modules

**Setup**:
```bash
cd frontend
./download-vad-assets.sh  # Downloads to public/vad-assets/
```

**Deployment** (`deploy-demo.sh`):
```bash
# Automatically downloads assets if not present
# Uploads to gs://$VOICE_GCS_BUCKET/vad-assets/
# 1-year cache headers (assets are content-addressed)
```

**Benefits**:
- ✅ **Faster initialization**: Same region as app (500ms vs 10-30s on slow connections)
- ✅ **No CDN dependency**: Eliminates jsdelivr.net failure point
- ✅ **Better caching**: 1-year cache, same browser cache as app
- ✅ **Simplified debugging**: Assets served from known location
- ✅ **Version control**: Assets versioned with deployment

### Consolidated VAD Control (October 21, 2025)

**Problem**: Three separate code paths trying to start VAD caused race conditions:
1. `handleConnect()` - Started VAD after connection
2. `pendingVADStart` useEffect - Waited for VAD loading to finish
3. Status change useEffect - Auto-started when connected

This led to:
- VAD stuck in loading state forever
- `pendingVADStart` flag never cleared
- Multiple redundant start calls
- Unclear why VAD was/wasn't running

**Solution**: Single source of truth useEffect with clear conditions

**Implementation** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):
```typescript
// FIX #2: SINGLE SOURCE OF TRUTH for VAD state management
useEffect(() => {
  const isConnected = status === 'connected' || status.startsWith('connected ')

  // VAD should run when ALL conditions met:
  const shouldRunVAD = isConnected && !pushToTalkMode && !vad.loading && !vad.errored

  if (shouldRunVAD && !vad.userSpeaking) {
    console.log('[VoiceOverlay] 🎙️ Starting VAD (conditions met)')
    vad.start()
  } else if (!shouldRunVAD && vad.userSpeaking) {
    console.log('[VoiceOverlay] ⏸️ Pausing VAD (conditions not met)')
    vad.pause()
  }

  // FIX #4: Display VAD errors to user
  if (vad.errored) {
    setError(`Voice detection error: ${vad.errored}`)
  }
}, [status, pushToTalkMode, vad.loading, vad.errored, vad.userSpeaking, vad.start, vad.pause])
```

**Removed**:
- ❌ `pendingVADStart` state variable
- ❌ Separate pendingVADStart useEffect
- ❌ VAD start calls in handleConnect
- ❌ VAD start calls in handlePushToTalkToggle

**Benefits**:
- ✅ **Single code path**: Only one place that starts/stops VAD
- ✅ **Clear logging**: Exactly why VAD started/stopped
- ✅ **No stuck states**: All conditions checked every render
- ✅ **Fewer bugs**: Can't have conflicting start/stop calls

### Connection Polling (October 21, 2025)

**Problem**: Hard-coded `setTimeout(100)` assumed connection ready after 100ms:
- Local dev: Works fine (WebSocket handshake ~20-50ms)
- Cloud deployment: Fails almost always (WSS + TLS handshake 500-2000ms)
- No user feedback when timeout insufficient
- Silent failures (recording never started)

**Solution**: Poll connection status until ready or timeout

**Implementation** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):
```typescript
// FIX #3: Poll for connected status instead of hard-coded delay
await connectionManager.connect()

const maxWaitMs = 5000
const startTime = Date.now()

while (Date.now() - startTime < maxWaitMs) {
  const currentStatus = connectionManager.getStatus()
  const isActive = currentStatus === 'connected' || currentStatus === 'switching_section'

  if (isActive) {
    console.log('[VoiceOverlay] ✅ Connection active, starting recording')
    await connectionManager.startRecording()
    break
  }

  // Wait 50ms before checking again
  await new Promise(resolve => setTimeout(resolve, 50))
}

// Check final status and show error if timed out
const finalStatus = connectionManager.getStatus()
if (finalStatus !== 'connected' && finalStatus !== 'switching_section') {
  console.error('[VoiceOverlay] ❌ Connection timeout, final status:', finalStatus)
  setError('Connection timed out - please try again')  // FIX #4: Show error
}
```

**Benefits**:
- ✅ **Works on cloud**: Waits up to 5 seconds for slow handshakes
- ✅ **Fast on local**: Exits poll immediately when ready (~50ms)
- ✅ **User feedback**: Shows timeout error instead of silent failure
- ✅ **Proper timing**: Adapts to actual network conditions

### Error Visibility (October 21, 2025)

**Problem**: Audio failures were silent:
- Microphone permission denied → no error shown
- VAD initialization failed → no error shown
- getUserMedia failed → console only
- Users confused why "Connect to Voice" didn't work

**Solution**: Display all audio errors in UI

**Implementation**:
```typescript
// FIX #4: Display microphone errors
try {
  const stream = await navigator.mediaDevices.getUserMedia(...)
  setSharedStream(stream)
} catch (err) {
  setStreamError(err.message)  // "Permission denied" etc.
}

// FIX #4: Display VAD errors
if (vad.errored) {
  setError(`Voice detection error: ${vad.errored}`)
}

// FIX #4: Show both stream and connection errors in UI
{(error || streamError) && (
  <div className="vff-error">
    {streamError && (
      <div><strong>🎤 Microphone Error:</strong> {streamError}</div>
    )}
    {error && <div>{error}</div>}
  </div>
)}
```

**Benefits**:
- ✅ **Clear feedback**: Users know exactly what failed
- ✅ **Actionable errors**: "Permission denied" → user knows to grant permission
- ✅ **No confusion**: Silent failures eliminated
- ✅ **Better debugging**: Errors visible without opening console

---

## VAD & Barge-In

**Architecture**: VAD-only barge-in system (moved from dual energy+VAD detection in October 2025)

**Client VAD**: Silero VAD detects speech → Opens audio gate → Flushes pre-buffer → Sends activity_start → Barge-in if Gemini speaking

**Backend**: Forwards to Gemini via send_realtime_input()

**Gemini VAD**: Automatic activity detection configured via `backend/config.py`:
- `VAD_START_SENSITIVITY`: "LOW" | "HIGH" | "UNSPECIFIED" - How quickly Gemini detects speech start
- `VAD_END_SENSITIVITY`: "LOW" | "HIGH" | "UNSPECIFIED" - How quickly Gemini detects speech end
- `VAD_PREFIX_PADDING_MS`: Milliseconds of audio before speech start to include (optional)
- `VAD_SILENCE_DURATION_MS`: Milliseconds of silence before ending speech (optional)

**Gemini Interruption**: Sends interrupted=true when user starts speaking

**Tool Safety**: 150ms rejection window blocks hallucinated tool calls during barge-in

### Privacy-Enhanced VAD-Gated Audio Flow

**Problem**: Previous architecture continuously sent all microphone audio to Gemini, including private conversations when user wasn't actively filling the form, violating user expectations (VAD light off = no audio sent).

**Solution**: Audio gate controlled by VAD state - only sends real audio when VAD confirms speech, sends silence otherwise.

#### Architecture

```
Microphone → AudioWorklet → Circular Pre-Buffer (400ms)
                                    ↓
                            Privacy Gate (VAD-controlled)
                                    ↓
              ┌─────────────────────┴─────────────────────┐
              │                                           │
         VAD Inactive                                VAD Active
              │                                           │
    Send Silence Chunks                    1. Flush 400ms Pre-Buffer
    (Privacy Protection)                   2. Send Live Audio Chunks
              │                            3. Send activity_start
              ↓                                           ↓
          WebSocket → Backend → Gemini Live API
```

#### Implementation Details

**audioManager.ts** (`frontend/src/shared/audioManager.ts`):

```typescript
// Circular pre-buffer (400ms at 16kHz = 6,400 samples)
const PREBUFFER_DURATION_MS = 400  // minSpeechMs (250) + margin (150)
const audioPreBuffer: Int16Array[] = []

// Privacy gate controlled by VAD
let vadActive = false

function setVADActive(active: boolean) {
  if (active && !wasActive) {
    // VAD activated: Flush pre-buffer to capture speech start
    for (const chunk of audioPreBuffer) {
      onAudioDataCallback(chunk.buffer)  // Send buffered audio
    }
    // Then continue sending live audio
  } else if (!active && wasActive) {
    // VAD deactivated: Switch to sending silence
    // Privacy: Non-speech audio never reaches Gemini
  }
}

// Audio processing in worklet message handler
if (!vadActive) {
  // Send silence (zeros) for privacy
  const silenceBuffer = new Int16Array(pcmChunk.length)
  onAudioDataCallback(silenceBuffer.buffer)
} else {
  // Send real audio
  onAudioDataCallback(pcmData)
}
```

**VoiceOverlay.tsx** (`frontend/src/demo/VoiceOverlay.tsx`):

```typescript
const vad = useDemoVAD({
  callbacks: {
    onSpeechStart: () => {
      // Open audio gate (sends pre-buffer + live audio)
      audioManager.setVADActive(true)
      
      // Trigger barge-in if Gemini speaking
      connectionManager.onVADSpeechStart()
    },
    onSpeechEnd: () => {
      // Close audio gate (switch to silence for privacy)
      audioManager.setVADActive(false)
      
      // Complete turn
      connectionManager.onVADSpeechEnd()
    }
  },
  sharedStream: sharedStreamRef.current
})
```

#### Pre-Buffer Mechanics

**Purpose**: Prevents clipping the start of speech (first syllable)

**Size**: 400ms = VAD confirmation time (250ms minSpeechMs) + safety margin (150ms)

**Operation**:
1. **Always buffering**: Rolling window stores last 400ms of audio chunks
2. **VAD inactive**: Buffer fills but audio sent as silence
3. **VAD activates**: Buffer flushed immediately, then live audio flows
4. **Result**: Gemini receives complete utterance including first syllable

**Example Timeline**:
```
t=0ms:    User starts speaking "Hello"
t=0-250ms: Audio buffered, silence sent (VAD confirming)
t=250ms:  VAD confirms speech → Flush buffer → "He-" captured
t=250ms+: Live audio flows → "-llo" captured in real-time
```

#### Benefits

✅ **Privacy Protection**: Non-speech audio never sent to Gemini (medical conversations, personal calls, etc.)  
✅ **User Expectation Alignment**: VAD light off = no audio transmitted  
✅ **No Speech Clipping**: 400ms pre-buffer captures speech start  
✅ **Seamless Barge-In**: Pre-buffer → activity_start coordination  
✅ **WebSocket Keepalive**: Silence chunks maintain connection  
✅ **Clean Architecture**: VAD controls audio flow, not just signaling  

#### Visual Feedback

**VAD Light Indicator** (in overlay):
- 🔴 **Red (pulsing)**: VAD active - audio being sent to Gemini
- ⚫ **Gray**: VAD inactive - only silence being sent (privacy mode)

**User Assumption**: "Light off = mic not listening" - now architecturally true!

### Delayed Barge-In (Noise Filtering)

**Problem**: Short noises (throat clears, coughs, grunts <450ms) were triggering immediate barge-in, interrupting Gemini unnecessarily even though they didn't contain valid speech.

**Solution**: Only trigger barge-in after speech has lasted ≥450ms (MIN_TURN_DURATION_MS).

**Implementation** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):

**On Speech Start** (`onSpeechStart`):
1. Record timestamp
2. Reset `bargeInTriggeredRef` flag
3. Open audio gate (start buffering to Gemini)
4. **Schedule delayed barge-in** via `setTimeout(450ms)`
5. **DO NOT** trigger barge-in immediately

**Delayed Barge-In Logic** (after 450ms):
- Check if speech is **still active** (`speechStartTimeRef !== null`)
- Check if duration **meets threshold** (`≥450ms`)
- If both true: Trigger barge-in + set `bargeInTriggeredRef = true`
- If false: Do nothing (speech ended before threshold)

**On Speech End** (`onSpeechEnd`):
1. Close audio gate (stop sending audio)
2. Check `bargeInTriggeredRef` flag
3. **If barge-in was triggered** (valid speech):
   - Send `activity_end` to Gemini
   - Reset escalation to 0
   - Log: "Valid turn detected"
4. **If barge-in was NOT triggered** (short noise):
   - **Do NOT** send `activity_end` (no turn to complete)
   - Restart watchdog timer
   - Log: "Turn too short - no barge-in triggered, discarding"

**Benefits**:

- ✅ **No unnecessary interruptions**: Throat clears don't interrupt Gemini
- ✅ **Smooth TTS playback**: Gemini continues speaking through brief noises
- ✅ **Fast barge-in for real speech**: 450ms is barely noticeable to users
- ✅ **Clean audio flow**: Short noises open/close gate without signaling
- ✅ **No deadlock risk**: Only send `activity_end` if we sent `activity_start`
- ✅ **Symmetrical protocol**: Barge-in and turn completion always paired

**Scenarios**:

- **Throat clear (200ms)**: VAD detects → Gate opens → 200ms later speech ends → Gate closes → Delayed barge-in timer never fires → ✅ No interruption
- **Real speech (1500ms)**: VAD detects → Gate opens → 450ms later **barge-in triggered** → 1500ms total speech ends → Gate closes → `activity_end` sent → ✅ Clean turn
- **Quick word (300ms)**: VAD detects → Gate opens → 300ms later speech ends (before 450ms) → Gate closes → Delayed barge-in never fires → ✅ No interruption

### Minimum Turn Duration Validation (DEPRECATED - See Delayed Barge-In)

**Note**: This section describes the old approach (validation on `onSpeechEnd`). The new approach (Delayed Barge-In) prevents interruption in the first place by validating duration on `onSpeechStart`.

~~**Problem**: Short grunts, coughs, or background noises trigger `activity_start` → `activity_end` cycle without sufficient audio for Gemini to process as a valid turn, causing conversational deadlock.~~

~~**Solution**: Frontend tracks speech duration and only sends `activity_end` if speech lasted ≥800ms.~~

**Implementation** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):

- `onSpeechStart`: Record timestamp, open audio gate
- `onSpeechEnd`: Calculate duration
  - If duration ≥800ms → send `activity_end` (valid turn)
  - If duration <800ms → ignore (let Gemini's VAD handle timeout)
  - **Always close gate** (privacy protection even for short noises)

**Benefits**:

- ✅ Prevents incomplete turns that confuse Gemini
- ✅ Gemini can gracefully continue where she left off
- ✅ No conversational deadlock from brief noises
- ✅ User doesn't have to restart conversation after accidental grunt
- ✅ Privacy maintained even during short false positives

### Activity Watchdog (Inactivity Recovery)

**Problem**: If Gemini or user becomes silent for extended periods (user walks away, Gemini confused, grunt deadlock), conversation stalls indefinitely, burning tokens.

**Solution**: Progressive escalation system monitors activity and intervenes at increasing levels.

**Timing**:

- Check every 1 second for inactivity
- 8 seconds without user speech OR Gemini audio → intervention
- 3 escalation levels over 24 seconds total

**Escalation Levels**:

1. **Level 1 (8s)**: Prompt for next field
   - Frontend sends: `{type: "recovery_prompt", level: 1, next_field_hint: "firstName (First Name)"}`
   - Backend uses: `RECOVERY_PROMPT_LEVEL_1` from `backend/config.py`
   - Recovers from minor confusion or short grunt deadlock

2. **Level 2 (16s)**: Check user presence
   - Frontend sends: `{type: "recovery_prompt", level: 2}`
   - Backend uses: `RECOVERY_PROMPT_LEVEL_2` from `backend/config.py`
   - Detects if user walked away or stopped responding

3. **Level 3 (18s)**: Graceful session close
   - Frontend sends: `{type: "recovery_prompt", level: 3}`
   - Backend uses: `RECOVERY_PROMPT_LEVEL_3` from `backend/config.py`
   - Gemini speaks goodbye message
   - Frontend sets `waitingForFarewellRef.current = true` flag
   - Backend detects when Gemini finishes speaking (transcript arrives after audio chunks)
   - Backend sends: `{type: "turn_complete"}` WebSocket message
   - Frontend receives signal → immediately disconnects (no timeout guessing)
   - Gemini session closed (saves tokens)
   - WebSocket closed
   - Field values preserved in sessionStorage (no data loss)
   - UI status reset to "Ready" (button shows "Connect to Voice")
   - User can reconnect instantly when ready

**Prompt Configuration** (`backend/config.py`):

All recovery prompt text is centralized in backend configuration for easy tuning:

- `RECOVERY_PROMPT_LEVEL_1`: "The user seems to have paused. Please ask them for: {next_field_hint}"
- `RECOVERY_PROMPT_LEVEL_2`: 'Say to the user: "Hello, are you still there? If you need a moment, just let me know."'
- `RECOVERY_PROMPT_LEVEL_3`: 'Say to the user: "I haven\'t heard from you in a while..."'

These are **SCRIPTS** for Gemini to read aloud, not commands directed at her.

**Timing Configuration** (`frontend/frontend.config.ts`):

- `INACTIVITY_TIMEOUT_MS`: 6000 (6 seconds between escalation levels)
- `MAX_ESCALATION_LEVEL`: 3 (18 seconds total: 6s + 12s + 18s)
- `MIN_SPEECH_DURATION_MS`: 450 (minimum valid user turn duration)

**Activity Tracking**:

- **User speech** (valid turn ≥450ms) → reset escalation to 0, restart timer
- **Gemini audio ends** → restart timer (escalation level unchanged)
- **Short noises** (<450ms) → ignored, timer continues
- **Audio playback callback**: Debounced 500ms to prevent log spam

**Turn Complete Detection** (Level 3 Signal-Based Disconnect):

**Problem**: Fixed timeouts couldn't account for variable speech speed and network latency, causing farewell message cutoff.

**Solution**: Backend signals exactly when Gemini finishes speaking using `output_transcription` event.

**Implementation**:
1. Backend: `on_transcript` callback sends `{type: "turn_complete"}` after transcript arrives
2. Frontend: `webFormConnection.ts` routes message to `window.vffOnTurnComplete()` callback
3. Overlays: Check `waitingForFarewellRef` flag, disconnect immediately if true
4. Result: Full farewell message plays, then instant disconnect (no guessing)

**Files**:
- `backend/services/form_filling_service.py` - Emits turn_complete signal
- `frontend/src/shared/connection.ts` - Window interface for callback
- `frontend/src/webFormConnection.ts` - Message routing
- `frontend/src/demo/VoiceOverlay.tsx` - Desktop handler
- `frontend/src/demo/VoiceOverlayMobile.tsx` - Mobile handler

**Lifecycle**:

- **Connect** → start watchdog
- **Disconnect/Pause** → stop watchdog
- **Unmount** → stop watchdog (cleanup)

**Implementation** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):

- `startActivityWatchdog()`: Initialize interval check
- `resetActivityTimer()`: Called on valid activity (user/Gemini)
- `handleEscalationLevel1/2/3()`: Progressive interventions
- `stopActivityWatchdog()`: Cleanup on disconnect/unmount
- `window.vffOnTurnComplete`: Callback for turn_complete signal

**Benefits**:

- ✅ **Prevents token burn**: Auto-disconnect after 18s of inactivity (was 24s)
- ✅ **No data loss**: SessionStorage preserves filled fields
- ✅ **Automatic recovery**: Nudges Gemini to continue after minor stalls
- ✅ **User-friendly**: Clear messaging at each escalation level
- ✅ **Fast reconnect**: Cloud connection is instant (~100ms)
- ✅ **Precise Level 3**: Full farewell message plays (no cutoff)
- ✅ **Signal-based**: Uses Gemini's own completion event (no timeout guessing)

### Audio Playback Fallback (Initial Message Retry)

**Problem**: Gemini's audio sometimes fails to play after connection or section switching, causing silent gaps where users expect to hear instructions. This is particularly noticeable after section changes when users are actively engaged.

**Solution**: Context-aware fallback mechanism that automatically resends the initial message if Gemini doesn't respond within a timeout period.

**Timing**:
- **Initial Connection**: 3.0 seconds (cold start, user expectations are patient)
- **Section Switching**: 1.5 seconds (warm transition, user expects immediate response)

**Implementation** (`backend/adapters/live_ai_gemini.py`):

**Detection Logic**:
```python
is_section_switch = "Section" in self._initial_message and "moving to" in self._initial_message.lower()
fallback_delay = 1.5 if is_section_switch else 3.0
```

**Fallback Mechanism**:
1. Backend sends initial message via `session.send_client_content()`
2. Start background task that waits for `fallback_delay` seconds
3. Track if Gemini responds: `gemini_has_responded = True` on first audio chunk
4. If timeout expires without response: Resend initial message
5. If response arrives before timeout: Cancel fallback (no duplicate)

**Scenarios**:

- **Initial Connection (Cold Start)**: Backend sends greeting → Waits 3.0s → If no audio, resends → User hears greeting within 3s max
- **Section Switch (Warm Transition)**: Backend sends section message → Waits 1.5s → If no audio, resends → User hears transition within 1.5s max
- **Audio Arrives On Time (Happy Path)**: Gemini responds → `gemini_has_responded = True` → Fallback exits cleanly → No duplicate

**Benefits**:

- ✅ **Faster recovery from audio loss during section switching** (1.5s vs 3s)
- ✅ **Maintains conservative timeout for initial connection** (cold start needs patience)
- ✅ **Better logging** for debugging audio issues
- ✅ **No breaking changes** - existing functionality preserved
- ✅ **Context-aware behavior** - adapts to user's engagement level

---

## Session Keep-Alive (Heartbeat)

**Problem**: Gemini Live API sessions timeout after periods of inactivity (user pauses, manual form filling), causing `"send_activity_end_no_session"` errors.

**Solution**: Periodic heartbeat sends silence packets to keep session alive.

**Implementation** (`backend/adapters/live_ai_gemini.py`):

- Heartbeat task runs concurrently with audio/text senders
- Sends 320 bytes of silence (20ms at 16kHz PCM16) every 30 seconds
- Automatically cancelled on session end

**Benefits**:

- Users can pause for minutes without losing session
- Minimal overhead: 10.7 bytes/second
- No token cost (silence doesn't trigger AI processing)
- Transparent to user experience

**Cleanup**: Heartbeat task properly cancelled via `asyncio.wait_for()` with 1s timeout during session teardown.

---

## Intentional Disconnect Prevention (Auto-Reconnect Fix)

**Problem**: Backend retry loop was automatically reconnecting after Level 3 timeout (intentional disconnect), instead of waiting for user to manually reconnect.

**Root Cause**:

- `finalize_gemini_session()` closes Gemini connection cleanly
- Gemini adapter catches `ConnectionClosed` exception, breaks inner loop
- Outer retry loop (designed for DNS/network errors) continued executing
- Since `attempt < max_attempts` (1 of 3), it automatically reconnected
- User experienced unwanted auto-reconnect without clicking Connect button

**Solution**: Added `_intentional_shutdown` flag to distinguish intentional vs accidental disconnects.

**Implementation** (`backend/adapters/live_ai_gemini.py`):

```python
# Instance variable (line 132)
self._intentional_shutdown: bool = False  # Track intentional finalize() to prevent auto-retry

# Set flag on intentional shutdown (line 310-312)
async def finalize(self):
    """Stop the background task and clear resources."""
    self._intentional_shutdown = True  # Prevent retry loop
    # ... rest of cleanup ...

# Check flag in retry loop (line 1083-1087)
while attempt < max_attempts:
    if self._intentional_shutdown:
        self._log.info("session_intentionally_closed_no_retry")
        return  # Exit cleanly, don't retry
    # ... rest of retry logic ...
```

**Lifecycle**:

1. **Level 3 timeout** → Frontend calls `endGeminiSession()`
2. **Backend finalize()** → Sets `_intentional_shutdown = True`
3. **Gemini disconnects** → ConnectionClosed exception caught
4. **Retry loop** → Checks flag, sees intentional shutdown, exits cleanly
5. **No auto-reconnect** → User must manually click Connect button
6. **Manual reconnect** → Frontend sends `restart_gemini_session` message
7. **Backend restarts** → `set_callbacks()` resets flag to False for new session

**Benefits**:

- ✅ **User control**: No unwanted reconnections after timeout
- ✅ **Clear UX**: System stays in "Ready" state until user clicks Connect
- ✅ **Network error tolerance**: Automatic retry still works for DNS/socket failures (max 3 attempts)
- ✅ **Clean separation**: Flag distinguishes user intent from network issues

**Files Modified**:

- `backend/adapters/live_ai_gemini.py` - Added flag and retry loop check

---

## Section Switching Architecture

**Overview**: Allows users to navigate between form sections while maintaining WebSocket connection and refreshing Gemini's context for the new section.

### Protocol Flow

1. **User Initiates Switch**
   - Frontend: User clicks section navigation
   - Frontend: Stops audio recording
   - Frontend: Waits for WebSocket send buffer to drain (`ws.bufferedAmount === 0`)

2. **Frontend Sends Switch Request**
   - **Message Type**: `manual_section_switch`
   - **Payload**: Embedded section info (no round-trip needed):
     ```typescript
     {
       type: "manual_section_switch",
       identifier: "2",  // Target section number
       section_info: {
         schema: {...},           // Section fields
         current_values: {...},   // Pre-filled values
         metadata: {
           section_number: 2,
           total_sections: 5,
           section_label: "Contact Information",
           previous_spoken_names: [...]  // Fields from completed sections
         },
         initial_field_hint: "..."  // Next unfilled field hint
       }
     }
     ```

3. **Backend Processes Switch**
   - **Route Handler** (`websocket_routes.py`):
     - Sets `drop_audio = True` to ignore queued audio frames
     - Calls `service.switch_to_section()`
   
   - **Service Layer** (`form_filling_service.py`):
     - Calls `await self._live_ai.finalize()` to close current Gemini session
     - Builds new system instruction with section context
     - Calls `self.start_session()` with new schema/values/instruction
     - Sends `section_switched` confirmation to frontend

4. **Frontend Receives Confirmation**
   - Updates overlay status from `switching_section` to `connected`
   - Resumes audio recording
   - User can immediately start speaking about new section

### Key Implementation Details

**WebSocket Buffer Management**:
- Frontend waits for `ws.bufferedAmount === 0` before sending control messages
- Prevents control messages from queuing behind audio frames
- Uses polling with 10ms intervals, 1-second max wait

**Audio Handling During Switch**:
- Backend drops audio frames while `drop_audio = True`
- Prevents stale audio from old section reaching new Gemini session
- Resumes processing after `section_info_response` or on error

**Non-Blocking Audio Processing**:
- Backend uses `asyncio.create_task()` for audio streaming
- Audio queue limited to 100 frames (maxsize=100)
- Uses `put_nowait()` to drop frames instead of blocking
- Prevents audio backlog from blocking WebSocket message reception

**Gemini Session Management**:
- `finalize()` fully closes old session and clears context
- `start_session()` creates fresh Gemini connection with:
  - New system instruction (section fields, metadata)
  - New initial message (field hint for first unfilled field)
  - Same callbacks (reused from initial connection)
- No partial updates or state carryover

**No Round-Trip Delay**:
- Previous implementation: Backend requests section info → waits → times out
- Current implementation: Frontend sends all data immediately
- Eliminates 5-second timeout issues and race conditions

### Error Handling

- **Missing section_info**: Backend logs warning, ignores request
- **Gemini finalize failure**: Logged but continues with new session creation
- **start_session failure**: Exception propagated, frontend receives error message
- **WebSocket send failure**: Logged, section switch completes anyway

### Benefits

✅ **Zero round-trips**: All section data sent in initial message  
✅ **Fresh Gemini context**: No field knowledge from previous sections  
✅ **Instant switching**: No timeout delays or buffering issues  
✅ **Persistent WebSocket**: Connection stays alive throughout navigation  
✅ **Robust error handling**: Graceful degradation on failures  

### Migration Notes

- **Breaking Change**: Removed `prepare_section_switch` request/response pattern
- **Deprecated Messages**: `section_info_response` handler kept for backward compatibility but unused
- **Frontend Required**: Must send embedded `section_info` in switch message

**Why Backend-Side Reconnect**:
- ✅ Properly flushes Gemini's context (old section fields forgotten)
- ✅ No WebSocket reconnection overhead
- ✅ No race conditions
- ✅ Backend controls AI session lifecycle
- ✅ Frontend stays connected throughout

**Required Changes**:
1. Backend: Add `switch_to_section()` method that tears down Gemini session and creates new one
2. Backend: Send `section_switched` confirmation to frontend
3. Frontend: Remove disconnect/reconnect logic from `switchSection()`
4. Frontend: Update state on receiving `section_switched` message

---

## Next Field Navigation (Token Optimized)

**Problem**: Separate messages to Gemini for field navigation double token usage per field.

**Solution**: Embed `next_field_hint` in existing message flow (single model turn per field).

### Flow Optimization

**Initial Message** (session start):
1. Frontend computes hint synchronously: `"Next unfilled field: firstName (First Name)"`
2. Frontend includes hint in handshake: `{schema, current_values, initial_field_hint}`
3. Backend extracts hint from handshake (no async request needed)
4. Backend appends to initial message: `"Begin with warm greeting and ask for: firstName (First Name)"`
5. One model turn → Gemini greets and asks for first field

**Tool Response** (each field update):
1. Gemini calls `update_form_fields` → Backend validates
2. Backend sends `form_updated` WITH `request_next_field_hint=true` and `request_id`
3. Frontend receives update → computes next hint → sends `next_field_hint_response`
4. Backend awaits hint (2s timeout) → includes in tool response `message` field
5. One model turn → Gemini confirms field and asks for next

**Key Benefits**:
- 50% reduction in model turns (1 instead of 2 per field)
- 50% reduction in network round trips
- Hint embedded in tool response = natural flow
- Backend remains stateless (frontend computes hint)
- No deadlock risk - hint available before WebSocket accept()

### Implementation

**Backend** (`websocket_routes.py`, `form_filling_service.py`):
- Handshake handler: Extracts `initial_field_hint` from handshake
- `start_session()`: Receives hint as parameter (no async request)
- Tool handler: `message = next_field_hint or "Fields updated successfully."`
- `send_form_update()`: Piggybacks hint request on form update, returns hint
- `handle_next_field_hint_response()`: Resolves async Future with hint

**Frontend** (`webFormConnection.ts`):
- `connect()`: Computes `initial_field_hint` before connection via `computeNextFieldHintString()`
- Handshake: Includes `initial_field_hint` in WebSocket handshake message
- `handleFormUpdated()`: Detects `request_next_field_hint`, responds with hint
- `computeNextFieldHintString()`: Computes formatted hint from sessionStorage

**Config** (`config.py`):
- `SYSTEM_INSTRUCTION`: "Use tool response hint → ask next field"
- `INITIAL_MESSAGE`: "Begin with warm greeting and ask for: " (hint appended)

---

## VAD Visual Indicators

**Purpose**: Provide real-time visual feedback when voice activity is detected, helping users understand when the system is listening and enabling VAD parameter tuning.

### Implementation

**VAD Library**: `@ricky0123/vad-react` - Professional Silero VAD model with React hooks

**Hook**: `frontend/src/demo/useDemoVAD.ts`
- Exposes `userSpeaking` boolean state
- Callbacks: `onSpeechStart`, `onSpeechEnd`, `onVADMisfire`
- Auto-starts when connection status becomes "connected"
- Pauses in push-to-talk mode
- **Audio Processing**: Custom `getStream` configuration with:
  - `echoCancellation: true` - Prevents Gemini's audio output from triggering false VAD detections (eliminates stuttering)
  - `noiseSuppression: true` - Reduces background noise interference
  - `autoGainControl: true` - Normalizes microphone volume for consistent detection

### Visual Design

**Desktop Overlay** (`VoiceOverlay.tsx`):
- Green pill badge in status bar
- Pulsing green dot + "LISTENING" text
- Light green background (#d1fae5) with green border
- Appears to the right of connection status
- Distinct from connection status icon

**Mobile FAB** (`VoiceOverlayMobile.tsx`):
- Small circular badge in top-right corner of FAB
- White background with pulsing green dot
- Positioned like a notification badge
- Clearly distinct from connection status pulse

### Auto-Start Logic

When using shared connection manager:
- useEffect monitors `status` prop
- When status becomes "connected" → `vad.start()` 
- When status disconnects → `vad.pause()`
- Respects push-to-talk mode (VAD disabled when PTT active)

---

## Shared Connection Manager (Demo)

**Problem**: Desktop and mobile overlays each created separate connection managers. Resizing window caused layout switch → connection lost → duplicate connections on reconnect.

**Solution**: Lift connection manager to parent component (`AdultIntakeDemo.tsx`) and share between desktop/mobile layouts.

### Architecture

**Parent Component** (`AdultIntakeDemo.tsx`):
- Creates single `ConnectionManager` instance on mount
- Stores in ref to survive React StrictMode remounts
- Passes manager + status to active overlay (desktop or mobile)
- Manager persists across layout switches

**Child Overlays** (`VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`):
- Accept optional `connectionManager` and `status` props
- If shared manager provided → use it (demo mode)
- If not provided → create own manager (standalone/bookmarklet mode)
- Sync status from parent via useEffect

### Benefits

- ✅ Window resize preserves connection state
- ✅ Switch desktop ↔ mobile: no interruption
- ✅ VAD state persists across layout changes
- ✅ No duplicate connections on reconnect
- ✅ Button states remain synchronized
- ✅ Still supports standalone mode (bookmarklet)

### React StrictMode Handling

**Issue**: React StrictMode mounts components twice in development
- First mount: creates manager
- StrictMode unmount: (cleanup skipped in old code)
- StrictMode remount: creates second manager → 2 connections!

**Solution**: Use ref to detect existing manager
```typescript
const connectionManagerRef = useRef<ConnectionManager | null>(null)

useEffect(() => {
  if (connectionManagerRef.current) return // Skip if exists
  // Create manager...
  connectionManagerRef.current = manager
  return () => {
    if (connectionManagerRef.current) {
      connectionManagerRef.current.disconnect()
      connectionManagerRef.current = null
    }
  }
}, [])
```

---

## Session Initialization (Simplified)

**Direct Start** (no warmup):
1. Client sends handshake with schema + current_values
2. Backend calls `start_session()` (registers callbacks, accepts WebSocket)
3. Backend sends system instruction with full form context
4. Backend requests `next_field_hint` from frontend
5. Backend sends initial message with hint appended
6. Gemini receives one complete context and begins

**Config**: Single template in `backend/config.py`:
- `SYSTEM_INSTRUCTION`: Full form-filling rules and context
- `INITIAL_MESSAGE`: Prompt for greeting (hint appended at runtime)

**Note**: Warmup/upgrade pattern removed for simplicity. All sessions start with full context.

---

## HIPAA Compliance

**Client**: sessionStorage (cleared on tab close)

**Backend**: In-memory schema only (destroyed on disconnect)

**Gemini**: Ephemeral audio processing per Vertex AI policies

**Logs**: Session IDs, errors, metrics ONLY - NO field values, NO PHI

**Transport**: TLS everywhere (WSS, HTTPS)

---

## Frontend Module Organization

**Shared Core Modules** (`frontend/src/shared/`):
- `connection.ts` - WebSocket connection management and session lifecycle
- `audioManager.ts` - Microphone recording & AI audio playback (16kHz/24kHz PCM16)
- `fieldManager.ts` - Form field updates & manual edit detection
- `config.ts` - Backend URL configuration (local dev / cloud switching)
- `metrics.ts` - VAD tuning & barge-in performance tracking
- `languages.ts` - Supported fill languages (80+ languages)
- `security.ts` - XSS prevention utilities
- `audio-processor.worklet.ts` - AudioWorklet for PCM16 conversion
- `greetingPrompts.ts` - Greeting carousel messages

**Demo Application** (`frontend/src/demo/`):
- `main.tsx` - React entry point
- `AdultIntakeDemo.tsx` - Demo component with pre-defined form schema
- `VoiceOverlay.tsx` - Desktop voice UI
- `VoiceOverlayMobile.tsx` - Mobile voice UI (FAB design)
- `GreetingCarousel.tsx` - Visual welcome component
- `useDemoVAD.ts` - Voice activity detection hook (@ricky0123/vad-react)

**Core State Management**:
- `webFormState.ts` - Form state management (sessionStorage)
- `webFormConnection.ts` - WebSocket message handling and connection logic

**VAD Tuning** (`frontend/src/vad-tuning/`):
- Development tools for tuning voice activity detection parameters

---

## Key Files

**Backend**:
- `config.py` - System configuration and settings
- `services/form_filling_service.py` - Core business logic
- `routes/websocket_routes.py` - WebSocket endpoint handlers
- `adapters/live_ai_gemini.py` - Gemini Live API integration

**Frontend State & Connection**:
- `webFormState.ts` - Form state management
- `webFormConnection.ts` - WebSocket message handling

**Frontend Shared Modules**:
- `shared/connection.ts` - Connection manager
- `shared/audioManager.ts` - Audio recording/playback
- `shared/fieldManager.ts` - Form field updates
- `shared/config.ts` - Backend URL configuration

**Demo Application**:
- `demo/main.tsx` - React entry point
- `demo/AdultIntakeDemo.tsx` - Main demo component
- `demo/VoiceOverlay.tsx` - Desktop UI
- `demo/VoiceOverlayMobile.tsx` - Mobile UI
- `demo/useDemoVAD.ts` - VAD integration

---

## Environment Configuration

### Backend Environment Variables

**Configuration**: Backend uses `.env` file loaded by `python-dotenv` in `main.py`

**Authentication Methods**:
- **Vertex AI** (default, `VERTEXAI=true` in `config.py`): Uses Application Default Credentials
  - No API key needed in `.env` file
  - Run: `gcloud auth application-default login`
  - Backend automatically uses gcloud credentials
- **Google AI Studio** (alternative): Set `GEMINI_API_KEY` in `.env`

**Development Logging**:
- `VFF_DEV_LOGGING=true` - Enables detailed tool call/response logging
- Default: `false` (production-safe)
- Controlled by `backend/utils/dev_logger.py`
- **Never set in production** - defaults to disabled for safety

**Example `backend/.env`**:
```bash
# Enable development logging (verbose output)
VFF_DEV_LOGGING=true

# Vertex AI users (default): No API key needed!
# Just run: gcloud auth application-default login

# Google AI Studio users: Uncomment and add your API key
# GEMINI_API_KEY=your-api-key-here

# Optional: Specify GCP project explicitly
# GOOGLE_CLOUD_PROJECT=your-project-id
```

**Security**:
- `.env` files in `.gitignore` (both root and `backend/.env`)
- Never commit secrets to repository
- Production deployments use service accounts (no `.env` file)

**Documentation**: See `backend/ENV_VARIABLES.md` for complete setup guide

### Frontend Environment Variables

**Backend URLs are controlled by environment variables:**

### Local Development
- `.env` file: `VITE_WS_URL=ws://localhost:8000/ws/fill`
- Run `npm run dev` → connects to local backend
- No timeout, no fallback needed

### Production Deployment
- Deploy script overrides: `VITE_WS_URL="wss://CLOUD_URL/ws/fill" npm run build:demo`
- Built app connects directly to cloud backend
- All operations (connect, section switching, reconnect) use same cloud URL
- See `frontend/deploy-demo.sh` line 23

### Configuration Priority
1. `window.__VFF_LOCAL_DEV` (runtime override for testing)
2. `import.meta.env.VITE_WS_URL` (build-time from deploy script or .env)
3. `ws://localhost:8000/ws/fill` (default fallback)

**Key File**: `frontend/src/shared/config.ts` - Single source of truth for backend URL resolution

