/**
 * mintSelectSlugs / stripTrailingCode (bd polyglot-pdf-g2fpr, PR 2).
 *
 * Mirrors backend/models/conditional_vocabulary.mint_select_slugs; the two
 * must stay in step so an option minted in the editor equals one minted by
 * the extractor or the migration. Same fixtures as the Python test on purpose.
 */
import { describe, it, expect } from 'vitest';
import { mintSelectSlugs, stripTrailingCode } from './fieldGrouping';

describe('stripTrailingCode', () => {
  it.each([
    ['Alabama (AL)', 'Alabama'],
    ['Armed Forces Americas (AA)', 'Armed Forces Americas'],
    ['District of Columbia (DC)', 'District of Columbia'],
    ['Alabama (AL)  ', 'Alabama'],
    ['Alabama', 'Alabama'],
    ['Alabama (al)', 'Alabama (al)'],
    ['Alabama (ALAB)', 'Alabama'],
    ['Alabama (ALABA)', 'Alabama (ALABA)'],
    ['(AL) Alabama', '(AL) Alabama'],
    ['', ''],
  ])('%s -> %s', (label, expected) => {
    expect(stripTrailingCode(label)).toBe(expected);
  });
});

describe('mintSelectSlugs', () => {
  it('state labels mint the bare name', () => {
    expect(mintSelectSlugs(['Alabama (AL)', 'Armed Forces Americas (AA)'], ['AL', 'AA']))
      .toEqual(['alabama', 'armed_forces_americas']);
  });

  it('a code that is already a slug IS the value, even under a reworded label', () => {
    expect(mintSelectSlugs(['5', '11'], ['5', '11'])).toEqual(['5', '11']);
    expect(mintSelectSlugs(['five feet', '11'], ['5', '11'])).toEqual(['5', '11']);
  });

  it('kept codes are reserved before minting, so a sibling cannot collide', () => {
    expect(mintSelectSlugs(['five', 'Five'], ['five', 'X'])).toEqual(['five', 'five_2']);
  });

  it('duplicate labels get positional suffixes', () => {
    expect(mintSelectSlugs(['Other', 'Other', 'Other 2'], ['A', 'B', 'C']))
      .toEqual(['other', 'other_2', 'other_2_2']);
  });

  it('a missing code is never kept', () => {
    expect(mintSelectSlugs(['Alabama (AL)', 'Alaska'], [undefined, undefined]))
      .toEqual(['alabama', 'alaska']);
  });
});
