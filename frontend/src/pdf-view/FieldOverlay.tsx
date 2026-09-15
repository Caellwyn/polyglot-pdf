/**
 * FieldOverlay -- a field's rect on the rendered PDF page, colored by FILL
 * state and painting the user's value inside it (bd polyglot-pdf-ogrt).
 *
 * Diverged from the schema editor's FieldOverlay: the editor colors by
 * metadata completeness; this one colors by fill state
 * (empty / filled / confirmed / current).
 *
 * - option-rect painting (bd lp5v): a selected radio/checkbox/checkbox_group
 *   option with its own pdf_position gets an X mark at that option's printed
 *   box (rendered as sibling divs in the same page-coordinate space; the
 *   field-level state box stays, keeping data-field-id for snap-to). Options
 *   without rects fall back to the label-at-field-rect painting.
 * - show_if dimming (bd lp5v): a conditionally-hidden field renders dimmed
 *   (never removed -- it exists on paper) and is not clickable; `current`
 *   wins over dimmed (never dim the field the voice model is on).
 * - click-to-edit (bd 7esr): with `onClick` present and the field not
 *   dimmed, the overlay (and its option marks, as extra pointer targets)
 *   opens the whole-field FieldEditPopover; the field box is the single
 *   accessible button (Enter/Space).
 */

import React from 'react';
import type { FormField } from '../schema-forms/types/schema';
import { pdfToScreenCoords, hasValidCoordinates } from './pdfCoordinates';
import {
  paintedValueFor,
  selectedOptionRects,
  fittedFontSize,
  type PaintedValue,
} from './valuePainting';

/**
 * How a field paints on the PDF overlay.
 *
 * 'skipped' exists because a deliberately-skipped required field used to paint
 * as 'empty' -- indistinguishable from one the user never touched (bd
 * polyglot-pdf-c9dfo). markFieldSkipped stores {value: null, skipped: true},
 * and fillStateFor's empty check fired on the null before anything could look
 * at the flag. The form view has always shown a "Skipped / needs follow-up"
 * badge for that state; the PDF surface silently did not, and
 * schemaFormState.ts's own docstring says it must ("NOT a silent blank").
 */
export type FillState = 'empty' | 'filled' | 'confirmed' | 'current' | 'skipped';

export interface FieldOverlayProps {
  field: FormField;
  /** UNWRAPPED raw value (see schema-forms/utils/fieldValue). */
  rawValue: unknown;
  fillState: FillState;
  scale: number;
  /** show_if says the field is hidden: render dimmed, not removed. */
  dimmed?: boolean;
  /**
   * Click-to-edit (bd polyglot-pdf-7esr): when present and the field is not
   * dimmed, the overlay (and its option marks -- bigger hit targets for the
   * SAME whole-field editor, never a direct toggle) becomes clickable and
   * keyboard-activatable. Dimmed fields are never clickable.
   */
  onClick?: (fieldId: string) => void;
}

const BORDERS: Record<FillState, string> = {
  empty: '1px solid rgba(148, 163, 184, 0.55)',
  filled: '2px solid rgb(59, 130, 246)',
  confirmed: '2px solid rgb(34, 197, 94)',
  current: '3px solid rgb(245, 158, 11)',
  // DOTTED purple, deliberately not the form view's amber badge colour: amber
  // is already 'current' here, and a skipped field must not read as the one the
  // assistant is asking about. Dashed is taken too (a dimmed show_if-hidden
  // field), so skipped carries BOTH an unused hue and an unused stroke -- the
  // point is that it cannot be mistaken for a blank.
  skipped: '2px dotted rgb(147, 51, 234)',
};

const BACKGROUNDS: Record<FillState, string> = {
  empty: 'transparent',
  filled: 'rgba(59, 130, 246, 0.06)',
  confirmed: 'rgba(34, 197, 94, 0.06)',
  current: 'rgba(245, 158, 11, 0.14)',
  // A tint, unlike 'empty''s transparent: on a printed form the border alone
  // can be lost against a ruled box, and the whole defect was a skip reading as
  // untouched.
  skipped: 'rgba(147, 51, 234, 0.08)',
};

