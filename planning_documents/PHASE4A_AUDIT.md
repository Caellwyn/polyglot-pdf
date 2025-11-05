# Phase 4A Audit - Voice Overlay Dependencies

**Date**: November 5, 2025  
**Status**: Complete  
**Files Analyzed**: 3 files (VoiceOverlay.tsx, VoiceOverlayMobile.tsx, connection.ts)

---

## Summary

Found **61 references** across 3 files that need updates:
- **VoiceOverlay.tsx**: 30 changes needed
- **VoiceOverlayMobile.tsx**: 24 changes needed  
- **connection.ts**: 7 changes needed

---

## VoiceOverlay.tsx - 30 Changes Required

### Category 1: Import Statements (3 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 21 | `import { WebFormStateManager, ... }` | `import { SchemaFormStateManager, ... }` |
| 21 | `type FormSchema` from `../webFormState` | `type FormSchema` from `../schema-forms/types/schema` |
| 21 | `type SectionIndex` | **REMOVE** (not needed) |

### Category 2: Props Interface (1 change)
| Line | Current | Change To |
|------|---------|-----------|
| 29 | `sectionIndex: SectionIndex` | **REMOVE** entire prop |
| 40 | Function signature includes `sectionIndex` | **REMOVE** from destructure |

### Category 3: State Variables (2 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 46 | `currentSection` (number) | `currentPartId` (string) |
| 47 | `completedSections: Set<number>` | `completedParts: Set<string>` |

### Category 4: Connection Manager Init (2 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 209 | `WebFormStateManager.initWithSections(schema, sectionIndex)` | `SchemaFormStateManager.init(schema)` |
| 235 | Dependency: `[schema, sectionIndex, ...]` | `[schema, ...]` (remove sectionIndex) |

### Category 5: Field Count Logic (6 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 510 | `WebFormStateManager.initWithSections(schema, sectionIndex)` | `SchemaFormStateManager.init(schema)` |
| 511 | `setCurrentSection(state.current_section \|\| 1)` | `setCurrentPartId(state.currentPartId \|\| schema.parts?.[0]?.id \|\| '')` |
| 512 | `setCompletedSections(state.completed_sections \|\| new Set())` | `setCompletedParts(state.completedParts \|\| new Set())` |
| 515 | `WebFormStateManager.getSectionFieldCount(state)` | `SchemaFormStateManager.getProgress(state)` then extract fields |
| 517 | Dependency: `[schema, sectionIndex]` | `[schema]` |
| 524 | `WebFormStateManager.getSectionFieldCount(state)` | `SchemaFormStateManager.getProgress(state)` |

### Category 6: State Sync Logic (8 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 522 | `WebFormStateManager.load()` | `SchemaFormStateManager.load()` |
| 528 | `if (state.current_section && state.current_section !== currentSection)` | `if (state.currentPartId && state.currentPartId !== currentPartId)` |
| 529 | `setCurrentSection(state.current_section)` | `setCurrentPartId(state.currentPartId)` |
| 534 | `const currentCompleted = new Set(Array.from(completedSections))` | `const currentCompleted = new Set(Array.from(completedParts))` |
| 540 | `setCompletedSections(newCompleted)` | `setCompletedParts(newCompleted)` |
| 547 | Dependency: `[currentSection, completedSections]` | `[currentPartId, completedParts]` |
| 560 | `WebFormStateManager.load()` | `SchemaFormStateManager.load()` |
| 588 | `WebFormStateManager.clear()` | `SchemaFormStateManager.clear()` |

### Category 7: Section Dropdown UI (8 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 756 | `Section {currentSection} of {sectionIndex.total_sections}` | `Part {getCurrentPartOrder()} of {schema.parts?.length \|\| 0}` |
| 756 | `{sectionIndex.sections[currentSection - 1]?.section_label}` | `{getCurrentPartLabel()}` |
| 765 | `{sectionIndex.sections.map((section) => ...)}` | `{schema.parts?.map((part) => ...) \|\| []}` |
| 768 | `section.section_number === currentSection` | `part.id === currentPartId` |
| 775 | `if (section.section_number === currentSection)` | `if (part.id === currentPartId)` |
| 783 | `setCurrentSection(section.section_number)` | `setCurrentPartId(part.id)` |
| 787 | `WebFormStateManager.load()` | `SchemaFormStateManager.load()` |
| 790-791 | `WebFormStateManager.switchSection()` + `getSectionFieldCount()` | `SchemaFormStateManager.switchToPart()` + `getProgress()` |
| 804-805 | `completedSections.has(section.section_number)` | `completedParts.has(part.id)` |

---

## VoiceOverlayMobile.tsx - 24 Changes Required

**Same pattern as VoiceOverlay.tsx** (synchronized changes):

### Category 1: Import Statements (3 changes)
Same as desktop (lines 13, 13, 13)

### Category 2: Props Interface (1 change)
Same as desktop (lines 21, 31)

### Category 3: State Variables (2 changes)
Similar to desktop (currentSection → currentPartId, completedSections → completedParts)

### Category 4: Connection Manager Init (2 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 192 | `WebFormStateManager.initWithSections(schema, sectionIndex)` | `SchemaFormStateManager.init(schema)` |
| 218 | Dependency: `[schema, sectionIndex, ...]` | `[schema, ...]` |

