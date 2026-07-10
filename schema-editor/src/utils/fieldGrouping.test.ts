// Tests for the merge/split (group/ungroup) helpers (bd polyglot-pdf-s4dp.1).
// The exit criteria are scenario-driven on W-7's reason_a..e radio group, which
// is not committed to the repo; we reproduce its essential shape (N separate
// checkbox fields, each "check one box") as a fixture here.

import { describe, it, expect } from 'vitest';
import {
  mergeFields,
  ungroupField,
  changeGroupKind,
  canChangeGroupKind,
  canUngroup,
  isGroupableField,
  mergeBlockReason,
  stripEditorState,
  optionValueReferencedBy,
  retargetOptionValueReferences,
} from './fieldGrouping';
import type { FormSchema, FormField, ConditionalDisplay } from '../types/schema';

// These tests construct and assert LEGACY single conditions; show_if's type is
// now the legacy-or-composite union (bd h76m.8), so narrow explicitly at the
// assertion sites.
function asAtom(cond: FormField['show_if']): ConditionalDisplay {
  return cond as ConditionalDisplay;
}

// A faithful local mirror of the runtime's frontend shouldShowField scalar-trigger
// semantics (frontend/src/schema-forms/utils/validation.ts), so these tests pin
// RUNTIME behavior -- whether a remapped condition actually fires -- not just the
// emitted shape. Cross-package import of the real evaluator is avoided (it lives in
// the separate `frontend` package); this covers only the boolean-checkbox operators
// the ungroup remap produces (fresh-eyes r3). An unchecked checkbox is `false`; a
// never-touched one is absent (undefined).
function runtimeShowIf(cond: ConditionalDisplay, values: Record<string, unknown>): boolean {
  const v = values[cond.field];
  switch (cond.operator) {
    case 'is_checked': return v === true;
    case 'is_empty': return v === null || v === undefined || v === '';
    case 'is_not_empty': return v !== null && v !== undefined && v !== '';
    case 'equals': return v === cond.value;
    case 'not_equals': return v !== cond.value;
    default: return true;
  }
}

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
  it('merges W-7 checkboxes into ONE v2 checkbox_group: slug values, per-option pdf, no field-level pdf', () => {
    const schema = w7Schema();
    const ids = ['reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e'];
    const { schema: merged, mergedFieldId } = mergeFields(schema, ids, 'checkbox_group');

    // Five source fields collapse to one.
    expect(merged.fields).toHaveLength(1);
    const f = merged.fields[0];
    expect(f.id).toBe('reason_a'); // first selected is the primary
    expect(mergedFieldId).toBe('reason_a');
    expect(f.type).toBe('checkbox_group');
    // v2: a group carries NO field-level pdf_field_name; identity is per-option.
    expect(f.pdf_field_name).toBeUndefined();
    // consolidated_widgets is a deleted-in-v2 legacy key.
    expect((f as unknown as Record<string, unknown>).consolidated_widgets).toBeUndefined();

    // Exactly five options: SEMANTIC slugs minted from labels, each carrying
    // its source widget's pdf_field_name.
    expect(f.options).toHaveLength(5);
    const slugs = f.options!.map(o => o.value);
    expect(slugs).toEqual(['reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e']
      .map((_, i) => `reason_${'abcde'[i]}`)); // labels 'Reason A'.. -> 'reason_a'..
    expect(new Set(slugs).size).toBe(5); // unique
    for (let i = 0; i < ids.length; i++) {
      expect(f.options![i].pdf_field_name).toBe(
        `form1[0].#subform[0].reason_${ids[i].slice(-1)}[0]`
      );
    }
  });

  it('merges into a radio when the group is single-select', () => {
    const schema = w7Schema();
    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b'], 'radio',
    );
    const f = merged.fields.find(x => x.id === 'reason_a')!;
    expect(f.type).toBe('radio');
    expect(f.pdf_field_name).toBeUndefined();
    expect(f.options!.map(o => o.value)).toEqual(['reason_a', 'reason_b']);
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
    // options[0] is the primary; its slug is minted from label 'Reason C'.
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

  it('merge -> save (strip stash) -> reload -> un-merge yields clean standalone fields (crit 2 fallback)', () => {
    const schema = w7Schema();
    const ids = ['reason_a', 'reason_b', 'reason_c', 'reason_d', 'reason_e'];
    // Merge into a v2 checkbox_group, then SAVE (strip the _ungroup stash) --
    // this is what a reload from disk delivers, forcing the reconstruction
    // fallback (not the lossless in-session path).
    const { schema: merged } = mergeFields(schema, ids, 'checkbox_group');
    const saved = stripEditorState(merged);
    const group = saved.fields.find(f => f.id === 'reason_a')!;
    expect((group as unknown as Record<string, unknown>)._ungroup).toBeUndefined();

    const unmerged = ungroupField(saved, 'reason_a');

    // Every reconstructed field is a clean STANDALONE: a checkbox with NO
    // options and its own pdf_field_name -- the shape a v2 standalone checkbox
    // requires (lint-clean; the backend model accepts it).
    expect(unmerged.fields).toHaveLength(5);
    const reconstructed = unmerged.fields.filter(f => f.section_id === 'reason');
    expect(reconstructed).toHaveLength(5);
    for (const f of reconstructed) {
      expect(f.type).toBe('checkbox');
      expect(f.options).toBeUndefined();
      expect(f.pdf_field_name).toBeTruthy();
      expect(f.pdf_field_name).toMatch(/reason_[a-e]\[0\]$/);
    }
    // The five source widgets are all recovered (identity via pdf_field_name).
    const leaves = reconstructed.map(f => f.pdf_field_name).sort();
    expect(leaves).toEqual(ids.map(id =>
      `form1[0].#subform[0].reason_${id.slice(-1)}[0]`).sort());
  });

  it('un-merges a checkbox_group dependent AFTER save/reload without dangling includes (fresh-eyes P4.2)', () => {
    const schema = w7Schema();
    // A dependent shown when the (soon-to-be-merged) reason_b box is checked.
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: 'is_checked' },
    } as FormField);
    schema.sections[0].fields.push('detail');

    // Merge into a checkbox_group -> the dependent's show_if becomes a
    // membership op (includes <reason_b's slug>) on the group.
    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    const mergedDetail = merged.fields.find(f => f.id === 'detail')!;
    expect(asAtom(mergedDetail.show_if).operator).toBe('includes');

    // SAVE (strip stash) -> RELOAD -> un-merge via the fallback path.
    const saved = stripEditorState(merged);
    const unmerged = ungroupField(saved, 'reason_a');
    const back = unmerged.fields.find(f => f.id === 'detail')!;

    // The membership op must be remapped to a boolean-checkbox condition on the
    // reconstructed reason_b field -- NOT left as a dangling `includes` that a
    // standalone boolean checkbox can never satisfy.
    const atom = asAtom(back.show_if);
    expect(atom.operator).not.toBe('includes');
    expect(atom.operator).toBe('is_checked');
    // It targets a reconstructed standalone field that actually exists.
    expect(unmerged.fields.some(f => f.id === atom.field && f.type === 'checkbox')).toBe(true);
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

  it('records source_type on each merged option', () => {
    const schema = w7Schema();
    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const f = merged.fields[0];
    expect(f.options!.every(o => o.source_type === 'checkbox')).toBe(true);
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
    expect(unmerged.fields.some(f => f.id === asAtom(detail.show_if).field)).toBe(true);
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

  it('maps not_equals <matched option> to `not_equals true` on THAT option field (show unless that option set)', () => {
    const schema = raceSchemaWithDependent();
    // 'asian' is a real option of p3_race; "show unless asian selected"
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'not_equals', value: 'asian',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // exact single-option inverse: not_equals true on the reconstructed 'asian'
    // field. NOT is_empty -- is_empty is false for an explicitly-unchecked (false)
    // checkbox, hiding the dependent forever (fresh-eyes r3, bd cjby).
    expect(detail.show_if).toEqual({ field: 'asian', operator: 'not_equals', value: true });
    expect(unmerged.fields.some(f => f.id === 'asian')).toBe(true);
    // runtime oracle: shown UNLESS asian is checked.
    expect(runtimeShowIf(asAtom(detail.show_if), { asian: true })).toBe(false);  // selected -> hidden
    expect(runtimeShowIf(asAtom(detail.show_if), { asian: false })).toBe(true);  // unchecked -> shown
    expect(runtimeShowIf(asAtom(detail.show_if), {})).toBe(true);                // untouched -> shown
  });

  it('runtime: equals <matched option> -> is_checked shows iff that option is checked', () => {
    const schema = raceSchemaWithDependent(); // detail show_if = equals 'asian'
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    expect(detail.show_if).toEqual({ field: 'asian', operator: 'is_checked' });
    expect(runtimeShowIf(asAtom(detail.show_if), { asian: true })).toBe(true);
    expect(runtimeShowIf(asAtom(detail.show_if), { asian: false })).toBe(false);
  });

  it("excludes an empty-string option value from the option map: not_equals '' stays a whole-group check", () => {
    const schema = w7Schema();
    schema.fields = [
      {
        id: 'grp', name: 'Grp', type: 'radio', section_id: 'reason',
        pdf_field_name: 'grp[0]', read_only: false, required: false,
        options: [
          { value: '', label: 'None', pdf_field_name: 'none[0]', source_type: 'checkbox' },
          { value: 'x', label: 'X', pdf_field_name: 'x[0]', source_type: 'checkbox' },
        ],
      },
      {
        id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
        pdf_field_name: 'detail[0]', read_only: false, required: false,
        show_if: { field: 'grp', operator: 'not_equals', value: '' },
      },
    ];
    schema.sections[0].fields = ['grp', 'detail'];
    const unmerged = ungroupField(schema, 'grp');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // '' did NOT match a specific option -> whole-group "populated" -> is_checked
    // on the primary, NOT is_empty on the ''-valued option's field.
    expect(detail.show_if).toEqual({ field: 'grp', operator: 'is_checked' });
  });

  it('preserves not_equals <non-empty-unmatched> on the primary (replicates the original always-show)', () => {
    const schema = raceSchemaWithDependent();
    schema.fields.find(f => f.id === 'detail')!.show_if = {
      field: 'p3_race', operator: 'not_equals', value: 'no_such_option',
    };
    const unmerged = ungroupField(schema, 'p3_race');
    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    // originally always true (consolidated never holds a non-option value); a bare
    // not_equals <X> on a boolean checkbox is likewise always true -> preserved.
    expect(detail.show_if).toEqual({ field: 'p3_race', operator: 'not_equals', value: 'no_such_option' });
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

  it('drops a primary show_if that would become self-referential (round 2)', () => {
    const schema = w7Schema();
    // primary gated on a sibling that is about to become one of its own options
    schema.fields.find(f => f.id === 'reason_a')!.show_if = { field: 'reason_b', operator: 'is_checked' };
    const merged = mergeFields(schema, ['reason_a', 'reason_b']).schema;
    // a self-referential show_if (radio gated on its own value) is unreachable; dropped
    expect(merged.fields[0].show_if).toBeUndefined();
  });
});

// P3.1 require_if parity (bd h76m.8 + fresh-eyes bd polyglot-pdf-319g): the
// PRIMARY's own require_if must be rewritten/pruned exactly like its show_if,
// and an untouched require_if must survive a merge -> un-merge round trip.
describe('require_if handling in merge/un-merge (bd 319g)', () => {
  it("rewrites the primary's require_if referencing a merged-away sibling (self-ref drops)", () => {
    const schema = w7Schema();
    // Primary reason_a required-when sibling reason_b is checked: post-merge
    // that is self-referential (b is an option of the merged field) -> drop.
    schema.fields[0].require_if = { field: 'reason_b', operator: 'is_checked' };

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const primary = merged.fields.find(f => f.id === 'reason_a')!;
    expect(primary.require_if).toBeUndefined();
    expect(primary.options?.length).toBe(2);
  });

  it("retargets a DEPENDENT's require_if onto the primary and restores it on un-merge", () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'dep', name: 'Dep', type: 'text', section_id: 'reason',
      pdf_field_name: 'dep[0]', read_only: false, required: false,
      require_if: { field: 'reason_b', operator: 'is_checked' },
    } as FormField);
    schema.sections[0].fields.push('dep');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const dep = merged.fields.find(f => f.id === 'dep')!;
    // Selection operator on a merged-away widget -> equals <option value>.
    expect(asAtom(dep.require_if as FormField['show_if']).field).toBe('reason_a');
    expect(asAtom(dep.require_if as FormField['show_if']).operator).toBe('equals');

    const unmerged = ungroupField(merged, 'reason_a');
    const depBack = unmerged.fields.find(f => f.id === 'dep')!;
    expect(depBack.require_if).toEqual({ field: 'reason_b', operator: 'is_checked' });
  });

  it('an untouched require_if survives merge -> un-merge verbatim (sentinel round-trip)', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'bystander', name: 'Bystander', type: 'text', section_id: 'reason',
      pdf_field_name: 'by[0]', read_only: false, required: false,
      // References a field OUTSIDE the merge; also give it a show_if that IS
      // rewritten, so its rewrite record carries had_require_if=true with no
      // recorded require_if -- the sentinel combination that used to clobber.
      require_if: { field: 'reason_e', operator: 'is_checked' },
      show_if: { field: 'reason_b', operator: 'is_checked' },
    } as FormField);
    schema.sections[0].fields.push('bystander');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const mid = merged.fields.find(f => f.id === 'bystander')!;
    expect(mid.require_if).toEqual({ field: 'reason_e', operator: 'is_checked' });

    const unmerged = ungroupField(merged, 'reason_a');
    const back = unmerged.fields.find(f => f.id === 'bystander')!;
    expect(back.require_if).toEqual({ field: 'reason_e', operator: 'is_checked' });
    expect(back.show_if).toEqual({ field: 'reason_b', operator: 'is_checked' });
  });

  it('rewrites composite show_if atoms on a dependent, preserving the composite shape', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'combo', name: 'Combo', type: 'text', section_id: 'reason',
      pdf_field_name: 'combo[0]', read_only: false, required: false,
      show_if: {
        all_of: [{ field: 'reason_b', operator: 'is_checked' }],
        none_of: [{ field: 'reason_e', operator: 'is_checked' }],
      },
    } as FormField);
    schema.sections[0].fields.push('combo');

    const { schema: merged } = mergeFields(schema, ['reason_a', 'reason_b']);
    const combo = merged.fields.find(f => f.id === 'combo')!;
    expect(combo.show_if).toEqual({
      all_of: [{ field: 'reason_a', operator: 'equals', value: 'reason_b' }],
      none_of: [{ field: 'reason_e', operator: 'is_checked' }],
    });

    const unmerged = ungroupField(merged, 'reason_a');
    const comboBack = unmerged.fields.find(f => f.id === 'combo')!;
    expect(comboBack.show_if).toEqual({
      all_of: [{ field: 'reason_b', operator: 'is_checked' }],
      none_of: [{ field: 'reason_e', operator: 'is_checked' }],
    });
  });
});

