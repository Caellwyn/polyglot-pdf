# Frontend Consolidation Plan - PDF Schema Voice Integration

**Created**: November 5, 2025
**Status**: In Progress
**Branch**: `claude/align-websockets-011CUpAutS2MaBKLNxYFQRQM`

---

## Executive Summary

Consolidate the frontend architecture by **deprecating the demo webform** and converging on **PDF schemas as the primary pattern**. This eliminates duplicate state managers, removes the adapter complexity, and establishes a single, maintainable architecture for voice-enabled PDF forms.

**Key Decision**: The demo webform (`AdultIntakeDemo.tsx`) predates the formal PDF schema system and uses a different section navigation pattern. Since the demo is preserved separately, we can remove it here and simplify the architecture by ~50%.

---

## Current State Analysis

### Two Incompatible Systems

#### Demo App (Old Pattern - Being Deprecated)
- **Location**: `frontend/src/demo/AdultIntakeDemo.tsx`
- **State Manager**: `WebFormStateManager` in `webFormState.ts`
- **Schema Pattern**: Custom with separate section index file
- **Section Navigation**: `section_number` (1-indexed integers)
- **Storage Key**: `web_form_state`
- **Status**: ✅ Working voice integration

```typescript
// Demo pattern (DEPRECATED)
interface WebFormState {
  current_values: Record<string, FieldValue>
  current_section?: number  // Integer section number
  section_index?: SectionIndex  // Separate index file
}
```

#### Schema Forms (New Pattern - Being Enhanced)
- **Location**: `frontend/src/schema-forms/`
- **State Manager**: `SchemaFormStateManager` in `schema-forms/state/schemaFormState.ts`
- **Schema Pattern**: PDF extraction following Pydantic models
- **Section Navigation**: `parts[].order` (part ordering)
- **Storage Key**: `schema_form_state`
- **Status**: ⚠️ No voice integration yet

```typescript
// Schema forms pattern (PRIMARY)
interface SchemaFormState {
  fieldValues: Record<string, any>
  currentSectionId: string  // Part ID like "part_1"
  schema: FormSchema  // PDF schema with parts/sections
}
```

### The Incompatibility

**It's NOT naming** - it's architectural evolution:

1. **Demo app built first** (before Pydantic models)
   - Used `section_number` property
   - Created separate `sections_index.json` files
   - Backend built to expect this pattern

2. **PDF extraction came later** (with formal models)
   - Uses `parts[].order` property (semantically identical to section_number)
   - Single file approach (no separate index)
   - Follows Pydantic `FormPart` / `FormSection` models

3. **The solution**: Use `parts[].order` directly as `section_number`
   - They're semantically identical (both are display order)
   - No schema changes needed
   - Frontend maps `order` → `section_number` in handshake

---

## Consolidation Strategy

### Core Philosophy

> **Converge on PDF schemas as the single source of truth**

- ✅ PDF schemas follow formal Pydantic models
- ✅ PDF extraction scales to 50+ USCIS forms
- ✅ No custom patterns to maintain
- ✅ Clean separation: extraction → schema → rendering → voice

### What We Keep (Voice Infrastructure)

1. ✅ **WebFormConnection.ts** - WebSocket communication layer
2. ✅ **connection.ts** - Connection manager orchestration
3. ✅ **fieldManager.ts** - Manual edit detection & AI confirmations
4. ✅ **audioManager.ts** - Audio streaming (16kHz/24kHz PCM16)
5. ✅ **VoiceOverlay.tsx** - Desktop voice UI
6. ✅ **VoiceOverlayMobile.tsx** - Mobile voice UI
7. ✅ **navigation.ts** - Field navigation logic
8. ✅ **metrics.ts** - Tool call tracking & hallucination detection

### What We Delete (Demo-Specific)

