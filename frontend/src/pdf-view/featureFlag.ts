/**
 * Preview-UI feature flag (epic polyglot-pdf-js7q).
 *
 * HARD CONSTRAINT (maintainer 2026-07-06): every UI surface of the preview-mode
 * epic renders ONLY when this flag is on. With the flag off (the default) the
 * app must behave identically to the pre-epic UI -- no new elements, no pdfjs
 * chunk fetched. Cutover (flipping the default) is a separate maintainer-gated
 * change; do not flip it here.
 *
 * Opt in by loading the app with ?previewUi=1 (persists for the rest of the
 * browser session via sessionStorage). Opt back out with ?previewUi=0.
 */

const QUERY_PARAM = 'previewUi';
const STORAGE_KEY = 'preview_ui_enabled';

/**
 * Whether the preview-mode UI is enabled for this browser session.
 *
 * Fail-closed: any storage/URL access error means "off".
 */
export function isPreviewUiEnabled(): boolean {
  try {
    const params = new URLSearchParams(window.location.search);
    const value = params.get(QUERY_PARAM);
    if (value === '1') {
      sessionStorage.setItem(STORAGE_KEY, '1');
      return true;
    }
    if (value === '0') {
      sessionStorage.removeItem(STORAGE_KEY);
      return false;
    }
    return sessionStorage.getItem(STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}
