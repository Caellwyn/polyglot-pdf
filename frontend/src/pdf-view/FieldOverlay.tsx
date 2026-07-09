/**
 * FieldOverlay -- a field's rect on the rendered PDF page, colored by FILL
 * state and painting the user's value inside it (bd polyglot-pdf-ogrt).
 *
 * Diverged from the schema editor's FieldOverlay: the editor colors by
 * metadata completeness and is clickable; this one colors by fill state
 * (empty / filled / confirmed / current) and is READ-ONLY (click-to-edit is
 * bead P2.3, polyglot-pdf-7esr).
 *
 * bd polyglot-pdf-lp5v adds two things:
 * - option-rect painting: a selected radio/checkbox/checkbox_group option
 *   with its own pdf_position gets an X mark at that option's printed box
 *   (rendered as sibling divs in the same page-coordinate space; the
 *   field-level state box stays, keeping data-field-id for snap-to). Options
 *   without rects fall back to the label-at-field-rect painting.
 * - show_if dimming: a conditionally-hidden field renders dimmed (never
 *   removed -- it exists on paper) and is not clickable; `current` wins over
 *   dimmed (never dim the field the voice model is on).
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

export type FillState = 'empty' | 'filled' | 'confirmed' | 'current';

export interface FieldOverlayProps {
  field: FormField;
  /** UNWRAPPED raw value (see schema-forms/utils/fieldValue). */
  rawValue: unknown;
  fillState: FillState;
  scale: number;
  /** show_if says the field is hidden: render dimmed, not removed. */
  dimmed?: boolean;
}

const BORDERS: Record<FillState, string> = {
  empty: '1px solid rgba(148, 163, 184, 0.55)',
  filled: '2px solid rgb(59, 130, 246)',
  confirmed: '2px solid rgb(34, 197, 94)',
  current: '3px solid rgb(245, 158, 11)',
};

const BACKGROUNDS: Record<FillState, string> = {
  empty: 'transparent',
  filled: 'rgba(59, 130, 246, 0.06)',
  confirmed: 'rgba(34, 197, 94, 0.06)',
  current: 'rgba(245, 158, 11, 0.14)',
};

const DIMMED_BORDER = '1px dashed rgba(148, 163, 184, 0.6)';

export const FieldOverlay: React.FC<FieldOverlayProps> = ({
  field,
  rawValue,
  fillState,
  scale,
  dimmed = false,
}) => {
  if (!hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  // `current` always wins: the field the voice model is on is never dimmed
  // (the border/background/snap cues must stay visible).
  const isDimmed = dimmed && fillState !== 'current';

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

  const stateClass = `pdf-field-overlay pdf-field-overlay--${fillState}`;
  return (
    <>
      <div
        className={isDimmed ? `${stateClass} pdf-field-overlay--dimmed` : stateClass}
        style={{
          left: `${pos.x}px`,
          top: `${pos.y}px`,
          width: `${pos.width}px`,
          height: `${pos.height}px`,
          border: isDimmed ? DIMMED_BORDER : BORDERS[fillState],
          backgroundColor: isDimmed ? 'transparent' : BACKGROUNDS[fillState],
        }}
        data-field-id={field.id}
        data-fill-state={fillState}
        data-dimmed={isDimmed || undefined}
        data-testid={`pdf-field-overlay-${field.id}`}
      >
        {content}
      </div>
      {optionRects.map(({ value, position }) => {
        const optPos = pdfToScreenCoords(position, scale);
        return (
          <div
            key={value}
            className={
              isDimmed
                ? 'pdf-field-overlay__option-mark pdf-field-overlay--dimmed'
                : 'pdf-field-overlay__option-mark'
            }
            style={{
              left: `${optPos.x}px`,
              top: `${optPos.y}px`,
              width: `${optPos.width}px`,
              height: `${optPos.height}px`,
              fontSize: `${Math.max(8, Math.min(optPos.height * 0.8, 24))}px`,
            }}
            data-testid={`pdf-option-mark-${field.id}-${value}`}
          >
            X
          </div>
        );
      })}
    </>
  );
};
