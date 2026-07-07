/**
 * Snap-to camera for Preview mode (bd polyglot-pdf-35t0).
 *
 * When the voice model advances to a new field, the viewport SNAPS to that
 * field's overlay -- instant positioning, deliberately NO animated pan/zoom
 * (maintainer decision: avoid motion discomfort). The user's own scrolling is
 * never fought: snapping happens only on a field CHANGE (or via the snap-back
 * button), so wandering between advances is free.
 *
 * DOM-based targeting via scrollIntoView(block:'center', behavior:'auto'):
 * it instantly centers the overlay in WHICHEVER ancestor actually scrolls
 * (the pane's own max-height viewport, and the window if needed) -- container
 * math with an assumed scroller silently no-ops when the layout makes a
 * different element the scroller (the bug the first cut of this hook had).
 * Pages lay out asynchronously (canvas sizing), so a snap retries briefly
 * until the overlay has a real height.
 */

import { useCallback, useEffect } from 'react';

const SNAP_RETRY_MS = 200;
const SNAP_RETRY_MAX = 10;

export function useSnapToField(
  containerRef: React.RefObject<HTMLElement | null>,
  currentFieldId: string | null | undefined,
  /** Gate: pages exist (the PDF document is loaded). */
  active: boolean
) {
  const snapTo = useCallback(
    (fieldId: string): boolean => {
      const container = containerRef.current;
      if (!container) return false;
      // Field ids can contain brackets (copy_to mirrors like "...[1]").
      const el = container.querySelector<HTMLElement>(
        `[data-field-id="${CSS.escape(fieldId)}"]`
      );
      if (!el) return false;
      if (el.getBoundingClientRect().height === 0) return false; // not laid out yet
      el.scrollIntoView({ behavior: 'auto', block: 'center', inline: 'nearest' });
      return true;
    },
    [containerRef]
  );

  // Snap on every current-field CHANGE, retrying briefly while pages lay out.
  useEffect(() => {
    if (!active || !currentFieldId) return;
    if (snapTo(currentFieldId)) return;
    let tries = 0;
    const timer = window.setInterval(() => {
      tries += 1;
      if (snapTo(currentFieldId) || tries >= SNAP_RETRY_MAX) {
        window.clearInterval(timer);
      }
    }, SNAP_RETRY_MS);
    return () => window.clearInterval(timer);
  }, [currentFieldId, active, snapTo]);

  return { snapTo };
}
