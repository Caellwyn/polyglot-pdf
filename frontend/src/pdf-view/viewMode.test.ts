import { describe, it, expect, beforeEach } from 'vitest';
import { getStoredViewMode, storeViewMode } from './viewMode';

describe('viewMode storage', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('returns null when nothing stored', () => {
    expect(getStoredViewMode()).toBe(null);
  });

  it('round-trips both modes', () => {
    storeViewMode('preview');
    expect(getStoredViewMode()).toBe('preview');
    storeViewMode('simplified');
    expect(getStoredViewMode()).toBe('simplified');
  });

  it('rejects junk values', () => {
    sessionStorage.setItem('preview_view_mode', 'bogus');
    expect(getStoredViewMode()).toBe(null);
  });
});
