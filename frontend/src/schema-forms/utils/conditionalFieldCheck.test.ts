/**
 * Unit tests for conditional field checking
 *
 * Tests the JIT schema loading conditional field access logic
 */

import { describe, it, expect } from 'vitest';
import { checkFieldAccess, evaluateFieldAvailability, getDependencyChain } from './conditionalFieldCheck';
import type { FormSchema, FormField } from '../types/schema';

describe('conditionalFieldCheck', () => {
  // Mock schema with conditional fields
  const mockSchema: FormSchema = {
    source: 'pdf',
    form_metadata: {
      title: 'Test Form',
      form_number: 'TEST-001',
      version: '1.0',
      language: 'en'
    },
    sections: [
      {
        id: 'section_1',
        label: 'Section 1',
        order: 1,
        fields: ['marital_status', 'spouse_name', 'spouse_birth_date', 'employment_status', 'employer_name']
      }
    ],
    fields: [
      // Independent field - no conditions
      {
        id: 'marital_status',
        name: 'Marital Status',
        spoken_name: 'marital status',
        type: 'radio',
        section_id: 'section_1',
        options: [
          { value: 'Single', label: 'Single' },
          { value: 'Married', label: 'Married' },
          { value: 'Divorced', label: 'Divorced' }
        ]
      } as FormField,

      // Conditionally shown field - depends on marital_status
      {
        id: 'spouse_name',
        name: 'Spouse Full Name',
        spoken_name: 'spouse name',
        type: 'text',
        section_id: 'section_1',
        show_if: {
          field: 'marital_status',
          operator: 'equals',
          value: 'Married'
        }
      } as FormField,

      // Nested conditional - depends on spouse_name being filled
      {
        id: 'spouse_birth_date',
        name: 'Spouse Date of Birth',
        spoken_name: 'spouse birth date',
        type: 'date',
        section_id: 'section_1',
        show_if: {
          field: 'spouse_name',
          operator: 'is_not_empty',
          value: ''
        }
      } as FormField,

      // Read-only field
      {
        id: 'form_version',
        name: 'Form Version',
        spoken_name: 'form version',
        type: 'text',
        section_id: 'section_1',
        read_only: true
      } as FormField,

      // Another independent field
      {
        id: 'employment_status',
        name: 'Employment Status',
        spoken_name: 'employment status',
        type: 'radio',
        section_id: 'section_1',
        options: [
          { value: 'Employed', label: 'Employed' },
          { value: 'Unemployed', label: 'Unemployed' }
        ]
      } as FormField,

      // Conditional on employment
      {
        id: 'employer_name',
        name: 'Employer Name',
        spoken_name: 'employer name',
        type: 'text',
        section_id: 'section_1',
        show_if: {
          field: 'employment_status',
          operator: 'equals',
          value: 'Employed'
        }
      } as FormField
    ]
  };

  describe('checkFieldAccess', () => {
    it('should allow access to independent fields', () => {
      const fieldValues = {};
      const result = checkFieldAccess('marital status', mockSchema, fieldValues);

      expect(result.accessible).toBe(true);
      expect(result.reason).toBeUndefined();
      expect(result.message).toBeUndefined();
    });

    it('should block access to hidden conditional field', () => {
      // spouse_name requires marital_status = 'Married'
      const fieldValues = {
        marital_status: 'Single'
      };

      const result = checkFieldAccess('spouse name', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.reason).toBe('field_hidden');
      expect(result.message).toContain('spouse name');
      expect(result.message).toContain('marital status');
      expect(result.message).toContain('Married');
      expect(result.required_fields).toBeDefined();
      expect(result.required_fields?.length).toBe(1);
      expect(result.required_fields?.[0].field_id).toBe('marital_status');
      expect(result.required_fields?.[0].spoken_name).toBe('marital status');
      expect(result.required_fields?.[0].required_value).toBe('Married');
      expect(result.required_fields?.[0].current_value).toBe('Single');
    });

    it('should allow access to conditional field when condition is met', () => {
      // spouse_name requires marital_status = 'Married'
      const fieldValues = {
        marital_status: 'Married'
      };

      const result = checkFieldAccess('spouse name', mockSchema, fieldValues);

      expect(result.accessible).toBe(true);
      expect(result.reason).toBeUndefined();
    });

    it('should block access to nested conditional field', () => {
      // spouse_birth_date requires spouse_name to be filled
      const fieldValues = {
        marital_status: 'Married',
        spouse_name: '' // Empty
      };

      const result = checkFieldAccess('spouse birth date', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.reason).toBe('field_hidden');
      expect(result.message).toContain('spouse birth date');
      expect(result.message).toContain('spouse name');
    });

    it('should allow access to nested conditional when all conditions met', () => {
      const fieldValues = {
        marital_status: 'Married',
        spouse_name: 'Jane Doe'
      };

      const result = checkFieldAccess('spouse birth date', mockSchema, fieldValues);

      expect(result.accessible).toBe(true);
    });

    it('should block access to read-only fields', () => {
      const fieldValues = {};
      const result = checkFieldAccess('form version', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.reason).toBe('field_read_only');
      expect(result.message).toContain('read-only');
    });

    it('should return not found for non-existent fields', () => {
      const fieldValues = {};
      const result = checkFieldAccess('nonexistent field', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.reason).toBe('field_not_found');
      expect(result.message).toContain('not found');
    });

    it('should handle FieldValue wrappers correctly', () => {
      // Test that unwrapFieldValue is being used
      const fieldValues = {
        marital_status: { value: 'Married', source: 'user' } // FieldValue wrapper
      };

      const result = checkFieldAccess('spouse name', mockSchema, fieldValues);

      expect(result.accessible).toBe(true);
    });

    it('should handle multiple independent conditional branches', () => {
      // employer_name requires employment_status = 'Employed'
      const fieldValues = {
        employment_status: 'Unemployed'
      };

      const result = checkFieldAccess('employer name', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.reason).toBe('field_hidden');
      expect(result.required_fields?.[0].field_id).toBe('employment_status');
      expect(result.required_fields?.[0].required_value).toBe('Employed');
    });
  });

  describe('getDependencyChain', () => {
    it('should return empty array for independent fields', () => {
      const field = mockSchema.fields.find(f => f.id === 'marital_status')!;
      const fieldValues = {};

      const chain = getDependencyChain(field, mockSchema, fieldValues);

      expect(chain).toEqual([]);
    });

    it('should return single dependency for first-level conditional', () => {
      const field = mockSchema.fields.find(f => f.id === 'spouse_name')!;
      const fieldValues = {};

      const chain = getDependencyChain(field, mockSchema, fieldValues);

      expect(chain.length).toBe(1);
      expect(chain[0].id).toBe('marital_status');
    });

    it('should return full chain for nested conditionals', () => {
      const field = mockSchema.fields.find(f => f.id === 'spouse_birth_date')!;
      const fieldValues = {};

      const chain = getDependencyChain(field, mockSchema, fieldValues);

      // spouse_birth_date -> spouse_name -> marital_status
      expect(chain.length).toBe(2);
      expect(chain[0].id).toBe('spouse_name');
      expect(chain[1].id).toBe('marital_status');
    });
  });

  describe('Real-world scenarios', () => {
    it('should guide Gemini from locked field to required field', () => {
      // Scenario: Gemini tries to get spouse name before asking about marital status
      const fieldValues = {}; // Nothing filled yet

      const result = checkFieldAccess('spouse name', mockSchema, fieldValues);

      expect(result.accessible).toBe(false);
      expect(result.message).toContain('marital status');
      expect(result.message).toContain('Married');

      // Gemini should now know to ask about 'marital status' first
      expect(result.required_fields?.[0].spoken_name).toBe('marital status');
    });

    it('should allow access after user fills required field', () => {
      // Scenario: User fills marital status, now spouse name is accessible
      const fieldValues = {
        marital_status: 'Married'
      };

      const result = checkFieldAccess('spouse name', mockSchema, fieldValues);

      expect(result.accessible).toBe(true);
      // Gemini can now ask user to fill spouse name
    });

    it('should handle complex conditional chains', () => {
      // Scenario: Gemini tries to jump to spouse_birth_date
      const fieldValues = {
        marital_status: 'Single' // Not married
      };

      const spouseDateResult = checkFieldAccess('spouse birth date', mockSchema, fieldValues);

      expect(spouseDateResult.accessible).toBe(false);
      // Should direct to spouse_name, which will then direct to marital_status
      expect(spouseDateResult.required_fields?.[0].spoken_name).toBe('spouse name');
    });
  });
});

