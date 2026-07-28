/**
 * The Ignored (grey) quarantine escape hatch (bd polyglot-pdf-mzkw).
 *
 * Pins the maintainer's contract: human-only, fully reversible, and gated so
 * ignoring can never silently strand a conditional or drop a required answer.
 */
import { describe, it, expect } from 'vitest';
import type { FormField, FormSchema } from '../types/schema';
import { stripEditorState } from './fieldGrouping';
import { renameBlockReason } from './fieldRename';
import {
  allFieldIds,
  dependentsOf,
  describeIgnoreBlock,
  getIgnoredFields,
  ignoreBlockReason,
  ignoreField,
  isIgnored,
  restoreField,
} from './ignoreField';

function field(id: string, extra: Partial<FormField> = {}): FormField {
  return {
    id, name: id, type: 'text', pdf_field_name: `pdf.${id}`,
    spoken_name: `spoken ${id}`, section_id: 'sec-1', read_only: false,
    help: { instructions: 'All set.' },
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
    sections: [{ id: 'sec-1', label: 'Section 1', order: 1, fields: fields.map(f => f.id) }],
    fields,
    ...extra,
  } as unknown as FormSchema;
}

describe('ignoreField gates (bd mzkw)', () => {
  it('refuses a required field -- clearing the flag is a deliberate first step', () => {
    const s = schemaWith([field('a', { validation: { required: true } })]);
    expect(ignoreBlockReason(s, 'a')).toBe('still-required');
    expect(ignoreField(s, 'a')).toBe(s); // untouched
  });

  it('allows a field whose required flag is explicitly false', () => {
    const s = schemaWith([field('a', { validation: { required: false } })]);
    expect(ignoreBlockReason(s, 'a')).toBeNull();
  });

  it.each([
    ['show_if', { show_if: { field: 'a', operator: 'is_not_empty' } }],
    ['require_if', { require_if: { field: 'a', operator: 'is_not_empty' } }],
    ['copy_to', { copy_to: ['a'] }],
    ['copy_from', { copy_from: 'a' }],
    ['address_fields', { address_fields: { street: 'a' } }],
  ])('refuses a field referenced by another field via %s', (_kind, dep) => {
    const s = schemaWith([field('a'), field('b', dep as Partial<FormField>)]);
    expect(ignoreBlockReason(s, 'a')).toBe('has-dependents');
    expect(dependentsOf(s, 'a')).toHaveLength(1);
  });

  it('finds a reference nested in a COMPOSITE condition bucket', () => {
    const s = schemaWith([
      field('a'),
      field('b', {
        show_if: { any_of: [{ field: 'a', operator: 'equals', value: 'x' }] },
      } as Partial<FormField>),
    ]);
    expect(ignoreBlockReason(s, 'a')).toBe('has-dependents');
  });

  it('refuses a field a SECTION condition depends on', () => {
    const s = schemaWith([field('a')]);
    (s.sections[0] as unknown as Record<string, unknown>).show_if = {
      field: 'a', operator: 'is_not_empty',
    };
    expect(dependentsOf(s, 'a').map(d => d.kind)).toEqual(['section_show_if']);
  });

  it('refuses a field a supplement lists', () => {
    const s = schemaWith([field('a')], {
      supplements: [{ id: 'sup1', name: 'Continuation', fields: ['a'] }],
    });
    expect(dependentsOf(s, 'a').map(d => d.kind)).toEqual(['supplement_fields']);
  });

  it('does NOT count the field own section membership as a dependent', () => {
    // sec-1 lists 'a' in fields[] -- that is its home, which ignoring relocates
    // by design, not a reference that blocks it.
    const s = schemaWith([field('a')]);
    expect(dependentsOf(s, 'a')).toEqual([]);
    expect(ignoreBlockReason(s, 'a')).toBeNull();
  });

  it('does not let a field block itself via its own condition', () => {
    const s = schemaWith([
      field('a', { show_if: { field: 'a', operator: 'is_not_empty' } } as Partial<FormField>),
    ]);
    expect(ignoreBlockReason(s, 'a')).toBeNull();
  });
});

