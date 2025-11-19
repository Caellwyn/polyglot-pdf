<!-- markdownlint-disable MD022 MD031 MD032 MD036 MD040 -->

# Voice Form Filler - Technical Architecture Guide

**Version**: 3.2
**Last Updated**: November 19, 2025
**Status**: Production-Ready Core with Active Development

---

## Executive Summary

The Voice Form Filler is a specialized application designed to help non-English speakers complete complex USCIS immigration forms through voice interaction with Gemini AI. The system prioritizes accuracy over speed, processing one field at a time with mandatory confirmation workflows. It addresses unique challenges including broken conditional logic in USCIS PDFs and deployment in noisy nonprofit office environments.

**Major Features (as of Nov 19, 2025)**:
- ✅ Schema-driven forms with section-based navigation (16 sections for I-90)
- ✅ Hallucination reduction features (PTT mode, audio filters, single-field constraint)
- ✅ Token reduction backend (94% reduction: 7,400→458 tokens, feature flag ready)
- ✅ Shared audio stream architecture (eliminates race conditions)
- ✅ Auto-scroll to fields when Gemini fills them (smooth scroll + highlight)
- ✅ **Confirmation system with legal audit trail** (completed Nov 18, 2025)
- ✅ **Gated onboarding flow with language selection and disclaimer** (completed Nov 19, 2025)
- ✅ **Reconnect button for idle timeouts** (completed Nov 19, 2025)
- ⚠️ Legacy demo system deprecated but not removed (cleanup pending)

---

## System Architecture Overview

### Core Technology Stack

**Frontend**
- **Framework**: React 18.x with TypeScript
- **State Management**: Custom SchemaFormStateManager with sessionStorage persistence
- **Audio Processing**: WebAudio API with custom audio worklet
- **PDF Rendering**: PDF.js for form display and interaction
- **Real-time Communication**: WebSocket client for bidirectional streaming

**Backend**
- **Framework**: Python FastAPI
- **Voice AI**: Gemini Live API integration
- **Architecture**: Stateless design for privacy compliance
- **Session Management**: Client-driven state with server validation
- **WebSocket Server**: Real-time bidirectional communication

**Data Flow**
```
User Voice Input → Audio Processing → WebSocket → Backend → Gemini Live API
                                                      ↓
UI Updates ← WebSocket ← Form Updates ← Validation ← Gemini Response
```

---

## Frontend Architecture

### Schema-Driven Form System

The application recently transitioned from a demo-based architecture to a schema-driven system. This provides consistent form handling across all USCIS forms.

#### Core Components

**SchemaFormStateManager** (`frontend/src/schema-forms/state/schemaFormState.ts`)
- Singleton state manager for all form operations
- Handles field updates, validation, and persistence
- Manages section-based navigation (e.g., section 1.1→1.2→1.3→2)
- Tracks completion status per section
- Stores data in sessionStorage for privacy
- Deduplication uses exact ID matching (no pattern-based merging)

**SchemaForm Component** (`frontend/src/schema-forms/components/SchemaForm.tsx`)
- Main form rendering component
- Handles section-based USCIS form structure (16 sections for I-90)
- Progress tracking shows section count (e.g., "Section 3 of 16 • 25% complete")
- Field rendering based on schema definitions
- Navigation properly sequential: 1.1→1.2→1.3→2 (fixed Nov 18, 2025)

**Field Components** (`frontend/src/schema-forms/components/fields/`)
- TextField, TextAreaField, SelectField, RadioField, CheckboxField, DateField
- All components handle FieldValue wrapper objects
- Type-safe unwrapping utilities prevent [object Object] display issues
- Support for both primitive values and wrapped values

#### FieldValue Wrapper System

**Problem Solved**: AI-filled fields need metadata (confirmation status, timestamp) while manual entries are primitives.

**Solution**: Unified handling through utility functions:
```typescript
// fieldValue.ts utilities
isFieldValue(value) - Type guard for detection
unwrapFieldValue(value) - Extract primitive value
unwrapToString(value) - Convert to string for text inputs
unwrapToBoolean(value) - Convert to boolean for checkboxes

// FieldValue structure
interface FieldValue {
  value: string | boolean | string[];
  confirmed: boolean;
  confirmedAt?: string; // ISO timestamp
  confirmationMethod?: 'ai_voice' | 'manual_edit' | 'manual_button';
  updatedAt?: string;
}
```

**Implementation Status**: ✅ Complete (Nov 8, 2025)
- All field components updated
- Unit tests: 26/26 passing
- Browser testing confirmed

#### Confirmation System

**Purpose**: Legal liability protection - prove users confirmed each field entry.

**Architecture** (Completed Nov 18, 2025):

