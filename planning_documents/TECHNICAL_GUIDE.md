# Voice Form Filler - Technical Architecture Guide

**Last Updated**: November 9, 2025
**Purpose**: Technical reference for navigating and understanding the codebase

**Recent Updates**:
- ✅ **Radio Button Tool Validation & Instructions** (Nov 9, 2025)
  - **Issue 1**: Gemini saw radio option labels ("Yes", "No") but didn't know the widget IDs to send ("P1_checkbox4[0]", "P1_checkbox4[1]")
  - **Issue 2**: Gemini didn't receive error feedback when radio updates failed (validation happened at frontend, not backend)
  - **Fix #1 - AI Context**: Updated `ai_context.py` to show both label AND value in options display
    - Before: `Options: [Yes (Proceed to...), No (Proceed to...)]`
    - After: `Options: ["Yes (Proceed to...)" (use value: P1_checkbox4[0]), "No (Proceed to...)" (use value: P1_checkbox4[1])]`
  - **Fix #2 - Tool Description**: Updated `update_form_fields` tool in `config.py` with explicit instructions
    - Added: "For radio/select fields: Use the 'value' from the option object shown in schema"
    - Example provided in tool description for clarity
  - **Fix #3 - Backend Validation**: Added radio field validation to `field_validator.py`
    - Added "radio" to validated field types (line 68)
    - Updated `_validate_select()` to extract values from option dicts and validate
    - Now returns proper ValidationError with `valid_options` list
  - **Fix #4 - Frontend Logging**: Enhanced connection.ts logging to show exact values being sent
    - Shows each field update: `→ p1_checkbox4 = "P1_checkbox4[0]"`
    - Logs application status and rejection reasons
  - **Fix #5 - React Re-rendering**: Fixed SchemaForm.tsx to re-render on field value changes
    - Previously only re-rendered on `currentPartId` changes
    - Now also checks `lastUpdated` timestamp to catch Gemini's field updates
  - **Files Changed**: `backend/services/ai_context.py`, `backend/config.py`, `backend/utils/field_validator.py`, `frontend/src/shared/connection.ts`, `frontend/src/schema-forms/components/SchemaForm.tsx`
  - **Impact**: Gemini now correctly fills radio buttons, receives validation feedback, and can self-correct when errors occur


- ✅ **Bug Fixes: FieldValue Wrapper Issues** (Nov 8, 2025)
  - **Bug 1 - [object Object] Display**: Form fields showed wrapper object instead of values
  - **Bug 2 - Radio Buttons Reset**: Fixed as side effect of Bug 1 unwrapping
  - **Bug 3 - Section Navigation**: Fixed Next/Previous buttons to use part-based navigation
  - **Bug 4 - Validation Always Failing**: Added unwrapping to validation logic
  - **Bug 5 - Conditional Fields Broken**: Added unwrapping to conditional visibility checks
  - **Root Cause**: FieldValue wrapper `{ value: string, confirmed?: boolean }` not unwrapped before use
  - **Solution**: Created centralized `fieldValue.ts` utility with unwrapping functions
  - **Files Changed**:
    - Field components: TextField, TextAreaField, SelectField, RadioField, CheckboxField, DateField (Bug 1)
    - Navigation: SchemaForm.tsx, schemaFormState.ts - added getNextPart/getPreviousPart, event listeners (Bug 3)
    - Validation: validation.ts - unwrap before validating and checking conditionals (Bugs 4 & 5)
  - **Testing**: 26/26 utility tests passing, all manual browser testing confirmed working
  - **Total Time**: ~90 minutes for 5 bugs
  - **Key Learning**: Centralized utility functions + comprehensive unwrapping = reliable state management

- ✅ **Audio Quality Fix** (Nov 7, 2025)
  - **Issue**: Noise gate was too aggressive (-40dB), causing speech clipping in PTT mode
  - **Fix #1**: Lowered noise gate threshold from -40dB to -50dB (gentler, preserves quiet speech)
  - **Fix #2**: Noise gate now bypassed completely in PTT mode (user explicitly controls audio)
  - **Fix #3**: Simplified audio flow logic - PTT mode only checks inputMuted flag (ignores vadActive)
  - **Impact**: Improved recognition accuracy, especially for consonants, quiet speakers, and pauses
  - **Files Changed**: `audio-processor.worklet.ts`, `audioManager.ts`, `VoiceOverlay.tsx`, `VoiceOverlayMobile.tsx`