// P3.1 (bd h76m.8): a COMPOSITE-gated field must behave correctly in the
// voice locked-field path -- the exit-criterion-3 coverage. The locked-field
// path is checkFieldAccess (tool-call gating + Gemini explanations) and
// evaluateFieldAvailability (the locked/hidden state webFormConnection reports
// back to the voice AI).
describe('composite-gated fields in the voice locked-field path (bd h76m.8)', () => {
  const compositeSchema: FormSchema = {
    source: 'pdf',
    form_metadata: { title: 'W7-ish', form_number: 'W-7', version: '1.0', language: 'en' },
    sections: [
      { id: 's1', label: 'S1', order: 1, fields: ['grp', 'country', 'detail'] },
    ],
    fields: [
      {
        id: 'grp',
        name: 'Reason for submitting',
        spoken_name: 'reason for submitting',
        type: 'checkbox',
        group_kind: 'checkbox',
        section_id: 's1',
        options: [
          { value: 'e_dependent', label: 'Dependent' },
          { value: 'f_spouse', label: 'Spouse' },
          { value: 'other', label: 'Other' },
        ],
      } as FormField,
      {
        id: 'country',
        name: 'Country of citizenship',
        spoken_name: 'country of citizenship',
        type: 'text',
        section_id: 's1',
      } as FormField,
      {
        // Shown when 'other' is ticked AND country is not USA:
        // all_of[includes other] + none_of[equals USA].
        id: 'detail',
        name: 'Other detail',
        spoken_name: 'other detail',
        type: 'text',
        section_id: 's1',
        show_if: {
          all_of: [{ field: 'grp', operator: 'includes', value: 'other' }],
          none_of: [{ field: 'country', operator: 'equals', value: 'USA' }],
        },
      } as FormField,
    ],
  } as FormSchema;

  it('checkFieldAccess blocks the field while the composite is unmet and lists EVERY trigger', () => {
    const result = checkFieldAccess('other detail', compositeSchema, {
      grp: ['e_dependent'],
      country: 'Canada',
    });

    expect(result.accessible).toBe(false);
    expect(result.reason).toBe('field_hidden');
    // Both atoms' triggers surface for the voice explanation.
    expect(result.required_fields?.map(f => f.field_id)).toEqual(['grp', 'country']);
    expect(result.message).toContain("'reason for submitting'");
    expect(result.message).toContain('1 more condition');
  });

  it('checkFieldAccess opens the field when the whole composite is satisfied', () => {
    const result = checkFieldAccess('other detail', compositeSchema, {
      grp: ['other', 'e_dependent'],
      country: 'Canada',
    });
    expect(result.accessible).toBe(true);
  });

  it('checkFieldAccess keeps the field blocked when none_of trips', () => {
    const result = checkFieldAccess('other detail', compositeSchema, {
      grp: ['other'],
      country: 'USA',
    });
    expect(result.accessible).toBe(false);
    expect(result.reason).toBe('field_hidden');
  });

  it('evaluateFieldAvailability reports locked with a first-trigger reason, then available when met', () => {
    const detail = compositeSchema.fields.find(f => f.id === 'detail')!;

    const locked = evaluateFieldAvailability(
      detail,
      { grp: { value: [] }, country: { value: 'Canada' } } as any,
      compositeSchema,
    );
    expect(locked.availability).toBe('locked');
    expect(locked.lockedReason).toContain("'reason for submitting'");
    expect(locked.lockedReason).toContain("select 'other'");
    expect(locked.lockedReason).toContain('1 more condition');

    const available = evaluateFieldAvailability(
      detail,
      { grp: { value: ['other'] }, country: { value: 'Canada' } } as any,
      compositeSchema,
    );
    expect(available.availability).toBe('available');
  });

  it('getDependencyChain walks every composite trigger and survives cycles', () => {
    const detail = compositeSchema.fields.find(f => f.id === 'detail')!;
    const deps = getDependencyChain(detail, compositeSchema, {});
    expect(deps.map(d => d.id).sort()).toEqual(['country', 'grp']);

    // Cycle: a shows-if b, b shows-if a -- must terminate, not recurse forever.
    const cyclic: FormSchema = {
      ...compositeSchema,
      fields: [
        { id: 'a', name: 'A', spoken_name: 'a', type: 'text', section_id: 's1',
          show_if: { field: 'b', operator: 'is_not_empty' } } as FormField,
        { id: 'b', name: 'B', spoken_name: 'b', type: 'text', section_id: 's1',
          show_if: { field: 'a', operator: 'is_not_empty' } } as FormField,
      ],
    } as FormSchema;
    const cycleDeps = getDependencyChain(cyclic.fields[0], cyclic, {});
    expect(cycleDeps.map(d => d.id)).toEqual(['b']);
  });
});
