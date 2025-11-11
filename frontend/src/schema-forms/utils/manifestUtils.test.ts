/**
 * Unit tests for Manifest Generation Utilities - Phase 3.2
 *
 * Tests manifest generation for JIT schema loading:
 * - Part manifest generation
 * - Handshake manifest building
 * - Schema inclusion logic
 * - Token estimation
 *
 * @version 1.0.0
 * @date 2025-11-10
 */

import { describe, it, expect } from 'vitest';
import {
  generatePartManifest,
  shouldIncludeSchema,
  buildHandshakeManifest,
  formatManifestForContext,
  estimateManifestTokens,
  getFieldSchema
} from './manifestUtils';
import type { FormSchema, FormPart } from '../types/schema';
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
        required: true
      },
      {
        id: 'lastName',
        name: 'Last Name',
        spoken_name: 'last name',
        type: 'text',
        required: true
      },
      {
        id: 'email',
        name: 'Email',
        spoken_name: 'email address',
        type: 'email',
        required: false
      },
      {
        id: 'phone',
        name: 'Phone',
        spoken_name: 'phone number',
        type: 'tel',
        required: false
      },
      {
        id: 'street',
        name: 'Street',
        spoken_name: 'street address',
        type: 'text',
        required: true
      },
      {
        id: 'city',
        name: 'City',
        spoken_name: 'city',
        type: 'text',
        required: true
      },
      {
        id: 'state',
        name: 'State',
        spoken_name: 'state',
        type: 'select',
        required: true,
        options: []
      }
    ]
  });

  const createTestState = (): SchemaFormState => ({
    schema: createTestSchema(),
    fieldValues: {},
    currentPartId: 'part-1',
    completedParts: new Set(),
    validationErrors: {},
    lastUpdated: Date.now(),
    loadedFieldIds: new Set(),
    jitModeEnabled: true
  });

  describe('generatePartManifest', () => {
    it('should generate manifest for a part with all fields', () => {
      const schema = createTestSchema();
      const part = schema.parts[0]; // part-1

      const manifest = generatePartManifest(part, schema);

      expect(manifest.part_id).toBe('part-1');
      expect(manifest.part_label).toBe('Personal Information');
      expect(manifest.fields).toHaveLength(4); // firstName, lastName, email, phone
    });

    it('should include field_id and spoken_name in manifest entries', () => {
      const schema = createTestSchema();
      const part = schema.parts[0];

      const manifest = generatePartManifest(part, schema);

      expect(manifest.fields[0]).toEqual({
        field_id: 'firstName',
        spoken_name: 'first name'
      });
      expect(manifest.fields[1]).toEqual({
        field_id: 'lastName',
        spoken_name: 'last name'
      });
    });

    it('should maintain field order from sections', () => {
      const schema = createTestSchema();
      const part = schema.parts[0];

      const manifest = generatePartManifest(part, schema);

      const fieldIds = manifest.fields.map(f => f.field_id);
      expect(fieldIds).toEqual(['firstName', 'lastName', 'email', 'phone']);
    });

    it('should handle part with multiple sections', () => {
      const schema = createTestSchema();
      const part = schema.parts[0]; // Has section-1a and section-1b

      const manifest = generatePartManifest(part, schema);

      expect(manifest.fields.length).toBeGreaterThan(0);
      // Should include fields from both sections
      const fieldIds = manifest.fields.map(f => f.field_id);
      expect(fieldIds).toContain('firstName'); // from section-1a
      expect(fieldIds).toContain('email'); // from section-1b
    });

    it('should use name as fallback if spoken_name missing', () => {
      const schema = createTestSchema();
      // Remove spoken_name from a field
      schema.fields[0].spoken_name = undefined as any;

      const part = schema.parts[0];
      const manifest = generatePartManifest(part, schema);

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
    it('should build manifest for current part', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest = buildHandshakeManifest('part-1', schema, state);

      expect(manifest.current_part.part_id).toBe('part-1');
      expect(manifest.current_part.part_label).toBe('Personal Information');
      expect(manifest.current_part.fields.length).toBeGreaterThan(0);
    });

    it('should include no previous parts if none completed', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest = buildHandshakeManifest('part-1', schema, state);

      expect(manifest.previous_parts).toHaveLength(0);
    });

    it('should include previous parts if completed', () => {
      const schema = createTestSchema();
      const state = createTestState();
      state.completedParts.add('part-1');
      state.currentPartId = 'part-2';

      const manifest = buildHandshakeManifest('part-2', schema, state);

      expect(manifest.previous_parts).toHaveLength(1);
      expect(manifest.previous_parts[0].part_id).toBe('part-1');
    });

    it('should throw error if part not found', () => {
      const schema = createTestSchema();
      const state = createTestState();

      expect(() => {
        buildHandshakeManifest('non-existent', schema, state);
      }).toThrow('Part non-existent not found');
    });
  });

  describe('formatManifestForContext', () => {
    it('should format manifest as pipe-separated text', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('part-1', schema, state);

      const formatted = formatManifestForContext(manifest);

      expect(formatted).toContain('CURRENT PART: Personal Information');
      expect(formatted).toContain('firstName|first name');
      expect(formatted).toContain('lastName|last name');
    });

    it('should include previous parts section when applicable', () => {
      const schema = createTestSchema();
      const state = createTestState();
      state.completedParts.add('part-1');

      const manifest = buildHandshakeManifest('part-2', schema, state);
      const formatted = formatManifestForContext(manifest);

      expect(formatted).toContain('PREVIOUS PARTS (lookup only):');
      expect(formatted).toContain('Personal Information:');
    });

    it('should use pipe separator for field entries', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('part-1', schema, state);

      const formatted = formatManifestForContext(manifest);

      // Check pipe separator format
      expect(formatted).toMatch(/\w+\|\w+/); // fieldId|spokenName pattern
    });
  });

  describe('estimateManifestTokens', () => {
    it('should return a positive token estimate', () => {
      const schema = createTestSchema();
      const state = createTestState();
      const manifest = buildHandshakeManifest('part-1', schema, state);

      const tokens = estimateManifestTokens(manifest);

      expect(tokens).toBeGreaterThan(0);
      expect(Number.isInteger(tokens)).toBe(true);
    });

    it('should estimate more tokens for larger manifests', () => {
      const schema = createTestSchema();
      const state = createTestState();

      const manifest1 = buildHandshakeManifest('part-1', schema, state);
      const tokens1 = estimateManifestTokens(manifest1);

      // Add completed part to increase manifest size
      state.completedParts.add('part-1');
      const manifest2 = buildHandshakeManifest('part-2', schema, state);
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
      expect(field?.required).toBe(false);
    });
  });
});
