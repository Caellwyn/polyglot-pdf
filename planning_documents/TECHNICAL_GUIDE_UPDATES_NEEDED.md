# TECHNICAL_GUIDE.md Required Updates

**Date**: November 20, 2025
**Based on**: Comprehensive codebase audit
**Source**: CODEBASE_AUDIT_FINDINGS.md

---

## Critical Corrections

### 1. Line 101 - confirmationMethod Values
**Current**:
```typescript
confirmationMethod?: 'ai_voice' | 'manual_button';
```

**Should be**:
```typescript
confirmationMethod?: 'ai_voice' | 'manual_edit';
```

**Reason**: The actual implementation uses `'manual_edit'` which is more accurate - confirmation is triggered by direct field editing, not a button click.

**Files to verify**:
- `frontend/src/schema-forms/types/schema.ts:345`
- `frontend/src/webFormConnection.ts:1224`

---

### 2. Add Critical Bug Note (RESOLVED - Nov 20, 2025)

Add note that `getFieldBySpokenName()` bug was fixed:

**Location**: After line 70 or in Known Issues section

**Text**:
```markdown
#### Bug Fixed (Nov 20, 2025)
- ✅ `getFieldBySpokenName()` in schemaFormState.ts was referencing deprecated properties (`currentPartId`, `completedParts`)
- ✅ Updated to use current properties (`currentSectionId`, `completedSections`)
- This fix ensures voice input field lookups work correctly
```

---

## Terminology Clarifications

### 3. Section vs Parts Architecture (Add to Form Schema Structure section)

**Add after line 498**:

```markdown
**Important Terminology**:

The I-90 schema uses a two-level hierarchy:
- **Parts**: 8 top-level organizational units (e.g., "Part 1. Information About You")
  - Used primarily for schema organization
  - Each part contains multiple sections via `section_ids` array
  - Present in schema but not directly used for UI navigation

- **Sections**: 16 detailed navigation units (e.g., "Part 1.1", "Part 1.2", "Part 2")
  - Used throughout frontend for navigation
  - Voice overlays show all 16 sections in dropdown
  - Progress tracking: "Section X of 16"
  - State management uses `currentSectionId` and `completedSections`

**Current Implementation**: The application has standardized on **sections** for all navigation,
while parts remain as organizational metadata in the schema.
```

---

### 4. Update Progress Tracking Description (Line 73-74)

**Current**:
```markdown
- ✅ Schema-driven forms with section-based navigation (16 sections for I-90)
```

**Add clarification**:
```markdown
- ✅ Schema-driven forms with section-based navigation (16 sections for I-90)
  - Note: Schema also defines 8 "parts" for organization, but UI navigation uses 16 sections
  - Progress displays as "Section X of 16 • Y% complete"
```

---

## JIT Schema System Clarifications

### 5. Update JIT Integration Status (Lines 913-947)

**Current status is ambiguous**. Add clarification:

**Replace**: "⚠️ **Frontend integration pending**"

**With**:
```markdown
**Frontend Integration Status** (Nov 20, 2025):
- ✅ **Utilities Complete**: All manifestUtils functions implemented and tested (20/20 tests passing)
- ✅ **State Management Ready**: `loadedFieldIds` and `jitModeEnabled` in SchemaFormState
- ⚠️ **Handshake Flow**: By design, initial handshake uses legacy format, then backend signals JIT mode
- ✅ **Subsequent Sections**: JIT mode activates for section switches after initial connection

**Why This Design**:
1. Frontend connects and sends initial handshake before knowing backend's JIT capability
2. Backend responds with `jit_mode_enabled` flag in `session_ready` message
3. Frontend switches to JIT mode for all subsequent section navigation
4. This provides backward compatibility with non-JIT backends

**Test Coverage**: 33/33 JIT-related tests passing
- Backend: 8/8 E2E tests + manifest unit tests
- Frontend: 20/20 manifestUtils tests
- Token reduction verified: 94% (7,400 → 458 tokens)
```

---

## New Sections to Add

### 6. Idle Timeout & Reconnect Button (Missing)

**Add after line 210 (VoiceOverlay section)**:

