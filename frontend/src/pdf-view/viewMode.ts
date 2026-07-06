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
