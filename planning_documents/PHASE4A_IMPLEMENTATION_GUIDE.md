# Phase 4A Implementation Guide - Voice Integration

**Date**: November 5, 2025  
**Status**: Ready to begin  
**Estimated Time**: 10-12 hours  
**Branch**: Create new branch `feature/phase4a-voice-integration`

---

## Executive Summary

Phase 4A wires the existing voice overlay components into the schema-driven form system. The voice overlay already works with the old demo app - we need to update it to use `SchemaFormStateManager` instead of `WebFormStateManager` and integrate it into `SchemaFormDemo`.

**Key Changes**:
1. Update VoiceOverlay to use SchemaFormState (remove WebFormState dependency)
2. Remove section_index prop (use schema.parts directly)
3. Integrate voice overlay into SchemaFormDemo
4. Test end-to-end voice interaction

---

## Current State Analysis

### ✅ What Works (No Changes Needed)

**Backend** (fully ready):
- Tool definitions: update_form_fields, get_form_status, switch_section, get_field_value, complete_section
- WebSocket handlers work with schema-based handshake
- Gemini Live integration functional
- Tool response handling complete

**Frontend Infrastructure** (ready to use):
- SchemaFormStateManager with WebSocket support (40/40 tests passing)
- WebFormConnection updated to use SchemaFormState
- Schema forms render correctly (132 fields, 8 parts)
- Session persistence via sessionStorage
- Validation system (required, format, patterns)

**Voice Components** (exist but need updates):
- VoiceOverlay.tsx - desktop UI
- VoiceOverlayMobile.tsx - mobile UI
- Connection manager (shared/connection.ts)
- Audio manager (shared/audioManager.ts)
- Field manager (shared/fieldManager.ts)
- VAD integration (useDemoVAD.tsx)

### ⏸️ What Needs Work

**VoiceOverlay.tsx** (20+ references to fix):
- Uses `WebFormStateManager` (line 21) → needs `SchemaFormStateManager`
- Uses `WebFormState` type → needs `SchemaFormState`
- Uses `SectionIndex` prop (line 29) → remove, use `schema.parts`
- Calls `initWithSections(schema, sectionIndex)` (line 209) → use `init(schema)`
- Calls `getSectionFieldCount()` (line 515) → use `getProgress()`
- Section dropdown shows `sectionIndex.sections` (line 765) → use `schema.parts`
- Current section tracking (line 47) → track by part ID, not number

**VoiceOverlayMobile.tsx** (same issues as desktop):
- All same updates needed as VoiceOverlay.tsx
- Keep changes synchronized between desktop and mobile

**SchemaFormDemo.tsx** (needs voice integration):
- No connection manager state
- No voice overlay components
- No audio stream setup
- No connection controls UI

---

## Implementation Plan

### Part 1: Update VoiceOverlay to use SchemaFormState (~4 hours)

#### Step 1.1: Update Imports and Types
**File**: `frontend/src/demo/VoiceOverlay.tsx`

**Changes**:
```typescript
// OLD
import { WebFormStateManager, type FormSchema, type SectionIndex } from '../webFormState'

// NEW
import { SchemaFormStateManager, type SchemaFormState } from '../schema-forms/state/schemaFormState'
import type { FormSchema } from '../schema-forms/types/schema'
```

**Props to update**:
```typescript
// OLD
interface VoiceOverlayProps {
	schema: FormSchema
	sectionIndex: SectionIndex  // ❌ REMOVE THIS
	...
}

// NEW
interface VoiceOverlayProps {
	schema: FormSchema  // Now includes parts array
	wsUrl?: string
	onClose?: () => void
	connectionManager?: ConnectionManager
	status?: string
	sharedStream?: MediaStream | null
	streamError?: string | null
}
```

#### Step 1.2: Update Section State Tracking
**File**: `frontend/src/demo/VoiceOverlay.tsx` (lines 47-49)

**Changes**:
```typescript
// OLD
const [currentSection, setCurrentSection] = useState(1)  // section_number
const [completedSections, setCompletedSections] = useState<Set<number>>(new Set())

// NEW
const [currentPartId, setCurrentPartId] = useState<string>('')  // part ID like "part_1"
const [completedParts, setCompletedParts] = useState<Set<string>>(new Set())
```

