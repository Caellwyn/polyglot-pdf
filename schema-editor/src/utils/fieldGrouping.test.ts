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
  mergeBlockReason,
  stripEditorState,
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
  it('accepts radio and checkbox with a pdf_field_name, rejects text', () => {
    expect(isGroupableField({ type: 'checkbox', pdf_field_name: 'c[0]' } as FormField)).toBe(true);
    expect(isGroupableField({ type: 'radio', pdf_field_name: 'r[0]' } as FormField)).toBe(true);
    expect(isGroupableField({ type: 'text', pdf_field_name: 't[0]' } as FormField)).toBe(false);
  });

  it('rejects a radio/checkbox WITHOUT a pdf_field_name (would be unfillable + non-reversible)', () => {
    expect(isGroupableField({ type: 'checkbox' } as FormField)).toBe(false);
    expect(isGroupableField({ type: 'checkbox', pdf_field_name: '' } as FormField)).toBe(false);
  });

  it('rejects an already-consolidated field (has options) so a re-merge cannot drop its options', () => {
    expect(isGroupableField({
      type: 'radio', pdf_field_name: 'r[0]',
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

  it('de-dupes a reconstructed id that would collide with a surviving field (fallback path)', () => {
    // A hand-authored consolidated field (NO stash) takes the reconstruction
    // path, where option.value -> id can collide with a surviving field id.
    const schema = w7Schema();
    schema.fields = [
      {
        id: 'race', name: 'Race', type: 'checkbox', section_id: 'reason',
        pdf_field_name: 'race[0]', read_only: false, required: false,
        options: [
          { value: 'race', label: 'A', pdf_field_name: 'a[0]' },
          { value: 'white', label: 'B', pdf_field_name: 'b[0]' },
        ],
      },
      // a surviving field squats on the would-be reconstructed id 'white'
      {
        id: 'white', name: 'Squatter', type: 'text', section_id: 'reason',
        pdf_field_name: 'squat[0]', read_only: false, required: false,
      },
    ];
    schema.sections[0].fields = ['race', 'white'];
    const unmerged = ungroupField(schema, 'race');
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

  it('rewrites show_if with CORRECT runtime semantics (is_checked on a widget -> equals option value)', () => {
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
    // reason_b is now an option of the merged radio reason_a; "is this widget
    // checked" becomes "radio equals reason_b's option value" -- a bare id swap
    // would leave is_checked, which never fires against a radio (Codex PR #256).
    expect(detail.show_if).toEqual({ field: 'reason_a', operator: 'equals', value: 'reason_b' });
  });

  it('restores the original show_if on un-merge (lossless inverse of the rewrite)', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: 'is_checked' },
    });
    schema.sections[0].fields.push('detail');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const unmerged = ungroupField(merged, 'reason_a');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'reason_b', operator: 'is_checked' });
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

  it('does NOT rewrite an untouched controls_fields array when only show_if changed', () => {
    const schema = w7Schema();
    const controls = [{ operator: 'is_checked' as const, value: true, shows: ['reason_c'] }];
    schema.fields.push({
      id: 'mixed', name: 'Mixed', type: 'text', section_id: 'reason',
      pdf_field_name: 'mixed[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: 'is_checked' }, // points at merged-away
      controls_fields: controls, // points only at reason_c (survives)
    });
    schema.sections[0].fields.push('mixed');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const mixed = merged.fields.find(f => f.id === 'mixed')!;
    expect(mixed.show_if!.field).toBe('reason_a'); // show_if rewritten
    expect(mixed.controls_fields).toBe(controls); // untouched array kept by reference
  });

  it('rewrites copy_to references to a merged-away field onto the primary', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'mirror', name: 'Mirror', type: 'text', section_id: 'reason',
      pdf_field_name: 'mirror[0]', read_only: false, required: false,
      copy_to: ['reason_b', 'reason_c'],
    });
    schema.sections[0].fields.push('mirror');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const mirror = merged.fields.find(f => f.id === 'mirror')!;
    expect(mirror.copy_to).toEqual(['reason_a', 'reason_c']);
  });
});

