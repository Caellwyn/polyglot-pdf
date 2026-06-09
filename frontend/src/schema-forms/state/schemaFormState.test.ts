/**
 * Unit tests for SchemaFormStateManager.
 *
 * Spec-derived (bd polyglot-pdf-uov.4): asserts the DOCUMENTED section-based
 * behavior of the state manager, not whatever the old part-based test happened
 * to assert. Navigation is by SECTION (the old "part" API was renamed); the
 * back-compat migration runs currentPartId -> currentSectionId (NOT the reverse,
 * which the pre-refactor test wrongly asserted). See
 * docs/components/schema-forms.md for the contract this pins.
 *
 * Covered: FieldValue wrapping, the real legacy-key migration on load(),
 * getCurrentSectionNumber, getHandshakePayload (section-scoped), section
 * extraction, previous-spoken-name collection over completed sections,
 * switchToSection, setSessionId, save/load round-trip, JIT tracking, edges.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { SchemaFormStateManager } from './schemaFormState'
import type { FormSchema, FieldValue } from '../types/schema'

describe('SchemaFormStateManager', () => {
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
    // parts[] is optional/legacy grouping metadata. Navigation is section-based;
    // it is kept here only to prove the manager ignores it for nav + handshake.
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
  // init() seeds the first section
  // ============================================================================

  describe('init()', () => {
    it('seeds currentSectionId to the lowest-order section', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      // getFirstSection sorts by order; section-1a has order 1.
      expect(state.currentSectionId).toBe('section-1a')
      expect(state.completedSections).toBeInstanceOf(Set)
      expect(state.completedSections.size).toBe(0)
      expect(state.fieldValues).toEqual({})
      // formSessionId is the persistent fss_ id (durability boundary).
      expect(state.formSessionId).toMatch(/^fss_/)
    })
  })

  // ============================================================================
  // FieldValue wrapping in updateField()
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
  // Backwards-compatibility migration on load()
  //
  // The REAL migration direction (source load()): the old part-keyed state
  // (currentPartId / completedParts) is migrated FORWARD to the section keys
  // (currentSectionId / completedSections). The pre-refactor test asserted the
  // reverse and was wrong.
  // ============================================================================

  describe('Backwards Compatibility Migration', () => {
    it('migrates currentPartId -> currentSectionId on load', () => {
      const schema = createTestSchema()

      // Old-style state keyed on the legacy part fields.
      const oldState = {
        schema,
        fieldValues: {},
        currentPartId: 'section-2a',     // legacy key
        completedParts: ['section-1a'],  // legacy key (array form in JSON)
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(oldState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      expect(loadedState!.currentSectionId).toBe('section-2a')
      // currentPartId is consumed and removed.
      expect((loadedState as any).currentPartId).toBeUndefined()
      expect(loadedState!.completedSections).toBeInstanceOf(Set)
      expect(loadedState!.completedSections.has('section-1a')).toBe(true)
    })

    it('prefers an existing currentSectionId over the legacy currentPartId', () => {
      const schema = createTestSchema()

      // Both keys present: the new key wins; the migration only fills a MISSING
      // currentSectionId (source: `if (parsed.currentPartId && !parsed.currentSectionId)`).
      const mixedState = {
        schema,
        fieldValues: {},
        currentSectionId: 'section-1a',
        currentPartId: 'section-2a',
        completedSections: ['section-1a'],
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(mixedState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState!.currentSectionId).toBe('section-1a')
    })

    it('converts a legacy completedParts array to a completedSections Set', () => {
      const schema = createTestSchema()

      const oldState = {
        schema,
        fieldValues: {},
        currentPartId: 'section-2a',
        completedParts: ['section-1a'],  // legacy array, no completedSections
        validationErrors: {},
        lastUpdated: Date.now()
      }

      sessionStorageMock['schema_form_state'] = JSON.stringify(oldState)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState!.completedSections).toBeInstanceOf(Set)
      expect(loadedState!.completedSections.has('section-1a')).toBe(true)
      expect(Array.from(loadedState!.completedSections)).toEqual(['section-1a'])
    })
  })

  // ============================================================================
  // getCurrentSectionNumber()
  // ============================================================================

  describe('getCurrentSectionNumber()', () => {
    it('returns the current section order value', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // Seeded on section-1a (order 1).
      expect(SchemaFormStateManager.getCurrentSectionNumber(state)).toBe(1)

      const onB = { ...state, currentSectionId: 'section-1b' } // order 2
      expect(SchemaFormStateManager.getCurrentSectionNumber(onB)).toBe(2)

      const on2a = { ...state, currentSectionId: 'section-2a' } // order 3
      expect(SchemaFormStateManager.getCurrentSectionNumber(on2a)).toBe(3)
    })

    it('returns 1 for a single-section legacy schema', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      expect(SchemaFormStateManager.getCurrentSectionNumber(state)).toBe(1)
    })

    it('returns 1 when the current section is not found', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)
      const invalidState = { ...state, currentSectionId: 'non-existent-section' }

      expect(SchemaFormStateManager.getCurrentSectionNumber(invalidState)).toBe(1)
    })
  })

  // ============================================================================
  // getHandshakePayload() -- section-scoped (NOT parts)
  // ============================================================================

  describe('getHandshakePayload()', () => {
    it('generates the expected payload shape', () => {
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
      expect(payload).toHaveProperty('form_session_id')
    })

    it('uses the current SECTION order as section_number', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // Seeded on section-1a (order 1).
      expect(SchemaFormStateManager.getHandshakePayload(state).section_number).toBe(1)

      const on1b = { ...state, currentSectionId: 'section-1b' } // order 2
      expect(SchemaFormStateManager.getHandshakePayload(on1b).section_number).toBe(2)

      const on2a = { ...state, currentSectionId: 'section-2a' } // order 3
      expect(SchemaFormStateManager.getHandshakePayload(on2a).section_number).toBe(3)
    })

    it('uses the current SECTION label as section_label', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // section-1a label is 'Name' (NOT the part-1 label 'Personal Information').
      expect(SchemaFormStateManager.getHandshakePayload(state).section_label).toBe('Name')
    })

    it('uses sections.length as total_sections', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // 4 sections in the fixture (NOT 3 parts).
      expect(SchemaFormStateManager.getHandshakePayload(state).total_sections).toBe(4)
    })

    it('passes fill_language through', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      expect(SchemaFormStateManager.getHandshakePayload(state, 'English').fill_language).toBe('English')
      expect(SchemaFormStateManager.getHandshakePayload(state, 'Spanish').fill_language).toBe('Spanish')
    })

    it('includes the current field values', () => {
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
  // extractSectionFields()
  // ============================================================================

  describe('extractSectionFields()', () => {
    it('extracts only the fields belonging to the section', () => {
      const schema = createTestSchema()

      const sectionSchema = SchemaFormStateManager.extractSectionFields(schema, 'section-1a')

      // section-1a holds field-1, field-2.
      expect(sectionSchema.fields.map(f => f.id)).toEqual(['field-1', 'field-2'])
    })

    it('returns just the one requested section', () => {
      const schema = createTestSchema()

      const sectionSchema = SchemaFormStateManager.extractSectionFields(schema, 'section-1a')

      expect(sectionSchema.sections.length).toBe(1)
      expect(sectionSchema.sections[0].id).toBe('section-1a')
    })

    it('preserves form metadata', () => {
      const schema = createTestSchema()

      const sectionSchema = SchemaFormStateManager.extractSectionFields(schema, 'section-2a')

      expect(sectionSchema.form_metadata).toEqual(schema.form_metadata)
    })

    it('extracts a multi-field section', () => {
      const schema = createTestSchema()

      // section-2a holds field-4, field-5.
      const sectionSchema = SchemaFormStateManager.extractSectionFields(schema, 'section-2a')

      expect(sectionSchema.sections.length).toBe(1)
      expect(sectionSchema.sections[0].id).toBe('section-2a')
      expect(sectionSchema.fields.map(f => f.id)).toEqual(['field-4', 'field-5'])
    })

    it('returns empty fields/sections for a non-existent section', () => {
      const schema = createTestSchema()

      const sectionSchema = SchemaFormStateManager.extractSectionFields(schema, 'non-existent')

      expect(sectionSchema.fields.length).toBe(0)
      expect(sectionSchema.sections.length).toBe(0)
    })
  })

  // ============================================================================
  // getPreviousSpokenNames() -- over completed SECTIONS
  // ============================================================================

  describe('getPreviousSpokenNames()', () => {
    it('collects spoken names from completed sections only', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      // Completed section-1a (fields 1,2); now on section-1b.
      state = { ...state, completedSections: new Set(['section-1a']), currentSectionId: 'section-1b' }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      expect(spokenNames).toContain('family name')
      expect(spokenNames).toContain('given name')

      // Nothing from sections not yet completed.
      expect(spokenNames).not.toContain('date of birth')
      expect(spokenNames).not.toContain('street address')
      expect(spokenNames).not.toContain('notes')
    })

    it('includes spoken aliases', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      state = { ...state, completedSections: new Set(['section-1a']), currentSectionId: 'section-1b' }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      // field-1 aliases
      expect(spokenNames).toContain('last name')
      expect(spokenNames).toContain('surname')
      // field-2 alias
      expect(spokenNames).toContain('first name')
    })

    it('returns an empty array when no section is completed', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      expect(SchemaFormStateManager.getPreviousSpokenNames(state)).toEqual([])
    })

    it('handles multiple completed sections', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)

      // Completed section-1a (1,2) and section-2a (4,5); now on section-3a.
      state = {
        ...state,
        completedSections: new Set(['section-1a', 'section-2a']),
        currentSectionId: 'section-3a'
      }

      const spokenNames = SchemaFormStateManager.getPreviousSpokenNames(state)

      expect(spokenNames).toContain('family name')
      expect(spokenNames).toContain('given name')
      expect(spokenNames).toContain('street address')
      expect(spokenNames).toContain('city')

      // section-3a (field-6 'notes') is current, not completed.
      expect(spokenNames).not.toContain('notes')
    })
  })

  // ============================================================================
  // switchToSection()
  // ============================================================================

  describe('switchToSection()', () => {
    it('marks the current section completed and switches to the target', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema) // on section-1a

      const newState = SchemaFormStateManager.switchToSection(state, 'section-2a')

      expect(newState.currentSectionId).toBe('section-2a')
      expect(newState.completedSections.has('section-1a')).toBe(true)
    })

    it('switches to any section by id, completing the one left behind', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema) // on section-1a

      const newState = SchemaFormStateManager.switchToSection(state, 'section-3a')

      expect(newState.currentSectionId).toBe('section-3a')
      expect(newState.completedSections.has('section-1a')).toBe(true)
    })

    it('does not mark complete when switching to the same section', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema) // on section-1a

      const newState = SchemaFormStateManager.switchToSection(state, 'section-1a')

      expect(newState.currentSectionId).toBe('section-1a')
      expect(newState.completedSections.has('section-1a')).toBe(false)
    })
  })

  // ============================================================================
  // setSessionId()
  // ============================================================================

  describe('setSessionId()', () => {
    it('sets sessionId in state', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const newState = SchemaFormStateManager.setSessionId(state, 'session-123')

      expect(newState.sessionId).toBe('session-123')
    })

    it('preserves other state properties', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'Test')

      const newState = SchemaFormStateManager.setSessionId(state, 'session-456')

      expect(newState.sessionId).toBe('session-456')
      expect(newState.fieldValues['field-1']).toBeDefined()
      expect(newState.currentSectionId).toBe(state.currentSectionId)
    })
  })

  // ============================================================================
  // Save/Load round-trip
  // ============================================================================

  describe('Save/Load Persistence', () => {
    it('persists FieldValue objects correctly', () => {
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

    it('preserves the completedSections Set across save/load', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema) // on section-1a

      state = SchemaFormStateManager.switchToSection(state, 'section-1b') // completes 1a
      state = SchemaFormStateManager.switchToSection(state, 'section-2a') // completes 1b

      SchemaFormStateManager.save(state)

      const loadedState = SchemaFormStateManager.load()

      expect(loadedState).not.toBeNull()
      expect(loadedState!.completedSections).toBeInstanceOf(Set)
      expect(loadedState!.completedSections.has('section-1a')).toBe(true)
      expect(loadedState!.completedSections.has('section-1b')).toBe(true)
    })

    it('preserves sessionId across save/load', () => {
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
  // Single-section (legacy) schema behavior
  // ============================================================================

  describe('Single-section schema', () => {
    it('seeds currentSectionId to the only section', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      expect(state.currentSectionId).toBe('section-1')
      expect(state.schema).toBeDefined()
    })

    it('reports section_number=1 and total_sections=1', () => {
      const schema = createLegacySchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)

      expect(payload.section_number).toBe(1)
      expect(payload.total_sections).toBe(1)
    })

    it('extracts all fields of the lone section', () => {
      const schema = createLegacySchema()

      const extracted = SchemaFormStateManager.extractSectionFields(schema, 'section-1')

      expect(extracted.fields.length).toBe(2)
      expect(extracted.sections.length).toBe(1)
    })
  })

  // ============================================================================
  // Edge cases
  // ============================================================================

  describe('Edge Cases', () => {
    it('handles an empty schema gracefully', () => {
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

      // No section to seed -> empty currentSectionId.
      expect(state.currentSectionId).toBe('')
      expect(state.fieldValues).toEqual({})
    })

    it('stores an update for a non-existent field id (no schema gate)', () => {
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

    it('returns null when loading from empty sessionStorage', () => {
      expect(SchemaFormStateManager.load()).toBeNull()
    })

    it('returns null on corrupted sessionStorage data', () => {
      sessionStorageMock['schema_form_state'] = 'invalid json{'

      expect(SchemaFormStateManager.load()).toBeNull()
    })
  })

  // ============================================================================
  // JIT schema-loading state tracking (Phase 3)
  // ============================================================================

  describe('JIT Schema Loading - State Tracking', () => {
    const testSchema = createTestSchema()

    it('initializes with an empty loadedFieldIds Set', () => {
      const state = SchemaFormStateManager.init(testSchema)

      expect(state.loadedFieldIds).toBeInstanceOf(Set)
      expect(state.loadedFieldIds.size).toBe(0)
    })

    it('initializes with jitModeEnabled false', () => {
      const state = SchemaFormStateManager.init(testSchema)

      expect(state.jitModeEnabled).toBe(false)
    })

    it('marks a field schema as loaded', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(state.loadedFieldIds.has('firstName')).toBe(true)
      expect(state.loadedFieldIds.size).toBe(1)
    })

    it('tracks multiple loaded fields', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'email')

      expect(state.loadedFieldIds.size).toBe(3)
      expect(state.loadedFieldIds.has('firstName')).toBe(true)
      expect(state.loadedFieldIds.has('lastName')).toBe(true)
      expect(state.loadedFieldIds.has('email')).toBe(true)
    })

    it('does not duplicate field ids in loadedFieldIds', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(state.loadedFieldIds.size).toBe(1)
    })

    it('checks whether a field schema is loaded', () => {
      let state = SchemaFormStateManager.init(testSchema)

      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'firstName')).toBe(false)

      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')

      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'firstName')).toBe(true)
      expect(SchemaFormStateManager.isFieldSchemaLoaded(state, 'lastName')).toBe(false)
    })

    it('enables JIT mode', () => {
      let state = SchemaFormStateManager.init(testSchema)

      state = SchemaFormStateManager.setJitMode(state, true)

      expect(state.jitModeEnabled).toBe(true)
    })

    it('disables JIT mode', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.setJitMode(state, true)

      state = SchemaFormStateManager.setJitMode(state, false)

      expect(state.jitModeEnabled).toBe(false)
    })

    it('clears loaded field ids', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')

      state = SchemaFormStateManager.clearLoadedFieldIds(state)

      expect(state.loadedFieldIds.size).toBe(0)
    })

    it('serializes loadedFieldIds to an array for storage', () => {
      let state = SchemaFormStateManager.init(testSchema)
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'firstName')
      state = SchemaFormStateManager.markFieldSchemaLoaded(state, 'lastName')

      SchemaFormStateManager.save(state)

      const stored = JSON.parse(sessionStorageMock['schema_form_state'])
      expect(Array.isArray(stored.loadedFieldIds)).toBe(true)
      expect(stored.loadedFieldIds).toContain('firstName')
      expect(stored.loadedFieldIds).toContain('lastName')
    })

    it('deserializes a loadedFieldIds array back to a Set on load', () => {
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

    it('initializes JIT fields when loading pre-JIT state', () => {
      // Old state saved before the JIT feature, keyed on the legacy part fields.
      const oldState = {
        schema: testSchema,
        fieldValues: {},
        currentPartId: 'section-1a',
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

    it('preserves loadedFieldIds + jitModeEnabled across save/load', () => {
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