// Negative selection predicates ("box is UNCHECKED") must convert to the
// negative group reference on merge (Codex PR #310 round 3), else a group gets
// a v2-invalid not_equals / a re-scoped is_empty.
describe('merge converts negative selection predicates (Codex PR #310 round 3)', () => {
  function schemaWithDep(op: ConditionalDisplay['operator'], value?: unknown): FormSchema {
    const schema = w7Schema();
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: op, ...(value !== undefined ? { value } : {}) },
    } as unknown as FormField);
    schema.sections[0].fields.push('detail');
    return schema;
  }

  it('not_equals true on a source checkbox -> not_includes <slug> for a checkbox_group', () => {
    const { schema: merged } = mergeFields(
      schemaWithDep('not_equals', true), ['reason_a', 'reason_b'], 'checkbox_group',
    );
    const atom = asAtom(merged.fields.find(f => f.id === 'detail')!.show_if);
    expect(atom.operator).toBe('not_includes');
    expect(atom.field).toBe('reason_a');
    expect(atom.value).toBe('reason_b'); // slug minted from label 'Reason B'
  });

  it('is_empty on a source checkbox -> not_includes <slug> for a checkbox_group', () => {
    const { schema: merged } = mergeFields(
      schemaWithDep('is_empty'), ['reason_a', 'reason_b'], 'checkbox_group',
    );
    const atom = asAtom(merged.fields.find(f => f.id === 'detail')!.show_if);
    expect(atom.operator).toBe('not_includes');
    expect(atom.value).toBe('reason_b');
  });

  it('radio merge uses not_equals <slug> for the negative predicate', () => {
    const { schema: merged } = mergeFields(
      schemaWithDep('not_equals', true), ['reason_a', 'reason_b'], 'radio',
    );
    const atom = asAtom(merged.fields.find(f => f.id === 'detail')!.show_if);
    expect(atom.operator).toBe('not_equals');
    expect(atom.value).toBe('reason_b');
  });

  it('un-merge inverts not_includes back to a boolean-checkbox condition', () => {
    const { schema: merged } = mergeFields(
      schemaWithDep('not_equals', true), ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    const saved = stripEditorState(merged);
    const unmerged = ungroupField(saved, 'reason_a');
    const atom = asAtom(unmerged.fields.find(f => f.id === 'detail')!.show_if);
    expect(atom.operator).not.toBe('not_includes'); // not dangling on a boolean box
    // negative option predicate inverts to `not_equals true` (unchecked).
    expect(atom.operator).toBe('not_equals');
    expect(atom.value).toBe(true);
  });
});

