import { describe, it, expect, beforeEach } from 'vitest';
import { isPreviewUiEnabled } from './featureFlag';

function setSearch(search: string) {
  window.history.replaceState({}, '', `/${search}`);
}

describe('isPreviewUiEnabled', () => {
  beforeEach(() => {
    sessionStorage.clear();
    setSearch('');
  });

  it('is OFF by default (no param, no persisted opt-in)', () => {
    expect(isPreviewUiEnabled()).toBe(false);
  });

  it('turns ON with ?previewUi=1 and persists for the session', () => {
    setSearch('?previewUi=1');
    expect(isPreviewUiEnabled()).toBe(true);

    // Subsequent navigation without the param stays on (sessionStorage).
    setSearch('');
    expect(isPreviewUiEnabled()).toBe(true);
  });

  it('turns OFF with ?previewUi=0 and clears the persisted opt-in', () => {
    setSearch('?previewUi=1');
    expect(isPreviewUiEnabled()).toBe(true);

    setSearch('?previewUi=0');
    expect(isPreviewUiEnabled()).toBe(false);

    setSearch('');
    expect(isPreviewUiEnabled()).toBe(false);
  });

  it('ignores other values of the param', () => {
    setSearch('?previewUi=yes');
    expect(isPreviewUiEnabled()).toBe(false);
  });
});
