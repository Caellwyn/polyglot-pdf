/**
 * FieldEditPopover -- click-to-edit editor for a Preview-mode field (bd
 * polyglot-pdf-7esr, sprint-9 epic).
 *
 * Absolutely positioned INSIDE .pdf-viewer__page-inner, in the same
 * page-coordinate space as the overlays: it scrolls with the page, so no
 * scroll listeners and no reposition math. Below the clicked rect by
 * default, flipped above it near the page bottom, clamped horizontally.
 *
 * The editor itself is the SAME FieldRenderer the Simplified view uses --
 * one input widget per type, one validation path, read_only +
 * flip_readonly_bit for free. Write-through on change (no Save button):
 * every keystroke/selection lands in SchemaFormState via the SchemaForm
 * handlers passed down, repainting the overlay live.
 *
 * Dismissal is owned here for Esc / click-outside / the X button; the OWNER
 * (PreviewPane) additionally closes on voice-advance (currentFieldId change)
 * and on zoom (scale change).
 */

import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { FormField } from '../schema-forms/types/schema';
import { FieldRenderer } from '../schema-forms/components/FieldRenderer';
import type { ScreenPosition } from './pdfCoordinates';

export interface FieldEditPopoverProps {
  field: FormField;
  /** WRAPPED FieldValue (same convention as SectionRenderer -> FieldRenderer). */
  value: any;
  /** Wrapped FieldValue map (conditional logic; evaluators unwrap internally). */
  allFieldValues: Record<string, any>;
  error?: string | null;
  onChange: (value: any) => void;
  onBlur: (fieldId: string) => void;
  onClose: () => void;
  /** The clicked overlay's SCREEN rect (page coords, already scaled). */
  anchor: ScreenPosition;
}

const POPOVER_WIDTH = 340;
const GAP = 6;
const EDGE = 8;
/** Estimated max popover height used only for the flip-above decision. */
const FLIP_THRESHOLD = 260;

export const FieldEditPopover: React.FC<FieldEditPopoverProps> = ({
  field,
  value,
  allFieldValues,
  error,
  onChange,
  onBlur,
  onClose,
  anchor,
}) => {
  const popoverRef = useRef<HTMLDivElement>(null);
  // Measured from the parent page container (page-inner) so clamping matches
  // the actual rendered page size at the current zoom.
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null);

  useLayoutEffect(() => {
    const parent = popoverRef.current?.parentElement;
    if (parent) {
      setPageSize({ width: parent.clientWidth, height: parent.clientHeight });
    }
  }, [anchor.x, anchor.y]);

  // Esc + click-outside dismissal. pointerdown (not click) so a drag starting
  // outside dismisses too; events inside the popover subtree are ignored.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    const onPointerDown = (e: PointerEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [onClose]);

  const pageWidth = pageSize?.width ?? POPOVER_WIDTH + 2 * EDGE;
  const pageHeight = pageSize?.height ?? Number.MAX_SAFE_INTEGER;
  const width = Math.min(POPOVER_WIDTH, pageWidth - 2 * EDGE);
  const left = Math.min(Math.max(anchor.x, EDGE), Math.max(EDGE, pageWidth - width - EDGE));
  const below = anchor.y + anchor.height + GAP;
  const flip = below + FLIP_THRESHOLD > pageHeight && anchor.y - GAP > FLIP_THRESHOLD / 2;

  const confirmed = value?.confirmed === true;
  const isReadOnly =
    !!field.read_only &&
    field.conditional_behavior?.unlock_method !== 'flip_readonly_bit' &&
    field.conditional_logic?.unlock_method !== 'flip_readonly_bit';

  return (
    <div
      ref={popoverRef}
      className="pdf-field-edit-popover"
      role="dialog"
      aria-label={`Edit ${field.name}`}
      data-testid={`pdf-field-edit-popover-${field.id}`}
      style={{
        left: `${left}px`,
        width: `${width}px`,
        ...(flip
          ? { top: `${anchor.y - GAP}px`, transform: 'translateY(-100%)' }
          : { top: `${below}px` }),
      }}
    >
      <div className="pdf-field-edit-popover__header">
        <span className="pdf-field-edit-popover__title">{field.name}</span>
        {isReadOnly && (
          <span className="pdf-field-edit-popover__readonly">read-only</span>
        )}
        <button
          type="button"
          className="pdf-field-edit-popover__close"
          aria-label="Close editor"
          onClick={onClose}
        >
          X
        </button>
      </div>
      <div className="pdf-field-edit-popover__body">
        <FieldRenderer
          field={field}
          value={value}
          onChange={onChange}
          onBlur={onBlur}
          error={error ?? null}
          allFieldValues={allFieldValues}
          confirmed={confirmed}
        />
      </div>
    </div>
  );
};
