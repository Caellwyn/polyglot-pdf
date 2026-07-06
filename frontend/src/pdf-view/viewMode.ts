/**
 * View-mode state for the dual-view UI (epic polyglot-pdf-js7q, bd vxwj).
 *
 * 'simplified' = the classic linear web form; 'preview' = the PDF view.
 * Persisted per browser session (sessionStorage) so a reload keeps the user's
 * chosen view. Deliberately NOT part of SchemaFormState: the mode is purely
 * presentational and must never reach the WS handshake.
 *
 * No pdfjs imports here -- this module is statically imported by SchemaForm,
 * so it must stay out of the heavy lazy chunk.
 */

export type ViewMode = 'simplified' | 'preview';

const STORAGE_KEY = 'preview_view_mode';

/** The stored mode for this browser session, or null if never set/invalid. */
export function getStoredViewMode(): ViewMode | null {
  try {
    const v = sessionStorage.getItem(STORAGE_KEY);
    return v === 'simplified' || v === 'preview' ? v : null;
  } catch {
    return null;
  }
}

export function storeViewMode(mode: ViewMode): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, mode);
  } catch {
    // Storage unavailable: the mode simply won't survive a reload.
  }
}

/**
 * Mobile-width mounts always start Simplified (epic rubric #5); matches the
 * voice overlay's initial-classify breakpoint in SchemaForm.
 */
export const MOBILE_INITIAL_BREAKPOINT = 768;

/**
 * The view mode a fresh mount starts in. A stored 'preview' choice is honored
 * only when the flag is on AND the viewport is desktop-width -- at mobile
 * width the initial mode is always Simplified, per the epic rubric.
 */
export function initialViewMode(
  flagOn: boolean,
  stored: ViewMode | null,
  viewportWidth: number
): ViewMode {
  if (!flagOn) return 'simplified';
  if (viewportWidth <= MOBILE_INITIAL_BREAKPOINT) return 'simplified';
  return stored ?? 'simplified';
}
