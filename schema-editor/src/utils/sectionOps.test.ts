// Section CRUD invariants (bd polyglot-pdf-6cfu.3).
import { describe, expect, it } from 'vitest';
import type { FormField, FormPart, FormSection } from '../types/schema';
import {
  addSection,
  isToReviewSection,
  mergeSections,
  mintSectionId,
  movedFieldCount,
  removeSection,
  renameSection,
  toReviewFieldIds,
} from './sectionOps';

const field = (id: string, section_id: string): FormField =>
  ({ id, name: id, type: 'text', section_id } as unknown as FormField);

const section = (id: string, label: string, order: number, fields: string[],
                 extra?: Partial<FormSection>): FormSection =>
  ({ id, label, order, fields, ...extra });

function fixture() {
  const fields = [
    field('f1', 'sec_a'), field('f2', 'sec_a'), field('f3', 'sec_b'),
    field('f4', 'sec_to_review_p1'),
  ];
  const sections = [
    section('sec_a', 'Alpha', 1, ['f1', 'f2'],
            { show_if: { field: 'f3', operator: 'equals', value: 'x' } as never }),
    section('sec_b', 'Beta', 2, ['f3']),
    section('sec_to_review_p1', 'To review', 3, ['f4']),
  ];
  const parts: FormPart[] = [
    { id: 'p1', label: 'Part 1', order: 1, section_ids: ['sec_a', 'sec_b'] },
    { id: 'p2', label: 'Part 2', order: 2, section_ids: ['sec_to_review_p1'] },
  ];
  return { fields, sections, parts };
}

describe('isToReviewSection / toReviewFieldIds', () => {
  it('keys on the sec_to_review prefix', () => {
    expect(isToReviewSection('sec_to_review_p1')).toBe(true);
    expect(isToReviewSection('sec_to_review_unplaced')).toBe(true);
    expect(isToReviewSection('sec_normal')).toBe(false);
    expect(isToReviewSection(undefined)).toBe(false);
  });

  it('lists the fields still awaiting re-filing', () => {
    const { fields } = fixture();
    expect(toReviewFieldIds(fields)).toEqual(['f4']);
  });
});

describe('mintSectionId', () => {
  it('slugs the label and dedupes against existing ids', () => {
    const { sections } = fixture();
    expect(mintSectionId('Alpha', sections)).toBe('sec_alpha');
    expect(mintSectionId('Beta!', [...sections, section('sec_beta', 'x', 4, [])]))
      .toBe('sec_beta_2');
  });

  it('never mints an id squatting the review-gate prefix', () => {
    expect(mintSectionId('To Review Later', [])).toBe('sec_x_to_review_later');
  });
});

describe('addSection', () => {
  it('appends an empty section with a fresh id and renumbers order', () => {
    const { fields, sections, parts } = fixture();
    const next = addSection(fields, sections, parts, '  Gamma  ');
    expect(next.sections).toHaveLength(4);
    const added = next.sections[3];
    expect(added).toMatchObject({ id: 'sec_gamma', label: 'Gamma', fields: [] });
    expect(next.sections.map(s => s.order)).toEqual([1, 2, 3, 4]);
    expect(next.fields).toBe(fields); // untouched
    expect(next.parts).toBe(parts);   // untouched (no dangling refs possible)
  });
});

describe('renameSection', () => {
  it('changes only the label, keeping the id stable', () => {
    const { fields, sections, parts } = fixture();
    const next = renameSection(fields, sections, parts, 'sec_a', 'Alpha 2');
    expect(next.sections[0]).toMatchObject({ id: 'sec_a', label: 'Alpha 2' });
    expect(next.sections[0].show_if).toEqual(sections[0].show_if);
    expect(next.fields).toBe(fields);
  });

  it('ignores a blank label', () => {
    const { fields, sections, parts } = fixture();
    const next = renameSection(fields, sections, parts, 'sec_a', '   ');
    expect(next.sections).toBe(sections);
  });
});

