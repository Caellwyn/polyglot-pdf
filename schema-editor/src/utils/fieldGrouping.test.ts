// Tests for the merge/split (group/ungroup) helpers (bd polyglot-pdf-s4dp.1).
// The exit criteria are scenario-driven on W-7's reason_a..e radio group, which
// is not committed to the repo; we reproduce its essential shape (N separate
// checkbox fields, each "check one box") as a fixture here.

import { describe, it, expect } from 'vitest';
import {
  mergeFields,
  ungroupField,
  canUngroup,
  isGroupableField,
} from './fieldGrouping';
import type { FormSchema, FormField } from '../types/schema';

// A separate per-widget checkbox field, the shape extraction emits for a
// "check one box" radio group before consolidation.
function reasonField(letter: string): FormField {
  return {
    id: `reason_${letter}`,
    name: `Reason ${letter.toUpperCase()}`,
    type: 'checkbox',
    section_id: 'reason',
    pdf_field_name: `form1[0].#subform[0].reason_${letter}[0]`,
    read_only: false,
    required: false,
    spoken_name: `reason ${letter}`,
  };
}

function w7Schema(): FormSchema {
  const letters = ['a', 'b', 'c', 'd', 'e'];
  const fields = letters.map(l => reasonField(l));
  return {
    source: 'pdf',
    form_metadata: {
      title: 'W-7',
      form_number: 'W-7',
      total_widgets: 5,
      total_fields: 5,
      version: '1',
      language: 'en',
    },
    parts: [],
    sections: [
      { id: 'reason', label: 'Reason', order: 0, fields: letters.map(l => `reason_${l}`) },
    ],
    fields,
  };
}

describe('isGroupableField', () => {
  it('accepts radio and checkbox, rejects text', () => {
    expect(isGroupableField({ type: 'checkbox' } as FormField)).toBe(true);
    expect(isGroupableField({ type: 'radio' } as FormField)).toBe(true);
    expect(isGroupableField({ type: 'text' } as FormField)).toBe(false);
  });

  it('rejects an already-consolidated field (has options) so a re-merge cannot drop its options', () => {
    expect(isGroupableField({
      type: 'radio',
      options: [{ value: 'a', label: 'A', pdf_field_name: 'a[0]' }],
    } as FormField)).toBe(false);
  });
});

describe('mergeFields (crit 1: group W-7 reason_a..e)', () => {
  it('merges 5 separate fields into ONE radio with 5 options, each carrying its pdf_field_name', () => {
    const schema = w7Schema();
    const ids = ['reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e'];
    const { schema: merged, mergedFieldId } = mergeFields(schema, ids);

    // Five source fields collapse to one.
    expect(merged.fields).toHaveLength(1);
    const f = merged.fields[0];
    expect(f.id).toBe('reason_a'); // first selected is the primary
    expect(mergedFieldId).toBe('reason_a');
    expect(f.type).toBe('radio');

    // Exactly five options, each carrying its source widget's pdf_field_name.
    expect(f.options).toHaveLength(5);
    for (let i = 0; i < ids.length; i++) {
      expect(f.options![i].pdf_field_name).toBe(
        `form1[0].#subform[0].reason_${ids[i].slice(-1)}[0]`
      );
      expect(f.options![i].value).toBe(ids[i]);
    }

    // consolidated_widgets mirrors the option values.
    expect(f.consolidated_widgets).toEqual(ids);
  });

  it('drops merged-away ids from the section field list (leaving only the primary)', () => {
    const schema = w7Schema();
    const { schema: merged } = mergeFields(schema, [
      'reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e',
    ]);
    expect(merged.sections[0].fields).toEqual(['reason_a']);
  });

  it('respects selection order for the primary', () => {
    const schema = w7Schema();
    const { schema: merged, mergedFieldId } = mergeFields(schema, [
      'reason_c', 'reason_a', 'reason_b',
    ]);
    expect(mergedFieldId).toBe('reason_c');
    expect(merged.fields.find(f => f.id === 'reason_c')!.options![0].value).toBe('reason_c');
  });

  it('is a no-op when fewer than 2 groupable fields are selected', () => {
    const schema = w7Schema();
    const { schema: out } = mergeFields(schema, ['reason_a']);
    expect(out).toBe(schema);
  });

  it('ignores non-groupable (text) fields in the selection', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'note', name: 'Note', type: 'text', section_id: 'reason',
      pdf_field_name: 'note[0]', read_only: false, required: false,
    });
    // Only one groupable field + one text field -> not enough to merge.
    const { schema: out } = mergeFields(schema, ['reason_a', 'note']);
    expect(out).toBe(schema);
  });
});