// require_if must be remapped in the un-merge FALLBACK exactly like show_if
// (bd h76m.10, Codex PR #310 round 2): it was previously left dangling.
describe('un-merge fallback remaps require_if too (Codex PR #310 round 2)', () => {
  it('remaps a checkbox_group dependent require_if after save/reload/un-merge', () => {
    const schema = w7Schema();
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      require_if: { field: 'reason_b', operator: 'is_checked' },
    } as FormField);
    schema.sections[0].fields.push('detail');

    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    expect(asAtom(merged.fields.find(f => f.id === 'detail')!.require_if).operator).toBe('includes');

    const saved = stripEditorState(merged);
    const unmerged = ungroupField(saved, 'reason_a');
    const back = asAtom(unmerged.fields.find(f => f.id === 'detail')!.require_if);
    // No dangling includes on a now-standalone boolean checkbox.
    expect(back.operator).not.toBe('includes');
    expect(back.operator).toBe('is_checked');
    expect(unmerged.fields.some(f => f.id === back.field && f.type === 'checkbox')).toBe(true);
  });
});

// Deleting a group option that a dependent references must be BLOCKED, not
// silently rewritten (bd h76m.10, Codex PR #310 round 2): a silent strip would
// flip a positive-trigger dependent from correctly-hidden to shown-for-all.
describe('optionValueReferencedBy (Codex PR #310)', () => {
  function groupSchema(): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp', 'dep', 'dep2', 'combo'] }],
      fields: [
        { id: 'grp', name: 'Grp', type: 'checkbox_group', section_id: 's1', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'a[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'b[0]' },
          ] },
        { id: 'dep', name: 'Dep', type: 'text', section_id: 's1', read_only: false, required: false,
          show_if: { field: 'grp', operator: 'includes', value: 'b' } },
        { id: 'dep2', name: 'Dep2', type: 'text', section_id: 's1', read_only: false, required: false,
          require_if: { field: 'grp', operator: 'includes', value: 'b' } },
        { id: 'combo', name: 'Combo', type: 'text', section_id: 's1', read_only: false, required: false,
          show_if: { all_of: [{ field: 'grp', operator: 'includes', value: 'a' }] } },
      ],
    } as unknown as FormSchema;
  }

  it('lists every dependent that references the slug via show_if OR require_if', () => {
    expect(optionValueReferencedBy(groupSchema(), 'grp', 'b').sort()).toEqual(['dep', 'dep2']);
  });

  it('finds a reference inside a composite condition', () => {
    expect(optionValueReferencedBy(groupSchema(), 'grp', 'a')).toEqual(['combo']);
  });

  it('returns empty when no dependent references the slug (safe to delete)', () => {
    expect(optionValueReferencedBy(groupSchema(), 'grp', 'no_such_slug')).toEqual([]);
  });

  it('ignores references to the SAME slug on a different trigger field', () => {
    const s = groupSchema();
    s.fields.push({ id: 'other', name: 'Other', type: 'checkbox_group', section_id: 's1',
      read_only: false, required: false,
      options: [{ value: 'b', label: 'B', pdf_field_name: 'ob[0]' }] } as unknown as FormField);
    // 'dep' references grp.b, not other.b -> deleting other.b is unblocked.
    expect(optionValueReferencedBy(s, 'other', 'b')).toEqual([]);
  });

  it('blocks a delete when ONLY a section show_if references the slug (bd qy29)', () => {
    // The 6b7z bead gave sections first-class show_if rewrites; the delete
    // guard must see a section-level reference too, or deleting the option
    // silently strands the section's condition.
    const s = groupSchema();
    // Remove the field-level references so the section is the ONLY referencer.
    s.fields = s.fields.map(f =>
      f.id === 'dep' || f.id === 'dep2' ? { ...f, show_if: undefined, require_if: undefined } : f,
    );
    s.sections = [{
      ...s.sections[0],
      show_if: { field: 'grp', operator: 'includes' as const, value: 'b' },
    }];
    expect(optionValueReferencedBy(s, 'grp', 'b')).toEqual(['section "S1"']);
    // The other slug stays unblocked by the section.
    expect(optionValueReferencedBy(s, 'grp', 'b_no_such')).toEqual([]);
  });

  it('lists field AND section referencers together (fields first)', () => {
    const s = groupSchema();
    s.sections = [{
      ...s.sections[0],
      show_if: { field: 'grp', operator: 'includes' as const, value: 'b' },
    }];
    expect(optionValueReferencedBy(s, 'grp', 'b')).toEqual(['dep', 'dep2', 'section "S1"']);
  });

  it('a section without show_if never blocks (the common case)', () => {
    // groupSchema()'s section carries no show_if; existing expectations hold.
    expect(optionValueReferencedBy(groupSchema(), 'grp', 'no_such_slug')).toEqual([]);
  });

  it('an empty section label falls back to the section id in the message', () => {
    const s = groupSchema();
    s.sections = [{
      ...s.sections[0],
      label: '',
      show_if: { field: 'grp', operator: 'includes' as const, value: 'b' },
    }];
    expect(optionValueReferencedBy(s, 'grp', 'b')).toEqual(['dep', 'dep2', 'section "s1"']);
  });
});