1. **State Model**
   - FieldValue objects track `confirmed` boolean and confirmation metadata
   - SchemaFormState persists confirmation status in sessionStorage
   - Auto-confirmation: Manual edits automatically marked as confirmed

2. **Backend Tools**
   - `confirm_field(field_id, confirmation_method)` - Marks field as confirmed
   - `get_form_status()` - Returns field values with confirmation status
   - Token-optimized responses (only returns unconfirmed fields)

3. **UI Indicators**
   - Green checkmark badge (✓) next to confirmed field labels
   - `form-field--confirmed` CSS class highlights confirmed fields
   - All 6 field types support confirmation UI

4. **Navigation Logic**
   - `computeNextField()` prioritizes unconfirmed fields over empty fields
   - Guides user through confirmation workflow systematically
   - 7/7 unit tests passing (navigation-confirmation.test.ts)

5. **Audit Logging** (`backend/utils/confirmation_logger.py`)
   - Logs: `{timestamp, form_id, form_session_id, field_id, confirmation_method}`
   - **NO PII logged** (field values never written to logs)
   - One JSONL file per form session: `logs/confirmations/{form_session_id}.jsonl`
   - Legal audit trail for liability protection

**Workflow**:
- User fills field via voice → Gemini asks "Is that correct?" → User confirms → Logged
- User types manually → Auto-confirmed immediately → Logged
- Next field hint prioritizes unconfirmed fields

### Voice Interaction Layer

#### Shared Audio Stream Architecture

**Problem Solved**: React component rendering race conditions where VoiceOverlay attempts to create audio stream before getUserMedia permissions are granted.

**Solution**: Parent component (`SchemaForm`) creates audio stream early, before child overlays render:
```typescript
// SchemaForm.tsx
const [sharedStream, setSharedStream] = useState<MediaStream | null>(null);

useEffect(() => {
  async function initSharedStream() {
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, sampleRate: 16000 }
    });
    setSharedStream(stream);
  }
  initSharedStream();
}, []);

// Pass to child overlays
<VoiceOverlay sharedStream={sharedStream} streamError={streamError} />
```

**Benefits**:
- Eliminates race conditions
- Single audio permission request
- Consistent stream across components
- Error handling at parent level

#### Audio Processing Pipeline

**Audio Worklet** (`frontend/src/shared/audio-processor.worklet.ts`)
```
Microphone → Noise Gate (-50dB) → High-Pass Filter (80Hz) → VAD → WebSocket
```

**Processing Features**:
- **Noise Gate**: -50dB threshold (adjusted Nov 7 for quiet speakers)
- **High-Pass Filter**: 80Hz cutoff to remove low-frequency rumble
- **VAD (Voice Activity Detection)**: Configurable but currently bypassed in PTT mode
- **Push-to-Talk Mode**: Default interaction mode for accuracy

#### Voice Overlays

**Desktop Overlay** (`frontend/src/demo/VoiceOverlay.tsx`)
- Push-to-Talk toggle (iOS-style switch)
- Section dropdown for navigation (shows all 16 sections for I-90)
- Visual indicators: ✓ (completed), → (current), ○ (pending)
- Field count display
- Connection status indicator with idle timeout detection
- Reconnect button for idle timeouts (no page refresh needed)
- Default: PTT mode enabled

**Mobile Overlay** (`frontend/src/demo/VoiceOverlayMobile.tsx`)
- Full-width PTT bar button at bottom
- Section dropdown matching desktop functionality
- Optimized for 8-inch tablets
- Touch-friendly controls
- Reconnect button for idle timeouts
- Default: PTT mode enabled

**Onboarding Flow** (Nov 19, 2025)
- **Language Selection Modal**: Icon-based modal appears on first visit
  - Uses native language names (e.g., "Español" not "Spanish")
  - Minimal text - relies on 🌍 🗣️💬 icons for universal understanding
  - Target audience: non-English speakers
  - Component: `LanguageSelectionModal.tsx`
- **Disclaimer Modal**: Appears after language selection
  - Gemini reads disclaimer aloud in selected language
  - "Listen Again" and "I Agree" buttons translated to user's language
  - Non-dismissible until accepted
  - Backend logging of acceptance with timestamp and language
  - Component: `DisclaimerModal.tsx`
- **Returning Users**: Skip both modals if disclaimer already accepted
  - State persisted in sessionStorage
  - Includes language preference and acceptance timestamp

**Connection Manager** (`frontend/src/shared/connection.ts`)
- WebSocket connection handling
- Handshake protocol with backend
- Tool call processing
- State synchronization
- Section-based navigation (16 sections for I-90)
- Shared audio stream management
- Auto-scroll to fields when Gemini updates them (smooth + highlight animation)