describe('ignoreField / restoreField round-trip (bd mzkw)', () => {
  const base = () => schemaWith([field('a'), field('b'), field('c')]);

  it('moves the field out of fields[] and out of its section', () => {
    const s = ignoreField(base(), 'b', '2026-07-28T00:00:00Z');
    expect(s.fields.map(f => f.id)).toEqual(['a', 'c']);
    expect(s.sections[0].fields).toEqual(['a', 'c']);
    expect(isIgnored(s, 'b')).toBe(true);
    const [entry] = getIgnoredFields(s);
    expect(entry.field.id).toBe('b');
    expect(entry.sectionId).toBe('sec-1');
    expect(entry.index).toBe(1);
    expect(entry.ignoredAt).toBe('2026-07-28T00:00:00Z');
  });

  it('restores the field to its EXACT original position', () => {
    const original = base();
    const restored = restoreField(ignoreField(original, 'b'), 'b');
    expect(restored.sections[0].fields).toEqual(['a', 'b', 'c']);
    expect(restored.fields.find(f => f.id === 'b')).toEqual(
      original.fields.find(f => f.id === 'b'),
    );
    expect(getIgnoredFields(restored)).toEqual([]);
    expect(isIgnored(restored, 'b')).toBe(false);
  });

  it('preserves the field verbatim, including its review note', () => {
    // The note is how an author records WHY they ignored it ("phantom field").
    const noted = field('ghost', {
      _review: { status: 'needs_followup', note: 'phantom field' },
    } as Partial<FormField>);
    const s = ignoreField(schemaWith([noted]), 'ghost');
    expect(getIgnoredFields(s)[0].field._review).toEqual({
      status: 'needs_followup', note: 'phantom field',
    });
    expect(restoreField(s, 'ghost').fields[0]._review?.note).toBe('phantom field');
  });

  it('restores UNSECTIONED when the original section was deleted meanwhile', () => {
    const ignored = ignoreField(base(), 'b');
    // The author deletes the section while 'b' sits quarantined.
    const sectionGone = { ...ignored, sections: [] } as unknown as FormSchema;
    const restored = restoreField(sectionGone, 'b');
    const b = restored.fields.find(f => f.id === 'b')!;
    expect('section_id' in b).toBe(false); // orphan bucket, not a dangling ref
  });

  it('clamps the restore index when the section shrank meanwhile', () => {
    const ignored = ignoreField(base(), 'c'); // was index 2
    const shrunk = {
      ...ignored,
      sections: [{ ...ignored.sections[0], fields: ['a'] }],
    } as unknown as FormSchema;
    expect(restoreField(shrunk, 'c').sections[0].fields).toEqual(['a', 'c']);
  });

  it('carries a merged field _ungroup stash through ignore -> restore', () => {
    // A consolidated (merged) field keeps its ungroup snapshot so it can still
    // be split after coming back. True by construction (the whole object is
    // stashed verbatim), but the rubric names it, so pin it.
    const merged = field('grp', {
      _ungroup: { sources: [{ id: 'grp_a' }], rewrites: [], sections: [] },
    } as unknown as Partial<FormField>);
    const s = ignoreField(schemaWith([field('a'), merged]), 'grp');
    const stashed = getIgnoredFields(s)[0].field as unknown as Record<string, unknown>;
    expect(stashed._ungroup).toEqual({
      sources: [{ id: 'grp_a' }], rewrites: [], sections: [],
    });
    const back = restoreField(s, 'grp').fields.find(f => f.id === 'grp');
    expect((back as unknown as Record<string, unknown>)._ungroup).toEqual(
      (merged as unknown as Record<string, unknown>)._ungroup,
    );
  });

  it('strips a parked field _ungroup stash on save, like a live one', () => {
    // The stash must not ride to disk from EITHER place: ignoreField's
    // dependents detector justifies not scanning _ungroup on the premise that
    // stripEditorState removes it on save, and that premise has to hold for a
    // merged-then-ignored field too (fresh-eyes).
    const merged = field('grp', {
      _ungroup: { sources: [{ id: 'grp_a' }], rewrites: [], sections: [] },
    } as unknown as Partial<FormField>);
    const s = ignoreField(schemaWith([field('a'), merged]), 'grp');
    // In memory it is still there (a same-session un-ignore + ungroup stays
    // lossless)...
    expect((getIgnoredFields(s)[0].field as unknown as Record<string, unknown>)._ungroup)
      .toBeDefined();
    // ...but the SAVED artifact carries no stash, parked or live.
    const saved = stripEditorState(s);
    expect((getIgnoredFields(saved)[0].field as unknown as Record<string, unknown>)._ungroup)
      .toBeUndefined();
    // ...and the parked field still restores fine from the saved shape.
    expect(restoreField(saved, 'grp').fields.map(f => f.id)).toEqual(['a', 'grp']);
  });

  it('does not promise more dependents than there are owners', () => {
    // One owner referencing through TWO surfaces produced 2 entries but 1
    // name, printing a "..." that implied unnamed extra fields (fresh-eyes).
    const s = schemaWith([
      field('target'),
      field('owner', {
        show_if: { field: 'target', operator: 'is_not_empty' },
        copy_to: ['target'],
      } as unknown as Partial<FormField>),
    ]);
    const deps = dependentsOf(s, 'target');
    expect(deps).toHaveLength(2);                     // two surfaces...
    expect(new Set(deps.map(d => d.ownerLabel)).size).toBe(1); // ...one owner
    const message = describeIgnoreBlock('has-dependents', deps);
    expect(message).not.toContain('...');
  });

  it('is a no-op for an unknown id, in both directions', () => {
    const s = base();
    expect(ignoreField(s, 'nope')).toBe(s);
    expect(restoreField(s, 'nope')).toBe(s);
  });

  it('never mutates the input schema', () => {
    const s = base();
    const snapshot = JSON.parse(JSON.stringify(s));
    ignoreField(s, 'b');
    expect(JSON.parse(JSON.stringify(s))).toEqual(snapshot);
  });
});

