# Confirmation System Design

**Date**: November 18, 2025
**Purpose**: Track user confirmations for liability protection
**Status**: Design Phase

---

## Overview

Implement a confirmation system where:
1. **Gemini cannot move to next field** until current field is confirmed
2. **Manual edits are auto-confirmed** (user typing = implicit confirmation)
3. **Verbal confirmations** require explicit user response (e.g., "yes", "correct", "that's right")
4. **All confirmations are logged** (anonymized, no PII) for liability defense
5. **UI shows confirmation status** visually for each field

---

## System Architecture

### Data Flow
```
User speaks → Gemini fills field → Gemini asks "Is that correct?"
→ User says "yes" → Gemini calls confirm_field tool → Field marked confirmed
→ Confirmation logged → Next field hint calculated (first unconfirmed)
→ Gemini moves to next field

OR

User types manually → Field auto-marked confirmed → Confirmation logged
→ Next field hint calculated → Gemini can reference field
```

---

## Phase 1: State & Data Model

### 1.1 Frontend FieldValue Type

**File**: `frontend/src/schema-forms/utils/fieldValue.ts`

**Current**:
```typescript
export interface FieldValue {
  value: string | boolean | null;
}
```

**New**:
```typescript
export interface FieldValue {
  value: string | boolean | null;
  confirmed: boolean; // NEW: Track confirmation status
  confirmedAt?: string; // NEW: ISO timestamp of confirmation
  confirmationMethod?: 'ai_voice' | 'manual_edit'; // NEW: How it was confirmed
}
```

### 1.2 SchemaFormState Updates

**File**: `frontend/src/schema-forms/state/schemaFormState.ts`

Add helper methods:
- `isFieldConfirmed(state, fieldId): boolean`
- `confirmField(state, fieldId, method): SchemaFormState`
- `getUnconfirmedFields(state): string[]` - Returns IDs of filled but unconfirmed fields

### 1.3 Backend Field State Response

**File**: `backend/services/callback_handler.py`

Update `get_form_status` tool response:
```python
# Current
{"field_id": "value"}

# New
{"field_id": {"value": "...", "confirmed": true}}
```

---

## Phase 2: Gemini Tools

### 2.1 New Tool: `confirm_field`

**Tool Declaration**:
```python
{
    "name": "confirm_field",
    "description": "Confirm that a field value is correct after user verification. MUST be called before moving to next field.",
    "parameters": {
        "type": "object",
        "properties": {
            "field_id": {
                "type": "string",
                "description": "ID of the field being confirmed"
            },
            "confirmation_method": {
                "type": "string",
                "enum": ["verbal", "manual"],
                "description": "How the field was confirmed (verbal: user said yes/correct, manual: user edited field)"
            }
        },
        "required": ["field_id", "confirmation_method"]
    }
}
```

**Tool Response**:
```json
{
  "success": true,
  "field_confirmed": "p1_line1_aliennumber",
  "next_field_hint": "Next, I'll ask for your last name",
  "next_field_schema": {...} // JIT mode
}
```

### 2.2 Tool Handler Implementation

**File**: `backend/services/callback_handler.py`

```python
async def _handle_confirm_field_tool(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Handle confirm_field tool call from Gemini."""
    field_id = arguments.get("field_id")
    confirmation_method = arguments.get("confirmation_method", "verbal")

    # Request confirmation from frontend
    await self._websocket.send_json({
        "type": "confirm_field",
        "field_id": field_id,
        "confirmation_method": confirmation_method
    })

    # Log confirmation (anonymized)
    if self._form_id and self._form_session_id:
        log_field_confirmation(
            form_id=self._form_id,
            form_session_id=self._form_session_id,
            field_id=field_id,
            field_name=self._get_field_name(field_id),
            confirmation_method=confirmation_method
        )

    # Get next unconfirmed field hint
    next_hint = await self._request_next_unconfirmed_field_hint()

    return {
        "success": True,
        "field_confirmed": field_id,
        "next_field_hint": next_hint
    }
```

### 2.3 Update `get_form_status` Tool

**Current behavior**: Returns field values only
**New behavior**: Returns value + confirmation status

```python
# Return format
{
    "field_values": {
        "firstName": {
            "value": "John",
            "confirmed": true
        },
        "lastName": {
            "value": "Doe",
            "confirmed": false  # Filled but not confirmed yet
        },
        "email": {
            "value": null,
            "confirmed": false  # Empty and unconfirmed
        }
    }
}
```

### 2.4 System Instruction Updates

Add to system instruction:
```
CONFIRMATION WORKFLOW:
1. After filling a field with update_form_fields, ask the user to confirm
   Example: "I've entered '123-45-6789' for your Social Security Number. Is that correct?"
2. Wait for user response (yes/correct/that's right/etc.)
3. If confirmed, call confirm_field tool BEFORE moving to next field
4. If user says no/incorrect, ask them to provide the correct value
5. Manual edits by user are automatically confirmed - you can reference them immediately

IMPORTANT: You MUST confirm each field before requesting the next field. Never skip confirmation.
```