### State Management Architecture

**Client-Side State Hierarchy**:
```
SchemaFormState
├── schema (form structure with sections array)
├── fieldValues (user data with FieldValue wrappers)
├── currentSectionId (active section, e.g., "part_1_1" for section 1.1)
├── completedSections (Set of completed section IDs)
├── validationErrors (field-level errors)
├── conditionalState (field visibility/requirements)
└── loadedFieldIds (fields sent to Gemini - JIT mode)
```

**Persistence Strategy**:
- All state stored in sessionStorage
- No server-side state storage (privacy requirement)
- State survives page refreshes
- Cleared on session end

---

## Backend Architecture

### Core Services

**FormFillingService** (`backend/services/form_filling_service.py`)
- Manages form-filling sessions
- Prepares context for Gemini
- Handles tool callbacks
- Validates field updates
- Section switching: Closes and restarts Gemini session with new section context
- Current: Sends full section schema (~7,400 tokens)
- Ready: Send field manifest + current field (~500 tokens with USE_JIT_SCHEMA=true)
- **Disclaimer Reading** (Nov 19, 2025):
  - `send_disclaimer_message()` method triggers Gemini to read disclaimer aloud
  - Uses command-style initiating message pattern (overrides "wait for user" behavior)
  - Supports all 18 spoken languages

**ValidationHandler** (`backend/services/validation_handler.py`)
- Field-level validation
- Type checking and format validation
- Conditional requirement checking
- Exact and fuzzy field matching

**CallbackHandler** (`backend/services/callback_handler.py`)
- Processes Gemini tool calls
- Routes to appropriate handlers
- Returns structured responses
- Includes next field hints (planned)

**AudioHandler** (`backend/services/audio_handler.py`)
- Manages audio streaming to/from Gemini
- Queues audio chunks for non-blocking delivery
- Handles activity start/end signals
- Integrates with LiveAI adapter

**RequestCoordinator** (`backend/services/request_coordinator.py`)
- Coordinates async request/response pattern
- Manages frontend state queries
- Handles timeouts and error recovery
- Ensures tool responses match requests
- Owns section-switching handshake (`prepare_section_switch` → `section_info_response`), decoupling
  `FormFillingService` from raw WebSocket traffic.

#### Section Switching Flow (Nov 2025 refresh)

1. Gemini calls the `switch_section` tool via Live AI.
2. `FormFillingService.handle_switch_section` awaits `request_section_info(...)` on the
  `RequestCoordinator`, which emits a `prepare_section_switch` message to the frontend.
3. The frontend responds with `section_info_response` containing schema, current values,
  metadata, and the next prompt hint; the coordinator resolves the awaiting future.
4. `FormFillingService.switch_to_section` finalizes the old Gemini session, rebuilds the
  callbacks/system instruction, and confirms the change back to the client.
5. The corresponding pytest coverage focuses on coordinator delegation instead of private
  futures on `FormFillingService` so the tests mirror production behavior.

**FieldUtils** (`backend/services/field_utils.py`)
- Builds field objects from schema
- Extracts spoken names for voice navigation
- Fuzzy field name matching
- Schema-to-dict conversions

### Gemini Live API Integration

**Adapter** (`backend/adapters/live_ai_gemini.py`)
- WebSocket session management with Gemini Live API
- Audio streaming to/from Gemini
- Tool registration and handling
- Implements `ILiveAI` port interface for dependency injection
- Configuration:
  ```python
  {
      "response_modalities": ["AUDIO"],
      "tools": [tool_definitions],
      "system_instruction": SYSTEM_INSTRUCTION,
      "realtime_input_config": {
          "automatic_activity_detection": {
              "disabled": True  # Manual activity signals used
          }
      }
  }
  ```

**System Instruction** (`backend/config.py`)
- Defines Gemini's behavior
- Enforces single-field workflow
- Requires confirmation for every field
- Multi-language support detection
- Off-topic redirection

### Tool Definitions

**Available Tools**:
1. `update_form_fields` - Update exactly one field value
2. `get_form_status` - Retrieve current field values
3. `switch_section` - Navigate to different section
4. `get_field_value` - Look up specific field by spoken name
5. `complete_section` - Mark section/part complete

**Tool Constraints**:
- Single-field updates only (multi-field disabled for accuracy)
- Mandatory confirmation after each update
- Validation before acceptance

### Field Validation System

**ValidationHandler** (`backend/services/validation_handler.py`)
- Orchestrates field matching and validation against schema constraints
- Extracts validation rules from `FormField.validation` object
- Delegates to `field_validator.py` for constraint checking
- Returns comprehensive validation results

