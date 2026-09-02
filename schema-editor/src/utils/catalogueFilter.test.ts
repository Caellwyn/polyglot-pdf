import { describe, it, expect } from 'vitest';
import {
  EMPTY_FILTER, filterKits, hiddenByFilterCount, isFilterActive, kitMatches,
  type CatalogueFilter, type FilterableKit,
} from './catalogueFilter';

const kit = (over: Partial<FilterableKit> & { id: string }): FilterableKit => ({
  label: null, status: 'draft', ...over,
});

const f = (over: Partial<CatalogueFilter> = {}): CatalogueFilter => ({
  ...EMPTY_FILTER, ...over,
});

describe('catalogue filter (bd n5fwd + tx8gi)', () => {
  it('shows everything by default', () => {
    const kits = [kit({ id: 'a' }), kit({ id: 'b', hidden: true })];
    expect(filterKits(kits, EMPTY_FILTER).map((k) => k.id)).toEqual(['a']);
    // ...everything EXCEPT hidden, which is the whole point of hiding.
    expect(isFilterActive(EMPTY_FILTER)).toBe(false);
  });

  it('only a literal true hides -- it FAILS VISIBLE', () => {
    // Mirrors the backend's `is True`. A malformed or hand-edited value must
    // never make a kit vanish from the only list that shows it.
    for (const bad of [undefined, false, null, 0, 1, '', 'true', 'false', {}]) {
      const k = { id: 'x', status: 'draft', hidden: bad } as unknown as FilterableKit;
      expect(kitMatches(k, EMPTY_FILTER), `hidden=${JSON.stringify(bad)}`).toBe(true);
    }
    expect(kitMatches(kit({ id: 'x', hidden: true }), EMPTY_FILTER)).toBe(false);
  });

  it('brings hidden kits back when asked -- nothing is unreachable', () => {
    const kits = [kit({ id: 'a' }), kit({ id: 'b', hidden: true })];
    expect(filterKits(kits, f({ includeHidden: true })).map((k) => k.id))
      .toEqual(['a', 'b']);
  });

  it('searches the LABEL and the ID, case-insensitively', () => {
    const kits = [
      kit({ id: 'form-2', label: 'W-7 (ITIN Application)' }),
      kit({ id: 'form-3', label: 'I-90' }),
    ];
    expect(filterKits(kits, f({ query: 'itin' })).map((k) => k.id)).toEqual(['form-2']);
    expect(filterKits(kits, f({ query: 'W-7' })).map((k) => k.id)).toEqual(['form-2']);
    // The ID matters: every server refusal names a kit by id, so an operator
    // reading an error pastes THAT in. Searching only labels fails exactly the
    // person who most needs to find the kit.
    expect(filterKits(kits, f({ query: 'form-3' })).map((k) => k.id)).toEqual(['form-3']);
  });

  it('treats a blank query as no query', () => {
    const kits = [kit({ id: 'a' })];
    expect(filterKits(kits, f({ query: '   ' })).map((k) => k.id)).toEqual(['a']);
    expect(isFilterActive(f({ query: '   ' }))).toBe(false);
  });

  it('filters by status, and an empty set means no status filter', () => {
    const kits = [
      kit({ id: 'a', status: 'draft' }),
      kit({ id: 'b', status: 'complete' }),
    ];
    expect(filterKits(kits, f({ statuses: new Set(['complete']) })).map((k) => k.id))
      .toEqual(['b']);
    expect(filterKits(kits, f({ statuses: new Set() })).map((k) => k.id))
      .toEqual(['a', 'b']);
  });

  it('combines text, status and hidden as AND', () => {
    const kits = [
      kit({ id: 'form-2', label: 'W-7', status: 'complete' }),
      kit({ id: 'form-3', label: 'W-7 draft', status: 'draft' }),
      kit({ id: 'form-4', label: 'W-7 old', status: 'complete', hidden: true }),
    ];
    expect(filterKits(kits, f({ query: 'w-7', statuses: new Set(['complete']) }))
      .map((k) => k.id)).toEqual(['form-2']);
    expect(filterKits(kits, f({
      query: 'w-7', statuses: new Set(['complete']), includeHidden: true,
    })).map((k) => k.id)).toEqual(['form-2', 'form-4']);
  });

  it('counts what it is holding back', () => {
    // The one thing telling an operator their list is incomplete, so it is
    // counted rather than inferred at each call site.
    const kits = [kit({ id: 'a' }), kit({ id: 'b', hidden: true }), kit({ id: 'c' })];
    expect(hiddenByFilterCount(kits, EMPTY_FILTER)).toBe(1);
    expect(hiddenByFilterCount(kits, f({ includeHidden: true }))).toBe(0);
    expect(hiddenByFilterCount(kits, f({ query: 'a' }))).toBe(2);
  });

  it('reports whether the filter is doing anything', () => {
    expect(isFilterActive(EMPTY_FILTER)).toBe(false);
    expect(isFilterActive(f({ query: 'x' }))).toBe(true);
    expect(isFilterActive(f({ statuses: new Set(['draft']) }))).toBe(true);
    expect(isFilterActive(f({ includeHidden: true }))).toBe(true);
  });
});