---

## Phase 3: Next Field Logic

### 3.1 Update `computeNextField()`

**File**: `frontend/src/navigation.ts`

**Current logic**: Returns first unfilled field
**New logic**:
1. Prioritize filled but unconfirmed fields
2. Then return unfilled fields
3. Skip confirmed fields

```typescript
export function computeNextField(state: SchemaFormState): FormField | null {
  const fields = getFieldOrder(state);

  // Priority 1: Filled but UNCONFIRMED fields
  const unconfirmed = fields.find(f => {
    const fieldValue = state.fieldValues[f.id];
    return fieldValue?.value != null && !fieldValue?.confirmed;
  });
  if (unconfirmed) return unconfirmed;

  // Priority 2: Empty fields
  const unfilled = fields.find(f => {
    const fieldValue = state.fieldValues[f.id];
    return fieldValue?.value == null || fieldValue?.value === '';
  });

  return unfilled || null;
}
```

### 3.2 Update Next Field Hint

Backend should use updated logic to calculate hint based on unconfirmed fields.

### 3.3 Section Navigation

When clicking "Next" button:
- If current field is unconfirmed, prompt user to confirm first
- Don't advance until field is confirmed

---

## Phase 4: UI Indicators

### 4.1 Visual Confirmation Indicator

Add checkmark icon to confirmed fields:

```tsx
// In field rendering component
{fieldValue?.confirmed && (
  <span className="confirmation-indicator" title="Confirmed">
    ✓
  </span>
)}
```

### 4.2 CSS Styles

```css
.field-confirmed {
  border-left: 3px solid #22c55e; /* Green indicator */
}

.field-filled-unconfirmed {
  border-left: 3px solid #f59e0b; /* Orange - needs confirmation */
}

.field-empty {
  border-left: 3px solid #e5e7eb; /* Gray - not filled */
}

.confirmation-indicator {
  color: #22c55e;
  font-weight: bold;
  margin-left: 0.5rem;
}
```

### 4.3 Voice Overlay Field List

Show confirmation status:
```
✓ First Name: John (confirmed)
⚠ Last Name: Doe (needs confirmation)
○ Email: (not filled)
```

---

## Phase 5: Auto-Confirmation Rules

### 5.1 Manual Edit Auto-Confirmation

**File**: `frontend/src/webFormConnection.ts`

When user manually edits a field:

```typescript
updateField(fieldId: string, value: any, options?: {confirmed?: boolean, emit?: boolean}) {
  const confirmed = options?.confirmed ?? false;
  const emit = options?.emit ?? false;

  // Auto-confirm manual edits
  const isManualEdit = !confirmed; // If not from AI, it's manual
  const finalConfirmed = confirmed || isManualEdit;

  this.state = SchemaFormStateManager.updateField(
    this.state,
    fieldId,
    value,
    {
      confirmed: finalConfirmed,
      confirmationMethod: isManualEdit ? 'manual_edit' : 'ai_voice'
    }
  );

  // Log confirmation if manual
  if (isManualEdit && finalConfirmed) {
    this.logFieldConfirmation(fieldId, 'manual_edit');
  }
}
```

---

## Phase 6: Confirmation Logging

### 6.1 Log Format

**File**: `backend/utils/confirmation_logger.py` (already created)

Log entry structure:
```json
{
  "timestamp": "2025-11-18T20:30:45.123Z",
  "event": "field_confirmed",
  "form_id": "I-90",
  "form_session_id": "fss_abc123_xyz789",
  "field_id": "p1_line1_aliennumber",
  "field_name": "Alien Registration Number",
  "confirmation_method": "ai_voice"
}
```

### 6.2 Log Storage

```
logs/confirmations/
  ├── fss_abc123_xyz789.jsonl  (one file per form session)
  ├── fss_def456_uvw012.jsonl
  └── ...
```

### 6.3 Log Events

1. **form_session_started**: When user starts filling form
2. **field_confirmed**: Each time a field is confirmed
3. **form_session_ended**: When user completes/abandons form

---

## Implementation Order (Dependency-Based)

1. **Phase 1** (State Model) - Foundation for everything
2. **Phase 5.1** (Auto-confirm manual edits) - Quick win, improves UX immediately
3. **Phase 2.1-2.2** (confirm_field tool) - Core confirmation mechanism
4. **Phase 2.3** (get_form_status update) - Gemini needs this to check status
5. **Phase 3** (Next field logic) - Depends on confirmation state
6. **Phase 2.4** (System instruction) - Update Gemini's behavior
7. **Phase 4** (UI indicators) - Visual feedback for users
8. **Phase 6** (Logging) - Final layer for liability protection

---

## Testing Strategy

### Unit Tests
- Test FieldValue with confirmed status
- Test computeNextField prioritization
- Test confirm_field tool handler
- Test auto-confirmation logic