```markdown
#### Idle Timeout & Reconnect Button (Nov 20, 2025)

**Purpose**: Allow users to manually reconnect after idle timeout without page refresh.

**Flow**:
1. **Backend Detection**: No messages for 60 seconds (configurable via `WS_IDLE_TIMEOUT_SEC`)
2. **Timeout Message**: Backend sends `idle_timeout` message type
3. **Flag Set**: Frontend sets `idleTimedOut = true` and status = `'idle_timeout'`
4. **Auto-Reconnect Blocked**: Flag prevents automatic reconnection attempts
5. **UI Changes**:
   - Status icon: ⏱️ (clock)
   - Status text: "Disconnected due to inactivity"
   - Button appears: "🔄 Reconnect"
6. **Manual Reconnect**: User clicks button → flag cleared → connection reestablished

**Implementation Files**:
- Frontend flag: `webFormConnection.ts:55` (`idleTimedOut`)
- Clear logic: `connection.ts:75-77`
- Desktop UI: `VoiceOverlay.tsx:1150-1156`
- Mobile UI: `VoiceOverlayMobile.tsx:844-846`

**Benefits**:
- No page refresh needed
- Preserves form data in sessionStorage
- Clear user feedback about why connection dropped
- Single-click recovery
```

---

### 7. Disclaimer Acceptance Flow (Expand existing section)

**Location**: After line 214 (Onboarding Flow)

**Add detailed implementation**:

```markdown
#### Detailed Disclaimer Implementation

**Components**:
1. **DisclaimerModal** (`DisclaimerModal.tsx`):
   - Non-dismissible (ESC blocked, no outside click, no X button)
   - English text display with multilingual buttons
   - "Listen Again" → Triggers Gemini to re-read aloud
   - "I Agree" → Logs acceptance and proceeds to form

2. **Language Selection** (First-time users only):
   - Modal appears on mount before any connection
   - 18 languages supported with native names
   - Selection triggers: connection + disclaimer modal

3. **Backend Logging**:
   - Endpoint: `POST /api/disclaimer-acceptance`
   - Logs: `form_session_id`, `language`, `timestamp`, `user_agent`, `client_ip`
   - File: Structured logging for audit trail
   - No PII in logs (only metadata)

4. **State Persistence**:
   - `disclaimerAccepted`: boolean flag in sessionStorage
   - `disclaimerAcceptedAt`: Unix timestamp (milliseconds)
   - `selectedLanguage`: User's chosen language
   - Returning users skip both modals automatically

**File Locations**:
- Modal component: `frontend/src/schema-forms/components/DisclaimerModal.tsx`
- CSS: `frontend/src/schema-forms/components/DisclaimerModal.css`
- Backend route: `backend/routes/disclaimer_routes.py`
- Integration: `VoiceOverlay.tsx:1760-1766`, `VoiceOverlayMobile.tsx:776-777`
```

---

### 8. Auto-Scroll Feature Details (Add after line 235)

**New Section**:

```markdown
### Auto-Scroll to Fields (Nov 18, 2025)

**Purpose**: Automatically scroll to and highlight fields when Gemini fills them.

**Implementation** (`webFormConnection.ts:1231-1250`):

```typescript
// Triggers only when confirmed = true (AI explicit confirmation)
if (confirmed && typeof document !== 'undefined') {
  setTimeout(() => {
    const element = document.getElementById(fieldId);
    if (element) {
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
        inline: 'nearest'
      });

      element.classList.add('field-highlight');
      setTimeout(() => {
        element.classList.remove('field-highlight');
      }, 1500);
    }
  }, 50);
}
```

**Trigger Conditions**:
- ✅ Triggers: When Gemini confirms field via `confirm_field` tool
- ❌ Does NOT trigger: When AI initially fills (unconfirmed)
- ❌ Does NOT trigger: On manual user edits

**Visual Effect** (`schema-form.css:460-486`):
- **Animation Duration**: 1.5 seconds
- **Effect**: Blue pulsing box-shadow (rgba(59, 130, 246, 0.7))
- **Scale**: Subtle 2% scale-up at midpoint (1.02x)
- **Border**: Blue highlight (#3b82f6) during animation
- **Timing**: 50ms delay for React DOM updates

**Benefits**:
- User sees which field was just filled
- No focus stealing (doesn't call `.focus()`)
- No keyboard popup on mobile (visual only)
- Works across all field types
```