describe('Codex PR #256 fixes', () => {
  it('rejects a cross-section merge (would move a field across the hierarchy)', () => {
    const schema = w7Schema();
    // move reason_b into a different section
    schema.sections.push({ id: 'other', label: 'Other', order: 1, fields: [] });
    const rb = schema.fields.find(f => f.id === 'reason_b')!;
    rb.section_id = 'other';
    schema.sections[0].fields = schema.sections[0].fields.filter(id => id !== 'reason_b');
    schema.sections[1].fields = ['reason_b'];

    expect(mergeBlockReason(schema, ['reason_a', 'reason_b'])).toBe('cross-section');
    expect(mergeFields(schema, ['reason_a', 'reason_b']).schema).toBe(schema); // no-op
  });

  it('rejects merging a field without a pdf_field_name', () => {
    const schema = w7Schema();
    schema.fields.find(f => f.id === 'reason_b')!.pdf_field_name = '';
    expect(mergeBlockReason(schema, ['reason_a', 'reason_b'])).toBe('missing-pdf-name');
    expect(mergeFields(schema, ['reason_a', 'reason_b']).schema).toBe(schema);
  });

  it('preserves ALL source metadata (help/validation/hidden) through merge -> un-merge', () => {
    const schema = w7Schema();
    const rb = schema.fields.find(f => f.id === 'reason_b')!;
    rb.help = { instructions: 'pick me' };
    rb.validation = { pattern: '^x$' };
    rb.hidden = true;

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const unmerged = ungroupField(merged, 'reason_a');
    const restored = unmerged.fields.find(f => f.id === 'reason_b')!;
    expect(restored.help).toEqual({ instructions: 'pick me' });
    expect(restored.validation).toEqual({ pattern: '^x$' });
    expect(restored.hidden).toBe(true);
  });

  it('preserves a non-primary source field own controls_fields through round-trip', () => {
    const schema = w7Schema();
    const rb = schema.fields.find(f => f.id === 'reason_b')!;
    rb.controls_fields = [{ operator: 'is_checked', value: true, shows: ['reason_e'] }];

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    // the merged radio carries reason_b's rule, re-keyed to fire on its option value
    const mergedRule = merged.fields[0].controls_fields!.find(c => c.value === 'reason_b');
    expect(mergedRule).toBeDefined();
    expect(mergedRule!.operator).toBe('equals');
    expect(mergedRule!.shows).toEqual(['reason_e']);

    // un-merge restores reason_b with its original controls intact
    const unmerged = ungroupField(merged, 'reason_a');
    const restored = unmerged.fields.find(f => f.id === 'reason_b')!;
    expect(restored.controls_fields).toEqual([{ operator: 'is_checked', value: true, shows: ['reason_e'] }]);
  });

  it('un-groups a hand-authored CHECKBOX group (no stash, fallback path)', () => {
    const schema = w7Schema();
    schema.fields = [{
      id: 'p3_race', name: 'Race', type: 'checkbox', section_id: 'reason',
      pdf_field_name: 'p3_race[0]', read_only: false, required: false,
      options: [
        { value: 'white', label: 'White', pdf_field_name: 'white[0]' },
        { value: 'asian', label: 'Asian', pdf_field_name: 'asian[0]' },
      ],
    }];
    schema.sections[0].fields = ['p3_race'];
    expect(canUngroup(schema.fields[0])).toBe(true);
    const unmerged = ungroupField(schema, 'p3_race');
    expect(unmerged.fields).toHaveLength(2);
    expect(unmerged.fields.map(f => f.pdf_field_name)).toEqual(['white[0]', 'asian[0]']);
  });
});