1. ❌ **AdultIntakeDemo.tsx** - Demo app component
2. ❌ **adult_intake_demo_schema.json** - Old demo schema
3. ❌ **adult_intake_sections_index.json** - Separate index pattern
4. ❌ **adult-intake-form.html** - Demo HTML (if exists)
5. ❌ Old `WebFormStateManager` class (merged into SchemaFormStateManager)

### What We Enhance (Convergence)

1. 🔄 **SchemaFormStateManager** - Add WebSocket serialization methods
2. 🔄 **WebFormConnection** - Update to use `parts[].order` as section_number
3. 🔄 **SchemaForm** - Wire in voice overlay components
4. 🔄 **SchemaFormDemo** - Add connection manager initialization

---

## Implementation Phases

### Phase 1: Merge State Managers ⏱️ 4 hours

**Goal**: Enhance `SchemaFormStateManager` with WebSocket capabilities

**Tasks**:

1. **Add FieldValue type support**:
```typescript
export interface FieldValue {
  value: string | boolean | null;
  confirmed?: boolean;  // Set by AI
  lastModified?: number;  // Timestamp
}
```

2. **Update fieldValues to use FieldValue wrapper**:
```typescript
export interface SchemaFormState {
  schema: FormSchema
  fieldValues: Record<string, FieldValue>  // ← Wrap values
  currentPartId: string  // "part_1", "part_2"...
  completedParts: Set<string>
  sessionId?: string  // Set by backend
  lastUpdated: number
}
```

3. **Add WebSocket-compatible methods**:
```typescript
static getCurrentPartNumber(state: SchemaFormState): number {
  const part = state.schema.parts.find(p => p.id === state.currentPartId)
  return part?.order ?? 1  // Use order as section_number
}

static getHandshakePayload(state: SchemaFormState, fillLanguage: string) {
  const currentPart = state.schema.parts.find(p => p.id === state.currentPartId)
  const sectionSchema = this.extractSectionFields(state.schema, state.currentPartId)

  return {
    schema: sectionSchema,
    current_values: state.fieldValues,
    section_number: currentPart?.order,      // ← Map order to section_number
    section_label: currentPart?.label,
    total_sections: state.schema.parts.length,
    previous_spoken_names: this.getPreviousSpokenNames(state),
    fill_language: fillLanguage
  }
}

static extractSectionFields(schema: FormSchema, partId: string): FormSchema {
  // Return schema with only fields from this part
  const part = schema.parts.find(p => p.id === partId)
  const section = schema.sections.find(s => part?.section_ids.includes(s.id))

  return {
    ...schema,
    fields: schema.fields.filter(f => section?.fields.includes(f.id))
  }
}

static switchToPart(state: SchemaFormState, partId: string): SchemaFormState {
  // Switch to a different part (for section navigation)
  const updatedState = {
    ...state,
    currentPartId: partId,
    lastUpdated: Date.now()
  }
  this.save(updatedState)
  return updatedState
}

static getPreviousSpokenNames(state: SchemaFormState): string[] {
  // Build list of spoken names from completed parts
  const completedParts = Array.from(state.completedParts)
  const spokenNames: string[] = []

  for (const partId of completedParts) {
    const part = state.schema.parts.find(p => p.id === partId)
    if (!part) continue

    const section = state.schema.sections.find(s => part.section_ids.includes(s.id))
    if (!section) continue

    for (const fieldId of section.fields) {
      const field = state.schema.fields.find(f => f.id === fieldId)
      if (field?.spoken_name) {
        spokenNames.push(field.spoken_name)
      }
    }
  }

  return spokenNames
}

static updateFieldValue(
  state: SchemaFormState,
  fieldId: string,
  value: any,
  options?: { confirmed?: boolean }
): SchemaFormState {
  const fieldValue: FieldValue = {
    value,
    confirmed: options?.confirmed,
    lastModified: Date.now()
  }

  const updatedState = {
    ...state,
    fieldValues: {
      ...state.fieldValues,
      [fieldId]: fieldValue
    },
    lastUpdated: Date.now()
  }

  this.save(updatedState)
  return updatedState
}

static completePart(state: SchemaFormState, partId: string): SchemaFormState {
  const updatedState = {
    ...state,
    completedParts: new Set([...state.completedParts, partId]),
    lastUpdated: Date.now()
  }
  this.save(updatedState)
  return updatedState
}
```

