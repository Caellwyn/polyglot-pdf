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
import { saveOnboardingState, clearOnboardingState } from '../onboardingStorage'
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
      },
      {
        // An a_number field: the ONE preset normalizeFieldValue actually
        // transforms (strips the "A" prefix + non-digits). Used to pin that
        // updateField normalizes the stored value rather than passing it through
        // raw -- a plain text field would make that assertion vacuous.
        id: 'field-anum',
        name: 'Alien Registration Number',
        spoken_name: 'a number',
        type: 'text',
        section_id: 'section-3a',
        validation: { required: false, format_preset: 'a_number' }
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

    // bd polyglot-pdf-p8sq: the FIRST connect's handshake reads
    // state.selectedLanguage; before this seed it was only written at
    // disclaimer-AGREE, so a fresh session's first connect carried no
    // language (wrong en-US ASR bias, option-translation warm-up skipped).
    it('seeds selectedLanguage from the onboarding choice (bd p8sq)', () => {
      sessionStorageMock['vff_selected_language'] = 'Spanish'
      const state = SchemaFormStateManager.init(createTestSchema())
      expect(state.selectedLanguage).toBe('Spanish')
      // ... and the handshake payload carries it on the FIRST connect.
      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect(payload.spoken_language).toBe('Spanish')
    })

    it('leaves selectedLanguage unset when onboarding recorded none', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      expect(state.selectedLanguage).toBeUndefined()
      expect(SchemaFormStateManager.getHandshakePayload(state).spoken_language)
        .toBeNull()
    })

    it('backfills a pre-p8sq persisted state missing selectedLanguage', () => {
      // A state saved BEFORE the seed existed: language chosen at onboarding
      // but absent from the persisted form state.
      const first = SchemaFormStateManager.init(createTestSchema())
      expect(first.selectedLanguage).toBeUndefined()
      sessionStorageMock['vff_selected_language'] = 'French'
      const resumed = SchemaFormStateManager.init(createTestSchema())
      expect(resumed.selectedLanguage).toBe('French')
      // The backfill persisted, so a raw load() sees it too.
      expect(SchemaFormStateManager.load()?.selectedLanguage).toBe('French')
    })

    it('does not overwrite an explicit selectedLanguage on resume', () => {
      sessionStorageMock['vff_selected_language'] = 'Spanish'
      const state = SchemaFormStateManager.init(createTestSchema())
      state.selectedLanguage = 'German' // e.g. set by a later language change
      SchemaFormStateManager.save(state)
      const resumed = SchemaFormStateManager.init(createTestSchema())
      expect(resumed.selectedLanguage).toBe('German')
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

    it('should accept FieldValue objects directly (metadata preserved)', () => {
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

      // field-1 is a plain text field, so normalizeFieldValue is a no-op on the
      // value and the wrapper's metadata (confirmed/lastModified) passes through.
      const fieldValue = updatedState.fieldValues['field-1'] as FieldValue
      expect(fieldValue).toEqual(customFieldValue)
    })

    it('normalizes the .value of a FieldValue object through the field preset', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      // field-anum has format_preset 'a_number': normalizeFieldValue strips the
      // leading "A" and any non-digits. The wrapper goes in raw; the STORED value
      // is normalized -- this pins that updateField does NOT pass .value through
      // untouched (the assertion the plain-text case above can't make).
      const updatedState = SchemaFormStateManager.updateField(
        state,
        'field-anum',
        { value: 'A 123-456-789', confirmed: true } as FieldValue
      )

      const fieldValue = updatedState.fieldValues['field-anum'] as FieldValue
      expect(fieldValue.value).toBe('123456789')
      // metadata on the wrapper is still preserved alongside the normalized value
      expect(fieldValue.confirmed).toBe(true)
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

    it('sends form_number on the JIT handshake, distinct from form_title (bd n0em)', () => {
      // The backend derives the confirmation audit trail's form_id from
      // schema.form_metadata.form_number. The manifest-first (JIT) transport --
      // the shipped default -- carries no full schema, so this key is the ONLY
      // way the real form id reaches the audit record; without it every
      // confirmation event logged form_id="unknown" (found in production).
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getJITHandshakePayload(state, 'English')

      expect(payload.form_number).toBe('I-90')
      // Identifier and human label must stay separate keys: collapsing them
      // would write a prose title where the audit expects an identifier.
      expect(payload.form_number).not.toBe(payload.form_title)
    })

    it('sends kit_id and edition_date on the JIT handshake (bd 47r3)', () => {
      // A form NUMBER identifies neither WHICH kit (two kits can share one --
      // a standard W-7 and a firm-specific variant) nor WHICH government
      // edition the client confirmed against. Both ride the handshake so the
      // confirmation audit trail can name the exact revision.
      saveOnboardingState({ formId: 'i-90', language: 'English' })
      const schema = createTestSchema()
      const withEdition = {
        ...schema,
        form_metadata: { ...schema.form_metadata, edition_date: '01/20/25' },
      }
      const state = SchemaFormStateManager.init(withEdition)

      const payload = SchemaFormStateManager.getJITHandshakePayload(state, 'English')

      expect(payload.kit_id).toBe('i-90')
      expect(payload.edition_date).toBe('01/20/25')
    })

    it('sends kit_id/edition_date as null when unavailable (bd 47r3)', () => {
      // A custom form legitimately has no government edition; the backend then
      // falls back to a content fingerprint rather than recording nothing.
      clearOnboardingState()
      const schema = createTestSchema()
      const noEdition = {
        ...schema,
        form_metadata: { ...schema.form_metadata, edition_date: undefined as any },
      }
      const state = SchemaFormStateManager.init(noEdition)

      const payload = SchemaFormStateManager.getJITHandshakePayload(state, 'English')

      expect(payload.kit_id).toBeNull()
      expect(payload.edition_date).toBeNull()
    })

    it('sends form_number as null when the schema has no form_number (bd n0em)', () => {
      // A kit lacking form_metadata.form_number must not crash the handshake --
      // the backend degrades that session to form_id="unknown", the pre-fix
      // behavior, rather than erroring.
      const schema = createTestSchema()
      const noNumber = {
        ...schema,
        form_metadata: { ...schema.form_metadata, form_number: undefined as any },
      }
      const state = SchemaFormStateManager.init(noNumber)

      const payload = SchemaFormStateManager.getJITHandshakePayload(state, 'English')

      expect(payload.form_number).toBeNull()
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

    // === Fix 2 (bd polyglot-pdf-wq9y): legacy payload must include type:'handshake' ===
    it('includes type:handshake in legacy (non-JIT) payload', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect((payload as any).type).toBe('handshake')
    })

    // === Fix 1 (bd polyglot-pdf-vmxx): resume flag ===
    it('defaults resume to false when not supplied', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state)
      expect((payload as any).resume).toBe(false)
    })

    it('sets resume:false on fresh connect', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state, 'English', false)
      expect((payload as any).resume).toBe(false)
    })

    it('sets resume:true on reconnect', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state, 'English', true)
      expect((payload as any).resume).toBe(true)
    })

    // === bd polyglot-pdf-y25o: spoken_language rides the handshake ===
    // The backend derives the per-connect ASR language bias from it, so it must
    // arrive BEFORE the Gemini connect -- the change_spoken_language message the
    // client sends after session_ready is too late for per-connect config.
    it('carries the selected spoken language (both handshake shapes)', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = { ...state, selectedLanguage: 'Spanish' }

      const legacy = SchemaFormStateManager.getHandshakePayload(state) as any
      expect(legacy.spoken_language).toBe('Spanish')

      const jitState = { ...state, jitModeEnabled: true }
      const jit = SchemaFormStateManager.getHandshakePayload(jitState) as any
      expect(jit.type).toBe('handshake_jit')
      expect(jit.spoken_language).toBe('Spanish')
    })

    it('sends spoken_language:null when no language was chosen yet', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state) as any
      expect(payload.spoken_language).toBeNull()
    })

    // === bd polyglot-pdf-bo4m: field.help must survive the handshake wire ===
    // The backend rebuilds the SI from THIS payload (stateless backend), and
    // help.instructions feeds the SI's "Note:" line -- if the handshake
    // stripped help, the voice AI would lose every field's fine print.
    it('legacy payload schema fields carry the help block intact', () => {
      const schema = createTestSchema()
      schema.fields[0].help = {
        instructions: 'Indicate if your name has legally changed since your ' +
          'Permanent Resident Card was issued.',
        format_hint: 'Yes / No / N/A'
      }
      const state = SchemaFormStateManager.init(schema)

      const payload = SchemaFormStateManager.getHandshakePayload(state) as any
      const sent = payload.schema.fields.find((f: any) => f.id === 'field-1')
      expect(sent.help).toBeDefined()
      expect(sent.help.instructions).toContain('Permanent Resident Card')
      expect(sent.help.format_hint).toBe('Yes / No / N/A')
    })

    // === bd polyglot-pdf-p68s (jnjj.45d): full_schema = the WHOLE form ===
    // The legacy `schema` is the current section only (2 fields); full_schema
    // must carry every field across every section for the secretary catalog.
    it('legacy payload carries full_schema = the whole form (all sections/fields)', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema) // seeded on section-1a (2 fields)

      const payload = SchemaFormStateManager.getHandshakePayload(state) as any

      // The section schema is just section-1a's two fields...
      expect(payload.schema.fields.map((f: any) => f.id)).toEqual(['field-1', 'field-2'])
      // ...but full_schema is the WHOLE form (7 fields, 4 sections).
      expect(payload.full_schema).toBeDefined()
      expect(payload.full_schema.fields.length).toBe(7)
      expect(payload.full_schema.sections.length).toBe(4)
    })

    it('JIT payload carries full_schema = the whole form (the production/DTI path)', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      // The JIT handshake is the production DTI path; it sends only a manifest +
      // first_field_schema for the live model, so full_schema is the secretary's
      // ONLY view of the whole form here.
      state = SchemaFormStateManager.setJitMode(state, true)

      const payload = SchemaFormStateManager.getHandshakePayload(state) as any

      expect(payload.type).toBe('handshake_jit')
      expect(payload.full_schema).toBeDefined()
      expect(payload.full_schema.fields.length).toBe(7)
      expect(payload.full_schema.sections.length).toBe(4)
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
  // hasInProgressSession() -- soft-refresh resume signal (bd polyglot-pdf-hc4b)
  // ============================================================================

  describe('hasInProgressSession()', () => {
    it('is false on a fresh session (no disclaimer, no values)', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      expect(SchemaFormStateManager.hasInProgressSession(state)).toBe(false)
    })

    it('is false when the disclaimer is accepted but no field is filled yet', () => {
      let state = SchemaFormStateManager.init(createTestSchema())
      state = { ...state, disclaimerAccepted: true }
      expect(SchemaFormStateManager.hasInProgressSession(state)).toBe(false)
    })

    it('is false when a field is filled but the disclaimer was not accepted', () => {
      let state = SchemaFormStateManager.init(createTestSchema())
      state = SchemaFormStateManager.updateField(state, 'field-1', 'Doe')
      expect(state.disclaimerAccepted).toBe(false)
      expect(SchemaFormStateManager.hasInProgressSession(state)).toBe(false)
    })

    it('is true mid-form (disclaimer accepted + at least one filled field)', () => {
      let state = SchemaFormStateManager.init(createTestSchema())
      state = { ...state, disclaimerAccepted: true }
      state = SchemaFormStateManager.updateField(state, 'field-1', 'Doe')
      expect(SchemaFormStateManager.hasInProgressSession(state)).toBe(true)
    })

    it('drives resume:true on the first post-reload handshake', () => {
      // A soft refresh builds a fresh connection (hasConnectedOnce=false), so the
      // handshake resume flag must come from persisted in-progress state.
      let state = SchemaFormStateManager.init(createTestSchema())
      state = { ...state, disclaimerAccepted: true }
      state = SchemaFormStateManager.updateField(state, 'field-1', 'Doe')

      const resume = SchemaFormStateManager.hasInProgressSession(state)
      const payload = SchemaFormStateManager.getHandshakePayload(state, 'English', resume)
      expect((payload as any).resume).toBe(true)
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

    it('keeps an already-completed section completed on same-section switch', () => {
      const schema = createTestSchema()
      // section-1a is current AND already in completedSections.
      const state = {
        ...SchemaFormStateManager.init(schema),
        currentSectionId: 'section-1a',
        completedSections: new Set(['section-1a'])
      }

      const newState = SchemaFormStateManager.switchToSection(state, 'section-1a')

      // Same-section switch reuses the existing set; the prior completion stands
      // and nothing new is added.
      expect(newState.currentSectionId).toBe('section-1a')
      expect(newState.completedSections.has('section-1a')).toBe(true)
      expect(newState.completedSections.size).toBe(1)
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
  // findSectionIdForField() -- drives continuous-mode UI section paging
  // (bd polyglot-pdf-gz20)
  // ============================================================================

  describe('findSectionIdForField()', () => {
    it('returns the section that contains the field', () => {
      const state = SchemaFormStateManager.init(createTestSchema())

      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-1')).toBe('section-1a')
      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-3')).toBe('section-1b')
      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-5')).toBe('section-2a')
      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-6')).toBe('section-3a')
    })

    it('resolves a []-alias field id to its base field section', () => {
      const state = SchemaFormStateManager.init(createTestSchema())

      // Gemini drops/adds the bracket; the section is keyed on the base id.
      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-4[]')).toBe('section-2a')
    })

    it('resolves a base id when the section lists the bracketed variant', () => {
      const schema = createTestSchema()
      // Section lists the field under its []-alias; a hint for the base id must
      // still resolve.
      schema.sections[2].fields = ['field-4[]', 'field-5']
      const state = SchemaFormStateManager.init(schema)

      expect(SchemaFormStateManager.findSectionIdForField(state, 'field-4')).toBe('section-2a')
    })

    it('returns null for an unknown field or empty id', () => {
      const state = SchemaFormStateManager.init(createTestSchema())

      expect(SchemaFormStateManager.findSectionIdForField(state, 'no-such-field')).toBeNull()
      expect(SchemaFormStateManager.findSectionIdForField(state, '')).toBeNull()
    })
  })

  // ============================================================================
  // getCurrentSectionFields() -- []-alias-consistent with findSectionIdForField
  // (bd polyglot-pdf-rctj)
  // ============================================================================

  describe('getCurrentSectionFields() []-alias handling', () => {
    it('renders a field whose section lists the []-alias while field.id is the base', () => {
      const schema = createTestSchema()
      // Section lists the field under its []-alias; field-4's own id is the base.
      schema.sections[2].fields = ['field-4[]', 'field-5']
      const state = { ...SchemaFormStateManager.init(schema), currentSectionId: 'section-2a' }

      const fields = SchemaFormStateManager.getCurrentSectionFields(state)

      expect(fields.map((f) => f.id)).toContain('field-4')
    })

    it('stays symmetric with findSectionIdForField: paging to the section renders the field', () => {
      // The exact bd rctj repro: onNextField pages the UI to the section
      // findSectionIdForField resolves, and the paged section must then
      // actually render that field -- not appear to be missing it.
      const schema = createTestSchema()
      schema.sections[2].fields = ['field-4[]', 'field-5']
      const state = SchemaFormStateManager.init(schema)

      const targetSectionId = SchemaFormStateManager.findSectionIdForField(state, 'field-4')
      expect(targetSectionId).toBe('section-2a')

      const pagedState = { ...state, currentSectionId: targetSectionId! }
      const fields = SchemaFormStateManager.getCurrentSectionFields(pagedState)

      expect(fields.map((f) => f.id)).toContain('field-4')
    })

    it('still returns exact-id fields unchanged (no regression to the common case)', () => {
      const state = SchemaFormStateManager.init(createTestSchema())

      const fields = SchemaFormStateManager.getCurrentSectionFields(state)

      expect(fields.map((f) => f.id)).toEqual(['field-1', 'field-2'])
    })

    it('renders a field whose section lists the BASE id while field.id is bracketed (reverse direction)', () => {
      // The mirror of the first test above: findSectionIdForField matches
      // BOTH directions (section-lists-base + field.id-bracketed is the
      // other half of its own bidirectional lookup), so getCurrentSectionFields
      // must stay symmetric here too, not just for the alias-in-section case.
      const schema = createTestSchema()
      schema.fields[3].id = 'field-4[]' // field-4 becomes the bracketed variant
      schema.sections[2].fields = ['field-4', 'field-5'] // section still lists the base
      const state = { ...SchemaFormStateManager.init(schema), currentSectionId: 'section-2a' }

      const fields = SchemaFormStateManager.getCurrentSectionFields(state)

      expect(fields.map((f) => f.id)).toContain('field-4[]')
    })
  })

  // ============================================================================
  // setVisibleSection() -- continuous-mode UI paging that PRESERVES the pin
  // (bd polyglot-pdf-gz20)
  // ============================================================================

  describe('setVisibleSection()', () => {
    it('changes currentSectionId', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      expect(state.currentSectionId).toBe('section-1a')

      const next = SchemaFormStateManager.setVisibleSection(state, 'section-2a')
      expect(next.currentSectionId).toBe('section-2a')
    })

    it('PRESERVES pinnedFieldId (unlike navigateToSection, which clears it)', () => {
      let state = SchemaFormStateManager.init(createTestSchema())
      state = SchemaFormStateManager.pinField(state, 'field-4')
      expect(state.pinnedFieldId).toBe('field-4')

      // setVisibleSection follows the model's own focus (which may include a
      // switch_to_field pin), so it must NOT abandon the pin.
      const paged = SchemaFormStateManager.setVisibleSection(state, 'section-2a')
      expect(paged.currentSectionId).toBe('section-2a')
      expect(paged.pinnedFieldId).toBe('field-4')

      // Contrast: navigateToSection (a manual jump) DOES clear it.
      const manual = SchemaFormStateManager.navigateToSection(state, 'section-2a')
      expect(manual.pinnedFieldId).toBeNull()
    })

    it('does not grow completedSections', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      const next = SchemaFormStateManager.setVisibleSection(state, 'section-2a')
      expect(next.completedSections.size).toBe(0)
    })

    it('is a no-op (same reference) when already on the target section', () => {
      const state = SchemaFormStateManager.init(createTestSchema())
      const same = SchemaFormStateManager.setVisibleSection(state, 'section-1a')
      expect(same).toBe(state)
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
      // The legacy part keys in this old state are also migrated forward.
      expect(loaded!.currentSectionId).toBe('section-1a')
      expect((loaded as any).currentPartId).toBeUndefined()
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

  // ============================================================================
  // B5 (bd polyglot-pdf-jnjj.17): the `steered` marker (Codex PR #275 fixes)
  // ============================================================================
  describe('markFieldsSteered + steered preservation', () => {
    it('marks a field steered and persists it', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBe(true)
      // Persisted to sessionStorage -> survives a reload.
      const loaded = SchemaFormStateManager.load()!
      expect((loaded.fieldValues['field-1'] as FieldValue).steered).toBe(true)
    })

    it('marks via the [] alias when the value is stored under the bracketed key', () => {
      // The verdict echoes the schema id (field-1), but the value lives under
      // field-1[] -- markFieldsSteered must follow the same []-fallback as reads, or
      // the marker lands nowhere and the field re-steers forever.
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1[]', 'v')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      expect((state.fieldValues['field-1[]'] as FieldValue).steered).toBe(true)
    })

    it('W4: RE-ARMS (clears steered) when a manual edit CHANGES the value (raw value)', () => {
      // W4 (bd polyglot-pdf-ny4s): a value CHANGE re-arms -- the corrected field
      // must re-enter the validator net. (Pre-W4 this test asserted preservation;
      // that unconditional carry-forward was the bug the maintainer flagged.)
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v2')
      expect((state.fieldValues['field-1'] as FieldValue).value).toBe('v2')
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBeFalsy()
    })

    it('W4: PRESERVES the marker when an edit does NOT change the value (raw value)', () => {
      // No value change (a re-confirm / no-op write) -> the marker stays, so a user
      // who confirms "both are intentional" is never re-asked (no-nagging guarantee).
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1') // same value
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBe(true)
    })

    it('W4: RE-ARMS when a FieldValue object CHANGES the value', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      state = SchemaFormStateManager.updateField(state, 'field-1', { value: 'v2', confirmed: true } as any)
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBeFalsy()
    })

    it('W4: a FieldValue object with an EXPLICIT steered wins over the re-arm rule', () => {
      // An incoming FieldValue that explicitly sets steered is honored (the caller
      // asserted intent); re-arm only governs the implicit carry-forward.
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      state = SchemaFormStateManager.updateField(state, 'field-1', { value: 'v2', steered: true } as any)
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBe(true)
    })

    it('skips a field with no entry (no spurious empty entry)', () => {
      const schema = createTestSchema()
      const state = SchemaFormStateManager.init(schema)
      const after = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      expect(after.fieldValues['field-1']).toBeUndefined()
    })

    it('PRESERVES the marker across an []-alias migration when the value is UNCHANGED (bd polyglot-pdf-5k52 + W4)', () => {
      // The marker was written under the bracketed key (field-1[]); the model then
      // re-writes the unbracketed id with the SAME value. The carry-forward must apply
      // the same []-alias fallback as markFieldsSteered (so the marker follows the
      // field across the variant) AND, since the value did not change, keep the marker
      // (W4 re-arm governs value changes, not the key-variant migration).
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1[]', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1[]'])
      expect((state.fieldValues['field-1[]'] as FieldValue).steered).toBe(true)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1') // same value, other variant
      expect((state.fieldValues['field-1'] as FieldValue).value).toBe('v1')
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBe(true)
    })

    it('W4: RE-ARMS across an []-alias migration when the value CHANGES', () => {
      // A value change re-arms even across the bracket-variant migration (the alias
      // fallback finds the prior value under the other key, sees it differ, clears).
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      state = SchemaFormStateManager.updateField(state, 'field-1[]', 'v2')
      expect((state.fieldValues['field-1[]'] as FieldValue).steered).toBeFalsy()
    })

    it('got6: an []-alias migration leaves NO stale entry under the old key', () => {
      // bd polyglot-pdf-got6: prior code wrote the new value under the incoming key
      // but left the OLD entry (stale value + stale steered) under the other variant.
      // A downstream reader that prefers the exact schema-id key (buildValidatorFields'
      // valueFor) would then read the stale value/steered, defeating W4's re-arm.
      // Now exactly ONE entry represents the field.
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1'])
      // Migrate the value to the bracket variant with a NEW value.
      state = SchemaFormStateManager.updateField(state, 'field-1[]', 'v2')
      // The stale exact-key entry is gone; only the bracket variant remains.
      expect(state.fieldValues['field-1']).toBeUndefined()
      expect((state.fieldValues['field-1[]'] as FieldValue).value).toBe('v2')
      expect((state.fieldValues['field-1[]'] as FieldValue).steered).toBeFalsy()
    })

    it('got6: reverse migration (bracketed -> unbracketed) also leaves no stale entry', () => {
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1[]', 'v1')
      state = SchemaFormStateManager.markFieldsSteered(state, ['field-1[]'])
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v2')
      expect(state.fieldValues['field-1[]']).toBeUndefined()
      expect((state.fieldValues['field-1'] as FieldValue).value).toBe('v2')
      expect((state.fieldValues['field-1'] as FieldValue).steered).toBeFalsy()
    })

    it('got6: a SAME-key rewrite does not spuriously delete the entry', () => {
      // The migration cleanup must only fire when the prior entry was under a
      // DIFFERENT key -- a normal same-key edit must keep working.
      const schema = createTestSchema()
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v1')
      state = SchemaFormStateManager.updateField(state, 'field-1', 'v2')
      expect((state.fieldValues['field-1'] as FieldValue).value).toBe('v2')
      expect(state.fieldValues['field-1[]']).toBeUndefined()
    })
  })

  // ==========================================================================
  // isSectionValid: require_if enforcement (bd c7st) + skip-placeholder (bd 4dxt)
  // ==========================================================================
  describe('isSectionValid + require_if enforcement + skip (c7st/4dxt)', () => {
    // A minimal schema: section 'sec' with a statically-required field 'req', a
    // conditionally-required field 'cond' (required only when trigger == 'yes'),
    // and the 'trigger'. shouldShowField/isFieldRequired read the wrapped
    // fieldValues map directly (they unwrap internally).
    const condSchema = (): FormSchema => ({
      source: 'pdf',
      form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'X' },
      sections: [{ id: 'sec', label: 'Sec', order: 1, fields: ['trigger', 'req', 'cond'] }],
      fields: [
        { id: 'trigger', name: 'Allow designee', spoken_name: 'allow designee', type: 'radio', section_id: 'sec',
          options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
        { id: 'req', name: 'Always required', spoken_name: 'always required', type: 'text', section_id: 'sec',
          validation: { required: true } },
        { id: 'cond', name: 'Designee name', spoken_name: 'designee name', type: 'text', section_id: 'sec',
          require_if: { field: 'trigger', operator: 'equals', value: 'yes' } },
      ],
    })

    it('blocks the section while a statically-required field is empty', () => {
      const state = SchemaFormStateManager.init(condSchema())
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(false)
    })

    it('passes once the statically-required field is filled and no require_if fires', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.updateField(state, 'req', 'Jane')
      // trigger unset -> cond not required
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(true)
    })

    it('ENFORCES require_if: a conditionally-required field must be filled when its condition holds (c7st)', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.updateField(state, 'req', 'Jane')
      state = SchemaFormStateManager.updateField(state, 'trigger', 'yes')
      // cond is now required but empty -> section invalid
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(false)
      state = SchemaFormStateManager.updateField(state, 'cond', 'Bob')
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(true)
    })

    it('does NOT require a conditionally-required field when its condition is unmet', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.updateField(state, 'req', 'Jane')
      state = SchemaFormStateManager.updateField(state, 'trigger', 'no')
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(true)
    })

    it('lets a force-SKIPPED required field satisfy the gate (4dxt)', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.updateField(state, 'req', 'Jane')
      state = SchemaFormStateManager.updateField(state, 'trigger', 'yes')
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(false)
      state = SchemaFormStateManager.markFieldSkipped(state, 'cond')
      // skipped required field satisfies the gate; form is submittable
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(true)
    })

    it('markFieldSkipped keeps the value empty (PDF prints blank) but marks it skipped + confirmed', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.markFieldSkipped(state, 'req')
      const fv = state.fieldValues['req'] as FieldValue
      expect(fv.skipped).toBe(true)
      expect(fv.confirmed).toBe(true)
      expect(fv.value).toBeNull()
    })

    it('setting a real value AFTER a skip drops the skipped flag (answered after all)', () => {
      let state = SchemaFormStateManager.init(condSchema())
      state = SchemaFormStateManager.markFieldSkipped(state, 'req')
      expect((state.fieldValues['req'] as FieldValue).skipped).toBe(true)
      state = SchemaFormStateManager.updateField(state, 'req', 'Jane')
      expect((state.fieldValues['req'] as FieldValue).skipped).toBeUndefined()
      expect((state.fieldValues['req'] as FieldValue).value).toBe('Jane')
    })

    it('does not block on a HIDDEN required field (require_if on an unshown field)', () => {
      // 'cond' is required-when-trigger=yes AND shown-when-trigger=yes; if it were
      // required but hidden, it could never be filled. Model that: gate on show_if.
      const schema: FormSchema = {
        source: 'pdf',
        form_metadata: { title: 'T', version: '1', language: 'en', form_number: 'X' },
        sections: [{ id: 'sec', label: 'Sec', order: 1, fields: ['trigger', 'hidden_req'] }],
        fields: [
          { id: 'trigger', name: 'Trigger', spoken_name: 'trigger', type: 'radio', section_id: 'sec',
            options: [{ value: 'yes', label: 'Yes' }, { value: 'no', label: 'No' }] },
          { id: 'hidden_req', name: 'Hidden required', spoken_name: 'hidden required', type: 'text', section_id: 'sec',
            validation: { required: true },
            show_if: { field: 'trigger', operator: 'equals', value: 'yes' } },
        ],
      }
      let state = SchemaFormStateManager.init(schema)
      state = SchemaFormStateManager.updateField(state, 'trigger', 'no')
      // hidden_req is required but NOT shown -> must not block the section
      expect(SchemaFormStateManager.isSectionValid(state, 'sec')).toBe(true)
    })
  })
})
