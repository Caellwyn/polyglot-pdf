# Implementation Plan: Bug Fixes & Token Reduction
## Voice Form Filler - November 2025

---

## Priority 1: Critical Bug Fixes (Day 1)
*These bugs block core functionality and must be fixed first*

### Bug 1: Manual Entry Shows [object Object]
**Severity**: High - Breaks manual form filling
**Time Estimate**: 30 minutes

#### Root Cause
Form fields are displaying the FieldValue wrapper object instead of the actual value.

#### Files to Check
- `frontend/src/schema-forms/components/fields/TextField.tsx`
- `frontend/src/schema-forms/components/fields/TextAreaField.tsx`
- `frontend/src/schema-forms/components/fields/SelectField.tsx`
- `frontend/src/schema-forms/components/fields/RadioField.tsx`
- `frontend/src/schema-forms/components/fields/CheckboxField.tsx`
- `frontend/src/schema-forms/components/fields/DateField.tsx`

#### Fix Implementation
```typescript
// In each field component, update the value prop handling:
// Current (broken):
value={value}

// Fixed:
value={typeof value === 'object' && value !== null && 'value' in value ? value.value : value}
```

#### Testing
1. Open form in browser
2. Type in any text field
3. Verify actual text appears, not "[object Object]"
4. Test all field types (text, select, radio, checkbox, date)

---

### Bug 2: Radio Buttons Reset Form
**Severity**: High - Data loss on interaction
**Time Estimate**: 1-2 hours

#### Root Cause
Radio button onChange handler is likely replacing entire state instead of updating single field.

#### Files to Check
- `frontend/src/schema-forms/components/fields/RadioField.tsx`
- `frontend/src/schema-forms/components/SchemaForm.tsx` (handleFieldChange method)
- `frontend/src/schema-forms/state/schemaFormState.ts` (updateFieldValue method)

#### Investigation Steps
1. Add console.log to RadioField onChange:
```typescript
console.log('Radio change:', {
  fieldId,
  oldValue: value,
  newValue: e.target.value,
  currentState: schemaFormState.getState()
});
```

2. Check state update pattern:
```typescript
// Bad - replaces entire fieldValues
onChange={(e) => updateFieldValue(fieldId, e.target.value)}
// If updateFieldValue does: this.state.fieldValues = { [fieldId]: value }

// Good - spreads existing state
onChange={(e) => updateFieldValue(fieldId, e.target.value)}
// If updateFieldValue does: this.state.fieldValues = { ...this.state.fieldValues, [fieldId]: value }
```

#### Fix Implementation
1. Ensure RadioField uses same value unwrapping as Bug 1
2. Verify state update preserves other fields
3. Check if radio value storage matches expected format (string vs FieldValue wrapper)

#### Testing
1. Fill out several fields in section 1
2. Click a radio button
3. Verify other fields retain their values
4. Verify radio button shows as selected
5. Refresh page and check sessionStorage persistence

---

### Bug 3: Section Navigation Broken
**Severity**: Critical - Can only access 1/8 of form
**Time Estimate**: 2-3 hours

#### Root Cause
Likely mismatch between "parts" (backend terminology) and "sections" (frontend display), or schema not properly parsed.

#### Files to Check
- `frontend/src/schema-forms/components/SchemaForm.tsx`
- `frontend/src/schema-forms/components/SectionRenderer.tsx`
- `frontend/src/schema-forms/state/schemaFormState.ts`
- `frontend/src/webFormConnection.ts`
- `frontend/src/demo/VoiceOverlay.tsx` (section change handlers)

#### Debugging Steps
1. Add extensive logging:
```typescript
// In SchemaForm.tsx
console.log('Schema structure:', {
  hasParts: !!schema.parts,
  partsCount: schema.parts?.length,
  partIds: schema.parts?.map(p => p.id),
  currentPartId: currentPartId,
  sections: schema.sections
});

// In SectionRenderer.tsx
console.log('Section render:', {
  currentSection,
  availableSections: sections,
  currentPartId
});

// In schemaFormState.ts switchToPart()
console.log('Switching part:', {
  from: this.state.currentPartId,
  to: partId,
  availableParts: this.state.schema?.parts?.map(p => p.id)
});
```