#### Step 1.3: Update Connection Manager Init
**File**: `frontend/src/demo/VoiceOverlay.tsx` (line 209)

**Changes**:
```typescript
// OLD
const state = WebFormStateManager.initWithSections(schema, sectionIndex)

// NEW
const state = SchemaFormStateManager.init(schema)
```

#### Step 1.4: Update Field Count Logic
**File**: `frontend/src/demo/VoiceOverlay.tsx` (line 515)

**Changes**:
```typescript
// OLD
const fieldCount = WebFormStateManager.getSectionFieldCount(state)

// NEW
const progress = SchemaFormStateManager.getProgress(state)
const fieldCount = { filled: progress.filledFields, total: progress.totalFields }
```

#### Step 1.5: Update Section Dropdown
**File**: `frontend/src/demo/VoiceOverlay.tsx` (lines 756-787)

**Changes**:
```typescript
// OLD
Section {currentSection} of {sectionIndex.total_sections}: {sectionIndex.sections[currentSection - 1]?.section_label}

{sectionIndex.sections.map((section) => (
	<div key={section.section_number} ...>
		Section {section.section_number}: {section.section_label}
	</div>
))}

// NEW
{schema.parts && (
	<>
		{schema.parts.find(p => p.id === currentPartId)?.label || 'Select Part'}
		
		{schema.parts.map((part) => (
			<div key={part.id} ...>
				Part {part.order}: {part.label}
			</div>
		))}
	</>
)}
```

#### Step 1.6: Update All WebFormStateManager Calls
**Search and replace** in `VoiceOverlay.tsx`:

| Old Call | New Call |
|----------|----------|
| `WebFormStateManager.load()` | `SchemaFormStateManager.load()` |
| `WebFormStateManager.clear()` | `SchemaFormStateManager.clear()` |
| `WebFormStateManager.initWithSections()` | `SchemaFormStateManager.init()` |
| `WebFormStateManager.getSectionFieldCount()` | `SchemaFormStateManager.getProgress()` |

#### Step 1.7: Repeat for VoiceOverlayMobile.tsx
**File**: `frontend/src/demo/VoiceOverlayMobile.tsx`

Apply **all same changes** from Steps 1.1-1.6 to mobile version.

---

### Part 2: Integrate Voice into SchemaFormDemo (~3 hours)

#### Step 2.1: Add Connection State
**File**: `frontend/src/schema-forms/SchemaFormDemo.tsx`

**Add imports**:
```typescript
import { createConnectionManager, type ConnectionManager } from '../shared/connection'
import { VoiceOverlay } from '../demo/VoiceOverlay'
import { VoiceOverlayMobile } from '../demo/VoiceOverlayMobile'
import { SPOKEN_LANGUAGES } from '../shared/languages'
```

**Add state**:
```typescript
// Connection state
const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(null)
const [status, setStatus] = useState<string>('disconnected')

// Shared audio stream (for VAD coordination)
const [sharedStream, setSharedStream] = useState<MediaStream | null>(null)
const [streamError, setStreamError] = useState<string | null>(null)

// Detect mobile
const [isMobile, setIsMobile] = useState(false)

// Voice controls
const [showVoiceOverlay, setShowVoiceOverlay] = useState(false)
const [selectedLanguage, setSelectedLanguage] = useState('')
```

#### Step 2.2: Add Mobile Detection
```typescript
useEffect(() => {
  const checkMobile = () => setIsMobile(window.innerWidth <= 768)
  checkMobile()
  window.addEventListener('resize', checkMobile)
  return () => window.removeEventListener('resize', checkMobile)
}, [])
```

#### Step 2.3: Add Shared Audio Stream Setup
```typescript
useEffect(() => {
  let mounted = true

  async function initSharedStream() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
          channelCount: 1,
          sampleRate: 16000,
        },
      })

      if (mounted) {
        setSharedStream(stream)
      } else {
        stream.getTracks().forEach(track => track.stop())
      }
    } catch (err) {
      if (mounted) {
        setStreamError(err instanceof Error ? err.message : 'Microphone access denied')
      }
    }
  }

  // Only request mic if voice overlay is shown
  if (showVoiceOverlay && !sharedStream) {
    initSharedStream()
  }

  return () => {
    mounted = false
  }
}, [showVoiceOverlay])
```

