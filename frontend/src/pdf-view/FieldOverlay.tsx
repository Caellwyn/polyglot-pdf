/**
 * FieldOverlay -- a field's rect on the rendered PDF page, colored by FILL
 * state and painting the user's value inside it (bd polyglot-pdf-ogrt).
 *
 * Diverged from the schema editor's FieldOverlay: the editor colors by
 * metadata completeness and is clickable; this one colors by fill state
 * (empty / filled / confirmed / current) and is READ-ONLY (click-to-edit is
 * phase 2 of the epic).
 */

import React from 'react';
import type { FormField } from '../schema-forms/types/schema';
import { pdfToScreenCoords, hasValidCoordinates } from './pdfCoordinates';
import { paintedValueFor, fittedFontSize, type PaintedValue } from './valuePainting';

export type FillState = 'empty' | 'filled' | 'confirmed' | 'current';

export interface FieldOverlayProps {
  field: FormField;
  /** UNWRAPPED raw value (see schema-forms/utils/fieldValue). */
  rawValue: unknown;
  fillState: FillState;
  scale: number;
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

export const FieldOverlay: React.FC<FieldOverlayProps> = ({
  field,
  rawValue,
  fillState,
  scale,
}) => {
  if (!hasValidCoordinates(field.pdf_position)) {
    return null;
  }

  const pos = pdfToScreenCoords(field.pdf_position, scale);
  const painted: PaintedValue = paintedValueFor(field, rawValue);

  let content: React.ReactNode = null;
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

  return (
    <div
      className={`pdf-field-overlay pdf-field-overlay--${fillState}`}
      style={{
        left: `${pos.x}px`,
        top: `${pos.y}px`,
        width: `${pos.width}px`,
        height: `${pos.height}px`,
        border: BORDERS[fillState],
        backgroundColor: BACKGROUNDS[fillState],
      }}
      data-field-id={field.id}
      data-fill-state={fillState}
      data-testid={`pdf-field-overlay-${field.id}`}
    >
      {content}
    </div>
  );
};