describe('Opus fallback review fixes', () => {
  it("remaps the PRIMARY's own control TARGET arrays referencing a merged-away sibling", () => {
    const schema = w7Schema();
    const ra = schema.fields.find(f => f.id === 'reason_a')!; // the primary
    // a control targeting a merged-away sibling (reason_b) + a survivor (reason_e)
    ra.controls_fields = [{ operator: 'is_checked', value: true, shows: ['reason_b', 'reason_e'] }];

    const merged = mergeFields(schema, ['reason_a', 'reason_b']).schema;
    const f = merged.fields.find(ff => ff.id === 'reason_a')!;
    // target array remapped (reason_b -> reason_a, de-duped), reason_e kept
    expect(f.controls_fields![0].shows).toEqual(['reason_a', 'reason_e']);
  });

  it("remaps a carried non-primary control's TARGET arrays (no dangling sibling)", () => {
    const schema = w7Schema();
    schema.fields.find(f => f.id === 'reason_b')!.controls_fields = [
      { operator: 'is_checked', value: true, shows: ['reason_c'] }, // reason_c also merged away
    ];
    const merged = mergeFields(schema, ['reason_a', 'reason_b', 'reason_c']).schema;
    const carried = merged.fields[0].controls_fields!.find(c => c.value === 'reason_b')!;
    // reason_c was merged away -> remapped to the primary, not left dangling
    expect(carried.shows).toEqual(['reason_a']);
  });

  it('stripEditorState removes the _ungroup stash from a saved schema', () => {
    const schema = w7Schema();
    const merged = mergeFields(schema, ['reason_a', 'reason_b']).schema;
    // the in-memory merged field carries the stash...
    expect((merged.fields[0] as unknown as Record<string, unknown>)._ungroup).toBeDefined();
    // ...but the save-time copy does not.
    const stripped = stripEditorState(merged);
    expect((stripped.fields[0] as unknown as Record<string, unknown>)._ungroup).toBeUndefined();
    // original schema object is untouched (stash still present for in-session ungroup)
    expect((merged.fields[0] as unknown as Record<string, unknown>)._ungroup).toBeDefined();
  });

  it('stripEditorState is a no-op (same reference) when no stash is present', () => {
    const schema = w7Schema();
    expect(stripEditorState(schema)).toBe(schema);
  });

  // bd polyglot-pdf-v444: the fallback (no-stash) ungroup must remap dependents of
  // the consolidated field onto the reconstructed split fields, else they dangle.
  function raceSchemaWithDependent(): FormSchema {
    const schema = w7Schema();
    schema.fields = [
      {
        id: 'p3_race', name: 'Race', type: 'radio', section_id: 'reason',
        pdf_field_name: 'p3_race[0]', read_only: false, required: false,
        options: [
          { value: 'p3_race', label: 'White', pdf_field_name: 'white[0]', source_type: 'checkbox' },
          { value: 'asian', label: 'Asian', pdf_field_name: 'asian[0]', source_type: 'checkbox' },
        ],
      },
      // a dependent that should show only when the (non-primary) 'asian' option is set
      {
        id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
        pdf_field_name: 'detail[0]', read_only: false, required: false,
        show_if: { field: 'p3_race', operator: 'equals', value: 'asian' },
      },
    ];
    schema.sections[0].fields = ['p3_race', 'detail'];
    return schema;
  }

  it('remaps a dependent show_if onto the reconstructed NON-PRIMARY option field (is_checked)', () => {
    const schema = raceSchemaWithDependent();
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // the 'asian' option reconstructs to a field with id 'asian'; the dependent
    // now tests that standalone field is checked, not the gone consolidated id.
    expect(detail.show_if).toEqual({ field: 'asian', operator: 'is_checked' });
    // and the target field actually exists post-split (resolvable, not dangling)
    expect(unmerged.fields.some(f => f.id === 'asian')).toBe(true);
  });

  it('remaps a dependent show_if onto the reconstructed PRIMARY option field (is_checked)', () => {
    const schema = raceSchemaWithDependent();
    // point the dependent at the primary option value instead
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'equals', value: 'p3_race',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // primary option reconstructs to id == fieldId ('p3_race')
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'is_checked' });
  });

  it('retargets a whole-group show_if (is_checked, no specific option) to the primary so it never dangles', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'is_checked',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'is_checked' });
    expect(unmerged.fields.some(f => f.id === detail.show_if!.field)).toBe(true);
  });

  // A whole-group "is the group populated" condition must NORMALIZE to an operator
  // that fires correctly on a standalone boolean checkbox -- preserving the
  // original `not_equals ''` / `is_not_empty` would be permanently TRUE on an
  // unchecked checkbox (false !== '' is always true), showing the dependent
  // forever. Real i-90 case: p1_line6c_aptsteflrnumber's `not_equals ''` on the
  // consolidated p1_unit_type6c_unit (bd polyglot-pdf-v444, fresh-eyes finding).
  it("normalizes a whole-group not_equals '' to is_checked on the primary (not permanently-true)", () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'not_equals', value: '',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'is_checked' });
  });

  it('normalizes a whole-group is_not_empty to is_checked on the primary', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'is_not_empty',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'is_checked' });
  });

  it('normalizes a whole-group is_empty to is_empty on the primary', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'is_empty',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'is_empty' });
  });

  it('leaves an unmatched non-empty equals as equals on the primary (stays unsatisfiable -> hidden, not spuriously shown)', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'equals', value: 'no_such_option',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // retargeted to a real field, operator preserved; equals a string on a boolean
    // checkbox is never true -> field stays hidden (correct "no such option").
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'equals', value: 'no_such_option' });
    expect(unmerged.fields.some(f => f.id === 'p3_race')).toBe(true);
  });

  // Coverage guard for the de-dup + remap interaction (fresh-eyes finding 2): when
  // an option value collides with a surviving field id, the dependent must follow
  // the SUFFIXED reconstructed id, not the bare value.
  it('remaps a dependent onto the DE-DUPED reconstructed id when the option value collides with a survivor', () => {
    const schema = w7Schema();
    schema.fields = [
      {
        id: 'p3_race', name: 'Race', type: 'radio', section_id: 'reason',
        pdf_field_name: 'p3_race[0]', read_only: false, required: false,
        options: [
          { value: 'p3_race', label: 'White', pdf_field_name: 'white[0]', source_type: 'checkbox' },
          { value: 'white', label: 'Asian', pdf_field_name: 'asian[0]', source_type: 'checkbox' },
        ],
      },
      // a surviving field squats on the would-be reconstructed id 'white'
      {
        id: 'white', name: 'Squatter', type: 'text', section_id: 'reason',
        pdf_field_name: 'squat[0]', read_only: false, required: false,
      },
      // dependent gated on the colliding 'white' option value
      {
        id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
        pdf_field_name: 'detail[0]', read_only: false, required: false,
        show_if: { field: 'p3_race', operator: 'equals', value: 'white' },
      },
    ];
    schema.sections[0].fields = ['p3_race', 'white', 'detail'];
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // the 'white' option reconstructs to 'white_1' (squatter holds 'white'); the
    // dependent must point at the suffixed id, and that field must exist.
    expect(detail.show_if).toEqual({ field: 'white_1', operator: 'is_checked' });
    expect(unmerged.fields.some(f => f.id === 'white_1')).toBe(true);
  });

  it('expands a dependent controls_fields target list referencing the consolidated id to all split ids', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = undefined;
    schema.fields.find(f => f.id === 'detail')!.controls_fields = [
      { operator: 'is_checked', value: true, shows: ['p3_race'] },
    ];
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.controls_fields![0].shows).toEqual(['p3_race', 'asian']);
  });

  it('expands a dependent copy_to referencing the consolidated id to all split ids (de-duped)', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = undefined;
    schema.fields.find(f => f.id === 'detail')!.copy_to = ['p3_race', 'detail'];
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.copy_to).toEqual(['p3_race', 'asian', 'detail']);
  });

  it('leaves a dependent that did NOT reference the consolidated field untouched (same reference)', () => {
    const schema = raceSchemaWithDependent();
    const detailBefore = schema.fields.find(f => f.id === 'detail')!;
    detailBefore.show_if = { field: 'some_other', operator: 'equals', value: 'x' };
    const unmerged = ungroupField(schema, 'p3_race');
    const detailAfter = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detailAfter).toBe(detailBefore);
  });

  it("re-keys the PRIMARY's own selection-operator control to equals its option value (round 2)", () => {
    const schema = w7Schema();
    schema.fields.find(f => f.id === 'reason_a')!.controls_fields = [
      { operator: 'is_checked', value: true, shows: ['reason_e'] },
    ];
    const merged = mergeFields(schema, ['reason_a', 'reason_b']).schema;
    const ctrl = merged.fields[0].controls_fields![0];
    // would-never-fire is_checked on a radio -> equals the primary's option value
    expect(ctrl.operator).toBe('equals');
    expect(ctrl.value).toBe('reason_a');
    expect(ctrl.shows).toEqual(['reason_e']);
  });

  it('drops a primary show_if that would become self-referential (round 2)', () => {
    const schema = w7Schema();
    // primary gated on a sibling that is about to become one of its own options
    schema.fields.find(f => f.id === 'reason_a')!.show_if = { field: 'reason_b', operator: 'is_checked' };
    const merged = mergeFields(schema, ['reason_a', 'reason_b']).schema;
    // a self-referential show_if (radio gated on its own value) is unreachable; dropped
    expect(merged.fields[0].show_if).toBeUndefined();
  });
});