const DIMMED_BORDER = '1px dashed rgba(148, 163, 184, 0.6)';

export const FieldOverlay: React.FC<FieldOverlayProps> = ({
  field,
  rawValue,
  fillState,
  scale,
  dimmed = false,
  onClick,
}) => {
  if (!hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  // `current` always wins: the field the voice model is on is never dimmed
  // (the border/background/snap cues must stay visible).
  const isDimmed = dimmed && fillState !== 'current';

  // Dimmed = visible-but-inert: the cue for "make this active" is the
  // controlling field, and editing an invisible-in-Simplified field could
  // contradict it.
  const clickable = !!onClick && !isDimmed;
  const activate = clickable ? () => onClick(field.id) : undefined;
  const interactiveProps = clickable
    ? {
        role: 'button' as const,
        tabIndex: 0,
        'aria-label': `Edit ${field.name}`,
        onClick: activate,
        onKeyDown: (e: React.KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            activate!();
          }
        },
        style: { pointerEvents: 'auto' as const, cursor: 'pointer' },
      }
    : { style: {} };

  const pos = pdfToScreenCoords(field.pdf_position, scale);

  // Option-rect painting: when any SELECTED option carries its own usable
  // rect, marks paint at those rects and the field-level box paints no text
  // (the mark placement IS the value display; a duplicate label at the field
  // rect would just clutter the form).
  const optionRects = selectedOptionRects(field, rawValue);

  let content: React.ReactNode = null;
  if (optionRects.length === 0) {
    const painted: PaintedValue = paintedValueFor(field, rawValue);
    if (painted.kind === 'check') {
      content = (
        <span
          className="pdf-field-overlay__check"
          style={{ fontSize: `${Math.max(8, Math.min(pos.height * 0.8, 24))}px` }}
        >
          X
        </span>
      );
    } else if (painted.kind === 'text') {
      const isMultiline = field.type === 'textarea';
      content = (
        <span
          className="pdf-field-overlay__text"
          style={{
            fontSize: `${fittedFontSize(painted.text, pos.width - 4, pos.height)}px`,
            whiteSpace: isMultiline ? 'normal' : 'nowrap',
          }}
        >
          {painted.text}
        </span>
      );
    }
  }

  const classes = ['pdf-field-overlay', `pdf-field-overlay--${fillState}`];
  if (isDimmed) classes.push('pdf-field-overlay--dimmed');
  if (clickable) classes.push('pdf-field-overlay--clickable');
  const { style: interactiveStyle, ...interactiveRest } = interactiveProps;
  return (
    <>
      <div
        className={classes.join(' ')}
        style={{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: `${pos.width}px`,
          height: `${pos.height}px`,
          border: isDimmed ? DIMMED_BORDER : BORDERS[fillState],
          backgroundColor: isDimmed ? 'transparent' : BACKGROUNDS[fillState],
          ...interactiveStyle,
        }}
        data-field-id={field.id}
        data-fill-state={fillState}
        data-dimmed={isDimmed || undefined}
        data-testid={`pdf-field-overlay-${field.id}`}
        {...interactiveRest}
      >
        {content}
      </div>
      {optionRects.map(({ value, position }) => {
        const optPos = pdfToScreenCoords(position, scale);
        const markClasses = ['pdf-field-overlay__option-mark'];
        if (isDimmed) markClasses.push('pdf-field-overlay--dimmed');
        if (clickable) markClasses.push('pdf-field-overlay--clickable');
        return (
          <div
            key={value}
            className={markClasses.join(' ')}
            style={{
              left: `${optPos.x}px`,
              top: `${optPos.y}px`,
              width: `${optPos.width}px`,
              height: `${optPos.height}px`,
              fontSize: `${Math.max(8, Math.min(optPos.height * 0.8, 24))}px`,
              ...interactiveStyle,
            }}
            data-testid={`pdf-option-mark-${field.id}-${value}`}
            {...(clickable
              ? // An option mark is an extra hit target for the SAME
                // whole-field editor -- the field box carries the accessible
                // button role; marks stay presentation with a click handler.
                { onClick: activate }
              : {})}
          >
            X
          </div>
        );
      })}
    </>
  );
};