4. **Update save/load to handle FieldValue**:
```typescript
static save(state: SchemaFormState): void {
  try {
    const serialized = {
      ...state,
      completedParts: Array.from(state.completedParts)
    }
    sessionStorage.setItem(this.STORAGE_KEY, JSON.stringify(serialized))
  } catch (error) {
    console.error("[SchemaFormState] Save failed:", error)
  }
}

static load(): SchemaFormState | null {
  try {
    const stored = sessionStorage.getItem(this.STORAGE_KEY)
    if (!stored) return null

    const parsed = JSON.parse(stored)

    // Restore Set from array
    if (parsed.completedParts) {
      parsed.completedParts = new Set(parsed.completedParts)
    }

    return parsed as SchemaFormState
  } catch (error) {
    console.error("[SchemaFormState] Load failed:", error)
    return null
  }
}
```

**Files Modified**:
- `frontend/src/schema-forms/state/schemaFormState.ts`
- `frontend/src/schema-forms/types/schema.ts` (add FieldValue export)

**Exit Criteria**:
- ✅ SchemaFormStateManager can generate WebSocket handshake
- ✅ `parts[].order` maps to `section_number`
- ✅ Field values wrapped in FieldValue type
- ✅ Previous spoken names extracted from completed parts
- ✅ All existing SchemaForm functionality still works

---

### Phase 2: Update WebFormConnection ⏱️ 2 hours

**Goal**: Make WebFormConnection work with SchemaFormState

**Tasks**:

1. **Update imports**:
```typescript
import {
  SchemaFormStateManager,
  type SchemaFormState
} from './schema-forms/state/schemaFormState'
import type { FormSchema } from './schema-forms/types/schema'
```

2. **Replace WebFormState with SchemaFormState**:
```typescript
export class WebFormConnection {
  private state: SchemaFormState  // ← Changed from WebFormState

  constructor(schema: FormSchema, callbacks: ConnectionCallbacks, fillLanguage: string) {
    this.state = SchemaFormStateManager.init(schema)
    this.callbacks = callbacks
    this.fillLanguage = fillLanguage
  }
}
```

3. **Update handshake generation**:
```typescript
private handleOpen(): void {
  this.reconnectAttempts = 0
  this.reconnectDelay = 1000
  this.enableAutoReconnect = true

  if (this.isSectionSwitching) {
    return
  }

  // Use SchemaFormStateManager for handshake
  const handshake = SchemaFormStateManager.getHandshakePayload(
    this.state,
    this.fillLanguage
  )
  this.send(handshake)
}
```

4. **Update section switching**:
```typescript
async switchSection(target: number | string, wsUrl: string): Promise<void> {
  let targetPartId: string

  if (typeof target === 'number') {
    // Find part by order number
    const part = this.state.schema.parts.find(p => p.order === target)
    if (!part) throw new Error(`Part with order ${target} not found`)
    targetPartId = part.id
  } else {
    // Already a part ID
    targetPartId = target
  }

  // Wait for buffer drain
  await this.waitForBufferDrain(1000)

  this.setStatus('switching_section')

  // Switch to target part in state
  this.state = SchemaFormStateManager.switchToPart(this.state, targetPartId)

  // Build section info
  const sectionSchema = SchemaFormStateManager.extractSectionFields(
    this.state.schema,
    targetPartId
  )

  const part = this.state.schema.parts.find(p => p.id === targetPartId)
  const previousSpokenNames = SchemaFormStateManager.getPreviousSpokenNames(this.state)

  // Send section switch with embedded info
  this.send({
    type: "manual_section_switch",
    identifier: part?.order.toString(),
    section_info: {
      schema: sectionSchema,
      current_values: this.state.fieldValues,
      metadata: {
        section_number: part?.order,
        total_sections: this.state.schema.parts.length,
        section_label: part?.label || '',
        previous_spoken_names: previousSpokenNames,
      },
      initial_field_hint: this.computeNextFieldHintString(),
    },
  })
}
```