---

## Minor Updates

### 9. Update Audio Processing Values (Lines 182-189)

**Verify and update**:

**Current values are correct, but add specifics**:
- **Noise Gate**: -50dB threshold (linear: 0.00316)
- **High-Pass Filter**: 80Hz cutoff, Q factor = 0.7
- **Sample Rate**: 16,000 Hz (must match getUserMedia)
- **PTT Mode**: Bypasses noise gate entirely when enabled

**File**: `frontend/src/shared/audio-processor.worklet.ts:34-92`

---

### 10. Update Shared Audio Stream Location (Lines 153-171)

**Add exact line numbers**:

**SchemaForm Stream Initialization** (`SchemaForm.tsx:71-110`):
```typescript
const stream = await navigator.mediaDevices.getUserMedia({
  audio: {
    channelCount: 1,
    sampleRate: 16000,
    echoCancellation: true,
    noiseSuppression: true,
    autoGainControl: true,
  },
})
```

**Stream Passed to Children** (`SchemaForm.tsx:469-486`):
- Desktop: `<VoiceOverlay sharedStream={sharedStream} ... />`
- Mobile: `<VoiceOverlayMobile sharedStream={sharedStream} ... />`

---

## File Path Updates

### 11. Update All Schema Paths

**Old paths** (deprecated):
```
frontend/public/pdf_schema_extractor/test_schemas/test_pdfs/i-90/
```

**New paths** (current):
```
form-kits/i-90/schema.json
form-kits/i-90/form.pdf
```

**Files to update**:
- Line 570-579 (Supported Forms section)
- Line 586-606 (Form Kit Workflow section)
- Line 1149 (File Structure section)

---

## Sections Confirmed Accurate (No Changes Needed)

These sections match the actual implementation perfectly:

- ✅ **Confirmation System** (Lines 111-147) - All details correct
- ✅ **FieldValue Wrapper System** (Lines 84-110) - Implementation matches
- ✅ **Validation System** (Lines 364-438) - Multi-error collection documented correctly
- ✅ **Tool Definitions** (Lines 347-360) - All 5 tools listed correctly
- ✅ **Privacy & Security** (Lines 848-861) - Accurate description
- ✅ **Technology Stack** (Lines 31-51) - All components listed correctly

---

## New PDF Filling Section (Already Added - Nov 20, 2025)

The PDF filling section appears to have been added recently to TECHNICAL_GUIDE.md (visible in git diff).
Verify it includes:
- ✅ PyMuPDF implementation
- ✅ Field flag manipulation (bit flipping)
- ✅ All field type support
- ✅ Frontend integration with fillPDF utility
- ✅ Form kit system integration

---

## Recommended Document Structure Additions

### Add these subsections to improve AI navigation:

**After Executive Summary, add**:
```markdown
## Quick Reference for AI Assistants

**Looking for**:
- Confirmation system? → See line 111-147
- PDF filling? → See line 622-720
- JIT schema? → See line 913-947
- Validation? → See line 364-438
- Audio processing? → See line 722-812
- WebSocket protocol? → See line 444-492
- File structure? → See line 1109-1186
```

---

## Priority Order for Updates

1. **HIGH**: Fix confirmationMethod value (line 101)
2. **HIGH**: Add JIT integration clarification (lines 913-947)
3. **MEDIUM**: Add Idle Timeout & Reconnect section
4. **MEDIUM**: Expand Disclaimer Acceptance details
5. **MEDIUM**: Add Auto-Scroll Feature section
6. **LOW**: Update all form-kits paths
7. **LOW**: Add bug fix note for getFieldBySpokenName

---

## Verification Checklist

After updates, verify:
- [ ] All line numbers are accurate
- [ ] All file paths use forward slashes or proper Windows format
- [ ] Code snippets are syntactically correct
- [ ] Cross-references between sections are accurate
- [ ] Version number updated to 4.0
- [ ] Last Updated date is November 20, 2025
- [ ] No contradictions with other planning documents

---

**Total Updates Needed**: 11 corrections + 3 new sections
**Estimated Time**: 30-45 minutes for careful implementation
**Risk**: LOW - mostly clarifications and additions, few deletions
