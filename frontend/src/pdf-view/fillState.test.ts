import { describe, it, expect } from 'vitest';
import { fillStateFor } from './PDFViewer';

const wrap = (value: unknown, confirmed = false) => ({ value, confirmed });

describe('fillStateFor', () => {
  it('treats empty-ish raw values as empty', () => {
    expect(fillStateFor('f', wrap(null), null)).toBe('empty');
    expect(fillStateFor('f', wrap(''), '')).toBe('empty');
    expect(fillStateFor('f', wrap(false), false)).toBe('empty');
    expect(fillStateFor('f', undefined, undefined)).toBe('empty');
  });

  it('treats a cleared checkbox_group selection ([]) as empty', () => {
    expect(fillStateFor('f', wrap([]), [])).toBe('empty');
    expect(fillStateFor('f', wrap([], true), [])).toBe('empty');
  });

  it('distinguishes filled from confirmed', () => {
    expect(fillStateFor('f', wrap('x'), 'x')).toBe('filled');
    expect(fillStateFor('f', wrap('x', true), 'x')).toBe('confirmed');
    expect(fillStateFor('f', wrap(['a'], true), ['a'])).toBe('confirmed');
  });

  it('current wins over every other state', () => {
    expect(fillStateFor('f', wrap('x', true), 'x', 'f')).toBe('current');
    expect(fillStateFor('f', wrap(null), null, 'f')).toBe('current');
    expect(fillStateFor('f', wrap('x'), 'x', 'other')).toBe('filled');
  });
});