#### Step 2.4: Add Voice Overlay UI
```typescript
// In return JSX, add at bottom:
{showVoiceOverlay && schema && (
  <>
    {isMobile ? (
      <VoiceOverlayMobile
        schema={schema}
        wsUrl={getBackendWsUrl()}
        onClose={() => setShowVoiceOverlay(false)}
        connectionManager={connectionManager}
        status={status}
        sharedStream={sharedStream}
        streamError={streamError}
      />
    ) : (
      <VoiceOverlay
        schema={schema}
        wsUrl={getBackendWsUrl()}
        onClose={() => setShowVoiceOverlay(false)}
        connectionManager={connectionManager}
        status={status}
        sharedStream={sharedStream}
        streamError={streamError}
      />
    )}
  </>
)}
```

#### Step 2.5: Add Connection Controls
```typescript
// Add button to toggle voice overlay
<div style={{ padding: "10px", background: "#f0f0f0", marginBottom: "20px" }}>
  <button 
    onClick={() => setShowVoiceOverlay(!showVoiceOverlay)} 
    style={{ padding: "8px 16px", cursor: "pointer", marginRight: "10px" }}
  >
    {showVoiceOverlay ? '🔇 Hide Voice' : '🎤 Enable Voice'}
  </button>
  
  <button 
    onClick={handleClearSession} 
    style={{ padding: "8px 16px", cursor: "pointer" }}
  >
    🗑️ Clear Form & Start Fresh
  </button>
  
  {status && status !== 'disconnected' && (
    <span style={{ marginLeft: "10px", color: status === 'connected' ? 'green' : 'orange' }}>
      Status: {status}
    </span>
  )}
</div>
```

#### Step 2.6: Add Backend URL Helper
```typescript
function getBackendWsUrl(): string {
  // Check if running locally or in production
  const isDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  
  if (isDev) {
    return 'ws://localhost:8000/ws/fill'
  } else {
    // Production backend URL (update with your actual backend)
    return 'wss://your-backend.com/ws/fill'
  }
}
```

---

### Part 3: End-to-End Testing (~3-4 hours)

#### Test Scenario 1: Basic Connection
**Steps**:
1. Open SchemaFormDemo
2. Click "Enable Voice" button
3. Grant microphone permissions
4. Verify voice overlay appears
5. Verify connection status shows "Connected"

**Expected**:
- ✅ Voice overlay visible
- ✅ Connection established
- ✅ No console errors

#### Test Scenario 2: Voice → Field Update
**Steps**:
1. Ensure connected
2. Speak: "My first name is John"
3. Wait for Gemini response
4. Check form field updates

**Expected**:
- ✅ Gemini calls update_form_fields
- ✅ Frontend updates state
- ✅ Field shows "John"
- ✅ Success response sent to Gemini
- ✅ Gemini confirms: "I've recorded your first name as John"

#### Test Scenario 3: Section Switching
**Steps**:
1. Fill a few fields in Part 1
2. Say: "Go to part 2"
3. Wait for section switch
4. Verify form shows Part 2 fields

**Expected**:
- ✅ Gemini calls switch_section
- ✅ Backend restarts session with Part 2
- ✅ Form displays Part 2 fields
- ✅ Part 1 data preserved in sessionStorage

#### Test Scenario 4: Field Value Query
**Steps**:
1. Fill field: "Phone Number" = "206-555-1234"
2. Move to next section
3. Say: "What's my phone number?"
4. Wait for Gemini response

**Expected**:
- ✅ Gemini calls get_field_value with spoken_name="Phone Number"
- ✅ Backend returns value
- ✅ Gemini speaks: "Your phone number is 206-555-1234"

#### Test Scenario 5: Manual Edit Detection
**Steps**:
1. AI fills field via voice
2. Manually type new value
3. Verify Gemini acknowledges

**Expected**:
- ✅ Field manager detects change
- ✅ manual_field_update sent to backend
- ✅ Gemini says: "I see you updated..."

