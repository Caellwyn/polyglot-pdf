/**
 * Unit tests for SchemaFormStateManager - Phase 1 WebSocket Integration
 *
 * Tests WebSocket-related functionality added in Phase 1:
 * - FieldValue wrapping/unwrapping
 * - Backwards compatibility migration
 * - WebSocket handshake payload generation
 * - Part extraction and spoken name collection
 * - State persistence (save/load)
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema, FieldValue } from '../types/schema'

describe('SchemaFormStateManager - Phase 1 WebSocket Integration', () => {
  let sessionStorageMock: { [key: string]: string }

  beforeEach(() => {
    // Mock sessionStorage
    sessionStorageMock = {}
    global.sessionStorage = {
      getItem: vi.fn((key: string) => sessionStorageMock[key] || null),
      setItem: vi.fn((key: string, value: string) => {
        sessionStorageMock[key] = value
      }),
      removeItem: vi.fn((key: string) => {
        delete sessionStorageMock[key]
      }),
      clear: vi.fn(() => {
        sessionStorageMock = {}
      }),
      length: 0,
      key: vi.fn(() => null)
    } as any
  })

  // ============================================================================
  // Test Schema Fixtures
  // ============================================================================

  const createTestSchema = (): FormSchema => ({
    source: 'pdf',
    form_metadata: {
      title: 'Test I-90 Form',
      version: '1.0.0',
      language: 'en',
      form_number: 'I-90',
      edition_date: '01/20/25',
      page_count: 5
    },
    parts: [
      {
        id: 'part-1',
        label: 'Personal Information',
        description: 'Basic information',
        order: 1,
        section_ids: ['section-1a', 'section-1b'],
        required: true
      },
      {
        id: 'part-2',
        label: 'Address Information',
        description: 'Contact details',
        order: 2,
        section_ids: ['section-2a'],
        required: true
      },
      {
        id: 'part-3',
        label: 'Additional Information',
        description: 'Extra details',
        order: 3,
        section_ids: ['section-3a'],
        required: false
      }
    ],
    sections: [
      {
        id: 'section-1a',
        label: 'Name',
        order: 1,
        fields: ['field-1', 'field-2']
      },
      {
        id: 'section-1b',
        label: 'Date of Birth',
        order: 2,
        fields: ['field-3']
      },
      {
        id: 'section-2a',
        label: 'Current Address',
        order: 3,
        fields: ['field-4', 'field-5']
      },
      {
        id: 'section-3a',
        label: 'Notes',
        order: 4,
        fields: ['field-6']
      }
    ],
    fields: [
      {
        id: 'field-1',
        name: 'Family Name (Last Name)',
        spoken_name: 'family name',
        spoken_aliases: ['last name', 'surname'],
        type: 'text',
        section_id: 'section-1a',
        validation: { required: true }
      },
      {
        id: 'field-2',
        name: 'Given Name (First Name)',
        spoken_name: 'given name',
        spoken_aliases: ['first name'],
        type: 'text',
        section_id: 'section-1a',
        validation: { required: true }
      },
      {
        id: 'field-3',
        name: 'Date of Birth',
        spoken_name: 'date of birth',
        spoken_aliases: ['birthday'],
        type: 'date',
        section_id: 'section-1b',
        validation: { required: true }
      },
      {
        id: 'field-4',
        name: 'Street Number and Name',
        spoken_name: 'street address',
        type: 'text',
        section_id: 'section-2a',
        validation: { required: true }
      },
      {
        id: 'field-5',
        name: 'City or Town',
        spoken_name: 'city',
        type: 'text',
        section_id: 'section-2a',
        validation: { required: true }
      },
      {
        id: 'field-6',
        name: 'Additional Notes',
        spoken_name: 'notes',
        type: 'textarea',
        section_id: 'section-3a',
        validation: { required: false }
      }
    ]
  })

  const createLegacySchema = (): FormSchema => ({
    source: 'web',
    form_metadata: {
      title: 'Legacy Web Form',
      version: '1.0.0',
      language: 'en'
    },
    sections: [
      {
        id: 'section-1',
        label: 'Contact Info',
        order: 1,
        fields: ['field-1', 'field-2']
      }
    ],
    fields: [
      {
        id: 'field-1',
        name: 'Name',
        spoken_name: 'name',
        type: 'text',
        section_id: 'section-1'
      },
      {
        id: 'field-2',
        name: 'Email',
        spoken_name: 'email',
        type: 'email',
        section_id: 'section-1'
      }
    ]
  })

  // ============================================================================
  // Test: FieldValue Wrapping in updateField()
  // ============================================================================

  describe('FieldValue Wrapping', () => {
    it('should wrap primitive values in FieldValue objects', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const updatedState = SchemaFormStateManager.updateField(
        state,
        'field-1',
        'Doe'
      )

      const fieldValue = updatedState.fieldValues['field-1'] as FieldValue
      expect(fieldValue).toBeDefined()
      expect(fieldValue.value).toBe('Doe')
      expect(fieldValue.lastModified).toBeDefined()
      expect(typeof fieldValue.lastModified).toBe('number')
    })

    it('should set confirmed flag when provided in options', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const updatedState = SchemaFormStateManager.updateField(
        state,
        'field-1',
        'Smith',
        { confirmed: true }
      )

      const fieldValue = updatedState.fieldValues['field-1'] as FieldValue
      expect(fieldValue.confirmed).toBe(true)
      expect(fieldValue.value).toBe('Smith')
    })

    it('should accept FieldValue objects directly', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const customFieldValue: FieldValue = {
        value: 'Johnson',
        confirmed: true,
        lastModified: 1234567890
      }

      const updatedState = SchemaFormStateManager.updateField(
        state,
        'field-1',
        customFieldValue
      )

      const fieldValue = updatedState.fieldValues['field-1'] as FieldValue
      expect(fieldValue).toEqual(customFieldValue)
    })

    it('should handle null and undefined values', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const updatedState1 = SchemaFormStateManager.updateField(
        state,
        'field-1',
        null
      )
      expect((updatedState1.fieldValues['field-1'] as FieldValue).value).toBeNull()

      const updatedState2 = SchemaFormStateManager.updateField(
        state,
        'field-1',
        undefined
      )
      expect((updatedState2.fieldValues['field-1'] as FieldValue).value).toBeUndefined()
    })
  })

  // ============================================================================
  // Test: Backwards Compatibility Migration
  // ============================================================================

  describe('Backwards Compatibility Migration', () => {
    it('should migrate currentSectionId to currentPartId on load', () => {
      const schema = createTestSchema()

      // Create old-style state
      const oldState = {
        schema,
        fieldValues: {},
        currentSectionId: 'part-2', // Old property name
        completedSections: ['part-1'], // Old property name (as array for JSON)
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(oldState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      expect(loadedState!.currentPartId).toBe('part-2')
      expect(loadedState!.currentSectionId).toBeUndefined()
      expect(loadedState!.completedParts).toBeInstanceOf(Set)
      expect(loadedState!.completedParts.has('part-1')).toBe(true)
    })

    it('should prefer currentPartId if both properties exist', () => {
      const schema = createTestSchema()

      // State with both old and new properties
      const mixedState = {
        schema,
        fieldValues: {},
        currentSectionId: 'part-1',
        currentPartId: 'part-2', // Should take precedence
        completedSections: ['part-1'],
        completedParts: ['part-2'],
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(mixedState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState!.currentPartId).toBe('part-2')
    })

    it('should convert completedSections array to completedParts Set', () => {
      const schema = createTestSchema()

      const oldState = {
        schema,
        fieldValues: {},
        currentPartId: 'part-2',
        completedSections: ['part-1'], // Old array format
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(oldState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState!.completedParts).toBeInstanceOf(Set)
      expect(loadedState!.completedParts.has('part-1')).toBe(true)
      expect(Array.from(loadedState!.completedParts)).toEqual(['part-1'])
    })
  })

  // ============================================================================
  // Test: getCurrentPartNumber()
  // ============================================================================

  describe('getCurrentPartNumber()', () => {
    it('should return the correct order value for current part', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // Should start with part-1 (order: 1)
      expect(SchemaFormStateManager.getCurrentPartNumber(state)).toBe(1)

      // Switch to part-2 (order: 2)
      const state2 = { ...state, currentPartId: 'part-2' }
      expect(SchemaFormStateManager.getCurrentPartNumber(state2)).toBe(2)

      // Switch to part-3 (order: 3)
      const state3 = { ...state, currentPartId: 'part-3' }
      expect(SchemaFormStateManager.getCurrentPartNumber(state3)).toBe(3)
    })

    it('should return 1 for schemas without parts', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      expect(SchemaFormStateManager.getCurrentPartNumber(state)).toBe(1)
    })

    it('should return 1 if current part not found', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)
      const invalidState = { ...state, currentPartId: 'non-existent-part' }

      expect(SchemaFormStateManager.getCurrentPartNumber(invalidState)).toBe(1)
    })
  })

  // ============================================================================
  // Test: getHandshakePayload()
  // ============================================================================

  describe('getHandshakePayload()', () => {
    it('should generate correct handshake payload structure', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state, 'English')

      expect(payload).toHaveProperty('schema')
      expect(payload).toHaveProperty('current_values')
      expect(payload).toHaveProperty('section_number')
      expect(payload).toHaveProperty('section_label')
      expect(payload).toHaveProperty('total_sections')
      expect(payload).toHaveProperty('previous_spoken_names')
      expect(payload).toHaveProperty('fill_language')
    })

    it('should use parts[].order as section_number', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // Part-1 has order: 1
      const payload1 = SchemaFormStateManager.getHandshakePayload(state)
      expect(payload1.section_number).toBe(1)

      // Switch to part-2 (order: 2)
      const state2 = { ...state, currentPartId: 'part-2' }
      const payload2 = SchemaFormStateManager.getHandshakePayload(state2)
      expect(payload2.section_number).toBe(2)

      // Switch to part-3 (order: 3)
      const state3 = { ...state, currentPartId: 'part-3' }
      const payload3 = SchemaFormStateManager.getHandshakePayload(state3)
      expect(payload3.section_number).toBe(3)
    })

    it('should include section_label from current part', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect(payload.section_label).toBe('Personal Information')
    })

    it('should include total_sections from parts.length', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect(payload.total_sections).toBe(3) // 3 parts in test schema
    })

    it('should include fill_language parameter', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payloadEnglish = SchemaFormStateManager.getHandshakePayload(state, 'English')
      expect(payloadEnglish.fill_language).toBe('English')

      const payloadSpanish = SchemaFormStateManager.getHandshakePayload(state, 'Spanish')
      expect(payloadSpanish.fill_language).toBe('Spanish')
    })

    it('should include current field values', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = SchemaFormStateManager.updateField(state, 'field-1', 'Doe')
      state = SchemaFormStateManager.updateField(state, 'field-2', 'John')

      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect(payload.current_values).toHaveProperty('field-1')
      expect(payload.current_values).toHaveProperty('field-2')
    })
  })

  // ============================================================================
  // Test: extractPartFields()
  // ============================================================================

  describe('extractPartFields()', () => {
    it('should extract schema with only fields from specified part', () => {
      const schema = createTestSchema()

      const partSchema = SchemaFormStateManager.extractPartFields(schema, 'part-1')

      // Part-1 has section-1a and section-1b with fields 1, 2, 3
      expect(partSchema.fields.length).toBe(3)
      expect(partSchema.fields.map(f => f.id)).toEqual(['field-1', 'field-2', 'field-3'])
    })

    it('should include only sections belonging to the part', () => {
      const schema = createTestSchema()

      const partSchema = SchemaFormStateManager.extractPartFields(schema, 'part-1')

      expect(partSchema.sections.length).toBe(2)
      expect(partSchema.sections.map(s => s.id)).toEqual(['section-1a', 'section-1b'])
    })

    it('should preserve form metadata', () => {
      const schema = createTestSchema()

      const partSchema = SchemaFormStateManager.extractPartFields(schema, 'part-2')

      expect(partSchema.form_metadata).toEqual(schema.form_metadata)
    })

    it('should handle part with single section', () => {
      const schema = createTestSchema()

      const partSchema = SchemaFormStateManager.extractPartFields(schema, 'part-2')

      // Part-2 has only section-2a with fields 4, 5
      expect(partSchema.sections.length).toBe(1)
      expect(partSchema.sections[0].id).toBe('section-2a')
      expect(partSchema.fields.length).toBe(2)
      expect(partSchema.fields.map(f => f.id)).toEqual(['field-4', 'field-5'])
    })

    it('should return empty fields/sections for non-existent part', () => {
      const schema = createTestSchema()

      const partSchema = SchemaFormStateManager.extractPartFields(schema, 'non-existent')

      expect(partSchema.fields.length).toBe(0)
      expect(partSchema.sections.length).toBe(0)
    })
  })

  // ============================================================================
  // Test: getPreviousSpokenNames()
  // ============================================================================

  describe('getPreviousSpokenNames()', () => {
    it('should collect spoken names from completed parts only', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      // Complete part-1 and move to part-2
      state = { ...state, completedParts: new Set(['part-1']), currentPartId: 'part-2' }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      // Part-1 has fields 1, 2, 3 with spoken names
      expect(spokenNames).toContain('family name')
      expect(spokenNames).toContain('given name')
      expect(spokenNames).toContain('date of birth')

      // Should NOT contain fields from part-2 or part-3
      expect(spokenNames).not.toContain('street address')
      expect(spokenNames).not.toContain('city')
      expect(spokenNames).not.toContain('notes')
    })

    it('should include spoken aliases', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = { ...state, completedParts: new Set(['part-1']), currentPartId: 'part-2' }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      // Field-1 has aliases
      expect(spokenNames).toContain('last name')
      expect(spokenNames).toContain('surname')

      // Field-2 has alias
      expect(spokenNames).toContain('first name')

      // Field-3 has alias
      expect(spokenNames).toContain('birthday')
    })

    it('should return empty array when no parts completed', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      expect(spokenNames).toEqual([])
    })

    it('should handle multiple completed parts', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      // Complete part-1 and part-2, now on part-3
      state = {
        ...state,
        completedParts: new Set(['part-1', 'part-2']),
        currentPartId: 'part-3'
      }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      // Should have all fields from part-1 and part-2
      expect(spokenNames).toContain('family name')
      expect(spokenNames).toContain('given name')
      expect(spokenNames).toContain('date of birth')
      expect(spokenNames).toContain('street address')
      expect(spokenNames).toContain('city')

      // Should NOT contain part-3 fields
      expect(spokenNames).not.toContain('notes')
    })
  })

  // ============================================================================
  // Test: switchToPart()
  // ============================================================================

  describe('switchToPart()', () => {
    it('should mark current part as completed and switch to next part', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.switchToPart(state, 'part-2')

      expect(newState.currentPartId).toBe('part-2')
      expect(newState.completedParts.has('part-1')).toBe(true)
    })

    it('should allow switching to any part by ID', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.switchToPart(state, 'part-3')

      expect(newState.currentPartId).toBe('part-3')
      expect(newState.completedParts.has('part-1')).toBe(true)
    })

    it('should not mark part as completed if switching to same part', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.switchToPart(state, 'part-1')

      expect(newState.currentPartId).toBe('part-1')
      expect(newState.completedParts.has('part-1')).toBe(false)
    })
  })

  // ============================================================================
  // Test: setSessionId()
  // ============================================================================

  describe('setSessionId()', () => {
    it('should set sessionId in state', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.setSessionId(state, 'session-123')

      expect(newState.sessionId).toBe('session-123')
    })

    it('should preserve other state properties', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'Test')

      const newState = SchemaFormStateManager.setSessionId(state, 'session-456')

      expect(newState.sessionId).toBe('session-456')
      expect(newState.fieldValues['field-1']).toBeDefined()
      expect(newState.currentPartId).toBe(state.currentPartId)
    })
  })

  // ============================================================================
  // Test: Save/Load Round-trip with FieldValue Objects
  // ============================================================================

  describe('Save/Load Persistence', () => {
    it('should persist FieldValue objects correctly', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = SchemaFormStateManager.updateField(state, 'field-1', 'Doe', { confirmed: true })
      state = SchemaFormStateManager.updateField(state, 'field-2', 'John')

      SchemaFormStateManager.save(state)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      const field1 = loadedState!.fieldValues['field-1'] as FieldValue
      const field2 = loadedState!.fieldValues['field-2'] as FieldValue

      expect(field1.value).toBe('Doe')
      expect(field1.confirmed).toBe(true)
      expect(field2.value).toBe('John')
    })

    it('should preserve completedParts Set across save/load', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = SchemaFormStateManager.switchToPart(state, 'part-2')
      state = SchemaFormStateManager.switchToPart(state, 'part-3')

      SchemaFormStateManager.save(state)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      expect(loadedState!.completedParts).toBeInstanceOf(Set)
      expect(loadedState!.completedParts.has('part-1')).toBe(true)
      expect(loadedState!.completedParts.has('part-2')).toBe(true)
    })

    it('should preserve sessionId across save/load', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = SchemaFormStateManager.setSessionId(state, 'session-789')

      SchemaFormStateManager.save(state)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      expect(loadedState!.sessionId).toBe('session-789')
    })
  })

  // ============================================================================
  // Test: Schemas Without Parts (Fallback Behavior)
  // ============================================================================

  describe('Schemas Without Parts (Legacy Support)', () => {
    it('should handle schemas without parts array', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      expect(state.currentPartId).toBe('section-1')
      expect(state.schema).toBeDefined()
    })

    it('should return section_number=1 for schemas without parts', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)

      expect(payload.section_number).toBe(1)
      expect(payload.total_sections).toBe(1)
    })

    it('should extract all fields for schemas without parts', () => {
      const schema = createLegacySchema()

      const extracted = SchemaFormStateManager.extractPartFields(schema, 'section-1')

      expect(extracted.fields.length).toBe(2)
      expect(extracted.sections.length).toBe(1)
    })
  })

  // ============================================================================
  // Test: Edge Cases and Error Handling
  // ============================================================================

  describe('Edge Cases', () => {
    it('should handle empty schema gracefully', () => {
      const emptySchema: FormSchema = {
        source: 'pdf',
        form_metadata: {
          title: 'Empty',
          version: '1.0',
          language: 'en'
        },
        sections: [],
        fields: []
      }

      const state = SchemaFormStateManager.init(emptySchema)

      expect(state.currentPartId).toBe('')
      expect(state.fieldValues).toEqual({})
    })

    it('should handle field update for non-existent field', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.updateField(
        state,
        'non-existent-field',
        'value'
      )

      expect(newState.fieldValues['non-existent-field']).toBeDefined()
      expect((newState.fieldValues['non-existent-field'] as FieldValue).value).toBe('value')
    })

    it('should return null when loading from empty sessionStorage', () => {
      const loaded = SchemaFormStateManager.load()

      expect(loaded).toBeNull()
    })

    it('should handle corrupted sessionStorage data', () => {
      sessionStorageMock['schema_form_state'] = 'invalid json{'

      const loaded = SchemaFormStateManager.load()

      expect(loaded).toBeNull()
    })
  })

  // ============================================================================
  // Phase 3: JIT Schema Loading Tests
  // ============================================================================

  describe('JIT Schema Loading - State Tracking', () => {
    const testSchema = createTestSchema()

    it('should initialize with empty loadedFieldIds Set', () => {
      const state = SchemaFormStateManager.init(testSchema)

      expect(state.loadedFieldIds).toBeInstanceOf(Set)
      expect(state.loadedFieldIds.size).toBe(0)
    })

    it('should initialize with jitModeEnabled false', () => {
      const state = SchemaFormStateManager.init(testSchema)

      expect(state.jitModeEnabled).toBe(false)
    })

    it('should mark field schema as loaded', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(state.loadedFieldIds.has('firstName')).toBe(true)
      expect(state.loadedFieldIds.size).toBe(1)
    })

    it('should track multiple loaded fields', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'email')

      expect(state.loadedFieldIds.size).toBe(3)
      expect(state.loadedFieldIds.has('firstName')).toBe(true)
      expect(state.loadedFieldIds.has('lastName')).toBe(true)
      expect(state.loadedFieldIds.has('email')).toBe(true)
    })

    it('should not duplicate field IDs in loadedFieldIds', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(state.loadedFieldIds.size).toBe(1)
    })

    it('should check if field schema is loaded', () => {
      let state = SchemaFormStateManager.init(testSchema)

      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'firstName')).toBe(false)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'firstName')).toBe(true)
      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'lastName')).toBe(false)
    })

    it('should enable JIT mode', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.setJitMode(state, true)

      expect(state.jitModeEnabled).toBe(true)
    })

    it('should disable JIT mode', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.setJitMode(state, true)

      state = SchemaFormStateManager.setJitMode(state, false)

      expect(state.jitModeEnabled).toBe(false)
    })

    it('should clear loaded field IDs', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')

      state = SchemaFormStateManager.clearLoadedFieldIds(state)

      expect(state.loadedFieldIds.size).toBe(0)
    })

    it('should serialize loadedFieldIds to array for storage', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')

      SchemaFormStateManager.save(state)

      const stored = JSON.parse(sessionStorageMock['schema_form_state'])
      expect(Array.isArray(stored.loadedFieldIds)).toBe(true)
      expect(stored.loadedFieldIds).toContain('firstName')
      expect(stored.loadedFieldIds).toContain('lastName')
    })

    it('should deserialize loadedFieldIds array to Set on load', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')
      SchemaFormStateManager.save(state)

      const loaded = SchemaFormStateManager.load()

      expect(loaded).not.toBeNull()
      expect(loaded!.loadedFieldIds).toBeInstanceOf(Set)
      expect(loaded!.loadedFieldIds.size).toBe(2)
      expect(loaded!.loadedFieldIds.has('firstName')).toBe(true)
      expect(loaded!.loadedFieldIds.has('lastName')).toBe(true)
    })

    it('should handle old state without loadedFieldIds', () => {
      // Simulate old state saved before JIT feature
      const oldState = {
        schema: testSchema,
        fieldValues: {},
        currentPartId: 'part-1',
        completedParts: [],
        validationErrors: {},
        lastUpdated: Date.now()
      }
      sessionStorageMock['schema_form_state'] = JSON.stringify(oldState)

      const loaded = SchemaFormStateManager.load()

      expect(loaded).not.toBeNull()
      expect(loaded!.loadedFieldIds).toBeInstanceOf(Set)
      expect(loaded!.loadedFieldIds.size).toBe(0)
      expect(loaded!.jitModeEnabled).toBe(false)
    })

    it('should preserve loadedFieldIds across save/load cycles', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'field1')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'field2')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'field3')
      state = SchemaFormStateManager.setJitMode(state, true)

      SchemaFormStateManager.save(state)
      const loaded = SchemaFormStateManager.load()

      expect(loaded).not.toBeNull()
      expect(loaded!.loadedFieldIds.size).toBe(3)
      expect(loaded!.loadedFieldIds.has('field1')).toBe(true)
      expect(loaded!.loadedFieldIds.has('field2')).toBe(true)
      expect(loaded!.loadedFieldIds.has('field3')).toBe(true)
      expect(loaded!.jitModeEnabled).toBe(true)
    })
  })
})