5. **Update field update handling**:
```typescript
private handleFormUpdated(message: any): void {
  const data = message?.data || {}
  const formState = data.form_state || {}
  const applied = data.applied_fields || []

  const appliedSet = new Set(applied.map((entry: any) => String(entry)))
  const updatedFields: Array<{ fieldId: string; value: any }> = []

  for (const field of this.state.schema.fields) {
    const value = formState[field.id] ?? formState[field.name ?? ""]
    if (value === undefined) continue

    const isApplied = appliedSet.has(field.id) || (field.name ? appliedSet.has(field.name) : false)
    if (appliedSet.size > 0 && !isApplied) continue

    const currentValue = this.state.fieldValues[field.id]?.value
    if (!isApplied && Object.is(currentValue, value)) continue

    // Use SchemaFormStateManager to update
    this.state = SchemaFormStateManager.updateFieldValue(
      this.state,
      field.id,
      value,
      { confirmed: isApplied }
    )

    updatedFields.push({ fieldId: field.id, value })
  }

  if (updatedFields.length && this.callbacks.onFieldUpdate) {
    this.callbacks.onFieldUpdate(updatedFields)
  }

  // Handle next field hint request if present
  if (data.request_next_field_hint && data.request_id) {
    const hint = this.computeNextFieldHintString()
    if (hint) {
      sessionStorage.setItem('vff_last_field_hint', hint)
    }
    this.send({
      type: "next_field_hint_response",
      request_id: data.request_id,
      hint: hint
    })
  }
}
```

6. **Remove old WebFormStateManager references**:
- Search for all `WebFormStateManager` imports
- Replace with `SchemaFormStateManager`
- Update method calls to match new API

**Files Modified**:
- `frontend/src/webFormConnection.ts`
- `frontend/src/shared/connection.ts` (update imports)

**Exit Criteria**:
- ✅ WebFormConnection uses SchemaFormState
- ✅ Handshake uses `parts[].order` as section_number
- ✅ Section switching works with part IDs
- ✅ Field updates use SchemaFormStateManager
- ✅ No references to old WebFormStateManager

---

### Phase 3: Wire Voice into SchemaForm ⏱️ 3 hours

**Goal**: Add voice overlay components to schema forms

**Tasks**:

1. **Update SchemaFormDemo to create connection manager**:
```typescript
// frontend/src/schema-forms/SchemaFormDemo.tsx

import { useState, useEffect } from "react"
import { SchemaForm } from "./components/SchemaForm"
import { createConnectionManager, type ConnectionManager } from "../shared/connection"
import { VoiceOverlay } from "../demo/VoiceOverlay"
import { VoiceOverlayMobile } from "../demo/VoiceOverlayMobile"
import type { FormSchema } from "./types/schema"

export function SchemaFormDemo() {
  const [schema, setSchema] = useState<FormSchema | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Connection state
  const [connectionManager, setConnectionManager] = useState<ConnectionManager | null>(null)
  const [status, setStatus] = useState<string>('disconnected')

  // Shared audio stream (for VAD coordination)
  const [sharedStream, setSharedStream] = useState<MediaStream | null>(null)
  const [streamError, setStreamError] = useState<string | null>(null)

  // Detect mobile
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 768)
    checkMobile()
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Create shared audio stream EARLY (before overlays render)
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

    initSharedStream()

    return () => {
      mounted = false
      if (sharedStream) {
        sharedStream.getTracks().forEach(track => track.stop())
      }
    }
  }, [])

  // Load I-90 schema
  useEffect(() => {
    async function loadSchema() {
      try {
        setLoading(true)
        const response = await fetch(
          "/pdf_schema_extractor/test_schemas/test_pdfs/i-90/i-90_schema.json"
        )

        if (!response.ok) {
          throw new Error(`Failed to load schema: ${response.statusText}`)
        }

        const schemaData = await response.json()
        setSchema(schemaData)
        setError(null)
      } catch (err) {
        console.error("[SchemaFormDemo] Failed to load schema:", err)
        setError(err instanceof Error ? err.message : "Unknown error")
      } finally {
        setLoading(false)
      }
    }

    loadSchema()
  }, [])

  // Initialize connection manager when schema and stream are ready
  useEffect(() => {
    if (schema && sharedStream && !connectionManager) {
      const manager = createConnectionManager(
        schema,
        setStatus,
        'English',  // Initial fill language
        sharedStream
      )
      setConnectionManager(manager)
    }
  }, [schema, sharedStream, connectionManager])

  const handleSubmit = (fieldValues: Record<string, any>) => {
    console.log("[SchemaFormDemo] Form submitted:", fieldValues)
    alert("Form submitted! Check console for values.")
  }

  const handleSectionChange = (sectionId: string) => {
    console.log("[SchemaFormDemo] Section changed to:", sectionId)
  }

  const handleClearSession = () => {
    if (confirm("Clear all form data and start fresh?")) {
      sessionStorage.removeItem("schema_form_state")
      window.location.reload()
    }
  }

  if (loading) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__loading">
          <p>Loading I-90 schema...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>Error Loading Schema</h2>
          <p>{error}</p>
        </div>
      </div>
    )
  }

  if (!schema) {
    return (
      <div className="schema-form-demo">
        <div className="schema-form-demo__error">
          <h2>No Schema Loaded</h2>
        </div>
      </div>
    )
  }

  return (
    <div className="schema-form-demo">
      <div style={{ padding: "10px", background: "#f0f0f0", marginBottom: "20px" }}>
        <button onClick={handleClearSession} style={{ padding: "8px 16px", cursor: "pointer" }}>
          🗑️ Clear Form & Start Fresh
        </button>
      </div>

      <SchemaForm
        schema={schema}
        pdfUrl="/pdfs/i-90.pdf"
        onSubmit={handleSubmit}
        onSectionChange={handleSectionChange}
      />

      {/* Voice overlay - desktop or mobile */}
      {connectionManager && !streamError && (
        isMobile ? (
          <VoiceOverlayMobile
            connectionManager={connectionManager}
            status={status}
            schema={schema}
          />
        ) : (
          <VoiceOverlay
            connectionManager={connectionManager}
            status={status}
            schema={schema}
          />
        )
      )}

      {streamError && (
        <div style={{
          position: 'fixed',
          bottom: 20,
          right: 20,
          background: '#f44336',
          color: 'white',
          padding: '10px',
          borderRadius: '4px'
        }}>
          Microphone error: {streamError}
        </div>
      )}
    </div>
  )
}
```

2. **Update VoiceOverlay to work with PDF schemas**:
- Verify schema property access (`schema.parts` vs `schema.sections`)
- Update section progress display
- Test language switcher

3. **Update connection.ts to handle FieldValue type**:
```typescript
// In fieldManager onManualEdit callback
onManualEdit: (fieldId, value) => {
  // Update using SchemaFormStateManager
  const updatedState = SchemaFormStateManager.updateFieldValue(
    state,
    fieldId,
    value,
    { confirmed: true }
  )
  Object.assign(state, updatedState)

  // Notify Gemini
  if (connection) {
    const field = schema.fields.find(f => f.id === fieldId)
    const fieldName = field?.name || fieldId
    connection.sendManualFieldUpdate(fieldId, fieldName, value)
  }
}
```

