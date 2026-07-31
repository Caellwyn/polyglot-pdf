import { describe, it, expect, beforeEach } from 'vitest';
import { getStoredViewMode, storeViewMode, initialViewMode, viewModeAfterResize, MOBILE_INITIAL_BREAKPOINT } from './viewMode';

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
    expect(initialViewMode(null, DESKTOP)).toBe('simplified');
    expect(initialViewMode(null, MOBILE)).toBe('simplified');
  });

  it('honors a stored preview choice at desktop width', () => {
    expect(initialViewMode('preview', DESKTOP)).toBe('preview');
  });

  it('honors a stored simplified choice at desktop width', () => {
    expect(initialViewMode('simplified', DESKTOP)).toBe('simplified');
  });

  it('mobile width ALWAYS starts simplified, even with stored preview (epic rubric #5)', () => {
    expect(initialViewMode('preview', MOBILE)).toBe('simplified');
    expect(initialViewMode('preview', MOBILE_INITIAL_BREAKPOINT)).toBe('simplified');
  });
});

describe('viewModeAfterResize (bd polyglot-pdf-ipin)', () => {
  // The caller only invokes this once it has classified the viewport as mobile
  // (shared dead-zone decision), so the helper takes no width -- it just
  // collapses Preview to Simplified and leaves Simplified alone.
  it('drops Preview to Simplified (mobile forces the mobile default)', () => {
    expect(viewModeAfterResize('preview')).toBe('simplified');
  });

  it('never auto-restores Preview: Simplified stays Simplified', () => {
    expect(viewModeAfterResize('simplified')).toBe('simplified');
  });
});