**Field Validator** (`backend/utils/field_validator.py`)
- Core validation logic for all field types
- **Multi-Error Collection** (Nov 19, 2025): Returns ALL validation errors per field, not just first error
- Supports comprehensive validation rules from schema

**Supported Validation Rules**:

1. **Text Fields** (`text`, `email`, `textarea`):
   - `min_length` / `max_length` - String length constraints
   - `pattern` - Regex pattern matching (e.g., `^\\d{7,9}$` for A-number)
   - `digits_only` - Only numeric digits allowed (boolean)

2. **Number Fields** (`number`, `tel`):
   - `min` / `max` - Numeric range constraints
   - Type validation (must be valid number)

3. **Date Fields** (`date`):
   - Format validation (YYYY-MM-DD)
   - `min` / `max` - Date range constraints
   - `date_constraint` - Special date rules:
     - `past_only` - Date must be in the past (e.g., birth dates)
     - `future_only` - Date must be in the future
     - `within_5_years` - Date must be within 5 years of today

4. **Select/Radio/Checkbox**:
   - `options` - Valid option list enforcement
   - Exact match validation (case-sensitive)

**Multi-Error Validation** (Nov 19, 2025):

When a field value violates multiple rules, ALL errors are returned to Gemini:

Example: User enters `b234` for Alien Registration Number (requires 7-9 digits, digits only):
```json
{
  "validation_errors": [
    {
      "field_id": "p1_line1_alien_number",
      "constraint": "digits_only",
      "message": "Must contain only digits (0-9)"
    },
    {
      "field_id": "p1_line1_alien_number",
      "constraint": "minLength",
      "message": "Too short (minimum 7 characters)",
      "constraint_value": 7
    }
  ]
}
```

Gemini receives both errors and informs user: "The A-number must contain only digits AND be 7-9 digits long."

This eliminates frustrating back-and-forth where users fix one error only to discover another.

**Validation Flow**:
```
Gemini calls update_form_fields
  ↓
ValidationHandler.validate_field_updates()
  ↓
Extract validation rules from FormField.validation
  ↓
field_validator.validate_field_value() - Returns List[ValidationError]
  ↓
All errors collected and returned to Gemini
  ↓
Gemini informs user of ALL issues at once
```

**Error Messages**: Designed to be clear and actionable for voice feedback:
- "Too short (minimum 12 characters)" instead of "Too short"
- "Must contain only digits (0-9)" instead of "Invalid format"
- "Date must be in the past" for birth dates

### WebSocket Protocol

**Handshake Message** (Parts-based, Phase 4A):
```json
{
  "type": "handshake",
  "part_data": {
    "part_id": "part_1",
    "part_order": 1,
    "total_parts": 8,
    "part_label": "Part 1 - Information About You",
    "fields": [...],  // Field list for current part
    "filled_count": 0,
    "total_fields": 37
  }
}
```

**Note**: Backend uses parts-based architecture (Phase 4A). Each part corresponds to a section of the form (e.g., Part 1, Part 2, etc.). The handshake provides the current part context to Gemini.

**Tool Call Flow**:
```
Client → {"type": "tool_call", "tool": "update_form_fields", "args": {...}}
Server → Validation → Gemini → Response
Client ← {"type": "tool_response", "success": true, "message": "Updated"}
```

**Disclaimer Flow** (Nov 19, 2025):
```
Client → {"type": "read_disclaimer", "spoken_language": "Spanish"}
Server → FormFillingService.send_disclaimer_message()
Server → Gemini reads disclaimer aloud in Spanish
Client ← {"type": "disclaimer_read_initiated", "language": "Spanish"}
```

**Disclaimer Acceptance Logging**:
```
Client → POST /api/disclaimer-acceptance
  {
    "form_session_id": "...",
    "language": "Spanish",
    "timestamp": 1700000000000,
    "user_agent": "..."
  }
Server → Logs to backend/logs/disclaimer_acceptance.log
Server ← {"status": "logged", "timestamp": "2025-11-19T..."}
```

---

## Form Schema Structure

### Schema Model

**Parts vs Sections Architecture** (Phase 4A):

The application uses a two-level hierarchy:

**Parts** (Top-Level Navigation):
- User-facing organizational units (e.g., "Part 1", "Part 2")
- Each part has:
  - `id`: String identifier (e.g., "part_1")
  - `order`: Numeric order (1-8 for I-90)
  - `label`: Display name (e.g., "Information About You")
  - `section_ids`: Array of section IDs within this part
- Used for navigation and progress tracking
- Backend sends one part at a time to Gemini

**Sections** (Detailed Field Organization):
- Internal field groupings within parts
- Each section has:
  - `id`: String identifier
  - `label`: Display name
  - `fields`: Array of field definitions