2. Check schema structure:
```typescript
// Verify schema has parts array
if (!schema.parts || schema.parts.length === 0) {
  console.error('Schema missing parts array!');
}

// Check if using section IDs vs part IDs
const isUsingSectionIds = currentPartId?.startsWith('section-');
const isUsingPartIds = currentPartId?.startsWith('part') || currentPartId?.startsWith('Part');
```

#### Fix Implementation
1. Ensure schema has proper `parts` array with sections
2. Verify `currentPartId` matches actual part IDs in schema
3. Fix section extraction logic in SectionRenderer
4. Ensure voice overlay section changes trigger UI updates
5. Verify manual navigation buttons use correct method calls

#### Testing
1. Load form and check console for schema structure
2. Click "Next Section" button - verify UI updates
3. Use voice command "go to section 2" - verify UI updates
4. Check all 8 sections are accessible
5. Verify section state persists on refresh

---

## Priority 2: Token Reduction Implementation (Day 2-3)
*Implement just-in-time field loading to reduce token usage by ~90%*

### Phase 1: Backend Modifications

#### Step 1.1: Modify FormFillingService Handshake
**File**: `backend/services/form_filling_service.py`

**Current Behavior**: Sends entire section schema (37 fields = ~7,400 tokens)

**New Behavior**: Send field manifest + current field only

```python
def _prepare_handshake_context(self, section_data):
    """Prepare lightweight context for handshake"""
    
    # Create field manifest (lightweight)
    field_manifest = []
    for field in section_data['fields']:
        field_manifest.append({
            'id': field['id'],
            'spoken_name': field.get('spoken_name', field['id']),
            'order': field.get('order', 0)
        })
    
    # Get first unfilled field for full schema
    current_field = self._get_next_unfilled_field(section_data['fields'])
    
    return {
        'field_manifest': field_manifest,  # ~400 tokens for 37 fields
        'current_field_detail': current_field  # ~200 tokens
    }
```

#### Step 1.2: Update System Instruction Template
**File**: `backend/config.py`

```python
SYSTEM_INSTRUCTION: str = (
    "LANGUAGE: Detect user's language from first utterance...\n\n"
    
    "Medical assistant: {form_title} | Section {section_number}/{total_sections}\n"
    "Progress: {filled_count}/{total_fields}\n\n"
    
    "AVAILABLE FIELDS:\n{field_manifest}\n\n"  # Lightweight list
    
    "CURRENT FIELD TO FILL:\n{current_field_detail}\n\n"  # Full details
    
    "WORKFLOW:\n"
    "1. Ask about CURRENT FIELD shown above\n"
    "2. When user answers → call update_form_fields\n"
    "3. Response will include next field details\n"
    "4. Continue with the newly provided field\n\n"
    
    "FIELD ACCESS:\n"
    "• To skip to a different field, use get_field_value first\n"
    "• This loads that field's full schema into context\n"
    "• Only loaded fields can be updated\n\n"
    
    # Rest remains the same...
)
```

#### Step 1.3: Update Tool Response Formats
**File**: `backend/services/callback_handler.py`

**Update `handle_update_form_fields` response**:
```python
def handle_update_form_fields(self, args, context):
    # ... existing validation and update logic ...
    
    # Get next field with full schema
    next_field = self._get_next_unfilled_field(context['fields'])
    
    return {
        "success": True,
        "message": f"Updated {field_id}",
        "next_field": next_field  # Full schema for next field
    }
```

#### Step 1.4: Enhance get_field_value Tool
**File**: `backend/services/form_filling_service.py`

```python
def handle_get_field_value(self, field_identifier):
    """Return full schema for requested field"""
    
    # Find field by ID or spoken name
    field = self._find_field(field_identifier)
    
    if not field:
        return {
            "found": False,
            "message": f"Field '{field_identifier}' not found",
            "available_fields": self._get_manifest_names()
        }
    
    # Return full schema entry
    return {
        "found": True,
        "field": field,  # Complete schema entry
        "value": self._get_current_value(field['id']),
        "message": f"Loaded field: {field['spoken_name']}"
    }
```

### Phase 2: Frontend Support

#### Step 2.1: Update Handshake Payload
**File**: `frontend/src/webFormConnection.ts`