// Renaming a referenced option's LABEL re-mints its slug (bd polyglot-pdf-432u).
// Unlike Remove (blocked by optionValueReferencedBy above), rename cannot block
// per-keystroke -- so every dependent's show_if/require_if that pointed at the
// old slug must be retargeted to the new one atomically with the rename,
// leaving no dangling reference.
describe('retargetOptionValueReferences (bd polyglot-pdf-432u)', () => {
  function groupSchema(): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp', 'dep', 'dep2', 'combo'] }],
      fields: [
        { id: 'grp', name: 'Grp', type: 'checkbox_group', section_id: 's1', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'a[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'b[0]' },
          ] },
        { id: 'dep', name: 'Dep', type: 'text', section_id: 's1', read_only: false, required: false,
          show_if: { field: 'grp', operator: 'includes', value: 'b' } },
        { id: 'dep2', name: 'Dep2', type: 'text', section_id: 's1', read_only: false, required: false,
          require_if: { field: 'grp', operator: 'includes', value: 'b' } },
        { id: 'combo', name: 'Combo', type: 'text', section_id: 's1', read_only: false, required: false,
          show_if: { all_of: [{ field: 'grp', operator: 'includes', value: 'a' }] } },
      ],
    } as unknown as FormSchema;
  }

  it('retargets a legacy show_if AND require_if from the old slug to the new one', () => {
    const s = groupSchema();
    const { fields: next } = retargetOptionValueReferences(s.fields, 'grp', 'b', 'whyte');
    const dep = next.find(f => f.id === 'dep')!;
    const dep2 = next.find(f => f.id === 'dep2')!;
    expect(asAtom(dep.show_if).value).toBe('whyte');
    expect(asAtom(dep2.require_if).value).toBe('whyte');
    // No dependent is left pointing at the stale slug.
    expect(optionValueReferencedBy({ ...s, fields: next }, 'grp', 'b')).toEqual([]);
    expect(optionValueReferencedBy({ ...s, fields: next }, 'grp', 'whyte').sort()).toEqual(['dep', 'dep2']);
  });

  it('retargets a reference inside a composite condition', () => {
    const s = groupSchema();
    const { fields: next } = retargetOptionValueReferences(s.fields, 'grp', 'a', 'alpha');
    const combo = next.find(f => f.id === 'combo')!;
    expect((combo.show_if as { all_of: ConditionalDisplay[] }).all_of[0].value).toBe('alpha');
    expect(optionValueReferencedBy({ ...s, fields: next }, 'grp', 'a')).toEqual([]);
    expect(optionValueReferencedBy({ ...s, fields: next }, 'grp', 'alpha')).toEqual(['combo']);
  });

  it('leaves fields with no reference to the old slug untouched (same object identity)', () => {
    const s = groupSchema();
    const { fields: next } = retargetOptionValueReferences(s.fields, 'grp', 'b', 'whyte');
    const combo = next.find(f => f.id === 'combo')!;
    // 'combo' references grp.a, not grp.b -> retargeting b leaves it untouched.
    expect(combo).toBe(s.fields.find(f => f.id === 'combo'));
  });

  it('ignores references to the SAME slug on a different trigger field', () => {
    const s = groupSchema();
    s.fields.push({ id: 'other', name: 'Other', type: 'checkbox_group', section_id: 's1',
      read_only: false, required: false,
      options: [{ value: 'b', label: 'B', pdf_field_name: 'ob[0]' }] } as unknown as FormField);
    const { fields: next } = retargetOptionValueReferences(s.fields, 'other', 'b', 'whyte');
    // 'dep' references grp.b, not other.b -> unaffected by retargeting other's slug.
    const dep = next.find(f => f.id === 'dep')!;
    expect(asAtom(dep.show_if).value).toBe('b');
  });

  it('is a no-op (same array identity) when the slug is unchanged', () => {
    const s = groupSchema();
    expect(retargetOptionValueReferences(s.fields, 'grp', 'b', 'b').fields).toBe(s.fields);
  });

  it('is a no-op (same array identity) when no dependent references the old slug', () => {
    const s = groupSchema();
    expect(retargetOptionValueReferences(s.fields, 'grp', 'no_such_slug', 'whatever').fields).toBe(s.fields);
  });

  it('also retargets a SECTION show_if referencing the renamed slug (bd polyglot-pdf-6b7z)', () => {
    const s = groupSchema();
    s.sections[0] = { ...s.sections[0], show_if: { field: 'grp', operator: 'includes', value: 'b' } };
    const { sections: nextSections } = retargetOptionValueReferences(
      s.fields, 'grp', 'b', 'whyte', s.sections,
    );
    expect(asAtom(nextSections[0].show_if).value).toBe('whyte');
  });

  it('leaves sections without a reference to the old slug untouched (same identity)', () => {
    const s = groupSchema();
    s.sections[0] = { ...s.sections[0], show_if: { field: 'grp', operator: 'includes', value: 'a' } };
    const { sections: nextSections } = retargetOptionValueReferences(
      s.fields, 'grp', 'b', 'whyte', s.sections,
    );
    expect(nextSections).toBe(s.sections);
  });

  it('sections default to [] (same reference) when the param is omitted', () => {
    const s = groupSchema();
    const { sections: nextSections } = retargetOptionValueReferences(s.fields, 'grp', 'b', 'whyte');
    expect(nextSections).toEqual([]);
  });
});