- Used for field organization and conditional logic
- Not directly exposed in navigation UI

**Top-Level Schema**:
```typescript
interface FormSchema {
  id: string
  title: string
  version: string
  parts: Part[]        // 8 parts in I-589
  sections: Section[]  // Detailed sections within parts
  metadata: {
    form_number: string
    edition_date: string
    expires: string
    omb_number: string
  }
}
```

**Part Structure**:
```typescript
interface Part {
  id: string          // e.g., "part_1"
  order: number       // 1-8
  label: string       // e.g., "Information About You"
  sections: string[]  // Section IDs in this part
}
```

**Field Structure**:
```typescript
interface Field {
  id: string
  type: "text" | "select" | "radio" | "checkbox" | "date" | "textarea"
  label: string
  spoken_name?: string    // For voice interaction
  validation?: {
    required?: boolean
    pattern?: string
    conditionally_required?: ConditionalRequirement
  }
  options?: Option[]      // For select/radio/checkbox
  order: number
}
```

### Schema Management

**Note**: Schema extraction and editing tools have been segregated into a separate application. This app consumes pre-built schemas only.

**Supported Forms**:
- ✅ I-90 (Green Card Renewal) - Production Ready
  - Version: `v9_conformant`
  - Location: `frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json`
  - Parts structure: 8 parts, 132 fields
  - Spoken names: 100% unique (verified)
- 📋 I-589 (Asylum) - Schema extraction complete, conformance pending (external app)
- 📋 I-485 (Adjustment of Status) - Planned
- 📋 I-765 (Work Permit) - Planned
- 📋 N-400 (Citizenship) - Planned

**Schema Location**:
- Production schemas: `frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/{form}/`
- Application loads schemas at runtime from public directory

### Form Kit Workflow (Schemas + PDFs)

Form kits are the canonical definition of a schema/PDF bundle. They live at the
repo root inside `form-kits/<kit-id>/` with at least:

- `schema.json` (the voice-friendly schema consumed by Gemini)
- One or more reference PDFs that match the schema (e.g., `i-90.pdf`)
- Optional supplemental files (instructions, audio hints, etc.)

**Publishing steps** (mirrors the README quick start):

1. Create/modify `form-kits/<kit-id>/` with the updated schema/PDF files.
2. Run the sync script so the frontend demo + manifest stay in lockstep:

   ```bash
   npm run form-kits:prepare
   ```

   This invokes `frontend/scripts/generate-form-manifest.ts`, which copies every
   kit into `frontend/public/form-kits/<kit-id>/` and regenerates
   `frontend/public/form-kits/index.json` (the dropdown + backend manifest).
3. Launch the frontend; the schema/demo picker now exposes the new kit and its
   `kitId` flows through every `/api/fill-pdf` call.

**Backend consumption**:

- `FORM_KITS_MODE` (default `local`) selects the storage backend. `local` reads
  directly from `FORM_KITS_LOCAL_ROOT` (defaults to `<repo>/form-kits`).
- `FORM_KITS_MODE=gcs` switches to `RemoteFormKitStore`, which fetches assets via
  HTTPS. Configure either:
  - `FORM_KITS_REMOTE_BASE_URL` (full prefix to public objects), or
  - `FORM_KITS_GCS_BUCKET` + optional `FORM_KITS_REMOTE_PREFIX` (defaults to
    `form-kits`).
- `FORM_KITS_REMOTE_TIMEOUT_SEC` tunes the HTTP fetch timeout (default 30s).

The backend service `backend/services/form_kits.py` centralizes this logic so
both PDF generation routes and `/api/fill-pdf` read from the same resolved kit
location, keeping dev/prd behavior identical.

---

## Audio Processing Architecture

### Processing Pipeline

**Capture Stage**:
```javascript
navigator.mediaDevices.getUserMedia({ audio: constraints })
  → MediaStreamAudioSourceNode
  → AudioWorkletNode (audio-processor)
```

**Worklet Processing**:
```javascript
// In audio-processor.worklet.ts
process(inputs, outputs) {
  // 1. Apply noise gate (-50dB threshold)
  // 2. Apply high-pass filter (80Hz cutoff)
  // 3. Convert to 16-bit PCM
  // 4. Buffer for streaming
}
```

**Streaming Stage**:
- 16kHz sample rate
- 16-bit PCM encoding
- Base64 encoding for WebSocket transport
- Chunk size: 4096 samples

### Push-to-Talk Implementation

**Default Mode**: PTT enabled for maximum accuracy

**Desktop Implementation**:
- Spacebar for PTT activation (hold to talk, release to stop)
- Visual feedback (red dot when active)
- iOS-style toggle switch for mode selection