### Category 5: Field Count Logic (6 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 464 | `WebFormStateManager.initWithSections(schema, sectionIndex)` | `SchemaFormStateManager.init(schema)` |
| 469 | `WebFormStateManager.getSectionFieldCount(state)` | `SchemaFormStateManager.getProgress(state)` |
| 471 | Dependency: `[schema, sectionIndex]` | `[schema]` |
| 476 | `WebFormStateManager.load()` | `SchemaFormStateManager.load()` |
| 478 | `WebFormStateManager.getSectionFieldCount(state)` | `SchemaFormStateManager.getProgress(state)` |

### Category 6: State Sync Logic (10+ changes)
Similar pattern to desktop - sync currentPartId and completedParts with sessionStorage

---

## connection.ts - 7 Changes Required

### Import Statement (1 change)
| Line | Current | Change To |
|------|---------|-----------|
| 17 | `type FormSchema` from `../webFormState` | `type FormSchema` from `../schema-forms/types/schema` |
| 19 | `import { WebFormStateManager }` | `import { SchemaFormStateManager }` from `../schema-forms/state/schemaFormState` |

### State Manager Calls (4 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 182 | `WebFormStateManager.init(schema)` | `SchemaFormStateManager.init(schema)` |
| 203 | `WebFormStateManager.updateFieldValue(...)` | `SchemaFormStateManager.updateFieldValue(...)` |
| 340 | `WebFormStateManager.updateFieldValue(...)` | `SchemaFormStateManager.updateFieldValue(...)` |

### Method Signatures (2 changes)
| Line | Current | Change To |
|------|---------|-----------|
| 47-51 | Section methods use section_number (number) | Update to use part order or part ID |

---

## Helper Functions Needed

We'll need to add these helper functions to both VoiceOverlay files:

```typescript
/**
 * Get current part order number (1-indexed) from currentPartId
 */
function getCurrentPartOrder(): number {
  if (!schema.parts || !currentPartId) return 0
  const part = schema.parts.find(p => p.id === currentPartId)
  return part?.order ?? 0
}

/**
 * Get current part label from currentPartId
 */
function getCurrentPartLabel(): string {
  if (!schema.parts || !currentPartId) return ''
  const part = schema.parts.find(p => p.id === currentPartId)
  return part?.label ?? ''
}

/**
 * Get part ID from order number (for backwards compat with connection manager)
 */
function getPartIdFromOrder(order: number): string | undefined {
  if (!schema.parts) return undefined
  const part = schema.parts.find(p => p.order === order)
  return part?.id
}
```

---

## Testing Strategy

### Unit Tests Needed

1. **Test VoiceOverlay prop changes**:
   - ✅ Accepts schema without sectionIndex
   - ✅ Initializes with first part from schema.parts
   - ✅ Tracks currentPartId as string, not number

2. **Test state initialization**:
   - ✅ `SchemaFormStateManager.init()` called correctly
   - ✅ currentPartId set to first part
   - ✅ completedParts initialized as empty Set<string>

3. **Test field count extraction**:
   - ✅ `getProgress()` returns {filledFields, totalFields}
   - ✅ Progress correctly calculated from SchemaFormState

4. **Test section dropdown**:
   - ✅ Maps schema.parts correctly
   - ✅ Shows part.label and part.order
   - ✅ Highlights current part
   - ✅ Shows completion checkmarks for completed parts

5. **Test part switching**:
   - ✅ Updates currentPartId
   - ✅ Calls SchemaFormStateManager.switchToPart()
   - ✅ Updates field count after switch

6. **Test state persistence**:
   - ✅ Loads state from sessionStorage correctly
   - ✅ Syncs currentPartId with loaded state
   - ✅ Syncs completedParts with loaded state

7. **Test clear functionality**:
   - ✅ Calls SchemaFormStateManager.clear()
   - ✅ Resets to first part

### Integration Tests Needed

1. **Connection manager integration**:
   - ✅ ConnectionManager created with schema (no sectionIndex)
   - ✅ Part switching propagates to backend
   - ✅ Section methods handle part IDs correctly

2. **WebSocket handshake**:
   - ✅ Handshake includes current part order as section_number
   - ✅ Backend receives correct part metadata

3. **State sync**:
   - ✅ Manual part changes sync with overlay
   - ✅ Backend-driven part changes update overlay

---

## Risk Assessment

### High Risk
- ❌ Section dropdown mapping - complex JSX changes
- ❌ State sync logic - timing sensitive

### Medium Risk
- ⚠️ Connection manager methods - section_number vs part ID confusion
- ⚠️ Helper function edge cases - null/undefined checks

### Low Risk
- ✅ Import statements - straightforward
- ✅ Simple state variable renames - low impact

---

## Execution Order

1. ✅ **First**: Update connection.ts (foundation)
2. ✅ **Second**: Update VoiceOverlay.tsx (desktop)
3. ✅ **Third**: Update VoiceOverlayMobile.tsx (copy changes from desktop)
4. ✅ **Fourth**: Write unit tests
5. ✅ **Fifth**: Write integration tests
6. ✅ **Sixth**: Manual testing

---

**Next Step**: Start with connection.ts updates, then proceed to VoiceOverlay.tsx