- ✅ **Phase 4A Migration Progress** (Nov 5, 2025)
  - **Connection Layer**: Migrated connection.ts to SchemaFormStateManager (17/17 tests passing)
  - **Voice Overlays**: Partially completed migration (audit done, implementation status unclear)
  - **Part-based navigation**: Replacing section-based with parts/currentPartId pattern
  - **Demo System**: Deprecated old demo.html and AdultIntakeDemo.tsx (marked for removal)
  - **Backend Fixes**:
    - Schema source validation: Now accepts both "web" and "pdf" sources (I-90 compatibility)
    - Fixed UnboundLocalError in live_ai_gemini.py (settings import moved to top of _run_session_loop)
    - Audio queue warning rate limiting (once per 5 seconds to prevent terminal flooding)
  - **UX Improvements**:
    - VoiceOverlay moved outside `<form>` element to prevent unwanted submit triggers
    - Removed verbose logging from schemaFormState.ts load/save methods (console spam eliminated)
  - **Backend Tests**: Fixed field_utils.py to use current FormField model, deleted 7 obsolete test files (102 tests passing)
  - All changes committed to origin/shared-audio-stream

- ✅ **Phase 2: WebSocket Connection Layer Complete** (Nov 5, 2025)
  - All WebSocket methods reimplemented for parts-based system
  - Navigation functions updated to use SchemaFormState
  - Helper methods added to SchemaFormStateManager
  - 20+ methods updated with 0 TypeScript errors

- ✅ **Phase 1: WebSocket State Manager Consolidation** (Nov 5, 2025)
  - Added FieldValue wrapper type for tracking AI-filled vs user-filled fields
  - WebSocket integration methods added to SchemaFormStateManager
  - 40 unit tests with 100% pass rate
  - Backwards compatibility migration implemented

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
├── schema, fieldValues, session_id
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

## Current State Management Architecture

### Primary: SchemaFormStateManager (schema-forms/state/schemaFormState.ts)
**Status**: ✅ Active, WebSocket-integrated, 40/40 tests passing

**Features**:
- Parts-based navigation (`currentPartId`, `completedParts`)
- FieldValue wrapper for AI vs user-filled tracking
- WebSocket handshake payload generation
- Session ID management from backend
- Backwards compatibility with legacy schemas

**Key Properties**:
```typescript
interface SchemaFormState {
  schema: FormSchema
  fieldValues: Record<string, FieldValue>
  currentPartId: string
  completedParts: Set<string>
  sessionId?: string
}
```

### Deprecated: WebFormStateManager (webFormState.ts)
**Status**: ⚠️ Being phased out, still referenced in some voice components

---

## Session Lifecycle

### Connection Flow

1. **Handshake**: Client sends schema + optional fieldValues → Backend stores schema, returns session_id
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

> **Note (Nov 2025)**: The multi-level activity watchdog escalation system documented in earlier versions has been deprecated. Current implementation uses a simple 60-second idle timeout without escalating warnings/nudges.

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

### Frontend (`frontend/`)

**Shared Modules** (`src/shared/`):
- `connection.ts` - WebSocket connection manager (updated Nov 5 for SchemaFormStateManager)
- `audioManager.ts` - Microphone & AI audio playback (16kHz/24kHz PCM16)
- `fieldManager.ts` - Form field updates & manual edit detection
- `config.ts` - Backend URL resolution
- `languages.ts` - 18 spoken + 80 fill languages
- `greetingPrompts.ts` - Carousel phrases

**Demo Application** (`src/demo/`):
- ⚠️ **DEPRECATED** - Being replaced by schema-forms pattern
- `AdultIntakeDemo.tsx` - Legacy demo component (marked for removal)
- `VoiceOverlay.tsx` - Desktop UI (partially migrated)
- `VoiceOverlayMobile.tsx` - Mobile UI (partially migrated)
- `GreetingCarousel.tsx` - Visual welcome
- `useDemoVAD.ts` - VAD integration hook

**Schema-Driven Forms** (`schema-forms/`):
- `types/schema.ts` - TypeScript types mirroring backend Pydantic models
- `state/schemaFormState.ts` - **PRIMARY** state manager with WebSocket support
- `components/SchemaForm.tsx` - Main schema-driven form renderer
- `components/SectionRenderer.tsx` - Section-based form rendering
- `components/fields/` - Field-specific renderers with FieldValue unwrapping
- `utils/fieldValue.ts` - **NEW** - Centralized FieldValue unwrapping utilities

---

## Known Issues & Pending Fixes

### High Priority Bugs

1. **Bug 2: Radio Buttons Reset Form** ⚠️
   - **Status**: Pending fix
   - **Impact**: Data loss when selecting radio buttons
   - **Suspected Cause**: onChange handler replacing entire state
   - **Files**: RadioField.tsx, schemaFormState.ts

2. **Bug 3: Section Navigation Broken** 🔴
   - **Status**: Pending fix
   - **Impact**: Can only access 1/8 of form
   - **Suspected Cause**: Parts vs sections mismatch
   - **Files**: SchemaForm.tsx, SectionRenderer.tsx, webFormConnection.ts

### Planned Improvements

1. **Token Reduction** (Day 2-3 implementation)
   - Goal: Reduce from 7,400 to <500 initial tokens
   - Strategy: Just-in-time field loading
   - Status: Planning complete, implementation pending

2. **Hallucination Reduction** (Branch: `feature/hallucination-reduction`)
   - Audio preprocessing filters (partial - noise gate done)
   - Push-to-Talk default mode (pending)
   - Single-field tool constraint (pending)
   - Enhanced confirmation workflow (pending)
   - Proactive audio activation (pending)

