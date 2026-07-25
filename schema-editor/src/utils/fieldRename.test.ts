/**
 * Field-id rename retargeting (bd polyglot-pdf-0x10.1).
 *
 * The id is the schema's join key: a rename must atomically retarget other
 * fields' show_if/require_if (legacy AND composite shapes), section-level
 * show_if, section fields[] membership, copy_to lists, and the untyped
 * supplements[].fields pass-through -- and the saved serialization must
 * carry no trace of the old id.
 */
import { describe, it, expect } from 'vitest';
import {
  recoverSelectionAfterVanish, renameBlockReason, renameFieldId,
} from './fieldRename';
import { stripEditorState } from './fieldGrouping';
import type { FormSchema, FormField } from '../types/schema';

function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: id, section_id: 'sec-1', read_only: false,
    ...extra,
  } as unknown as FormField;
}

function schemaWith(fields: FormField[], extra: Record<string, unknown> = {}): FormSchema {
  return {
    source: 'pdf',
    form_metadata: {
      title: 'T', form_number: 'T', total_widgets: fields.length,
      total_fields: fields.length, version: '1', language: 'en',
    },
    parts: [],
    sections: [
      { id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) },
    ],
    fields,
    ...extra,
  } as unknown as FormSchema;
}

describe('renameBlockReason (bd 0x10.1)', () => {
  const schema = schemaWith([field('a'), field('b')]);

  it('blocks empty, duplicate and non-slug ids with readable reasons', () => {
    expect(renameBlockReason(schema, 'a', '')).toMatch(/empty/i);
    expect(renameBlockReason(schema, 'a', '   ')).toMatch(/empty/i);
    expect(renameBlockReason(schema, 'a', 'b')).toMatch(/already exists/);
    expect(renameBlockReason(schema, 'a', 'Has Spaces')).toMatch(/snake_case/);
    expect(renameBlockReason(schema, 'a', '9starts_with_digit')).toMatch(/snake_case/);
    expect(renameBlockReason(schema, 'a', 'kebab-case')).toMatch(/snake_case/);
  });

  it('allows a clean slug and treats the unchanged id as a no-op', () => {
    expect(renameBlockReason(schema, 'a', 'relationship_to_us_person')).toBeNull();
    expect(renameBlockReason(schema, 'a', 'a')).toBeNull();
  });
});

