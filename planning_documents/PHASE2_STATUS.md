# Phase 2: WebSocket Connection Layer - Status Report

**Date:** November 5, 2025
**Status:** PARTIALLY COMPLETE - Core functionality updated, section methods pending

---

## Summary

Phase 2 aimed to update `webFormConnection.ts` to use `SchemaFormStateManager` instead of `WebFormStateManager`. The basic WebSocket functionality has been successfully updated, but the section-switching methods require additional work to map from the old section-based system to the new parts-based system.

---

## Completed ✅

### 1. Import Updates
- ✅ Updated imports to use `SchemaFormStateManager` and `SchemaFormState`
- ✅ Removed references to old `WebFormStateManager` in core methods

### 2. Type Declarations
- ✅ Changed `private state: WebFormState` → `private state: SchemaFormState`
- ✅ Updated `getState()` return type to `SchemaFormState`

### 3. Core Methods Updated
- ✅ `constructor()` - Uses `SchemaFormStateManager.init()`
- ✅ `handleOpen()` - Uses `SchemaFormStateManager.getHandshakePayload()`
- ✅ `handleSessionReady()` - Uses `SchemaFormStateManager.setSessionId()`
- ✅ `updateField()` - Uses `SchemaFormStateManager.updateField()`
- ✅ `flushField()` - Uses `state.fieldValues` instead of `state.current_values`
- ✅ `handleFormUpdated()` - Uses `state.fieldValues`
- ✅ `handleGetFormStateRequest()` - Uses `state.fieldValues`
- ✅ `getCompletionPercentage()` - Uses `SchemaFormStateManager.getProgress()`
- ✅ `reset()` - Uses `SchemaFormStateManager.clear()`

---

## Pending / Requires Refactoring ⚠️

### 1. Section-Switching Methods

The following methods reference properties that don't exist in `SchemaFormState`:
- `section_index` (old multi-section form metadata)
- `current_section` (replaced by `currentPartId`)
- `completed_sections` (replaced by `completedParts`)
- `full_schema` (just `schema` now)

**Methods Requiring Reimplementation:**

#### Backend Request Handlers
- `handlePrepareSectionSwitchRequest()` - Line ~570
  - **Issue:** References `section_index`, uses `WebFormStateManager.switchSection()`
  - **Solution:** Find part by order number, use `switchToPart()`

- `handleSwitchSectionRequest()` - Line ~525
  - **Status:** Stubbed out with TODO comment
  - **Solution:** Parse identifier, find part, call `switchToPart()`

- `handleGetFieldValueRequest()` - Line ~710
  - **Issue:** Uses `WebFormStateManager.getSpokenNameMap()`
  - **Solution:** Use `getPreviousSpokenNames()` + current part fields

- `handleCompleteSectionRequest()` - Line ~765
  - **Issue:** Uses `WebFormStateManager.completeSection()`
  - **Solution:** Use `markPartComplete()` or `switchToPart()`

#### Public Section Methods
- `startSection(sectionNumber)` - Line ~1235
  - **Issue:** Uses `section_index`, `switchSection()`, `getSpokenNameMap()`, `getSectionLabel()`
  - **Solution:** Map section_number to parts[].order, rebuild using parts

- `switchSection(target)` - Line ~1310
  - **Issue:** Uses `findSectionByLabel()`, `switchSection()`, `getSpokenNameMap()`, `getSectionLabel()`
  - **Solution:** Search parts by order/label, use `switchToPart()`

- `completeSection()` - Line ~1395
  - **Issue:** Uses `completeSection()`, `startSection()`
  - **Solution:** Use `mark PartComplete()` + `switchToPart()`