describe('ungroupField (crit 2: reversible)', () => {
  it('restores the separate per-widget fields after a merge', () => {
    const schema = w7Schema();
    const ids = ['reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e'];
    const { schema: merged } = mergeFields(schema, ids);
    expect(merged.fields).toHaveLength(1);

    const unmerged = ungroupField(merged, 'reason_a');

    // Five separate fields again, each with its widget's pdf_field_name.
    expect(unmerged.fields).toHaveLength(5);
    for (const id of ids) {
      const f = unmerged.fields.find(ff => ff.id === id);
      expect(f).toBeDefined();
      expect(f!.options).toBeUndefined();
      expect(f!.pdf_field_name).toBe(
        `form1[0].#subform[0].reason_${id.slice(-1)}[0]`
      );
    }

    // The section slot is restored to the full set, in order.
    expect(unmerged.sections[0].fields).toEqual(ids);
  });

  it('is a no-op on a field that is not un-groupable (single option)', () => {
    const schema = w7Schema();
    schema.fields = [{
      id: 'solo', name: 'Solo', type: 'radio', section_id: 'reason',
      pdf_field_name: 'solo[0]', read_only: false, required: false,
      options: [{ value: 'a', label: 'A', pdf_field_name: 'a[0]' }],
    }];
    expect(ungroupField(schema, 'solo')).toBe(schema);
  });

  it('is a no-op on a field with options lacking pdf_field_name', () => {
    const schema = w7Schema();
    schema.fields = [{
      id: 'plain', name: 'Plain', type: 'select', section_id: 'reason',
      pdf_field_name: 'plain[0]', read_only: false, required: false,
      options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }],
    }];
    expect(canUngroup(schema.fields[0])).toBe(false);
    expect(ungroupField(schema, 'plain')).toBe(schema);
  });

  it('de-dupes a reconstructed id that would collide with a surviving field', () => {
    const schema = w7Schema();
    // Merge a + b, leaving reason_b's id free... then add a NEW field that
    // already owns the would-be reconstructed id to force a collision.
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    // reason_c..e survive; inject a field that squats on 'reason_b'.
    merged.fields.push({
      id: 'reason_b', name: 'Squatter', type: 'text', section_id: 'reason',
      pdf_field_name: 'squat[0]', read_only: false, required: false,
    });
    const unmerged = ungroupField(merged, 'reason_a');
    // The reconstructed second option must NOT reuse the squatted id.
    const ids = unmerged.fields.map(f => f.id);
    const dupes = ids.filter((id, i) => ids.indexOf(id) !== i);
    expect(dupes).toHaveLength(0);
  });
});

describe('round-trip preserves the primary identity', () => {
  it('merge -> ungroup keeps the primary field id and pdf_field_name', () => {
    const schema = w7Schema();
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const unmerged = ungroupField(merged, 'reason_a');
    const primary = unmerged.fields.find(f => f.id === 'reason_a');
    expect(primary).toBeDefined();
    expect(primary!.pdf_field_name).toBe('form1[0].#subform[0].reason_a[0]');
  });
});

describe('fresh-eyes fixes (bd polyglot-pdf-s4dp.1)', () => {
  it('returns null (never undefined) for mergedFieldId on an empty selection', () => {
    const schema = w7Schema();
    const { schema: out, mergedFieldId } = mergeFields(schema, []);
    expect(out).toBe(schema);
    expect(mergedFieldId).toBeNull();
  });

  it('restores each source field TYPE on un-merge (radio stays radio)', () => {
    const schema = w7Schema();
    // make both sources radio (the degenerate "merge two standalone radios" case)
    schema.fields.forEach(f => { if (f.id.startsWith('reason_')) f.type = 'radio'; });
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const unmerged = ungroupField(merged, 'reason_a');
    expect(unmerged.fields.find(f => f.id === 'reason_a')!.type).toBe('radio');
    expect(unmerged.fields.find(f => f.id === 'reason_b')!.type).toBe('radio');
  });

  it('preserves a mixed radio+checkbox merge through un-merge', () => {
    const schema = w7Schema();
    schema.fields.find(f => f.id === 'reason_a')!.type = 'radio';
    schema.fields.find(f => f.id === 'reason_b')!.type = 'checkbox';
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const unmerged = ungroupField(merged, 'reason_a');
    expect(unmerged.fields.find(f => f.id === 'reason_a')!.type).toBe('radio');
    expect(unmerged.fields.find(f => f.id === 'reason_b')!.type).toBe('checkbox');
  });

  it('rewrites show_if references to a merged-away field onto the primary', () => {
    const schema = w7Schema();
    // an unrelated field shows only when reason_b (about to be merged away) is set
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: 'is_checked' },
    });
    schema.sections[0].fields.push('detail');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const detail = merged.fields.find(f => f.id === 'detail')!;
    // reason_b no longer exists; the reference now points at the primary reason_a
    expect(detail.show_if!.field).toBe('reason_a');
  });

  it('rewrites controls_fields references to a merged-away field onto the primary (de-duped)', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'trigger', name: 'Trigger', type: 'checkbox', section_id: 'reason',
      pdf_field_name: 'trigger[0]', read_only: false, required: false,
      controls_fields: [{ operator: 'is_checked', value: true, shows: ['reason_a', 'reason_b', 'reason_c'] }],
    });
    schema.sections[0].fields.push('trigger');

    // merge a+b -> both map to reason_a; the shows list must de-dupe to [reason_a, reason_c]
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const trigger = merged.fields.find(f => f.id === 'trigger')!;
    expect(trigger.controls_fields![0].shows).toEqual(['reason_a', 'reason_c']);
  });

  it('records source_type on each merged option', () => {
    const schema = w7Schema();
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const f = merged.fields[0];
    expect(f.options!.every(o => o.source_type === 'checkbox')).toBe(true);
  });
});
