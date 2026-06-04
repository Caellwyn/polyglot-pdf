/**
 * Unit tests for Manifest Generation Utilities - JIT schema loading
 *
 * Tests manifest generation for JIT schema loading:
 * - Section manifest generation
 * - Handshake manifest building
 * - Schema inclusion logic
 * - Token estimation
 *
 * Wire-format note: the manifest's section keys are section-canonical
 * (current_section / previous_sections / section_id / section_label) per
 * bd polyglot-pdf-zun. The `parts` navigation array keeps its key name
 * because the backend wire contract reads manifest.parts.
 */

import { describe, it, expect } from 'vitest';
import {
  generateSectionManifest,
  shouldIncludeSchema,
  buildHandshakeManifest,
  formatManifestForContext,
  estimateManifestTokens,
  getFieldSchema
} from './manifestUtils';
import type { FormSchema, FormSection } from '../types/schema';
import type { SchemaFormState } from '../state/schemaFormState';

describe('Manifest Generation Utilities', () => {
  // Test schema fixture
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
      }
    ],
    sections: [
      {
        id: 'section-1a',
        label: 'Name',
        order: 1,
        fields: ['firstName', 'lastName']
      },
      {
        id: 'section-1b',
        label: 'Details',
        order: 2,
        fields: ['email', 'phone']
      },
      {
        id: 'section-2a',
        label: 'Address',
        order: 1,
        fields: ['street', 'city', 'state']
      }
    ],
    fields: [
      {
        id: 'firstName',
        name: 'First Name',
        spoken_name: 'first name',
        type: 'text',
        section_id: 'section-1a'
      },
      {
        id: 'lastName',
        name: 'Last Name',
        spoken_name: 'last name',
        type: 'text',
        section_id: 'section-1a'
      },
      {
        id: 'email',
        name: 'Email',
        spoken_name: 'email address',
        type: 'email',
        section_id: 'section-1b'
      },
      {
        id: 'phone',
        name: 'Phone',
        spoken_name: 'phone number',
        type: 'tel',
        section_id: 'section-1b'
      },
      {
        id: 'street',
        name: 'Street',
        spoken_name: 'street address',
        type: 'text',
        section_id: 'section-2a'
      },
      {
        id: 'city',
        name: 'City',
        spoken_name: 'city',
        type: 'text',
        section_id: 'section-2a'
      },
      {
        id: 'state',
        name: 'State',
        spoken_name: 'state',
        type: 'select',
        section_id: 'section-2a',
        options: []
      }
    ]
  });

  const sectionById = (schema: FormSchema, id: string): FormSection =>
    schema.sections.find(s => s.id === id)!;

  const createTestState = (): SchemaFormState => ({
    schema: createTestSchema(),
    fieldValues: {},
    currentSectionId: 'section-1a',
    completedSections: new Set(),
    validationErrors: {},
    lastUpdated: Date.now(),
    loadedFieldIds: new Set(),
    jitModeEnabled: true
  } as SchemaFormState);

  describe('generateSectionManifest', () => {
    it('should generate manifest for a section with all fields', () => {
      const schema = createTestSchema();
      const section = sectionById(schema, 'section-1a');

      const manifest = generateSectionManifest(section, schema);

      expect(manifest.section_id).toBe('section-1a');
      expect(manifest.section_label).toBe('Name');
      expect(manifest.fields).toHaveLength(2); // firstName, lastName
    });

    it('should include field_id and spoken_name in manifest entries', () => {
      const schema = createTestSchema();
      const section = sectionById(schema, 'section-1a');

      const manifest = generateSectionManifest(section, schema);

      expect(manifest.fields[0]).toEqual({
        field_id: 'firstName',
        spoken_name: 'first name'
      });
      expect(manifest.fields[1]).toEqual({
        field_id: 'lastName',
        spoken_name: 'last name'
      });
    });

    it('should maintain field order from the section', () => {
      const schema = createTestSchema();
      const section = sectionById(schema, 'section-2a');

      const manifest = generateSectionManifest(section, schema);

      const fieldIds = manifest.fields.map(f => f.field_id);
      expect(fieldIds).toEqual(['street', 'city', 'state']);
    });

    it('should use name as fallback if spoken_name missing', () => {
      const schema = createTestSchema();
      // Remove spoken_name from a field
      schema.fields[0].spoken_name = undefined as any;

      const section = sectionById(schema, 'section-1a');
      const manifest = generateSectionManifest(section, schema);

      expect(manifest.fields[0].spoken_name).toBe('First Name');
    });
  });

  describe('shouldIncludeSchema', () => {
    it('should return true if field schema not yet loaded', () => {
      const state = createTestState();

      const result = shouldIncludeSchema('firstName', state);

      expect(result).toBe(true);
    });

    it('should return false if field schema already loaded', () => {
      const state = createTestState();
      state.loadedFieldIds.add('firstName');

      const result = shouldIncludeSchema('firstName', state);

      expect(result).toBe(false);
    });

    it('should handle multiple loaded fields correctly', () => {
      const state = createTestState();
      state.loadedFieldIds.add('firstName');
      state.loadedFieldIds.add('lastName');

      expect(shouldIncludeSchema('firstName', state)).toBe(false);
      expect(shouldIncludeSchema('lastName', state)).toBe(false);
      expect(shouldIncludeSchema('email', state)).toBe(true);
    });
  });

  describe('buildHandshakeManifest', () => {
    it('should build manifest for current section', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest = buildHandshakeManifest('section-1a', schema, state);

      expect(manifest.current_section.section_id).toBe('section-1a');
      expect(manifest.current_section.section_label).toBe('Name');
      expect(manifest.current_section.fields.length).toBeGreaterThan(0);
    });

    it('should include the section navigation list under the parts wire key', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest = buildHandshakeManifest('section-1a', schema, state);

      expect(manifest.parts.map(p => p.id)).toEqual([
        'section-1a',
        'section-1b',
        'section-2a'
      ]);
    });

    it('should include no previous sections if none completed', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest = buildHandshakeManifest('section-1a', schema, state);

      expect(manifest.previous_sections).toHaveLength(0);
    });

    it('should include previous sections if completed', () => {
      const schema = createTestSchema();
      const state = createTestState();
      state.completedSections.add('section-1a');
      state.currentSectionId = 'section-1b';

      const manifest = buildHandshakeManifest('section-1b', schema, state);

      expect(manifest.previous_sections).toHaveLength(1);
      expect(manifest.previous_sections[0].section_id).toBe('section-1a');
    });

    it('should throw error if section not found', () => {
      const schema = createTestSchema();
      const state = createTestState();

      expect(() => {
        buildHandshakeManifest('non-existent', schema, state);
      }).toThrow('Section non-existent not found');
    });
  });

  describe('formatManifestForContext', () => {
    it('should format manifest as pipe-separated text', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('section-1a', schema, state);

      const formatted = formatManifestForContext(manifest);

      expect(formatted).toContain('CURRENT SECTION: Name');
      expect(formatted).toContain('firstName|first name');
      expect(formatted).toContain('lastName|last name');
    });

    it('should include previous sections block when applicable', () => {
      const schema = createTestSchema();
      const state = createTestState();
      state.completedSections.add('section-1a');

      const manifest = buildHandshakeManifest('section-1b', schema, state);
      const formatted = formatManifestForContext(manifest);

      expect(formatted).toContain('PREVIOUS SECTIONS (lookup only):');
      expect(formatted).toContain('Name:');
    });

    it('should use pipe separator for field entries', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('section-1a', schema, state);

      const formatted = formatManifestForContext(manifest);

      // Check pipe separator format
      expect(formatted).toMatch(/\w+\|\w+/); // fieldId|spokenName pattern
    });
  });

  describe('estimateManifestTokens', () => {
    it('should return a positive token estimate', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('section-1a', schema, state);

      const tokens = estimateManifestTokens(manifest);

      expect(tokens).toBeGreaterThan(0);
      expect(Number.isInteger(tokens)).toBe(true);
    });

    it('should estimate more tokens for larger manifests', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest1 = buildHandshakeManifest('section-1a', schema, state);
      const tokens1 = estimateManifestTokens(manifest1);

      // Add completed section to increase manifest size
      state.completedSections.add('section-1a');
      const manifest2 = buildHandshakeManifest('section-1b', schema, state);
      const tokens2 = estimateManifestTokens(manifest2);

      expect(tokens2).toBeGreaterThan(tokens1);
    });
  });

  describe('getFieldSchema', () => {
    it('should return field schema by ID', () => {
      const schema = createTestSchema();

      const field = getFieldSchema('firstName', schema);

      expect(field).toBeDefined();
      expect(field?.id).toBe('firstName');
      expect(field?.spoken_name).toBe('first name');
    });

    it('should return undefined for non-existent field', () => {
      const schema = createTestSchema();

      const field = getFieldSchema('nonExistent', schema);

      expect(field).toBeUndefined();
    });

    it('should return complete field object with all properties', () => {
      const schema = createTestSchema();

      const field = getFieldSchema('email', schema);

      expect(field).toBeDefined();
      expect(field?.id).toBe('email');
      expect(field?.name).toBe('Email');
      expect(field?.spoken_name).toBe('email address');
      expect(field?.type).toBe('email');
      expect(field?.section_id).toBe('section-1b');
    });
  });
});