describe('removeSection', () => {
  it('re-files fields to the destination and keeps both sides consistent', () => {
    const { fields, sections, parts } = fixture();
    const next = removeSection(fields, sections, parts, 'sec_a', 'sec_b');
    expect(next.sections.map(s => s.id)).toEqual(['sec_b', 'sec_to_review_p1']);
    const dest = next.sections[0];
    expect(dest.fields).toEqual(['f3', 'f1', 'f2']);
    const byId = new Map(next.fields.map(f => [f.id, f]));
    expect(byId.get('f1')!.section_id).toBe('sec_b');
    expect(byId.get('f2')!.section_id).toBe('sec_b');
    expect(next.sections.map(s => s.order)).toEqual([1, 2]);
  });

  it('orphans fields when no destination is given', () => {
    const { fields, sections, parts } = fixture();
    const next = removeSection(fields, sections, parts, 'sec_a', null);
    const byId = new Map(next.fields.map(f => [f.id, f]));
    expect(byId.get('f1')!.section_id).toBe('');
    expect(byId.get('f2')!.section_id).toBe('');
  });

  it('prunes the removed id from parts and drops emptied parts', () => {
    const { fields, sections, parts } = fixture();
    const next = removeSection(fields, sections, parts, 'sec_to_review_p1', 'sec_b');
    expect(next.parts).toEqual([
      { id: 'p1', label: 'Part 1', order: 1, section_ids: ['sec_a', 'sec_b'] },
    ]); // p2 emptied -> dropped
  });

  it('leaves untouched sections (and their show_if) alone', () => {
    const { fields, sections, parts } = fixture();
    const next = removeSection(fields, sections, parts, 'sec_b', null);
    expect(next.sections[0].show_if).toEqual(sections[0].show_if);
  });

  it('is a no-op for an unknown section or self-destination', () => {
    const { fields, sections, parts } = fixture();
    expect(removeSection(fields, sections, parts, 'nope', null).sections)
      .toBe(sections);
    expect(removeSection(fields, sections, parts, 'sec_a', 'sec_a').sections)
      .toBe(sections);
  });
});

describe('mergeSections', () => {
  it('empties a To-review section into a real one (the review workflow)', () => {
    const { fields, sections, parts } = fixture();
    const next = mergeSections(fields, sections, parts, 'sec_to_review_p1', 'sec_a');
    expect(next.sections.map(s => s.id)).toEqual(['sec_a', 'sec_b']);
    expect(next.sections[0].fields).toEqual(['f1', 'f2', 'f4']);
    const f4 = next.fields.find(f => f.id === 'f4')!;
    expect(f4.section_id).toBe('sec_a');
    expect(toReviewFieldIds(next.fields)).toEqual([]);
  });

  it('does not duplicate a field id already listed by the target', () => {
    const { fields, sections, parts } = fixture();
    // Corrupt input: target already lists f4. The merge must not double it.
    sections[0] = { ...sections[0], fields: ['f1', 'f2', 'f4'] };
    const next = mergeSections(fields, sections, parts, 'sec_to_review_p1', 'sec_a');
    expect(next.sections[0].fields).toEqual(['f1', 'f2', 'f4']);
  });

  it('is a no-op on self-merge or unknown ids', () => {
    const { fields, sections, parts } = fixture();
    expect(mergeSections(fields, sections, parts, 'sec_a', 'sec_a').sections)
      .toBe(sections);
    expect(mergeSections(fields, sections, parts, 'sec_a', 'nope').sections)
      .toBe(sections);
  });
});

describe('drift healing (bd polyglot-pdf-w7rg interplay)', () => {
  it('removeSection moves by section_id, not the stale fields[] listing', () => {
    // Drifted kit: f9 POINTS at sec_a but is not listed; f1 is LISTED by
    // sec_a but was re-pointed to sec_b via the FieldEditor dropdown.
    const fields = [
      field('f1', 'sec_b'), field('f9', 'sec_a'), field('f3', 'sec_b'),
    ];
    const sections = [
      section('sec_a', 'Alpha', 1, ['f1']),      // stale listing
      section('sec_b', 'Beta', 2, ['f3']),
    ];
    const next = removeSection(fields, sections, undefined, 'sec_a', 'sec_b');
    const dest = next.sections[0];
    // f9 (pointing) moved; f1 (drifted away) neither doubled nor moved.
    expect(dest.fields).toEqual(['f3', 'f9']);
    const byId = new Map(next.fields.map(f => [f.id, f]));
    expect(byId.get('f9')!.section_id).toBe('sec_b');
    expect(byId.get('f1')!.section_id).toBe('sec_b'); // untouched
    // No field id appears in two sections or in none.
    const listed = next.sections.flatMap(s => s.fields);
    expect(new Set(listed).size).toBe(listed.length);
  });

  it('movedFieldCount counts by section_id (matches removeSection)', () => {
    const fields = [field('f1', 'sec_b'), field('f9', 'sec_a')];
    expect(movedFieldCount(fields, 'sec_a')).toBe(1);
  });
});