**Files Modified**:
- `frontend/src/schema-forms/SchemaFormDemo.tsx`
- `frontend/src/demo/VoiceOverlay.tsx` (minor updates)
- `frontend/src/demo/VoiceOverlayMobile.tsx` (minor updates)
- `frontend/src/shared/connection.ts` (update field manager callback)

**Exit Criteria**:
- ✅ Voice overlay renders in SchemaFormDemo
- ✅ Can connect to backend and establish session
- ✅ Microphone access works
- ✅ Connection status displays correctly
- ✅ Language switcher functional

---

### Phase 4: Testing & Validation ⏱️ 2 hours

**Goal**: Verify end-to-end voice interaction with I-90 schema

**Test Scenarios**:

1. **Connection Flow**:
   - [ ] Click Connect button
   - [ ] Backend receives handshake with `section_number: 1`
   - [ ] Session ready message received
   - [ ] Connection status shows "Connected"

2. **Voice Interaction**:
   - [ ] Speak into microphone
   - [ ] Audio streams to backend
   - [ ] Gemini responds with audio
   - [ ] Audio plays back in browser

3. **Field Updates**:
   - [ ] AI says "Your first name is..."
   - [ ] Field updates with green checkmark
   - [ ] Value visible in form
   - [ ] Value persists in sessionStorage

4. **Manual Edits**:
   - [ ] Type into field manually
   - [ ] Green checkmark clears
   - [ ] Backend notified via `manual_field_update`
   - [ ] Gemini acknowledges the change

5. **Section Navigation**:
   - [ ] Say "go to part 2"
   - [ ] Backend receives switch request with `order: 2`
   - [ ] Form switches to Part 2 fields
   - [ ] Previous Part 1 data preserved

6. **Session Persistence**:
   - [ ] Fill several fields
   - [ ] Refresh page (F5)
   - [ ] All field values restored
   - [ ] Current section restored

7. **PDF Download**:
   - [ ] Fill multiple fields
   - [ ] Click "Download PDF"
   - [ ] PDF downloads with values filled
   - [ ] Values match form exactly

**Files to Test**:
- All Phase 1-3 modified files
- Backend WebSocket handlers (no changes, but verify compatibility)

**Exit Criteria**:
- ✅ All 7 test scenarios pass
- ✅ No console errors
- ✅ No WebSocket disconnects
- ✅ No data loss on refresh

---

### Phase 5: Cleanup & Documentation ⏱️ 1 hour

**Goal**: Remove deprecated code and update documentation

**Tasks**:

1. **Delete demo app files**:
```bash
rm frontend/src/demo/AdultIntakeDemo.tsx
rm frontend/public/adult_intake_demo_schema.json
rm frontend/public/adult_intake_sections_index.json
# Keep adult-intake-form.html if still used for testing
```

2. **Delete old state manager**:
```bash
# Delete WebFormStateManager from webFormState.ts
# Keep only type definitions that are still used
# Update exports to point to SchemaFormStateManager
```

3. **Update imports across codebase**:
```bash
# Search for remaining WebFormStateManager imports
grep -r "WebFormStateManager" frontend/src/
# Replace with SchemaFormStateManager
```

4. **Update TECHNICAL_GUIDE.md**:
   - Mark activity watchdog as deprecated
   - Add section on PDF schema voice integration
   - Update state management section
   - Document `parts[].order` → `section_number` mapping

5. **Update PROJECT_STATUS.md**:
   - Mark Phase 3B as complete
   - Document frontend consolidation
   - Update file locations

**Files Modified**:
- `planning_documents/TECHNICAL_GUIDE.md`
- `planning_documents/PROJECT_STATUS.md`
- `frontend/src/webFormState.ts` (cleanup old code)

**Exit Criteria**:
- ✅ All demo app files deleted
- ✅ No broken imports
- ✅ Documentation updated
- ✅ Commit with clear message