**Mobile Implementation**:
- Full-width bar button at screen bottom
- Touch-and-hold interaction
- Visual feedback matching desktop

**Benefits**:
- Eliminates false VAD triggers
- Reduces background noise pickup
- User controls exactly when to speak
- Critical for noisy office environments

### Auto-Scroll Feature (Added Nov 18, 2025)

**Implementation**: When Gemini fills a field, the UI automatically scrolls to bring that field into view with visual feedback.

**Location**: `frontend/src/webFormConnection.ts` in `updateField()` method

**Behavior**:
```typescript
// Only triggers when Gemini fills a field (confirmed: true)
if (confirmed && typeof document !== 'undefined') {
  setTimeout(() => {
    const element = document.getElementById(fieldId);
    if (element) {
      // Smooth scroll to center the field
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest'
      });

      // Add highlight animation (1.5s blue pulse)
      element.classList.add('field-highlight');
      setTimeout(() => {
        element.classList.remove('field-highlight');
      }, 1500);
    }
  }, 50);
}
```

**Visual Feedback** (`frontend/src/schema-forms/styles/schema-form.css`):
- 1.5-second blue pulse animation
- Scales field slightly (1.02x) at peak
- Blue border color during highlight
- Works on text inputs, textareas, and select elements

**Benefits**:
- User sees which field Gemini just filled
- No focus stealing (user can keep typing in another field)
- No keyboard popup on mobile (doesn't call `.focus()`)
- Works on both desktop and mobile
- Smooth UX without disrupting user's workflow

---

## Conditional Logic System (In Development)

### Current State
- 26 conditional rules in string format
- Basic show/hide functionality
- Manual evaluation in frontend

### Planned Architecture

**Conditional Index Structure**:
```json
{
  "triggers": {
    "field_123": ["field_456", "field_789"]
  },
  "dependencies": {
    "field_456": {
      "trigger": "field_123",
      "condition": "value === 'Yes'"
    }
  }
}
```

**Runtime Evaluator** (Planned):
- JavaScript-based evaluation
- Real-time field visibility updates
- Validation rule modifications
- Voice AI integration for skip logic

---

## Privacy & Security Architecture

### Privacy by Design
- **No server storage** of user data
- **Client-side persistence** only (sessionStorage)
- **Stateless backend** - no session storage
- **Automatic cleanup** on session end

### Security Measures
- WebSocket authentication via handshake
- Input validation at multiple layers
- Rate limiting on tool calls
- Sanitization of Gemini responses
- No PII logging

---

## Deployment Architecture

### Target Environment
- **Primary**: 8-inch Amazon Fire HD 8 tablets
- **Secondary**: Desktop browsers (Chrome, Firefox)
- **Setting**: Nonprofit offices with multiple concurrent users

### Infrastructure Requirements
- Node.js 18+ for frontend build
- Python 3.10+ for backend
- WebSocket support
- HTTPS required for audio capture
- Gemini API credentials

### Configuration

**Frontend** (`.env`):
```
VITE_WS_URL=wss://your-backend/ws
VITE_API_URL=https://your-backend/api
```

**Backend** (`config.py`):
```python
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISABLE_GEMINI_VAD = True
PROACTIVE_AUDIO = False  # Currently disabled
# Note: Token reduction not yet implemented
```

### WebSocket Endpoints

- `/ws/echo` - Echo test endpoint for WebSocket validation
- `/ws/audio` - Audio streaming test endpoint
- `/ws/fill` - Main form filling endpoint with Gemini integration

---

## Performance Metrics

### Current Performance (Legacy Mode - USE_JIT_SCHEMA=false)

- **Initial context**: ~7,400 tokens (full section schema)
- **Per-field update**: ~300 tokens
- **Audio latency**: <100ms processing
- **WebSocket latency**: <50ms typical

### JIT Schema Performance (Backend Ready - November 12, 2025)

**Status**: ✅ **Backend implementation complete**, ⚠️ **Frontend integration pending**

**Verified Metrics** (I-90 Part 1 - Backend Testing):
- **Initial context**: **458 tokens** (94% reduction from 7,400) ✅
- **Token accumulation**: Part 3 reaches 779 tokens (with previous parts included)
- **Per-field update**: <250 tokens (with next_field_schema included)
- **Feature flag**: `USE_JIT_SCHEMA=true` in backend config

**Backend Implementation Status**:
- ✅ Phase 2.1-2.6: Backend infrastructure complete
  - `manifest_service.py` created with manifest generation functions
  - `ai_context.py` updated to send manifest when JIT enabled
  - Tool responses include next field schema
  - Feature flag toggles between modes
- ✅ Phase 3.1-3.2: Frontend state tracking ready
  - `loadedFieldIds` tracking in SchemaFormState
  - `manifestUtils.ts` with 20 passing tests
- ⚠️ Phase 3.3: Frontend connection manager **NOT YET INTEGRATED**
  - Current handshake uses full schema via `getHandshakePayload()`
  - Manifest utilities exist but not used in WebSocket handshake
  - Integration pending

**Next Steps for Production**:
1. Integrate manifestUtils into frontend connection handshake (Phase 3.3)
2. Live Gemini API testing with JIT mode (Phase 4.2-4.3)
3. Error recovery and user acceptance testing (Phase 4.4-4.5)
4. Enable feature flag in production once validated

**Test Results**:
- ✅ 8/8 backend integration tests passing
- ✅ Manifest contains only field_id|spoken_name pairs
- ✅ All 38 Part 1 fields have unique spoken names
- ✅ Next field schema retrieval working
- ✅ Previous part manifests retained for cross-section queries

### Accuracy Metrics
- **Field accuracy**: >99% with confirmation
- **Hallucination rate**: Target <1%
- **Confirmation rate**: 100% (mandatory)

---

## Known Issues & Limitations

### Resolved Issues (Nov 18, 2025)
- ✅ FieldValue wrapper display issues ([object Object])
- ✅ Radio button state reset bug
- ✅ Section navigation skipping subsections (1.1→2 instead of 1.1→1.2→1.3→2)
- ✅ Validation failures with FieldValue objects
- ✅ Conditional field visibility
- ✅ Voice overlay section dropdowns showing incorrect data
- ✅ Aggressive section deduplication merging distinct sections

### Current Limitations
- JIT mode requires `USE_JIT_SCHEMA=true` flag (disabled by default)
- Manual context reset not possible with Gemini Live
- Some USCIS PDF conditional logic requires workarounds
- Background noise handling relies on PTT mode
- Conditional field access checking needs frontend integration

### In Development
- Live Gemini API testing with JIT mode (Phase 4.3)
- Conditional field dependency checking (Phase 2.4 backend integration)
- Error recovery and edge case testing (Phase 4.3)
- Multi-form conformance pipeline (I-589 pending)
- User acceptance testing (Phase 4.5)

---

## Development Workflow

### Branch Strategy
- `main` - Stable production code
- `feature/schema-forms` - Schema system development
- `feature/hallucination-reduction` - AI accuracy improvements
- `fix/critical-bugs-and-token-reduction` - Bug fixes and optimization

### Testing Strategy

**Unit Tests**:
- Field component unwrapping logic
- State management operations
- Validation rules
- Schema conformance

**Integration Tests**:
- Voice overlay with schema forms
- WebSocket communication
- Tool call processing
- State persistence

**E2E Tests**:
- Complete form filling flow
- Multi-language interaction
- Error recovery
- Session management

### Key Design Principles

1. **Accuracy Over Speed**: Single-field updates with mandatory confirmation
2. **Privacy First**: No server-side data storage
3. **Accessibility**: Designed for non-English speakers who cannot read forms
4. **Robustness**: Handle noisy environments and broken PDF logic
5. **Maintainability**: Schema-driven architecture for multiple forms

---

## API Reference

### Frontend APIs

**SchemaFormStateManager**:
```typescript
init(schema: FormSchema): SchemaFormState
load(): SchemaFormState | null
save(): void
clear(): void
updateFieldValue(fieldId: string, value: any): void
switchToPart(partId: string): void
getProgress(state: SchemaFormState): ProgressInfo
getCurrentSection(): Section | null
```

**Connection Manager** (`frontend/src/shared/connection.ts`):
```typescript
constructor(schema: FormSchema)
connect(): Promise<void>
disconnect(): void
sendAudio(audioData: ArrayBuffer): void
handleToolCall(tool: string, args: any): void
startPart(partId: string): Promise<void>
switchToPart(partId: string): Promise<void>
completePart(): Promise<void>
```

### Backend APIs

**WebSocket Endpoints**:
- `/ws/echo` - Echo test endpoint for WebSocket validation
- `/ws/audio` - Audio streaming test endpoint
- `/ws/fill` - Main form filling endpoint with Gemini integration

**REST Endpoints** (if applicable):
- `GET /api/schemas/{form_id}` - Retrieve form schema
- `POST /api/validate` - Validate field values

---

## Troubleshooting Guide

### Common Issues

**Audio Not Capturing**:
- Check HTTPS requirement
- Verify microphone permissions
- Test PTT mode activation
- Check noise gate threshold

**Field Updates Not Saving**:
- Verify sessionStorage enabled
- Check FieldValue unwrapping
- Validate schema structure
- Review WebSocket connection

**Section Navigation Broken**:
- Ensure parts array exists in schema
- Check currentPartId format
- Verify section mapping

**High Token Usage**:
- Token reduction not yet implemented
- Use field manifest when available
- Monitor with logging

---

## Future Architecture Plans

### Short Term (1-2 weeks)
- Complete token reduction implementation
- Finalize hallucination reduction features
- Apply conformance to I-589 form

### Medium Term (1 month)
- Full conditional logic system
- Multi-form support (I-485, I-765, N-400)
- Database backend option

### Long Term (3+ months)
- Multi-user session support
- Advanced analytics dashboard
- Automated testing pipeline
- Cloud deployment architecture

---

## Appendix: File Structure

```
voice-form-filler/
├── frontend/
│   ├── src/
│   │   ├── schema-forms/
│   │   │   ├── components/
│   │   │   │   ├── SchemaForm.tsx
│   │   │   │   ├── SectionRenderer.tsx
│   │   │   │   └── fields/
│   │   │   ├── state/
│   │   │   │   └── schemaFormState.ts
│   │   │   ├── types/
│   │   │   │   └── schema.ts
│   │   │   └── utils/
│   │   │       ├── fieldValue.ts
│   │   │       ├── validation.ts
│   │   │       ├── manifestUtils.ts (JIT mode)
│   │   │       ├── conditionalFieldCheck.ts
│   │   │       └── pdfFiller.ts
│   │   ├── demo/
│   │   │   ├── VoiceOverlay.tsx
│   │   │   ├── VoiceOverlayMobile.tsx
│   │   │   ├── GreetingCarousel.tsx
│   │   │   └── useDemoVAD.ts
│   │   ├── shared/
│   │   │   ├── connection.ts
│   │   │   ├── audioManager.ts
│   │   │   ├── fieldManager.ts
│   │   │   ├── metrics.ts
│   │   │   ├── config.ts
│   │   │   ├── languages.ts
│   │   │   └── audio-processor.worklet.ts
│   │   ├── navigation.ts
│   │   └── webFormConnection.ts
│   └── public/
│       ├── schema-form-demo.html (production demo)
│       ├── adult_intake_demo.html (deprecated)
│       └── pdf_schema_extractor/
│           └── test_schemas/ (schemas provided by external tool)
├── backend/
│   ├── config.py (JIT feature flag: USE_JIT_SCHEMA)
│   ├── services/
│   │   ├── form_filling_service.py
│   │   ├── validation_handler.py
│   │   ├── callback_handler.py
│   │   ├── audio_handler.py
│   │   ├── request_coordinator.py
│   │   ├── field_utils.py
│   │   ├── manifest_service.py (JIT mode)
│   │   └── ai_context.py (JIT handshake logic)
│   ├── adapters/
│   │   └── live_ai_gemini.py
│   ├── ports/
│   │   └── live_ai_port.py
│   ├── routes/
│   │   ├── websocket_routes.py
│   │   ├── vad_config_routes.py
│   │   └── pdf_fill_routes.py
│   ├── utils/
│   │   ├── fuzzy_field_matcher.py
│   │   ├── field_validator.py
│   │   ├── dev_file_logger.py
│   │   ├── token_file_logger.py
│   │   └── structured_logger.py
│   ├── tests/
│   │   └── unit/
│   │       └── test_jit_schema_loading.py
│   └── test_jit_system_e2e.py (8/8 passing)
└── planning_documents/
    ├── TECHNICAL_GUIDE.md (this file)
    ├── PROJECT_CONTEXT.md
    └── IMPLEMENTATION_PLAN.md

Note: Schema extraction and editing components segregated to external application
```

---

**Document Version**: 3.0
**Compiled**: November 12, 2025
**Next Review**: December 1, 2025

**Update Summary (v3.0 - November 12, 2025)**:
- ✅ Verified hallucination reduction features (PTT mode, audio filters, single-field constraint)
- ✅ Documented JIT schema system status (backend complete, frontend pending)
- ✅ Clarified Phase 3.3 integration gap (frontend handshake not using manifests yet)
- ✅ Updated performance metrics with actual test results (458 tokens achieved)
- ✅ Removed schema extraction pipeline (segregated to external app)
- ✅ Updated file structure with JIT-related files
- ✅ Marked legacy demo system as deprecated
- ✅ Added major features summary in executive section

**Previous Update (v2.1 - November 10, 2025)**:
- Fixed file path references and WebSocket protocol
- Added shared audio stream pattern
- Clarified parts vs sections architecture

This document represents the verified state of the Voice Form Filler application as of November 12, 2025, based on comprehensive code review and testing. All features marked as implemented have been verified in the `shared-audio-stream` branch.
