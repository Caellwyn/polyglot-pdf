import { describe, it, expect, beforeEach } from 'vitest';
import { getStoredViewMode, storeViewMode, initialViewMode, MOBILE_INITIAL_BREAKPOINT } from './viewMode';

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

describe('initialViewMode', () => {
  const DESKTOP = 1280;
  const MOBILE = 390;

  it('defaults simplified with nothing stored, any width', () => {
    expect(initialViewMode(true, null, DESKTOP)).toBe('simplified');
    expect(initialViewMode(true, null, MOBILE)).toBe('simplified');
  });

  it('honors a stored preview choice at desktop width, flag on', () => {
    expect(initialViewMode(true, 'preview', DESKTOP)).toBe('preview');
  });

  it('mobile width ALWAYS starts simplified, even with stored preview (epic rubric #5)', () => {
    expect(initialViewMode(true, 'preview', MOBILE)).toBe('simplified');
    expect(initialViewMode(true, 'preview', MOBILE_INITIAL_BREAKPOINT)).toBe('simplified');
  });

  it('flag off is always simplified regardless of stored mode', () => {
    expect(initialViewMode(false, 'preview', DESKTOP)).toBe('simplified');
  });
});
