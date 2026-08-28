/**
 * Auto-populate ("copy") links, editable from both ends (bd polyglot-pdf-g33y2).
 *
 * The relationship is STORED once, as copy_to on the source, and the
 * target-side view is derived -- so these tests pin that both directions agree
 * by construction, that the refusals are real, and that the read_only coupling
 * the maintainer required actually happens.
 */
import { describe, it, expect } from 'vitest';
import {
  addCopyLink, copySources, copyTargets, linkableSources, linkableTargets,
  removeCopyLink, whyNotLinkable,
} from './copyLinks';
import type { FormField, FormSchema } from '../types/schema';

function field(p: Partial<FormField> & { id: string }): FormField {
  return {
    name: p.id, type: 'text', pdf_field_name: `${p.id}[0]`,
    read_only: false, ...p,
  } as FormField;
}

function schema(fields: FormField[]): FormSchema {
  return {
    source: 'pdf',
    form_metadata: { title: 'T', form_number: 'T-1', version: '1', language: 'en' },
    parts: [],
    sections: [{ id: 's1', label: 'S1', order: 1, fields: fields.map(f => f.id) }],
    fields,
  } as unknown as FormSchema;
}

/** The i-90 shape: one source populating one page-8 repeat. */
const LINKED = schema([
  field({ id: 'family_name', copy_to: ['p8_family_name'] }),
  field({ id: 'p8_family_name', read_only: true }),
  field({ id: 'other' }),
]);

describe('both directions are readable from one stored link', () => {
  it('the source lists its targets', () => {
    expect(copyTargets(LINKED.fields[0])).toEqual(['p8_family_name']);
  });

  it('the target derives its sources', () => {
    expect(copySources(LINKED, 'p8_family_name')).toEqual(['family_name']);
  });

  it('an unlinked field has neither', () => {
    expect(copyTargets(LINKED.fields[2])).toEqual([]);
    expect(copySources(LINKED, 'other')).toEqual([]);
  });

  it('a field never reports itself as its own source', () => {
    const self = schema([field({ id: 'a', copy_to: ['a'] })]);  // hand-edited junk
    expect(copySources(self, 'a')).toEqual([]);
  });
});

describe('malformed copy_to degrades instead of throwing', () => {
  it.each([
    ['absent', undefined],
    ['not an array', 'p8_family_name'],
    ['carrying non-strings', [null, 42, {}]],
    ['carrying an empty id', ['']],
  ])('%s', (_label, raw) => {
    const f = { id: 'a', copy_to: raw } as unknown as FormField;
    expect(copyTargets(f)).toEqual([]);
    expect(() => copySources(schema([f]), 'x')).not.toThrow();
  });
});

describe('refusals', () => {
  it('refuses a self-link', () => {
    expect(whyNotLinkable(LINKED, 'other', 'other')).toMatch(/itself/i);
  });

  it('refuses an unknown target', () => {
    expect(whyNotLinkable(LINKED, 'other', 'ghost')).toMatch(/no longer exists/i);
  });

  it('refuses a duplicate link', () => {
    expect(whyNotLinkable(LINKED, 'family_name', 'p8_family_name'))
      .toMatch(/already linked/i);
  });

  it('refuses a direct loop', () => {
    expect(whyNotLinkable(LINKED, 'p8_family_name', 'family_name'))
      .toMatch(/loop/i);
  });

  it('refuses an INDIRECT loop (a->b->c, then c->a)', () => {
    const chain = schema([
      field({ id: 'a', copy_to: ['b'] }),
      field({ id: 'b', copy_to: ['c'] }),
      field({ id: 'c' }),
    ]);
    expect(whyNotLinkable(chain, 'c', 'a')).toMatch(/loop/i);
    // ...but an unrelated new link is still fine.
    expect(whyNotLinkable(chain, 'a', 'c')).toBeNull();
  });

  it('does not hang on a pre-existing cycle in a hand-edited kit', () => {
    const cyclic = schema([
      field({ id: 'a', copy_to: ['b'] }),
      field({ id: 'b', copy_to: ['a'] }),
      field({ id: 'z' }),
    ]);
    expect(whyNotLinkable(cyclic, 'z', 'a')).toBeNull();
  });

  it('allows a legitimate new link', () => {
    expect(whyNotLinkable(LINKED, 'family_name', 'other')).toBeNull();
  });
});

describe('adding a link', () => {
  it('writes copy_to on the SOURCE, not the target', () => {
    const next = addCopyLink(LINKED, 'family_name', 'other');
    expect(copyTargets(next.find(f => f.id === 'family_name'))).toEqual(
      ['p8_family_name', 'other']);
    expect((next.find(f => f.id === 'other') as { copy_to?: unknown }).copy_to)
      .toBeUndefined();
  });

  it('sets read_only on the TARGET (the maintainer coupling)', () => {
    const next = addCopyLink(LINKED, 'family_name', 'other');
    expect(next.find(f => f.id === 'other')!.read_only).toBe(true);
  });

  it('is a no-op (same array) when the link is refused', () => {
    expect(addCopyLink(LINKED, 'family_name', 'p8_family_name'))
      .toBe(LINKED.fields);
    expect(addCopyLink(LINKED, 'other', 'other')).toBe(LINKED.fields);
  });
});

describe('removing a link', () => {
  it('drops the target from the source', () => {
    const next = removeCopyLink(LINKED, 'family_name', 'p8_family_name');
    expect(copyTargets(next.find(f => f.id === 'family_name'))).toEqual([]);
  });

  it('deletes copy_to entirely rather than leaving an empty array', () => {
    const next = removeCopyLink(LINKED, 'family_name', 'p8_family_name');
    const src = next.find(f => f.id === 'family_name') as { copy_to?: unknown };
    expect('copy_to' in src).toBe(false);
  });

  it('keeps the other targets when several are linked', () => {
    const many = schema([
      field({ id: 'a', copy_to: ['b', 'c'] }),
      field({ id: 'b' }), field({ id: 'c' }),
    ]);
    const next = removeCopyLink(many, 'a', 'b');
    expect(copyTargets(next.find(f => f.id === 'a'))).toEqual(['c']);
  });

  it('LEAVES read_only set -- a field may be read-only for its own reasons', () => {
    const next = removeCopyLink(LINKED, 'family_name', 'p8_family_name');
    expect(next.find(f => f.id === 'p8_family_name')!.read_only).toBe(true);
  });

  it('unlinking from the TARGET side removes the same stored link', () => {
    // The UI offers this from B; it must rewrite A, since A owns the storage.
    const sources = copySources(LINKED, 'p8_family_name');
    const next = removeCopyLink(LINKED, sources[0], 'p8_family_name');
    expect(copyTargets(next.find(f => f.id === 'family_name'))).toEqual([]);
  });
});

describe('pickers offer only legal choices', () => {
  it('targets exclude self, the already-linked, and loop-makers', () => {
    const ids = linkableTargets(LINKED, 'family_name').map(f => f.id);
    expect(ids).toEqual(['other']);
  });

  it('sources exclude self and loop-makers', () => {
    const ids = linkableSources(LINKED, 'family_name').map(f => f.id);
    expect(ids).not.toContain('family_name');
    expect(ids).not.toContain('p8_family_name');  // would loop
    expect(ids).toContain('other');
  });
});