### Integration Tests
- User fills field → Gemini asks for confirmation → User confirms → Log created
- User manually edits → Auto-confirmed → Log created
- Next field hint skips confirmed fields
- Form completion with all fields confirmed

### E2E Tests
- Complete full form with voice confirmations
- Complete full form with manual edits (all auto-confirmed)
- Mixed: some voice, some manual
- Verify confirmation logs exist for each session

---

## Success Criteria

✅ Gemini cannot move to next field without confirmation
✅ Manual edits are auto-confirmed
✅ Confirmation logs created (anonymized, no PII)
✅ UI shows visual confirmation indicators
✅ Next field logic prioritizes unconfirmed fields
✅ All confirmations logged with timestamps
✅ Form session logs can be retrieved by form_session_id

---

## Risk Mitigation

**Risk**: Gemini ignores confirmation requirement
**Mitigation**: System instruction + tool validation + next_field_hint logic all enforce it

**Risk**: User confused by confirmation prompts
**Mitigation**: Clear voice prompts ("Is that correct?") + visual indicators

**Risk**: Logs contain PII accidentally
**Mitigation**: Code review + automated PII detection + only log field IDs, never values

**Risk**: Performance impact from logging
**Mitigation**: Async logging + batch writes + JSONL format (append-only)

---

## Implementation Status (November 19, 2025)

### ✅ COMPLETED - All Phases Implemented

The confirmation system has been fully implemented and is in production. Below are the key implementation details and bug fixes:

### Implementation Summary

**Phases Completed**:
1. ✅ Phase 1-6: Full confirmation system with state tracking, tools, UI, and logging
2. ✅ Backend tools (`confirm_field`, `get_form_status` with confirmation status)
3. ✅ Frontend UI indicators (green checkmarks)
4. ✅ Audit logging (anonymized, no PII in `logs/confirmations/*.jsonl`)
5. ✅ Auto-confirmation for manual edits
6. ✅ System instructions enforce workflow

### Critical Bugs Fixed (November 19, 2025)

#### Bug #1: Auto-Confirmation on AI Fills

**Problem**: Fields were being automatically confirmed when Gemini filled them, skipping the required user confirmation step.

**Root Cause**: `webFormConnection.ts` was setting `confirmed: true` when receiving field updates from Gemini (lines 320, 375, 420).

**Fix**: Changed all AI field updates to set `confirmed: false`. Only manual user edits are auto-confirmed.

**Files Modified**:
- `frontend/src/webFormConnection.ts` (3 locations)

**Correct Flow Now**:
```
1. Gemini requests field value
2. User provides value
3. Gemini calls update_form_fields → field saved with confirmed: false
4. Gemini reads back value and asks "Is that correct?"
5. User confirms "yes"
6. Gemini calls confirm_field tool → field updated to confirmed: true
7. Gemini moves to next field
```

#### Bug #2: Unknown Control Error After Confirmation

**Problem**: After confirming the first field, frontend received `unknown_control` error and lost PTT button.

**Root Cause**: Frontend was sending unnecessary `field_confirmed` acknowledgment back to backend, which had no handler for this message type.

**Fix**: Removed the acknowledgment message from `webFormConnection.ts:883-888`. Backend already logs confirmations internally when handling the `confirm_field` tool call.

**Files Modified**:
- `frontend/src/webFormConnection.ts`

### System Instructions

Enhanced system instructions to explicitly enforce confirmation workflow:

```
CRITICAL: Fields filled by you (AI) are NOT confirmed until user explicitly says yes.
Never skip confirmation. Never move to next field without calling confirm_field.
Only manual edits by user are auto-confirmed.
```

**Files Modified**:
- `backend/config.py` (both `SYSTEM_INSTRUCTION` and `JIT_SYSTEM_INSTRUCTION`)

### Confirmation Logging

All confirmations are logged to `backend/logs/confirmations/{form_session_id}.jsonl`:

```json
{
  "timestamp": "2025-11-19T22:30:45.123Z",
  "event": "field_confirmed",
  "form_id": "I-90",
  "form_session_id": "fss_abc123_xyz789",
  "field_id": "p1_line1_firstname",
  "field_name": "First Name",
  "confirmation_method": "ai_voice"
}
```

**No PII**: Logs contain field IDs and metadata only, never actual field values.

### Testing

**E2E Testing**: Confirmation workflow has been tested end-to-end:
- ✅ Gemini fills field → field shows as unconfirmed (no checkmark)
- ✅ Gemini asks "Is that correct?"
- ✅ User confirms "yes"
- ✅ Gemini calls `confirm_field` tool
- ✅ Green checkmark appears
- ✅ Gemini moves to next field
- ✅ Multiple fields confirmed successfully
- ✅ No errors or PTT button loss

### Next Steps

The confirmation system is fully functional. Future enhancements could include:
- Bulk confirmation UI for reviewing all fields before submission
- Confirmation history view in UI
- Export confirmation logs for legal/audit purposes