#### Test Scenario 6: Session Persistence
**Steps**:
1. Fill 5-10 fields via voice
2. Refresh page (F5)
3. Verify all data restored

**Expected**:
- ✅ All field values restored
- ✅ Current part restored
- ✅ Can resume form filling

#### Test Scenario 7: Mobile Responsive
**Steps**:
1. Resize browser to mobile width (< 768px)
2. Enable voice
3. Test basic interaction

**Expected**:
- ✅ Mobile voice overlay renders
- ✅ Voice interaction works
- ✅ UI scales correctly

---

## Todo List (18 Tasks)

Managed via `manage_todo_list` tool:

1. ✅ Audit VoiceOverlay dependencies on WebFormStateManager
2. ⏸️ Update VoiceOverlay imports to use SchemaFormStateManager
3. ⏸️ Remove section_index dependency from VoiceOverlay
4. ⏸️ Update VoiceOverlay section tracking state
5. ⏸️ Test updated VoiceOverlay independently
6. ⏸️ Add connection manager state to SchemaFormDemo
7. ⏸️ Add shared audio stream setup to SchemaFormDemo
8. ⏸️ Add mobile detection to SchemaFormDemo
9. ⏸️ Integrate VoiceOverlay into SchemaFormDemo render
10. ⏸️ Add connection controls UI to SchemaFormDemo
11. ⏸️ Test basic voice connection flow
12. ⏸️ Test voice → field update flow
13. ⏸️ Test section switching via voice
14. ⏸️ Test field value queries
15. ⏸️ Test manual edit detection
16. ⏸️ Test session persistence across reload
17. ⏸️ Document test results and create test checklist
18. ⏸️ Fix any critical bugs found during testing

---

## Success Criteria

**Must achieve all** before marking Phase 4A complete:

- [ ] VoiceOverlay uses SchemaFormState (no WebFormState references)
- [ ] No section_index prop (uses schema.parts directly)
- [ ] Voice overlay integrated into SchemaFormDemo
- [ ] Can connect and establish WebSocket session
- [ ] Voice commands update fields correctly
- [ ] Section switching works ("go to part 2")
- [ ] Field queries work ("what's my phone number?")
- [ ] Manual edits detected and sent to Gemini
- [ ] Session persists across page reload
- [ ] Mobile and desktop voice overlays both work
- [ ] No console errors or unexpected disconnects
- [ ] All 7 test scenarios pass

---

## Files to Modify

**Primary Changes**:
1. `frontend/src/demo/VoiceOverlay.tsx` (~50 lines changed)
2. `frontend/src/demo/VoiceOverlayMobile.tsx` (~50 lines changed)
3. `frontend/src/schema-forms/SchemaFormDemo.tsx` (~100 lines added)

**Potential Updates** (if issues found):
4. `frontend/src/shared/connection.ts` (navigation logic)
5. `frontend/src/webFormConnection.ts` (tool response handling)

**No Changes Needed**:
- Backend files (already ready)
- SchemaFormStateManager (already has WebSocket methods)
- Validation system (already works)
- Audio/field managers (already compatible)

---

## Risk Mitigation

**Risk**: VoiceOverlay breaks during refactor  
**Mitigation**: Test after each step, keep old version for reference

**Risk**: Section switching doesn't work with parts  
**Mitigation**: WebFormConnection already handles parts, verify mapping

**Risk**: Audio stream causes race conditions  
**Mitigation**: Use shared stream pattern (already implemented in demo)

**Risk**: Mobile overlay inconsistent with desktop  
**Mitigation**: Apply same changes to both, test both thoroughly

---

## Next Steps After Phase 4A

Once Phase 4A is complete and tested:

1. **Phase 4B**: Implement frontend tool call validation (~3 hours)
2. **Phase 4C**: Tune error messages for Gemini (~4 hours)
3. **Phase 5**: PDF export implementation (~8 hours)
4. **Phase 6**: Multi-language testing and pilot (~10 hours)

**Total remaining**: ~25 hours to MVP complete

---

**Ready to begin?** Start with Task #1 (audit VoiceOverlay dependencies).