describe('a parked id is still OWNED (bd mzkw)', () => {
  it('rename refuses an id that belongs to an ignored field', () => {
    // The corruption path fresh-eyes found: park a broken field, rename its
    // replacement to the parked id, un-ignore -> two fields share one id.
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    expect(allFieldIds(s).has('b')).toBe(true);  // parked, but still owned
    const reason = renameBlockReason(s, 'a', 'b');
    expect(reason).toContain('ignored field');
    // ...and the normal duplicate message still covers a LIVE collision.
    const live = schemaWith([field('a'), field('b')]);
    expect(renameBlockReason(live, 'a', 'b')).toContain('already exists');
  });

  it('allFieldIds spans live and parked fields', () => {
    const s = ignoreField(schemaWith([field('a'), field('b'), field('c')]), 'b');
    expect([...allFieldIds(s)].sort()).toEqual(['a', 'b', 'c']);
  });
});

describe('the stash survives the save path (bd mzkw)', () => {
  it('stripEditorState keeps _ignored_fields (it strips only _ungroup)', () => {
    const s = ignoreField(schemaWith([field('a'), field('b')]), 'b');
    const saved = stripEditorState(s);
    expect(getIgnoredFields(saved)).toHaveLength(1);
    // And it survives a JSON round-trip, i.e. what actually hits disk / the PUT.
    const reloaded = JSON.parse(JSON.stringify(saved)) as FormSchema;
    expect(getIgnoredFields(reloaded)[0].field.id).toBe('b');
    expect(restoreField(reloaded, 'b').fields.map(f => f.id)).toEqual(['a', 'b']);
  });

  it('tolerates a malformed stash from a hand-edited kit', () => {
    const s = schemaWith([field('a')], {
      _ignored_fields: ['junk', null, 42, { field: { noId: true } }],
    });
    expect(getIgnoredFields(s)).toEqual([]);
    expect(isIgnored(s, 'a')).toBe(false);
  });
});