- `getCurrentSection()` - Line ~1425
  - **Issue:** Returns `state.current_section` (doesn't exist)
  - **Solution:** Get current part, return `part.order`

- `getCompletedSections()` - Line ~1432
  - **Issue:** Returns `state.completed_sections` (doesn't exist)
  - **Solution:** Map `completedParts` IDs to order numbers

### 2. Navigation Functions Compatibility

The navigation functions in `navigation.ts` expect `WebFormState`:
- `computeNextField(state: WebFormState)`
- `isFormComplete(state: WebFormState)`
- `getFieldOrder(state: WebFormState, fieldId: string)`

**Solution:** Update `navigation.ts` to accept `SchemaFormState` OR create adapter functions

---

## TypeScript Compilation Errors

Current errors (as of last check):
```
src/webFormConnection.ts(495,24): error TS2345: Argument of type 'SchemaFormState' is not assignable to parameter of type 'WebFormState'.
src/webFormConnection.ts(581,116): error TS2339: Property 'section_index' does not exist on type 'SchemaFormState'.
src/webFormConnection.ts(1429,23): error TS2339: Property 'current_section' does not exist on type 'SchemaFormState'.
src/webFormConnection.ts(1436,23): error TS2339: Property 'completed_sections' does not exist on type 'SchemaFormState'.
... (30+ errors total)
```

---

## Implementation Plan for Completion

### Step 1: Update Navigation Functions (1 hour)
Update `navigation.ts` to work with `SchemaFormState`:
- Change imports from `WebFormState` to `SchemaFormState`
- Update property references: `current_values` → `fieldValues`
- Test navigation logic still works

### Step 2: Implement Helper Methods (1 hour)
Add missing helper methods to `SchemaFormStateManager`:
```typescript
// Get field values for spoken name lookup
static getFieldBySpokenName(state: SchemaFormState, spokenName: string): string | null {
  // Search current + completed parts for field with matching spoken_name
}

// Get part label by order number
static getPartLabel(state: SchemaFormState, orderNumber: number): string {
  const part = state.schema.parts?.find(p => p.order === orderNumber);
  return part?.label || '';
}

// Find part by label
static findPartByLabel(state: SchemaFormState, label: string): string | null {
  const part = state.schema.parts?.find(p =>
    p.label.toLowerCase() === label.toLowerCase()
  );
  return part?.id || null;
}
```

### Step 3: Reimplement Section Methods (2-3 hours)
Rewrite each section method to use parts:

**Example: `switchSection()`**
```typescript
async switchSection(target: number | string, wsUrl: string): Promise<void> {
  let targetPartId: string;

  if (typeof target === 'number') {
    // Find part by order number
    const part = this.state.schema.parts?.find(p => p.order === target);
    if (!part) throw new Error(`Part with order ${target} not found`);
    targetPartId = part.id;
  } else {
    // Find by label or use as ID directly
    targetPartId = SchemaFormStateManager.findPartByLabel(this.state, target) || target;
  }

  await this.waitForBufferDrain(1000);
  this.setStatus('switching_section');

  // Switch to target part
  this.state = SchemaFormStateManager.switchToPart(this.state, targetPartId);

  // Build section info using parts
  const part = this.state.schema.parts?.find(p => p.id === targetPartId);
  const partSchema = SchemaFormStateManager.extractPartFields(this.state.schema, targetPartId);
  const previousSpokenNames = SchemaFormStateManager.getPreviousSpokenNames(this.state);

  // Send section switch (backend still uses section_number)
  this.send({
    type: "manual_section_switch",
    identifier: part?.order.toString(),
    section_info: {
      schema: partSchema,
      current_values: this.state.fieldValues,
      metadata: {
        section_number: part?.order,
        total_sections: this.state.schema.parts?.length || 1,
        section_label: part?.label || '',
        previous_spoken_names: previousSpokenNames,
      },
      initial_field_hint: this.computeNextFieldHintString(),
    },
  });
}
```

### Step 4: Testing (1 hour)
- Unit tests for updated methods
- Integration test with WebSocket backend
- Verify section switching works end-to-end

---

## Estimated Time to Complete

- **Navigation updates:** 1 hour
- **Helper methods:** 1 hour
- **Section method rewrites:** 2-3 hours
- **Testing & fixes:** 1 hour

**Total:** 5-6 hours

---

## Next Steps

1. Complete Phase 2 by implementing the pending section methods
2. OR proceed to Phase 3 (voice overlay) and circle back to section switching later
3. Document final decision in PROJECT_STATUS.md

---

## Files Modified

- ✅ `frontend/src/webFormConnection.ts` - Partial update (core methods complete, section methods pending)
- ⏳ `frontend/src/navigation.ts` - Needs update to use SchemaFormState
- ⏳ Helper methods need to be added to `SchemaFormStateManager`
