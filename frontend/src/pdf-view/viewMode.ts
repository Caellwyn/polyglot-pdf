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
 * only at desktop width -- at mobile width the initial mode is always
 * Simplified, per the epic rubric.
 *
 * With no stored choice the default is Simplified: the cutover (bd
 * polyglot-pdf-v437) made the Preview UI always REACHABLE, but deliberately did
 * NOT make it the landing view -- that remains a separate maintainer call.
 *
 * CALLER CONTRACT: this function RESOLVES a mode but does not PERSIST it.
 * Whenever the resolved mode differs from what is stored, the caller must write
 * the result back (storeViewMode) -- the guard is `mode !== stored`, NOT just
 * the mobile case. That covers three situations: the mobile-width demotion of a
 * stored 'preview' (otherwise state and storage disagree and the stale
 * 'preview' resurrects at the next desktop-width mount); a junk stored value,
 * which gets normalized; and a fresh mount with nothing stored, which writes
 * 'simplified' (inert -- `stored ?? 'simplified'` makes "never chose" and
 * "chose Simplified" indistinguishable). SchemaForm's viewMode initialiser
 * implements exactly this; a second caller must too.
 */
export function initialViewMode(
  stored: ViewMode | null,
  viewportWidth: number
): ViewMode {
  if (viewportWidth <= MOBILE_INITIAL_BREAKPOINT) return 'simplified';
  return stored ?? 'simplified';
}

/**
 * The view mode after a LIVE resize has classified the viewport as MOBILE (bd
 * polyglot-pdf-ipin). The initial mode is chosen once at mount by
 * initialViewMode(); this handles a same-tab resize (or device rotation) that
 * crosses into mobile mid-session. To keep the mobile-defaults-Simplified
 * intent (epic rubric #5) true for a live resize -- not only a fresh mount --
 * being at mobile forces Preview back to Simplified.
 *
 * The caller decides "are we mobile now?" and only calls this when the answer
 * is yes -- deliberately, so the reset shares the SAME mobile classification
 * (dead-zone hysteresis) that drives which overlay renders, and the two can
 * never disagree (a desktop overlay never pairs with a mobile-defaulted form).
 *
 * It is one-directional on purpose: entering mobile drops Preview, but leaving
 * mobile does NOT auto-restore Preview (the user re-picks it). A desktop-width
 * resize never calls this at all, so a deliberate desktop Simplified/Preview
 * choice is never overridden.
 */
export function viewModeAfterResize(current: ViewMode): ViewMode {
  return current === 'preview' ? 'simplified' : current;
}