describe('renameFieldId retargets every reference (bd 0x10.1)', () => {
  it('retargets legacy and composite conditions, section show_if, section membership and copy_to in one pass', () => {
    const schema = schemaWith([
      field('treaty_country'),
      field('legacy_dep', {
        show_if: { field: 'treaty_country', operator: 'equals', value: 'x' },
      }),
      field('composite_dep', {
        require_if: {
          all_of: [
            { field: 'treaty_country', operator: 'is_not_empty' },
            { field: 'legacy_dep', operator: 'equals', value: 'y' },
          ],
        },
      }),
      field('copier', { copy_to: ['treaty_country', 'legacy_dep'] }),
    ]);
    (schema.sections[0] as any).show_if = {
      field: 'treaty_country', operator: 'is_not_empty',
    };

    const out = renameFieldId(schema, 'treaty_country', 'relationship_to_us_person');

    expect(out.fields[0].id).toBe('relationship_to_us_person');
    expect((out.fields[1] as any).show_if.field).toBe('relationship_to_us_person');
    const atoms = (out.fields[2] as any).require_if.all_of;
    expect(atoms[0].field).toBe('relationship_to_us_person');
    expect(atoms[1].field).toBe('legacy_dep'); // untouched sibling atom
    expect((out.fields[3] as any).copy_to).toEqual([
      'relationship_to_us_person', 'legacy_dep',
    ]);
    expect(out.sections[0].fields).toEqual([
      'relationship_to_us_person', 'legacy_dep', 'composite_dep', 'copier',
    ]);
    expect((out.sections[0] as any).show_if.field).toBe('relationship_to_us_person');
  });

  it('retargets address_fields slot references (untyped pass-through)', () => {
    const schema = schemaWith([
      field('addr_group', {
        address_fields: {
          street: 'street_field', apt: null, city: 'city_field',
          state: 'state_field', zip: 'zip_field',
        },
      } as unknown as Partial<FormField>),
      field('street_field'),
    ]);
    const out = renameFieldId(schema, 'street_field', 'mailing_street');
    expect((out.fields[0] as any).address_fields).toEqual({
      street: 'mailing_street', apt: null, city: 'city_field',
      state: 'state_field', zip: 'zip_field',
    });
    expect(out.fields[1].id).toBe('mailing_street');
    // Renaming a field the map does NOT reference leaves the map untouched
    // (same object -- no gratuitous rewrite).
    const out2 = renameFieldId(schema, 'addr_group', 'address_group');
    expect((out2.fields[0] as any).address_fields).toBe(
      (schema.fields[0] as any).address_fields,
    );
  });

  it('retargets the untyped supplements[].fields pass-through', () => {
    const schema = schemaWith([field('a'), field('b')], {
      supplements: [
        { id: 's', name: 'S', purpose: 'S', fields: ['a', 'b'] },
      ],
    });
    const out = renameFieldId(schema, 'a', 'renamed_a');
    expect((out as any).supplements[0].fields).toEqual(['renamed_a', 'b']);
  });

  it('drops an in-session merge stash that mentions the old id (ungroup falls back to reconstruction)', () => {
    const grp = field('grp', {
      type: 'checkbox_group',
      options: [
        { value: 'x', label: 'X', pdf_field_name: 'x[0]' },
        { value: 'y', label: 'Y', pdf_field_name: 'y[0]' },
      ],
    });
    (grp as any)._ungroup = {
      sources: [{ id: 'grp' }, { id: 'other' }],
      rewrites: [], sections: [],
    };
    const schema = schemaWith([grp, field('dep')]);
    const out = renameFieldId(schema, 'grp', 'race_group');
    expect(out.fields[0].id).toBe('race_group');
    expect((out.fields[0] as any)._ungroup).toBeUndefined();
    // A stash NOT mentioning the renamed id survives.
    const out2 = renameFieldId(schema, 'dep', 'dep_renamed');
    expect((out2.fields[0] as any)._ungroup).toBeDefined();
  });

  it('exit criterion 3: the real save serialization carries zero references to the old id', () => {
    // Display/PDF properties deliberately do NOT share the id text: name /
    // spoken_name / pdf_field_name must NOT be touched by an id rename (the
    // PDF widget binding travels with the field), so the whole-JSON grep
    // below is exact -- any surviving "old_name" IS a missed id reference.
    const schema = schemaWith([
      field('old_name', {
        name: 'Display Name', spoken_name: 'display name',
        pdf_field_name: 'topmostSubform.widget[7]',
      }),
      field('dep', {
        show_if: { any_of: [{ field: 'old_name', operator: 'is_not_empty' }] },
        copy_to: ['old_name'],
      }),
      // copy_from: the untyped single-id twin of copy_to (real i-90 shape).
      field('header_repeat', { copy_from: 'old_name' } as unknown as Partial<FormField>),
    ], {
      supplements: [{ id: 's', name: 'S', purpose: 'S', fields: ['old_name'] }],
    });
    (schema.sections[0] as any).show_if = { field: 'old_name', operator: 'is_not_empty' };

    const out = renameFieldId(schema, 'old_name', 'new_name');
    const saved = JSON.stringify(stripEditorState(out));
    expect(saved).not.toContain('"old_name"');
    expect(saved).toContain('"new_name"');
    // The PDF widget binding travelled untouched.
    expect((out.fields[0] as any).pdf_field_name).toBe('topmostSubform.widget[7]');
  });

  it('is identity on a blocked or unchanged rename', () => {
    const schema = schemaWith([field('a'), field('b')]);
    expect(renameFieldId(schema, 'a', 'a')).toBe(schema);
    expect(renameFieldId(schema, 'a', 'b')).toBe(schema); // duplicate -> untouched
    expect(renameFieldId(schema, 'a', 'Not A Slug')).toBe(schema);
  });
});


describe('recoverSelectionAfterVanish (bd 6hhc nit 2)', () => {
  const fields = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];

  it('recovers by position on a rename (same count, slot exists)', () => {
    // 'b' was selected at index 1 with count 3; an undo renamed it back, so
    // index 1 now holds the restored field -> re-select it.
    expect(recoverSelectionAfterVanish(fields, 1, 3)).toBe('b');
    expect(recoverSelectionAfterVanish(
      [{ id: 'a' }, { id: 'b2' }, { id: 'c' }], 1, 3)).toBe('b2');
  });

  it('DESELECTS on a structural change that dropped a field (count fell)', () => {
    // The fresh-eyes case: a Repair-all / delete reload removed the selected
    // field; count changed, so do NOT re-point to an unrelated field.
    expect(recoverSelectionAfterVanish([{ id: 'a' }, { id: 'c' }], 1, 3))
      .toBeNull();
  });

  it('DESELECTS when a field was added (count rose)', () => {
    expect(recoverSelectionAfterVanish(
      [{ id: 'a' }, { id: 'b' }, { id: 'c' }, { id: 'd' }], 1, 3)).toBeNull();
  });

  it('DESELECTS when the last-known index no longer exists', () => {
    // Same count is required, so a shrink can never leave a valid prevIndex;
    // but guard the bound explicitly.
    expect(recoverSelectionAfterVanish([{ id: 'a' }], 2, 1)).toBeNull();
  });

  it('DESELECTS with no prior index/count (nothing to recover from)', () => {
    expect(recoverSelectionAfterVanish(fields, null, 3)).toBeNull();
    expect(recoverSelectionAfterVanish(fields, 1, null)).toBeNull();
  });
});
