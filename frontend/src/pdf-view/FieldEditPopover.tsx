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
import { isBlankFieldValue, unwrapFieldValue } from '../schema-forms/utils/fieldValue';
import { isFieldRequired } from '../schema-forms/utils/validation';
import type { ScreenPosition } from './pdfCoordinates';

export interface FieldEditPopoverProps {
  field: FormField;
  /** WRAPPED FieldValue (same convention as SectionRenderer -> FieldRenderer). */
  value: any;
  /** Wrapped FieldValue map (conditional logic; evaluators unwrap internally). */
  allFieldValues: Record<string, any>;
  /**
   * The WHOLE schema field list, passed on to isFieldRequired -- the same third
   * argument SectionRenderer gives it in the form view, so the two surfaces
   * call the predicate identically.
   *
   * HONEST NOTE ON WHAT THIS DOES TODAY: nothing observable. isFieldRequired
   * forwards it to evaluateConditionGroup -> evaluateAtomicCondition, which
   * ACCEPTS a `fields` parameter and never reads it -- the trigger value is
   * looked up in `fieldValues`, not in `fields`. Verified by mutation: passing
   * `[field]` here changes no test outcome, because it changes no behaviour.
   *
   * It is passed anyway because the alternative is worse: hard-coding `[field]`
   * would bake in an assumption about an evaluator internal that is not part of
   * its contract, and would break silently the day a conditional needs to look a
   * field up by id. Do NOT add a test asserting this argument matters until it
   * does -- such a test could only pass by coincidence.
   */
  allFields: FormField[];
  error?: string | null;
  onChange: (value: any) => void;
  onBlur: (fieldId: string) => void;
  onClose: () => void;
  /**
   * Mark this field intentionally unanswered. OPTIONAL: when absent the skip
   * button is not rendered, exactly as SectionRenderer's `!!onFieldSkip` gate
   * behaves in the form view.
   *
   * Preview mode shipped without this, so a user whose other exit was voice had
   * no UI escape from a field they could not answer -- the doc's rule is that
   * leaving a required field blank must be explicit, "said aloud, or via the
   * skip control" (docs/components/schema-forms.md), and in Preview the control
   * did not exist (bd polyglot-pdf-ykfx0).
   */
  onFieldSkip?: (fieldId: string) => void;
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
  allFields,
  error,
  onChange,
  onBlur,
  onClose,
  onFieldSkip,
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
  const skipped = value?.skipped === true;

  // The SAME four conditions SectionRenderer gates its "Skip for now" button on
  // (required + still empty + not already skipped + a handler exists), using the
  // SAME shared predicates rather than a re-typed copy -- the two surfaces must
  // agree about when skipping is offered, or a user sees the affordance in one
  // view and not the other for the identical field. SectionRenderer additionally
  // has a `disabled` prop; the popover has no disabled mode (a read-only field
  // is handled separately below), so there is nothing to mirror for it.
  //
  // `empty` must use the shared isBlankFieldValue, not a bare === '': a
  // space-filled required field has to remain skippable, which is the shape bd
  // polyglot-pdf-xtj97 pinned on the voice side.
  const required = isFieldRequired(field, allFieldValues, allFields);
  const empty = isBlankFieldValue(unwrapFieldValue(value));
  const canSkip = !!onFieldSkip && required && empty && !skipped;

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
        {skipped && (
          <p className="pdf-field-edit-popover__skipped">
            Marked as needs follow-up -- this required question was left
            unanswered on purpose. Enter a value above to answer it.
          </p>
        )}
        {canSkip && (
          <button
            type="button"
            className="form-field__skip-button"
            onClick={() => {
              onFieldSkip!(field.id);
              // Close after skipping: the field is resolved, so leaving the
              // editor open over a question the user just set aside invites a
              // second click on a button that has now vanished.
              onClose();
            }}
            title="Mark this required question as intentionally unanswered (e.g. to ask a translator later). You can still answer it afterward."
          >
            Skip for now
          </button>
        )}
      </div>
    </div>
  );
};