describe('changeGroupKind (in-place checkbox_group <-> radio flip)', () => {
  // A consolidated group with two dependents: one gated on a specific option
  // slug (must move across the membership boundary), one gated on a whole-group
  // operator (kind-agnostic, must stay put).
  function grpKindSchema(type: 'checkbox_group' | 'radio'): FormSchema {
    return {
      source: 'pdf',
      form_metadata: {
        title: 'T', form_number: 'T', total_widgets: 2, total_fields: 3,
        version: '1', language: 'en',
      },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp', 'dep', 'whole'] }],
      fields: [
        {
          id: 'grp', name: 'Group', type, section_id: 's1',
          pdf_field_name: '', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'ga[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'gb[0]' },
          ],
        } as unknown as FormField,
        // Gated on a SPECIFIC option slug -- the operator must flip with the kind.
        {
          id: 'dep', name: 'Dep', type: 'text', section_id: 's1',
          pdf_field_name: 'dep[0]', read_only: false, required: false,
          show_if: {
            field: 'grp',
            operator: type === 'checkbox_group' ? 'includes' : 'equals',
            value: 'a',
          },
          require_if: {
            field: 'grp',
            operator: type === 'checkbox_group' ? 'not_includes' : 'not_equals',
            value: 'b',
          },
        } as unknown as FormField,
        // Gated on a WHOLE-GROUP operator (no specific option) -- kind-agnostic.
        {
          id: 'whole', name: 'Whole', type: 'text', section_id: 's1',
          pdf_field_name: 'whole[0]', read_only: false, required: false,
          show_if: { field: 'grp', operator: 'is_checked' },
        } as unknown as FormField,
      ],
    };
  }

  it('flips checkbox_group -> radio and rewrites option-slug dependents to equality', () => {
    const s = grpKindSchema('checkbox_group');
    const next = changeGroupKind(s, 'grp', 'radio');
    expect(next).not.toBe(s);
    expect(next.fields.find(f => f.id === 'grp')!.type).toBe('radio');
    // options[] unchanged (same slugs + per-option pdf_field_name).
    const opts = next.fields.find(f => f.id === 'grp')!.options!;
    expect(opts.map(o => o.value)).toEqual(['a', 'b']);
    expect(opts.map(o => o.pdf_field_name)).toEqual(['ga[0]', 'gb[0]']);
    // Positive membership -> equality; negative membership -> not_equals.
    const dep = next.fields.find(f => f.id === 'dep')!;
    expect(asAtom(dep.show_if)).toEqual({ field: 'grp', operator: 'equals', value: 'a' });
    expect(asAtom(dep.require_if)).toEqual({ field: 'grp', operator: 'not_equals', value: 'b' });
    // Whole-group operator is kind-agnostic -- left untouched.
    const whole = next.fields.find(f => f.id === 'whole')!;
    expect(asAtom(whole.show_if)).toEqual({ field: 'grp', operator: 'is_checked' });
  });

  it('flips radio -> checkbox_group and rewrites option-slug dependents to membership', () => {
    const s = grpKindSchema('radio');
    const next = changeGroupKind(s, 'grp', 'checkbox_group');
    expect(next).not.toBe(s);
    expect(next.fields.find(f => f.id === 'grp')!.type).toBe('checkbox_group');
    const dep = next.fields.find(f => f.id === 'dep')!;
    expect(asAtom(dep.show_if)).toEqual({ field: 'grp', operator: 'includes', value: 'a' });
    expect(asAtom(dep.require_if)).toEqual({ field: 'grp', operator: 'not_includes', value: 'b' });
  });

  it('rewrites dependents inside a COMPOSITE condition, atom-wise', () => {
    const s = grpKindSchema('checkbox_group');
    // Replace dep's show_if with a composite referencing grp.a AND an unrelated atom.
    s.fields.find(f => f.id === 'dep')!.show_if = {
      all_of: [
        { field: 'grp', operator: 'includes', value: 'a' },
        { field: 'other', operator: 'equals', value: 'x' },
      ],
    };
    const next = changeGroupKind(s, 'grp', 'radio');
    const dep = next.fields.find(f => f.id === 'dep')!;
    const composite = dep.show_if as { all_of: { field: string; operator: string; value: unknown }[] };
    expect(composite.all_of[0]).toEqual({ field: 'grp', operator: 'equals', value: 'a' });
    // The unrelated atom is untouched.
    expect(composite.all_of[1]).toEqual({ field: 'other', operator: 'equals', value: 'x' });
  });

  it('is a no-op (same reference) when already the requested kind', () => {
    const s = grpKindSchema('radio');
    expect(changeGroupKind(s, 'grp', 'radio')).toBe(s);
  });

  it('is a no-op (same reference) for a non-group field or a missing id', () => {
    const s = grpKindSchema('radio');
    // A plain text field is not a group.
    expect(changeGroupKind(s, 'dep', 'checkbox_group')).toBe(s);
    // No such field.
    expect(changeGroupKind(s, 'nope', 'checkbox_group')).toBe(s);
  });

  // A shared-name radio (field-level pdf_field_name + option pdf_on_value, no
  // per-option pdf_field_name) has NO valid checkbox_group form -- the backend
  // rejects a checkbox_group with a field-level pdf_field_name / options lacking
  // their own pdf_field_name (bd polyglot-pdf-8qfj, fresh-eyes gap).
  function sharedNameRadioSchema(): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp'] }],
      fields: [
        {
          id: 'grp', name: 'Group', type: 'radio', section_id: 's1',
          pdf_field_name: 'form1[0].grp[0]', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_on_value: 'A' },
            { value: 'b', label: 'B', pdf_on_value: 'B' },
          ],
        } as unknown as FormField,
      ],
    };
  }

  it('REFUSES a shared-name radio -> checkbox_group flip (would mint an invalid group)', () => {
    const s = sharedNameRadioSchema();
    expect(canChangeGroupKind(s, s.fields[0], 'checkbox_group')).toBe(false);
    // changeGroupKind is a no-op (same reference) rather than producing an
    // un-promotable schema.
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  it('canChangeGroupKind: flipping TO radio is always valid for a group', () => {
    // A per-option-pdf checkbox_group can always become a radio.
    const s = grpKindSchema('checkbox_group');
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'radio')).toBe(true);
    // Even a shared-name group is a valid radio (it already is one).
    const shared = sharedNameRadioSchema();
    expect(canChangeGroupKind(shared, shared.fields[0], 'radio')).toBe(false); // already radio
  });

  it('canChangeGroupKind: a per-option-pdf radio CAN become a checkbox_group', () => {
    // grpKindSchema('radio') options each carry pdf_field_name and there is no
    // field-level pdf_field_name -> a valid checkbox_group target.
    const s = grpKindSchema('radio');
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(true);
    // And the flip actually happens.
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).not.toBe(s);
  });

  it('canChangeGroupKind: rejects a non-group field', () => {
    const s = grpKindSchema('radio');
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'dep')!, 'radio')).toBe(false);
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'dep')!, 'checkbox_group')).toBe(false);
  });

  it('REFUSES a radio -> checkbox_group flip when a SECTION show_if holds in/not_in on the group', () => {
    // A section's show_if is the legacy single atom only (backend
    // FormSection.show_if) -- it can NEVER hold the any_of composite that
    // expanding a fully-live `in [a,b]` mints, so the flip must be blocked
    // even though a FIELD carrying the same condition could expand (bd
    // polyglot-pdf-6b7z, Opus outer-review finding).
    const s = grpKindSchema('radio');
    // Sanity: without the section condition the flip is allowed (pins that
    // the block below comes from the section, not the fixture).
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(true);

    s.sections[0] = {
      ...s.sections[0],
      show_if: { field: 'grp', operator: 'in' as const, value: ['a', 'b'] },
    };
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(false);
    // And changeGroupKind is a no-op (same reference) rather than minting a
    // composite into the section's show_if.
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  // A radio trigger can carry a list-valued in/not_in dependent (a value that is
  // an array of option slugs -- ConditionBuilder offers in/not_in on a radio).
  // A checkbox_group trigger cannot (in/not_in are scalar-trigger-only), so a
  // radio -> checkbox_group flip must expand a TOP-LEVEL in/not_in into a
  // membership composite, and REFUSE the flip when the atom is nested in a
  // composite (bd polyglot-pdf-8qfj, fresh-eyes round 2).
  function radioWithListDep(depCond: FormField['show_if']): FormSchema {
    return {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 2, total_fields: 2, version: '1', language: 'en' },
      parts: [],
      sections: [{ id: 's1', label: 'S1', order: 0, fields: ['grp', 'dep'] }],
      fields: [
        {
          id: 'grp', name: 'Group', type: 'radio', section_id: 's1',
          pdf_field_name: '', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'ga[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'gb[0]' },
            { value: 'c', label: 'C', pdf_field_name: 'gc[0]' },
          ],
        } as unknown as FormField,
        {
          id: 'dep', name: 'Dep', type: 'text', section_id: 's1',
          pdf_field_name: 'dep[0]', read_only: false, required: false,
          show_if: depCond,
        } as unknown as FormField,
      ],
    };
  }

  it('expands a TOP-LEVEL `in` dependent to any_of[includes...] on radio -> checkbox_group', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'in', value: ['a', 'b'] });
    const next = changeGroupKind(s, 'grp', 'checkbox_group');
    expect(next).not.toBe(s);
    const dep = next.fields.find(f => f.id === 'dep')!;
    expect(dep.show_if).toEqual({
      any_of: [
        { field: 'grp', operator: 'includes', value: 'a' },
        { field: 'grp', operator: 'includes', value: 'b' },
      ],
    });
  });

  it('expands a TOP-LEVEL `not_in` dependent to none_of[includes...] on radio -> checkbox_group', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'not_in', value: ['a', 'c'] });
    const next = changeGroupKind(s, 'grp', 'checkbox_group');
    const dep = next.fields.find(f => f.id === 'dep')!;
    expect(dep.show_if).toEqual({
      none_of: [
        { field: 'grp', operator: 'includes', value: 'a' },
        { field: 'grp', operator: 'includes', value: 'c' },
      ],
    });
  });

  it('REFUSES the flip when an in/not_in atom is NESTED in a composite (cannot expand in one level)', () => {
    const s = radioWithListDep({
      all_of: [
        { field: 'grp', operator: 'in', value: ['a', 'b'] },
        { field: 'other', operator: 'equals', value: 'x' },
      ],
    });
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(false);
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  // A top-level in/not_in is only losslessly expandable when EVERY member is a
  // current option slug. An empty list, a stale member, or a non-array value
  // must refuse the flip rather than strand a checkbox_group-invalid `in` or
  // silently drop members (bd polyglot-pdf-8qfj, fresh-eyes round 4).
  it('REFUSES a top-level `in` whose members are ALL stale (resolves to zero live slugs)', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'in', value: ['deleted_slug'] });
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(false);
    // No-op rather than emitting a raw `in` on a checkbox_group.
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  it('REFUSES a top-level `not_in` with SOME stale members (would silently widen none_of)', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'not_in', value: ['a', 'stale_x'] });
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(false);
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  it('REFUSES a top-level `in` with a non-array value', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'in', value: 'a' as unknown as string[] });
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(false);
    expect(changeGroupKind(s, 'grp', 'checkbox_group')).toBe(s);
  });

  it('ALLOWS a fully-live top-level `in` (every member a current slug) and expands it', () => {
    const s = radioWithListDep({ field: 'grp', operator: 'in', value: ['a', 'c'] });
    expect(canChangeGroupKind(s, s.fields.find(f => f.id === 'grp')!, 'checkbox_group')).toBe(true);
    const next = changeGroupKind(s, 'grp', 'checkbox_group');
    const dep = next.fields.find(f => f.id === 'dep')!;
    expect(dep.show_if).toEqual({
      any_of: [
        { field: 'grp', operator: 'includes', value: 'a' },
        { field: 'grp', operator: 'includes', value: 'c' },
      ],
    });
  });
});