```typescript
private createHandshakePayload() {
    const manifest = this.createFieldManifest();
    const currentField = this.getCurrentFieldDetail();
    
    return {
        // ... existing fields ...
        field_manifest: manifest,  // Lightweight
        current_field_detail: currentField,  // Full schema
        // Remove full fields array
    };
}

private createFieldManifest() {
    return this.currentSectionFields.map(field => ({
        id: field.id,
        spoken_name: field.spoken_name || field.id,
        order: field.order || 0
    }));
}
```

#### Step 2.2: Track Loaded Fields
**File**: `frontend/src/schema-forms/state/schemaFormState.ts`

```typescript
export interface SchemaFormState {
    // ... existing fields ...
    loadedFieldIds: Set<string>;  // Track which fields have been sent to Gemini
}

// Add method to mark field as loaded
markFieldLoaded(fieldId: string) {
    this.state.loadedFieldIds.add(fieldId);
    this.save();
}

isFieldLoaded(fieldId: string): boolean {
    return this.state.loadedFieldIds.has(fieldId);
}
```

### Phase 3: Testing & Validation

#### Step 3.1: Token Usage Monitoring
Add logging to track actual token usage:

```python
# In backend/services/form_filling_service.py
def log_context_size(self, context_type, data):
    """Estimate and log token usage"""
    # Rough estimate: 1 token ≈ 4 characters
    char_count = len(json.dumps(data))
    token_estimate = char_count / 4
    
    logger.info(f"Context {context_type}: ~{token_estimate} tokens")
    return token_estimate
```

#### Step 3.2: Test Scenarios

1. **Linear Flow Test**
   - Start form, fill fields 1-10 sequentially
   - Monitor token accumulation
   - Verify each tool response includes next field

2. **Skip Navigation Test**
   - Start form, skip to field 20
   - Verify get_field_value loads field 20
   - Verify subsequent update works

3. **Mixed Navigation Test**
   - Fill fields 1-3
   - Skip to field 10
   - Go back to field 4
   - Verify all navigations work

4. **Section Change Test**
   - Complete section 1 with new token model
   - Switch to section 2
   - Verify clean context switch

---

## Implementation Schedule

### Day 1 (8 hours)
- [ ] Morning: Fix Bug 1 - [object Object] display (30 min)
- [ ] Morning: Fix Bug 2 - Radio button state reset (2 hours)
- [ ] Afternoon: Debug Bug 3 - Section navigation (3 hours)
- [ ] Afternoon: Test all fixes together (1 hour)
- [ ] End of day: Commit fixes, update TECHNICAL_GUIDE.md

### Day 2 (6 hours)
- [ ] Morning: Implement backend token reduction (Phase 1)
- [ ] Morning: Update system instruction and tools
- [ ] Afternoon: Implement frontend support (Phase 2)
- [ ] Afternoon: Initial testing of token reduction

### Day 3 (4 hours)
- [ ] Morning: Complete token reduction testing
- [ ] Morning: Fix any issues found
- [ ] Afternoon: Performance metrics collection
- [ ] Afternoon: Documentation updates

---

## Success Metrics

### Bug Fixes
- [ ] All form fields accept and display manual input correctly
- [ ] Radio buttons update without resetting other fields
- [ ] All 8 sections are navigable via UI and voice
- [ ] State persists correctly across refreshes

### Token Reduction
- [ ] Initial context < 500 tokens (vs 7,400)
- [ ] Average tokens per field < 250
- [ ] Total tokens for 37-field section < 2,500 (vs 7,400)
- [ ] No degradation in voice interaction quality

---

## Rollback Plan

If token reduction causes issues:

1. **Quick Rollback**: 
   - Revert `SYSTEM_INSTRUCTION` template
   - Revert handshake payload to send full fields array
   - Single config flag to toggle: `USE_TOKEN_REDUCTION = False`

2. **Partial Rollback**:
   - Keep manifest approach
   - But send 5-10 fields at a time instead of 1

3. **Git Strategy**:
   - Create branch: `fix/critical-bugs-and-token-reduction`
   - Commit bug fixes separately from token changes
   - Can cherry-pick bug fixes if token reduction needs more work
