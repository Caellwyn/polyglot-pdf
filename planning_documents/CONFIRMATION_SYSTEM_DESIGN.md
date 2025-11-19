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