// Section-level show_if rewriting (bd polyglot-pdf-6b7z). The backend
// validates a section's show_if with the SAME operator/trigger matrix as a
// field's (form_models.py FormSection.show_if, ~line 627), so a section gated
// on a group must be rewritten across group-kind flip / merge / ungroup
// exactly like a dependent field's show_if -- otherwise a loaded kit's
// section show_if strands a stale operator and the backend rejects the kit at
// promotion.
describe('section show_if rewriting across group mutations (bd polyglot-pdf-6b7z)', () => {
  it('changeGroupKind flips a section-level condition the same as a field-level one', () => {
    const schema: FormSchema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 2, total_fields: 2, version: '1', language: 'en' },
      parts: [],
      sections: [
        { id: 's1', label: 'S1', order: 0, fields: ['grp'] },
        {
          id: 's2', label: 'S2', order: 1, fields: ['other'],
          show_if: { field: 'grp', operator: 'includes', value: 'a' },
        },
      ],
      fields: [
        {
          id: 'grp', name: 'Group', type: 'checkbox_group', section_id: 's1',
          pdf_field_name: '', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'ga[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'gb[0]' },
          ],
        } as unknown as FormField,
        {
          id: 'other', name: 'Other', type: 'text', section_id: 's2',
          pdf_field_name: 'other[0]', read_only: false, required: false,
        },
      ],
    };

    const next = changeGroupKind(schema, 'grp', 'radio');
    const s2 = next.sections.find(s => s.id === 's2')!;
    // checkbox_group `includes` on the trigger becomes radio `equals` -- the
    // exact rewrite a field-level dependent gets (see the flip tests above).
    expect(asAtom(s2.show_if)).toEqual({ field: 'grp', operator: 'equals', value: 'a' });

    // And the reverse direction.
    const back = changeGroupKind(next, 'grp', 'checkbox_group');
    const s2Back = back.sections.find(s => s.id === 's2')!;
    expect(asAtom(s2Back.show_if)).toEqual({ field: 'grp', operator: 'includes', value: 'a' });
  });

  it('mergeFields rewrites a section show_if referencing a merged-away field, and lossless ungroup restores it byte-for-byte', () => {
    const schema = w7Schema();
    // Section 'reason' is shown only when reason_b is checked -- reason_b is
    // about to be merged away into the consolidated group.
    const originalShowIf = { field: 'reason_b', operator: 'is_checked' as const };
    schema.sections[0] = { ...schema.sections[0], show_if: originalShowIf };

    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    const mergedSection = merged.sections.find(s => s.id === 'reason')!;
    // The whole-group is_checked selection op on a merged-away widget becomes
    // a membership (includes <slug>) reference on the consolidated group --
    // the same rewrite rewriteReferences applies to a dependent field.
    expect(asAtom(mergedSection.show_if)).toEqual({
      field: 'reason_a', operator: 'includes', value: 'reason_b',
    });

    // Lossless ungroup (stash present) restores the section's original show_if
    // verbatim -- AND the field membership in the same pass (the two section
    // rewrites land together; pin their interaction, fresh-eyes nit).
    const unmerged = ungroupField(merged, 'reason_a');
    const restoredSection = unmerged.sections.find(s => s.id === 'reason')!;
    expect(restoredSection.show_if).toEqual(originalShowIf);
    expect(restoredSection.fields).toEqual(schema.sections[0].fields);
  });

  it('ungroupField fallback path (no stash) remaps a section atom the same way it remaps a dependent field atom', () => {
    const schema = w7Schema();
    const originalShowIf = { field: 'reason_b', operator: 'is_checked' as const };
    schema.sections[0] = { ...schema.sections[0], show_if: originalShowIf };
    // Add a field-level dependent with the SAME condition, so the section and
    // field remaps can be compared directly.
    schema.fields.push({
      id: 'detail', name: 'Detail', type: 'text', section_id: 'reason',
      pdf_field_name: 'detail[0]', read_only: false, required: false,
      show_if: { field: 'reason_b', operator: 'is_checked' },
    } as FormField);
    schema.sections[0].fields.push('detail');

    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    // Strip the stash (simulating save -> reload) to force the fallback path.
    const saved = stripEditorState(merged);
    const unmerged = ungroupField(saved, 'reason_a');

    const detail = unmerged.fields.find(f => f.id === 'detail')!;
    const section = unmerged.sections.find(s => s.id === 'reason')!;

    // Both the field-level and section-level whole-group `includes` remap to
    // `is_checked` on the reconstructed reason_b field -- identical treatment.
    expect(asAtom(detail.show_if).operator).toBe('is_checked');
    expect(asAtom(section.show_if!).operator).toBe('is_checked');
    expect(asAtom(section.show_if!).field).toBe(asAtom(detail.show_if).field);
    expect(unmerged.fields.some(f => f.id === asAtom(section.show_if!).field && f.type === 'checkbox')).toBe(true);
  });

  it('retargetOptionValueReferences retargets a section condition (App.tsx call-site shape: fields + sections in, {fields, sections} out)', () => {
    const schema: FormSchema = {
      source: 'pdf',
      form_metadata: { title: 'T', form_number: 'T', total_widgets: 1, total_fields: 1, version: '1', language: 'en' },
      parts: [],
      sections: [
        { id: 's1', label: 'S1', order: 0, fields: ['grp'] },
        {
          id: 's2', label: 'S2', order: 1, fields: [],
          show_if: { field: 'grp', operator: 'includes', value: 'b' },
        },
      ],
      fields: [
        { id: 'grp', name: 'Grp', type: 'checkbox_group', section_id: 's1', pdf_field_name: '', read_only: false, required: false,
          options: [
            { value: 'a', label: 'A', pdf_field_name: 'a[0]' },
            { value: 'b', label: 'B', pdf_field_name: 'b[0]' },
          ] },
      ],
    };
    const { sections } = retargetOptionValueReferences(schema.fields, 'grp', 'b', 'whyte', schema.sections);
    const s2 = sections.find(s => s.id === 's2')!;
    expect(asAtom(s2.show_if)).toEqual({ field: 'grp', operator: 'includes', value: 'whyte' });
  });

  it('a section WITHOUT show_if round-trips through every mutation without gaining the key', () => {
    const schema = w7Schema(); // section 'reason' has no show_if
    expect('show_if' in schema.sections[0]).toBe(false);

    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    expect('show_if' in merged.sections[0]).toBe(false);

    const flipped = changeGroupKind(merged, 'reason_a', 'radio');
    expect('show_if' in flipped.sections[0]).toBe(false);

    const unmerged = ungroupField(flipped, 'reason_a');
    expect('show_if' in unmerged.sections[0]).toBe(false);

    // Also verify the retarget path leaves an unreferenced section untouched
    // (same identity, no key added).
    const { sections: retargetedSections } = retargetOptionValueReferences(
      unmerged.fields, 'reason_a', 'x', 'y', unmerged.sections,
    );
    expect(retargetedSections).toBe(unmerged.sections);
    expect('show_if' in retargetedSections[0]).toBe(false);
  });

  it('a composite section show_if (invalid per backend but representable) is rewritten atom-wise without crashing', () => {
    const schema = w7Schema();
    // Not backend-valid (sections are legacy-only per form_models.py), but the
    // editor type allows it (bd polyglot-pdf-6b7z) and the rewrite must not
    // crash on a hand-edited kit carrying one.
    schema.sections[0] = {
      ...schema.sections[0],
      show_if: {
        all_of: [
          { field: 'reason_b', operator: 'is_checked' },
          { field: 'reason_c', operator: 'is_checked' },
        ],
      } as unknown as FormField['show_if'],
    };

    const { schema: merged } = mergeFields(
      schema, ['reason_a', 'reason_b', 'reason_c'], 'checkbox_group',
    );
    const mergedSection = merged.sections.find(s => s.id === 'reason')!;
    const composite = mergedSection.show_if as { all_of: ConditionalDisplay[] };
    // Both atoms referenced merged-away widgets -> both rewrite to membership
    // on the consolidated group, preserving the composite shape.
    expect(composite.all_of).toEqual([
      { field: 'reason_a', operator: 'includes', value: 'reason_b' },
      { field: 'reason_a', operator: 'includes', value: 'reason_c' },
    ]);

    // changeGroupKind must also handle a composite section condition without
    // crashing.
    const flipped = changeGroupKind(merged, 'reason_a', 'radio');
    const flippedComposite = flipped.sections.find(s => s.id === 'reason')!.show_if as {
      all_of: ConditionalDisplay[];
    };
    expect(flippedComposite.all_of).toEqual([
      { field: 'reason_a', operator: 'equals', value: 'reason_b' },
      { field: 'reason_a', operator: 'equals', value: 'reason_c' },
    ]);
  });
});