3. **Voice AI Conditional Logic**
   - Convert 26 string conditionals to structured format
   - Build bidirectional index
   - Create JavaScript evaluator
   - Status: Requirements defined, implementation pending

---

## Audio Processing Pipeline

### Current Configuration (Nov 7, 2025)

**Noise Gate**:
- Threshold: -50dB (lowered from -40dB for gentler processing)
- Completely bypassed in PTT mode
- Applied before VAD in auto mode

**High-Pass Filter**:
- Status: Planned but not confirmed implemented
- Target: 80Hz cutoff with Q-factor 0.7

**VAD (Voice Activity Detection)**:
- Thresholds: 0.90/0.70 (optimized Oct 22)
- Pre-buffer: 700ms (reduces missed speech)
- Works in noisy environments

**PTT (Push-to-Talk)**:
- Status: Available, not yet default
- Bypasses all audio preprocessing
- User has explicit control

---

## Tool Definitions (Backend)

Current tools available to Gemini:

1. **update_form_fields** - Update form field values
   - Currently accepts multiple fields
   - Planned: Single-field constraint for accuracy

2. **get_form_status** - Get completion percentage and filled count

3. **switch_section** - Navigate to different form section
   - Maps parts to section numbers

4. **get_field_value** - Retrieve specific field value
   - Includes fuzzy matching (52% threshold)
   - Planned: Enhanced for just-in-time loading

5. **complete_section** - Mark section as complete and move to next

---

## Testing

### Backend Tests
- **Status**: 102 tests passing (7 obsolete files deleted)
- **Coverage**: Core services at 100%
- **Location**: `backend/tests/`

### Frontend Tests
- **SchemaFormState**: 40/40 tests passing
- **FieldValue utilities**: 26/26 tests passing
- **Location**: `frontend/src/schema-forms/state/schemaFormState.test.ts`

### Manual Testing Checklist
1. Connect → Verify session_id appears
2. Record → Speak → Playback is smooth
3. Fields update → Green outline + checkmark
4. Refresh page → DOM restored from sessionStorage
5. Interrupt Gemini → TTS stops in <50ms
6. Radio buttons → Don't reset other fields (currently failing)
7. Section navigation → Can access all sections (currently failing)

---

## Common Development Tasks

### Adding a New Field Type
1. Add to `schema-forms/types/schema.ts`
2. Create component in `schema-forms/components/fields/`
3. Add to FIELD_COMPONENTS map in `SectionRenderer.tsx`
4. Ensure FieldValue unwrapping in component
5. Add backend validation in `validation_handler.py`

### Debugging WebSocket Messages
1. Enable dev logging: `VFF_DEV_LOGGING=true` in .env
2. Check browser DevTools Network tab for WS frames
3. Backend logs in `backend/logs/`
4. Use `utils/tool_call_logger.py` for privacy-safe logging

### Testing Voice Integration
1. Use `http://localhost:5174/schema-form-demo.html`
2. Load I-90 schema from dropdown
3. Click microphone icon
4. Speak to test voice filling
5. Check console for errors

---

## Configuration

### Environment Variables
```bash
# Backend
VFF_DEV_LOGGING=true          # Verbose logging (dev only)
PROACTIVE_AUDIO=false          # Gemini proactive audio (pending activation)
DISABLE_GEMINI_VAD=false       # Manual VAD control
VOICE_GCS_BUCKET=bucket-name   # GCS bucket for production
VOICE_PROJECT_NAME=project-id  # GCP project ID

# Frontend
VITE_API_URL=http://localhost:8000  # Backend URL
```

### Key Files
- `backend/config.py` - System instructions, tool definitions
- `frontend/src/shared/config.ts` - Backend URL resolution
- `.env` files - Local development overrides

---

## Recent Improvements Summary

### Completed (Confirmed Working)
- ✅ [object Object] display fix with FieldValue unwrapping
- ✅ Audio quality improvements (noise gate threshold)
- ✅ Phase 1 & 2 WebSocket consolidation
- ✅ Field query robustness with fuzzy matching
- ✅ Race condition fix for message queuing
- ✅ Next field hint enhancement

### In Progress (Partially Complete)
- ⏳ Phase 4A voice overlay integration (audit done, implementation unclear)
- ⏳ Hallucination reduction features (noise gate done, others pending)
- ⏳ Frontend consolidation (state managers updated, demo deprecation pending)

### Planned (Not Started)
- ⏰ Token reduction implementation
- ⏰ Bug 2 & 3 fixes
- ⏰ Voice AI conditional logic
- ⏰ Multi-form conformance

---

## Next Steps for Development

1. **Immediate**: Fix Bug 2 (radio buttons) and Bug 3 (section navigation)
2. **Day 2-3**: Implement token reduction for efficiency
3. **Week 2**: Complete hallucination reduction features
4. **Week 3**: Implement conditional logic system
5. **Ongoing**: Multi-form conformance pipeline