---

## Effort Summary

| Phase | Task | Time | Status |
|-------|------|------|--------|
| 1 | Merge state managers | 4 hrs | Pending |
| 2 | Update WebFormConnection | 2 hrs | Pending |
| 3 | Wire voice into SchemaForm | 3 hrs | Pending |
| 4 | Testing & validation | 2 hrs | Pending |
| 5 | Cleanup & documentation | 1 hr | Pending |
| **Total** | | **12 hrs** | |

**Previous estimate** (with adapter pattern): 23-31 hours
**New estimate** (consolidation): 12 hours
**Reduction**: 52-61%

---

## Benefits of Consolidation

### Simplicity ✅
- **One state manager** (SchemaFormStateManager)
- **One schema format** (PDF schemas with parts/sections)
- **No adapter layer** (direct integration)
- **No dual patterns** to maintain

### Separation of Concerns ✅
- **SchemaFormStateManager**: State + WebSocket serialization
- **WebFormConnection**: WebSocket communication
- **SchemaForm**: UI rendering
- **Voice overlays**: Voice interaction
- **Field/Audio managers**: Specialized handlers

### Maintainability ✅
- **Single source of truth** (PDF schemas)
- **Clear migration path** for 50+ forms
- **No legacy code** to support
- **Pydantic models** define structure

### Scalability ✅
- **PDF extraction scales** to any USCIS form
- **No manual section indices** to maintain
- **Automated schema updates** (re-run extraction)
- **Voice works for all forms** automatically

---

## Risk Mitigation

### Risk: Breaking existing functionality
**Mitigation**:
- Incremental phases with exit criteria
- Keep voice infrastructure intact
- Test each phase before moving forward

### Risk: State migration issues
**Mitigation**:
- FieldValue wrapper is additive (backwards compatible)
- Can coexist with old state temporarily
- Clear sessionStorage option in UI

### Risk: Backend incompatibility
**Mitigation**:
- Backend already accepts section_number
- `parts[].order` maps directly to section_number
- No backend changes required

---

## Rollback Strategy

If issues arise, rollback is straightforward:

1. **Revert Phase 1**: Keep old WebFormStateManager
2. **Revert Phase 2**: Restore old WebFormConnection imports
3. **Revert Phase 3**: Remove voice overlay from SchemaFormDemo
4. **Restore demo app**: Cherry-pick commits from previous branch

**Rollback time**: 1-2 hours (Git revert + testing)

---

## Success Criteria

### Technical ✅
- [ ] SchemaFormStateManager generates valid handshakes
- [ ] WebSocket connection establishes successfully
- [ ] Voice overlay renders and functions
- [ ] Field updates work (AI → form, form → AI)
- [ ] Section navigation works
- [ ] Session persistence works
- [ ] PDF download works

### Code Quality ✅
- [ ] No duplicate state managers
- [ ] No unused imports
- [ ] No console errors
- [ ] TypeScript compiles without warnings
- [ ] All existing tests pass

### Documentation ✅
- [ ] TECHNICAL_GUIDE.md updated
- [ ] PROJECT_STATUS.md updated
- [ ] This plan document reflects reality
- [ ] Clear commit messages

---

## Post-Consolidation Next Steps

After consolidation is complete:

1. **Test with other PDF schemas** (I-589, N-400)
2. **Fix checkbox/radio filling** in backend (Phase 3A completion)
3. **Performance optimization** (if needed)
4. **Production deployment** preparation
5. **User acceptance testing** with real forms

---

## Notes

- **Demo app preserved separately**: Original AdultIntakeDemo saved in separate repo
- **No backwards compatibility needed**: Can break demo app safely
- **PDF schemas are correct**: Follow Pydantic models properly
- **`order` = `section_number`**: Semantically identical, just different names

---

**Document Owner**: Development Team
**Last Updated**: November 5, 2025
**Status**: Ready to implement Phase 1
